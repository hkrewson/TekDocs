import json
import secrets

import pytest
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import TenantMembership, User
from apps.core.models import AuditEvent, InstallationState

LOGIN_URL = "/_allauth/browser/v1/auth/login"
SESSION_URL = "/_allauth/browser/v1/auth/session"
SESSIONS_URL = "/_allauth/browser/v1/auth/sessions"


@pytest.fixture
def owner_credentials(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=password,
    )
    return result, password


def login(client: Client, email: str, password: str, *, user_agent: str) -> None:
    client.get(SESSION_URL)
    response = client.post(
        LOGIN_URL,
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
        headers={"X-CSRFToken": client.cookies["csrftoken"].value, "User-Agent": user_agent},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_users_can_list_and_revoke_only_their_own_sessions(owner_credentials):
    result, password = owner_credentials
    first = Client(enforce_csrf_checks=True)
    second = Client(enforce_csrf_checks=True)
    login(first, result.owner.email, password, user_agent="First test browser")
    login(second, result.owner.email, password, user_agent="Second test browser")

    listed = first.get(SESSIONS_URL, headers={"User-Agent": "First test browser"})
    assert listed.status_code == 200
    sessions = listed.json()["data"]
    assert len(sessions) == 2
    assert sum(item["is_current"] for item in sessions) == 1
    other = next(item for item in sessions if not item["is_current"])
    assert other["user_agent"] == "Second test browser"
    assert "last_seen_at" in other

    unrelated = User.objects.create_user(
        email="technician@example.com",
        password=f"{secrets.token_urlsafe(24)}Bb8!",
        display_name="Technician",
    )
    TenantMembership.objects.create(tenant=result.tenant, user=unrelated)
    foreign_store = SessionStore()
    foreign_store.create()
    foreign = UserSession.objects.create(
        user=unrelated,
        ip="127.0.0.1",
        user_agent="Unrelated browser",
        session_key=foreign_store.session_key,
    )
    denied = first.delete(
        SESSIONS_URL,
        data=json.dumps({"sessions": [foreign.pk]}),
        content_type="application/json",
        headers={"X-CSRFToken": first.cookies["csrftoken"].value},
    )
    assert denied.status_code == 400
    assert UserSession.objects.filter(pk=foreign.pk).exists()

    revoked = first.delete(
        SESSIONS_URL,
        data=json.dumps({"sessions": [other["id"]]}),
        content_type="application/json",
        headers={"X-CSRFToken": first.cookies["csrftoken"].value},
    )
    assert revoked.status_code == 200
    assert len(revoked.json()["data"]) == 1
    assert first.get(reverse("auth-context")).status_code == 200
    assert second.get(reverse("auth-context")).status_code == 403
    event = AuditEvent.objects.get(action="auth.session_revoked")
    assert event.actor == result.owner
    assert event.tenant == result.tenant
    assert event.metadata == {}


@pytest.mark.django_db
def test_session_revocation_requires_csrf(owner_credentials):
    result, password = owner_credentials
    client = Client(enforce_csrf_checks=True)
    login(client, result.owner.email, password, user_agent="Current test browser")
    session_id = client.get(SESSIONS_URL).json()["data"][0]["id"]

    response = client.delete(SESSIONS_URL, data=json.dumps({"sessions": [session_id]}), content_type="application/json")

    assert response.status_code == 403
    assert client.get(reverse("auth-context")).status_code == 200


@pytest.mark.django_db
def test_session_client_change_creates_value_free_audit_event(owner_credentials):
    result, password = owner_credentials
    client = Client(enforce_csrf_checks=True)
    login(client, result.owner.email, password, user_agent="Original test browser")

    response = client.get(SESSIONS_URL, headers={"User-Agent": "Changed test browser"})

    assert response.status_code == 200
    event = AuditEvent.objects.get(action="auth.session_client_changed")
    assert event.actor == result.owner
    assert event.tenant == result.tenant
    assert event.metadata == {}


@pytest.mark.django_db
def test_login_success_failure_and_logout_create_value_free_audit_events(owner_credentials):
    result, password = owner_credentials
    client = Client(enforce_csrf_checks=True)
    client.get(SESSION_URL)
    invalid = client.post(
        LOGIN_URL,
        data=json.dumps({"email": result.owner.email, "password": "incorrect-password"}),
        content_type="application/json",
        headers={"X-CSRFToken": client.cookies["csrftoken"].value},
    )
    assert invalid.status_code == 400
    login(client, result.owner.email, password, user_agent="Audit test browser")
    signed_out = client.delete(SESSION_URL, headers={"X-CSRFToken": client.cookies["csrftoken"].value})
    assert signed_out.status_code == 401

    failed = AuditEvent.objects.get(action="auth.login_failed")
    succeeded = AuditEvent.objects.get(action="auth.login_succeeded")
    logged_out = AuditEvent.objects.get(action="auth.logged_out")
    assert failed.actor is None
    assert succeeded.actor == logged_out.actor == result.owner
    assert failed.tenant == succeeded.tenant == logged_out.tenant == result.tenant
    assert failed.metadata == succeeded.metadata == logged_out.metadata == {}
    assert failed.request_id is not None


@pytest.mark.django_db
@override_settings(ACCOUNT_RATE_LIMITS={"login": "1/m/ip"})
def test_login_rate_limit_returns_too_many_requests(owner_credentials):
    result, _password = owner_credentials
    cache.clear()
    client = Client(enforce_csrf_checks=True, REMOTE_ADDR="192.0.2.20")
    client.get(SESSION_URL)

    def attempt():  # type: ignore[no-untyped-def]
        return client.post(
            LOGIN_URL,
            data=json.dumps({"email": result.owner.email, "password": "incorrect-password"}),
            content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )

    assert attempt().status_code == 400
    assert attempt().status_code == 429


def test_authentication_rate_limit_policy_is_explicit():
    assert settings.ACCOUNT_RATE_LIMITS == {
        "login": "20/m/ip",
        "login_failed": "10/m/ip,5/10m/key",
        "reset_password": "10/h/ip,3/h/key",
        "reset_password_from_key": "10/h/ip",
    }
