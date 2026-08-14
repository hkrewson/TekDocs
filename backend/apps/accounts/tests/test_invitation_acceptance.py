import re
import secrets
import threading
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import Invitation, InvitationState, TenantMembership, User
from apps.core.models import AuditEvent, InstallationState

SESSION_URL = "/_allauth/browser/v1/auth/session"


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def issue_token(installation) -> tuple[Invitation, str]:  # type: ignore[no-untyped-def]
    owner_client = Client()
    owner_client.force_login(installation.owner)
    response = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )
    assert response.status_code == 201
    match = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)
    assert match is not None
    return Invitation.objects.get(pk=response.json()["id"]), match.group(1)


def acceptance_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    assert client.get(SESSION_URL).status_code == 401
    return client, client.cookies["csrftoken"].value


def accept(client: Client, csrf: str, token: str, password: str | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        reverse("invitation-accept"),
        {
            "token": token,
            "display_name": "Invited Technician",
            "password": password or f"{secrets.token_urlsafe(24)}Aa7!",
        },
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )


@pytest.mark.django_db
def test_invitation_acceptance_creates_verified_member_and_session(installation):
    invitation, token = issue_token(installation)
    client, csrf = acceptance_client()

    response = accept(client, csrf, token)

    assert response.status_code == 200
    user = User.objects.get(email="invitee@example.com")
    payload = response.json()
    assert payload["role"] == "read_only"
    assert "people.view" in payload["permissions"]
    assert "people.create" not in payload["permissions"]
    assert {key: payload[key] for key in ("user", "tenant")} == {
        "user": {"id": str(user.id), "email": user.email, "display_name": "Invited Technician"},
        "tenant": {"id": str(installation.tenant.id), "name": installation.tenant.name},
    }
    invitation.refresh_from_db()
    assert invitation.state == InvitationState.ACCEPTED
    assert invitation.accepted_by == user
    assert invitation.accepted_at is not None
    assert invitation.token_digest == ""
    assert TenantMembership.objects.filter(tenant=installation.tenant, user=user).exists()
    email = EmailAddress.objects.get(user=user)
    assert email.email == user.email
    assert email.primary is True
    assert email.verified is True
    assert client.get(reverse("auth-context")).status_code == 200
    event = AuditEvent.objects.get(entity_id=invitation.id, action="invitation.accepted")
    assert event.actor == user
    assert event.metadata == {}
    assert token not in str(response.json())
    assert token not in str(event.metadata)
    assert client.get(reverse("invitation-list-create")).status_code == 403


@pytest.mark.django_db
def test_weak_password_rolls_back_without_consuming_invitation(installation):
    invitation, token = issue_token(installation)
    client, csrf = acceptance_client()

    response = accept(client, csrf, token, password="password")

    assert response.status_code == 400
    invitation.refresh_from_db()
    assert invitation.state == InvitationState.PENDING
    assert invitation.matches_active_token(token)
    assert User.objects.filter(email="invitee@example.com").exists() is False
    assert TenantMembership.objects.count() == 1
    assert EmailAddress.objects.filter(email="invitee@example.com").exists() is False


@pytest.mark.django_db
def test_unavailable_invitation_states_share_one_safe_response(installation):
    invitation, token = issue_token(installation)
    client, csrf = acceptance_client()
    Invitation.objects.filter(pk=invitation.pk).update(
        created_at=timezone.now() - timedelta(days=1),
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    expired = accept(client, csrf, token)
    malformed = accept(client, csrf, "not-a-token")

    assert expired.status_code == 410
    assert malformed.status_code == 410
    assert expired.json()["error"]["detail"] == malformed.json()["error"]["detail"]
    invitation.refresh_from_db()
    assert invitation.state == InvitationState.EXPIRED
    assert invitation.token_digest == ""
    assert User.objects.filter(email="invitee@example.com").exists() is False


@pytest.mark.django_db
def test_revoked_and_used_tokens_cannot_be_reused(installation):
    revoked_invitation, revoked_token = issue_token(installation)
    owner_client = Client()
    owner_client.force_login(installation.owner)
    assert (
        owner_client.post(reverse("invitation-revoke", kwargs={"invitation_id": revoked_invitation.id})).status_code
        == 200
    )
    client, csrf = acceptance_client()
    revoked = accept(client, csrf, revoked_token)

    second = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "second@example.com"},
        content_type="application/json",
    )
    assert second.status_code == 201
    match = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)
    assert match is not None
    used_token = match.group(1)
    accepted = client.post(
        reverse("invitation-accept"),
        {"token": used_token, "display_name": "Second User", "password": f"{secrets.token_urlsafe(24)}Aa7!"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )
    reuse_client, reuse_csrf = acceptance_client()
    reused = accept(reuse_client, reuse_csrf, used_token)

    assert revoked.status_code == 410
    assert accepted.status_code == 200
    assert reused.status_code == 410
    assert revoked.json()["error"]["detail"] == reused.json()["error"]["detail"]


@pytest.mark.django_db
def test_acceptance_requires_csrf_and_anonymous_session(installation):
    _invitation, token = issue_token(installation)
    without_csrf = Client(enforce_csrf_checks=True)
    missing = accept(without_csrf, "", token)

    owner_client = Client(enforce_csrf_checks=True)
    owner_client.force_login(installation.owner)
    owner_client.get(SESSION_URL)
    authenticated = accept(owner_client, owner_client.cookies["csrftoken"].value, token)

    assert missing.status_code == 403
    assert authenticated.status_code == 409
    assert User.objects.filter(email="invitee@example.com").exists() is False


@pytest.mark.django_db(transaction=True)
def test_concurrent_acceptance_creates_exactly_one_account(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Invitation acceptance concurrency contract requires PostgreSQL")
    _invitation, token = issue_token(installation)
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def activate() -> None:
        client, csrf = acceptance_client()
        barrier.wait()
        statuses.append(accept(client, csrf, token).status_code)

    threads = [threading.Thread(target=activate), threading.Thread(target=activate)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(statuses) == [200, 410]
    assert User.objects.filter(email="invitee@example.com").count() == 1
    assert TenantMembership.objects.filter(tenant=installation.tenant).count() == 2
