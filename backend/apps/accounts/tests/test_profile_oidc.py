import json
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.internal.stagekit import LOGIN_SESSION_KEY
from allauth.core.context import request_context
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from allauth.socialaccount.adapter import get_adapter as get_socialaccount_adapter
from allauth.socialaccount.internal.flows.login import _login as complete_existing_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.providers.openid_connect.views import OpenIDConnectOAuth2Adapter
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import AuditEvent, InstallationState

SESSION_URL = "/_allauth/browser/v1/auth/session"
OIDC_REDIRECT_URL = "/_allauth/browser/v1/auth/provider/redirect"
OIDC_PROVIDER = {
    "id": "company-sso",
    "name": "Company SSO",
    "discovery_url": "https://identity.example.test/.well-known/openid-configuration",
    "client_id": "tekdocs-client",
    "client_secret": "never-return-this-secret",
}
OIDC_ALLAUTH_SETTINGS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": OIDC_PROVIDER["id"],
                "name": OIDC_PROVIDER["name"],
                "client_id": OIDC_PROVIDER["client_id"],
                "secret": OIDC_PROVIDER["client_secret"],
                "settings": {
                    "server_url": OIDC_PROVIDER["discovery_url"],
                    "email_authentication": True,
                },
            }
        ]
    }
}


@pytest.fixture
def owner(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    return bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )


@pytest.mark.django_db
def test_profile_update_requires_membership_csrf_and_records_value_free_audit(owner):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner.owner)
    client.get(SESSION_URL)
    url = reverse("auth-profile")

    missing_csrf = client.patch(
        url,
        data=json.dumps({"display_name": "Operations Lead"}),
        content_type="application/json",
    )
    assert missing_csrf.status_code == 403

    updated = client.patch(
        url,
        data=json.dumps({"display_name": "Operations Lead"}),
        content_type="application/json",
        headers={"X-CSRFToken": client.cookies["csrftoken"].value},
    )
    assert updated.status_code == 200
    assert updated.json()["user"] == {
        "id": str(owner.owner.id),
        "email": owner.owner.email,
        "display_name": "Operations Lead",
    }
    owner.owner.refresh_from_db()
    assert owner.owner.display_name == "Operations Lead"
    event = AuditEvent.objects.get(action="auth.profile_updated")
    assert event.actor == owner.owner
    assert event.tenant == owner.tenant
    assert event.metadata == {}


@pytest.mark.django_db
def test_profile_update_rejects_invalid_input_and_unrelated_users(owner):
    client = Client()
    client.force_login(owner.owner)
    invalid = client.patch(reverse("auth-profile"), {"display_name": "   "}, content_type="application/json")
    assert invalid.status_code == 400

    unrelated = User.objects.create_user(
        email="unrelated@example.com",
        display_name="Unrelated",
        password=secrets.token_urlsafe(24),
    )
    client.force_login(unrelated)
    denied = client.patch(reverse("auth-profile"), {"display_name": "Changed"}, content_type="application/json")
    assert denied.status_code == 403
    assert not AuditEvent.objects.filter(action="auth.profile_updated").exists()


@override_settings(TEKDOCS_OIDC_PROVIDER=OIDC_PROVIDER, SOCIALACCOUNT_PROVIDERS=OIDC_ALLAUTH_SETTINGS)
def test_public_oidc_provider_contract_excludes_configuration_and_secrets(client):
    response = client.get(reverse("auth-providers"))

    assert response.status_code == 200
    assert response.json() == {"providers": [{"id": "company-sso", "name": "Company SSO"}]}
    serialized = response.content.decode()
    assert OIDC_PROVIDER["client_id"] not in serialized
    assert OIDC_PROVIDER["client_secret"] not in serialized
    assert OIDC_PROVIDER["discovery_url"] not in serialized


@override_settings(TEKDOCS_OIDC_PROVIDER=None)
def test_oidc_provider_contract_is_empty_by_default(client):
    assert client.get(reverse("auth-providers")).json() == {"providers": []}


@override_settings(TEKDOCS_OIDC_PROVIDER=OIDC_PROVIDER, SOCIALACCOUNT_PROVIDERS=OIDC_ALLAUTH_SETTINGS)
@pytest.mark.django_db
def test_oidc_redirect_uses_allauth_state_boundary(client, monkeypatch):
    monkeypatch.setattr(
        OpenIDConnectOAuth2Adapter,
        "openid_config",
        property(
            lambda _self: {
                "authorization_endpoint": "https://identity.example.test/authorize",
                "token_endpoint": "https://identity.example.test/token",
                "userinfo_endpoint": "https://identity.example.test/userinfo",
                "jwks_uri": "https://identity.example.test/keys",
                "issuer": "https://identity.example.test",
            }
        ),
    )
    client.get(SESSION_URL)
    response = client.post(
        OIDC_REDIRECT_URL,
        {
            "provider": OIDC_PROVIDER["id"],
            "process": "login",
            "callback_url": "http://testserver/",
        },
        headers={"X-CSRFToken": client.cookies["csrftoken"].value},
    )

    assert response.status_code == 302
    redirect = urlsplit(response["Location"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == "https://identity.example.test/authorize"
    query = parse_qs(redirect.query)
    assert query["client_id"] == [OIDC_PROVIDER["client_id"]]
    assert set(query["scope"][0].split()) == {"openid", "profile", "email"}
    assert query["state"][0]
    assert OIDC_PROVIDER["client_secret"] not in response["Location"]


@pytest.mark.django_db
@override_settings(TEKDOCS_OIDC_PROVIDER=OIDC_PROVIDER, SOCIALACCOUNT_PROVIDERS=OIDC_ALLAUTH_SETTINGS)
def test_existing_oidc_identity_with_enrolled_totp_stops_at_mfa(owner):
    TOTP.activate(owner.owner, generate_totp_secret())
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    SessionMiddleware(lambda _request: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    with request_context(request):
        provider = get_socialaccount_adapter(request).get_provider(request, OIDC_PROVIDER["id"])
        sociallogin = SocialLogin(
            user=owner.owner,
            account=SocialAccount(provider=OIDC_PROVIDER["id"], uid="trusted-issuer-subject"),
            provider=provider,
        )
        sociallogin._did_authenticate_by_email = owner.owner.email
        complete_existing_social_login(request, sociallogin)

    pending_login = request.session[LOGIN_SESSION_KEY]
    assert pending_login["state"]["stages"]["current"] == "mfa_authenticate"
    assert request.session.get("_auth_user_id") is None
    assert SocialAccount.objects.filter(user=owner.owner, provider=OIDC_PROVIDER["id"]).exists()
