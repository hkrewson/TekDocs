import re
import secrets
from datetime import timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, Invitation, OrganizationAccessAssignment, TenantMembership, User
from apps.core.models import InstallationState
from apps.core.organizations import create_organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Portal Test MSP",
        owner_email="portal-owner@example.invalid",
        owner_display_name="Portal Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):  # type: ignore[no-untyped-def]
    client = Client()
    client.force_login(installation.owner)
    return client


def _client_organization(installation, name: str):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, LLC",
        website="",
        classifications=["client"],
    )


def _acceptance_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    assert client.get("/_allauth/browser/v1/auth/session").status_code == 401
    return client, client.cookies["csrftoken"].value


@pytest.mark.django_db
def test_client_invitation_binds_portal_session_to_exact_organization(owner_client, installation):
    organization = _client_organization(installation, "Portal Client")
    sibling = _client_organization(installation, "Sibling Client")
    issued = owner_client.post(
        reverse("client-invitation-list-create", kwargs={"organization_entity_id": organization.entity_id}),
        {"email": "portal-user@example.invalid"},
        content_type="application/json",
    )

    assert issued.status_code == 201
    assert issued.json()["role"] == BuiltInRole.CLIENT_USER
    assert issued.json()["organization"] == {"id": str(organization.entity_id), "name": "Portal Client"}
    match = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)
    assert match is not None
    portal, csrf = _acceptance_client()
    accepted = portal.post(
        reverse("invitation-accept"),
        {
            "token": match.group(1),
            "display_name": "Portal User",
            "password": f"{secrets.token_urlsafe(24)}Aa7!",
        },
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert accepted.status_code == 200
    assert accepted.json()["surface"] == "client_portal"
    assert accepted.json()["organization"] == {"id": str(organization.entity_id), "name": "Portal Client"}
    membership = TenantMembership.objects.get(user__email="portal-user@example.invalid")
    assert membership.role == BuiltInRole.CLIENT_USER
    assert membership.organization == organization
    assert portal.get(reverse("client-portal-context")).status_code == 200
    assert (
        portal.get(
            reverse("organization-document-list-create", kwargs={"organization_entity_id": organization.entity_id})
        ).status_code
        == 403
    )
    assert (
        portal.get(
            reverse("organization-document-list-create", kwargs={"organization_entity_id": sibling.entity_id})
        ).status_code
        == 404
    )
    assert portal.get(reverse("organization-list-create")).status_code == 403


@pytest.mark.django_db
def test_administrator_can_invite_a_client_user_without_managing_msp_staff(installation):
    organization = _client_organization(installation, "Administrator Client")
    administrator = User.objects.create_user(
        email="portal-administrator@example.invalid", display_name="Portal Administrator"
    )
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=administrator,
        role=BuiltInRole.ADMINISTRATOR,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=organization,
        membership=membership,
        created_by=installation.owner,
    )
    TOTP.activate(administrator, generate_totp_secret())
    client = Client()
    client.force_login(administrator)

    client_invitation = client.post(
        reverse("client-invitation-list-create", kwargs={"organization_entity_id": organization.entity_id}),
        {"email": "client-user@example.invalid"},
        content_type="application/json",
    )

    assert client_invitation.status_code == 201
    assert client.get(reverse("invitation-list-create")).status_code == 403


@pytest.mark.django_db
def test_msp_session_cannot_enter_portal_and_non_client_invitation_is_hidden(owner_client, installation):
    vendor = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Supplier",
        legal_name="Supplier, LLC",
        website="",
        classifications=["vendor"],
    )

    assert owner_client.get(reverse("client-portal-context")).status_code == 403
    assert (
        owner_client.get(
            reverse("client-invitation-list-create", kwargs={"organization_entity_id": vendor.entity_id})
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_client_membership_database_guard_rejects_scope_retargeting(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Client membership guard requires PostgreSQL")
    first = _client_organization(installation, "First Client")
    second = _client_organization(installation, "Second Client")
    user = User.objects.create_user(email="guarded-portal@example.invalid", display_name="Guarded Portal")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=user,
        role=BuiltInRole.CLIENT_USER,
        organization=first,
    )

    with pytest.raises(DatabaseError, match="identity is immutable"), transaction.atomic():
        TenantMembership.objects.filter(pk=membership.pk).update(organization=second)
    with pytest.raises(DatabaseError, match="organization scope"), transaction.atomic():
        Invitation.objects.create(
            tenant=installation.tenant,
            organization=None,
            role=BuiltInRole.CLIENT_USER,
            email="invalid-scope@example.invalid",
            token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
            invited_by=installation.owner,
            expires_at=timezone.now() + timedelta(days=1),
        )
