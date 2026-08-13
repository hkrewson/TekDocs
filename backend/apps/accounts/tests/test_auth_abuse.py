import json
import secrets
from urllib.parse import urlsplit

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import AuditEvent, InstallationState

LOGIN_URL = "/_allauth/browser/v1/auth/login"
SESSION_URL = "/_allauth/browser/v1/auth/session"
SIGNUP_URL = "/_allauth/browser/v1/auth/signup"
OIDC_REDIRECT_URL = "/_allauth/browser/v1/auth/provider/redirect"
RESET_REQUEST_URL = "/_allauth/browser/v1/auth/password/request"


@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    cache.clear()


@pytest.fixture
def owner_credentials(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    email = f"owner-{secrets.token_hex(8)}@example.invalid"
    result = bootstrap_owner(
        tenant_name="Abuse Test MSP",
        owner_email=email,
        owner_display_name="Installation Owner",
        password=password,
    )
    return result, password


def anonymous_client() -> Client:
    client = Client(enforce_csrf_checks=True)
    assert client.get(SESSION_URL).status_code == 401
    return client


def post_json(client: Client, url: str, payload: dict[str, str], *, csrf: bool = True):  # type: ignore[no-untyped-def]
    headers = {"X-CSRFToken": client.cookies["csrftoken"].value} if csrf else {}
    return client.post(url, data=json.dumps(payload), content_type="application/json", headers=headers)


@pytest.mark.django_db
def test_failed_login_is_enumeration_safe_and_value_free(owner_credentials):
    result, _password = owner_credentials
    submitted_password = secrets.token_urlsafe(32)
    unknown_email = f"unknown-{secrets.token_hex(8)}@example.invalid"
    known_client = anonymous_client()
    unknown_client = anonymous_client()

    known = post_json(known_client, LOGIN_URL, {"email": result.owner.email, "password": submitted_password})
    unknown = post_json(unknown_client, LOGIN_URL, {"email": unknown_email, "password": submitted_password})

    assert known.status_code == unknown.status_code == 400
    assert known.json() == unknown.json()
    serialized_responses = f"{known.json()} {unknown.json()}"
    assert result.owner.email not in serialized_responses
    assert unknown_email not in serialized_responses
    assert submitted_password not in serialized_responses
    events = list(AuditEvent.objects.filter(action="auth.login_failed"))
    assert len(events) == 2
    assert all(event.actor is None and event.metadata == {} for event in events)


@pytest.mark.django_db
def test_login_rotates_attacker_supplied_session_and_logout_invalidates_it(owner_credentials):
    result, password = owner_credentials
    client = anonymous_client()
    session = client.session
    session["untrusted_marker"] = secrets.token_urlsafe(16)
    session.save()
    before_login = session.session_key

    logged_in = post_json(client, LOGIN_URL, {"email": result.owner.email, "password": password})

    assert logged_in.status_code == 200
    after_login = client.session.session_key
    assert after_login
    assert after_login != before_login
    assert client.get(reverse("auth-context")).status_code == 200
    logged_out = client.delete(SESSION_URL, headers={"X-CSRFToken": client.cookies["csrftoken"].value})
    assert logged_out.status_code == 401
    assert client.get(reverse("auth-context")).status_code == 403


@pytest.mark.django_db
@override_settings(TEKDOCS_OIDC_PROVIDER=None, SOCIALACCOUNT_PROVIDERS={})
def test_public_identity_creation_and_cross_site_mutations_stay_closed(owner_credentials):
    result, _password = owner_credentials
    client = anonymous_client()
    proposed_email = f"public-{secrets.token_hex(8)}@example.invalid"
    proposed_password = f"{secrets.token_urlsafe(24)}Bb8!"
    invitation_token = secrets.token_urlsafe(32)

    signup = post_json(client, SIGNUP_URL, {"email": proposed_email, "password": proposed_password})
    reset_without_csrf = post_json(client, RESET_REQUEST_URL, {"email": result.owner.email}, csrf=False)
    invitation_without_csrf = post_json(
        client,
        reverse("invitation-accept"),
        {"token": invitation_token, "display_name": "Untrusted", "password": proposed_password},
        csrf=False,
    )
    unknown_oidc = post_json(
        client,
        OIDC_REDIRECT_URL,
        {"provider": "unconfigured-provider", "process": "login", "callback_url": "http://testserver/"},
    )

    assert signup.status_code in {400, 403, 405}
    assert reset_without_csrf.status_code == 403
    assert invitation_without_csrf.status_code == 403
    assert unknown_oidc.status_code == 302
    oidc_error_url = urlsplit(unknown_oidc.headers["Location"])
    assert oidc_error_url.netloc == "testserver"
    assert oidc_error_url.path == "/"
    assert oidc_error_url.query == "error=unknown&error_process=login"
    assert User.objects.filter(email=proposed_email).exists() is False
    serialized = (
        f"{signup.content!r} {reset_without_csrf.content!r} "
        f"{invitation_without_csrf.content!r} {unknown_oidc.content!r}"
    )
    assert proposed_password not in serialized
    assert invitation_token not in serialized


@pytest.mark.django_db
def test_malformed_oversized_and_method_override_requests_fail_without_echo(owner_credentials):
    result, _password = owner_credentials
    client = anonymous_client()
    marker = f"must-not-echo-{secrets.token_hex(16)}"
    csrf_headers = {"X-CSRFToken": client.cookies["csrftoken"].value}

    malformed = client.post(
        LOGIN_URL,
        data=f'{{"email":"{marker}"',
        content_type="application/json",
        headers=csrf_headers,
    )
    oversized = client.post(
        LOGIN_URL,
        data=json.dumps({"email": result.owner.email, "password": marker + "x" * (2 * 1024 * 1024)}),
        content_type="application/json",
        headers=csrf_headers,
    )
    traced = client.generic("TRACE", LOGIN_URL)
    overridden = client.get(SESSION_URL, headers={"X-HTTP-Method-Override": "POST"})

    assert malformed.status_code in {400, 415}
    assert oversized.status_code in {400, 413}
    assert traced.status_code in {400, 405}
    assert overridden.status_code == 401
    assert marker not in f"{malformed.content!r} {oversized.content!r} {traced.content!r} {overridden.content!r}"
