import re
import secrets
import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.settings import api_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, Invitation, InvitationState, TenantMembership, User
from apps.core.models import AuditEvent, Entity, InstallationState, Organization, OrganizationClassification, Tenant


@pytest.fixture
def installation(db):
    cache.clear()
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.mark.django_db
def test_owner_invitation_mutations_are_rate_limited(owner_client, installation, monkeypatch):
    monkeypatch.setitem(api_settings.DEFAULT_THROTTLE_RATES, "staff_invitations", "1/h")

    first = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "first@example.com"},
        content_type="application/json",
    )
    limited = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "second@example.com"},
        content_type="application/json",
    )

    assert first.status_code == 201
    assert limited.status_code == 429
    assert Invitation.objects.filter(tenant=installation.tenant).count() == 1


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def invitation_token(message_index: int = -1) -> str:
    match = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[message_index].body)
    assert match is not None
    return match.group(1)


@pytest.mark.django_db
def test_owner_issues_and_lists_digest_only_invitation(owner_client, installation, settings):
    settings.TEKDOCS_PUBLIC_URL = "https://docs.example.test"

    created = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "Invitee@Example.com"},
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["email"] == "invitee@example.com"
    assert created.json()["state"] == InvitationState.PENDING
    assert "token" not in str(created.json()).lower()
    invitation = Invitation.objects.get()
    token = invitation_token()
    assert len(token) >= 43
    assert invitation.token_digest == Invitation.digest_token(token)
    assert token not in invitation.token_digest
    assert invitation.matches_active_token(token)
    assert "https://docs.example.test/auth/invitations/accept#token=" in mail.outbox[0].body
    assert mail.outbox[0].alternatives[0].mimetype == "text/html"
    assert invitation.last_sent_at is not None
    assert invitation.delivery_attempts == 1
    assert invitation.send_count == 1

    listed = owner_client.get(reverse("invitation-list-create"))
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert token not in str(listed.json())
    events = AuditEvent.objects.filter(entity_id=invitation.id).order_by("occurred_at")
    assert [event.action for event in events] == ["invitation.issued", "invitation.delivered"]
    assert all(event.metadata == {} for event in events)
    assert token not in str(list(events.values("action", "metadata")))


@pytest.mark.django_db
def test_owner_without_totp_cannot_use_privileged_invitation_actions(owner_client, installation):
    installation.owner.authenticator_set.filter(type="totp").delete()

    listed = owner_client.get(reverse("invitation-list-create"))
    response = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "mfa-required@example.com"},
        content_type="application/json",
    )

    assert listed.status_code == 200
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "privileged_mfa_required"


@pytest.mark.django_db
def test_invitation_resend_rotates_token_and_revoke_invalidates_it(owner_client, installation):
    created = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )
    invitation = Invitation.objects.get(pk=created.json()["id"])
    first_token = invitation_token()

    resent = owner_client.post(reverse("invitation-resend", kwargs={"invitation_id": invitation.id}))

    assert resent.status_code == 200
    invitation.refresh_from_db()
    second_token = invitation_token()
    assert second_token != first_token
    assert invitation.matches_active_token(first_token) is False
    assert invitation.matches_active_token(second_token) is True
    assert invitation.delivery_attempts == 2
    assert invitation.send_count == 2

    revoked = owner_client.post(reverse("invitation-revoke", kwargs={"invitation_id": invitation.id}))

    assert revoked.status_code == 200
    invitation.refresh_from_db()
    assert invitation.state == InvitationState.REVOKED
    assert invitation.revoked_at is not None
    assert invitation.token_digest == ""
    assert invitation.matches_active_token(second_token) is False
    assert owner_client.post(reverse("invitation-resend", kwargs={"invitation_id": invitation.id})).status_code == 409


@pytest.mark.django_db
def test_duplicate_existing_user_and_invalid_invitation_are_rejected(owner_client, installation):
    first = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )
    duplicate = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "INVITEE@example.com"},
        content_type="application/json",
    )
    invalid = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "not-an-address"},
        content_type="application/json",
    )
    User.objects.create_user(email="member@example.com", display_name="Existing member")
    existing_user = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "member@example.com"},
        content_type="application/json",
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert invalid.status_code == 400
    assert existing_user.status_code == 409
    assert Invitation.objects.count() == 1


@pytest.mark.django_db
def test_expired_invitation_is_replaced_and_old_token_stays_invalid(owner_client, installation):
    first = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )
    old = Invitation.objects.get(pk=first.json()["id"])
    old_token = invitation_token()
    Invitation.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=2),
        expires_at=timezone.now() - timedelta(days=1),
    )

    replacement = owner_client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )

    assert replacement.status_code == 201
    old.refresh_from_db()
    assert old.state == InvitationState.EXPIRED
    assert old.token_digest == ""
    assert old.matches_active_token(old_token) is False
    assert Invitation.objects.filter(email="invitee@example.com").count() == 2


@pytest.mark.django_db
def test_delivery_failure_retains_safe_resendable_invitation(owner_client, installation):
    with patch("apps.accounts.invitations.send_invitation_email", side_effect=OSError("sensitive host failure")):
        response = owner_client.post(
            reverse("invitation-list-create"),
            {"email": "invitee@example.com"},
            content_type="application/json",
        )

    assert response.status_code == 503
    payload = str(response.json())
    assert "invitee@example.com" not in payload
    assert "sensitive host failure" not in payload
    invitation = Invitation.objects.get()
    assert invitation.state == InvitationState.PENDING
    assert invitation.last_sent_at is None
    assert invitation.last_delivery_failed_at is not None
    assert invitation.delivery_attempts == 1
    assert invitation.send_count == 0
    assert len(invitation.token_digest) == 64
    failure = AuditEvent.objects.get(entity_id=invitation.id, action="invitation.delivery_failed")
    assert failure.metadata == {}

    resent = owner_client.post(reverse("invitation-resend", kwargs={"invitation_id": invitation.id}))
    assert resent.status_code == 200
    invitation.refresh_from_db()
    assert invitation.send_count == 1
    assert invitation.delivery_attempts == 2


@pytest.mark.django_db
def test_invitation_endpoints_deny_anonymous_unrelated_and_cross_tenant_access(client, installation):
    anonymous = client.get(reverse("invitation-list-create"))
    unrelated = User.objects.create_user(email="unrelated@example.com", display_name="Unrelated")
    client.force_login(unrelated)
    denied = client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )

    second_tenant = Tenant.objects.create(name="Other MSP", slug="other")
    TenantMembership.objects.create(
        tenant=second_tenant,
        user=unrelated,
        role=BuiltInRole.READ_ONLY,
    )
    foreign = Invitation.objects.create(
        tenant=second_tenant,
        email="foreign@example.com",
        token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
        invited_by=unrelated,
        expires_at=timezone.now() + timedelta(days=1),
    )
    client.force_login(installation.owner)
    hidden = client.post(reverse("invitation-revoke", kwargs={"invitation_id": foreign.id}))

    assert anonymous.status_code == 403
    assert denied.status_code == 403
    assert hidden.status_code == 404
    assert Invitation.objects.filter(tenant=installation.tenant).count() == 0


@pytest.mark.django_db
def test_administrator_cannot_view_or_issue_msp_staff_invitations(client, installation):
    administrator = User.objects.create_user(email="administrator@example.com", display_name="Administrator")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=administrator,
        role=BuiltInRole.ADMINISTRATOR,
    )
    TOTP.activate(administrator, generate_totp_secret())
    client.force_login(administrator)

    listed = client.get(reverse("invitation-list-create"))
    issued = client.post(
        reverse("invitation-list-create"),
        {"email": "new-staff@example.com"},
        content_type="application/json",
    )

    assert listed.status_code == 403
    assert issued.status_code == 403
    assert Invitation.objects.count() == 0


@pytest.mark.django_db
def test_msp_staff_invitation_list_excludes_client_portal_invitations(owner_client, installation):
    client_organization = Organization.objects.create(
        tenant=installation.tenant,
        entity=Entity.objects.create_owned(
            tenant=installation.tenant,
            entity_type="organization",
            display_name="Client organization",
        ),
    )
    OrganizationClassification.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        kind="client",
    )
    Invitation.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        role=BuiltInRole.CLIENT_USER,
        email="client-user@example.com",
        token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
        invited_by=installation.owner,
        expires_at=timezone.now() + timedelta(days=1),
    )

    listed = owner_client.get(reverse("invitation-list-create"))

    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.django_db
def test_invitation_creation_requires_csrf_for_browser_session(installation):
    client = Client(enforce_csrf_checks=True)
    client.force_login(installation.owner)

    response = client.post(
        reverse("invitation-list-create"),
        {"email": "invitee@example.com"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert Invitation.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_invitation_issuance_creates_one_pending_record(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Invitation concurrency contract requires PostgreSQL")
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def issue() -> None:
        client = Client()
        client.force_login(installation.owner)
        barrier.wait()
        response = client.post(
            reverse("invitation-list-create"),
            {"email": "invitee@example.com"},
            content_type="application/json",
        )
        statuses.append(response.status_code)

    threads = [threading.Thread(target=issue), threading.Thread(target=issue)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(statuses) == [201, 409]
    assert Invitation.objects.filter(state=InvitationState.PENDING).count() == 1
