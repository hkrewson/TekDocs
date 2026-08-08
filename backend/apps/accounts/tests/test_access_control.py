import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import PERMISSION_CATALOG, ROLE_DEFINITIONS, PermissionKey
from apps.core.models import AuditEvent, Entity, InstallationState, Organization, OrganizationClassification, Tenant


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Policy MSP",
        owner_email="policy-owner@example.com",
        owner_display_name="Policy Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(tenant: Tenant, name: str, *, access_mode: str = "all_authorized") -> Organization:
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity, access_mode=access_mode)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def member(installation, *, role: BuiltInRole, email: str = "member@example.com"):  # type: ignore[no-untyped-def]
    user = User.objects.create_user(email=email, display_name=role.label)
    membership = TenantMembership.objects.create(tenant=installation.tenant, user=user, role=role)
    client = Client()
    client.force_login(user)
    return user, membership, client


@pytest.mark.django_db
def test_permission_and_role_catalogs_are_bounded_and_scope_roles_explicitly(owner_client):
    response = owner_client.get(reverse("access-control-catalog"))

    assert response.status_code == 200
    assert len({item.key for item in PERMISSION_CATALOG}) == len(PERMISSION_CATALOG)
    assert len({item.value for item in ROLE_DEFINITIONS}) == 7
    assert {item["value"] for item in response.json()["roles"]} == {
        "owner",
        "administrator",
        "technician",
        "contributor",
        "read_only",
        "client_administrator",
        "client_user",
    }
    role_scopes = {item["value"]: item["assignable_scope"] for item in response.json()["roles"]}
    assert role_scopes["owner"] == "installation"
    assert role_scopes["technician"] == "tenant"
    assert role_scopes["client_user"] == "organization"
    assert next(
        item for item in response.json()["permissions"] if item["key"] == PermissionKey.MEMBERSHIPS_ASSIGN_ROLE
    )["requires_mfa"]


@pytest.mark.django_db
def test_member_listing_and_role_assignment_are_tenant_scoped_value_free_and_non_self(
    owner_client,
    installation,
):
    target, membership, _ = member(installation, role=BuiltInRole.READ_ONLY)
    foreign_tenant = Tenant.objects.create(name="Foreign", slug="foreign-policy")
    foreign_user = User.objects.create_user(email="foreign@example.com", display_name="Foreign")
    TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_user, role=BuiltInRole.ADMINISTRATOR)

    listed = owner_client.get(reverse("access-control-members"))
    changed = owner_client.patch(
        reverse("access-control-member-role", kwargs={"user_id": target.id}),
        {"role": "technician"},
        content_type="application/json",
    )

    assert listed.status_code == 200
    assert {(item["email"], item["role"]) for item in listed.json()} == {
        (installation.owner.email, "owner"),
        (target.email, "read_only"),
    }
    assert changed.status_code == 200
    membership.refresh_from_db()
    assert membership.role == BuiltInRole.TECHNICIAN
    assert not AuditEvent.objects.get(action="membership.role_assigned", entity_id=target.id).metadata
    assert (
        owner_client.patch(
            reverse("access-control-member-role", kwargs={"user_id": installation.owner.id}),
            {"role": "administrator"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        owner_client.patch(
            reverse("access-control-member-role", kwargs={"user_id": foreign_user.id}),
            {"role": "administrator"},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert (
        owner_client.patch(
            reverse("access-control-member-role", kwargs={"user_id": target.id}),
            {"role": "client_administrator"},
            content_type="application/json",
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_role_assignment_requires_owner_mfa_and_csrf(installation, owner_client):
    target, _, _ = member(installation, role=BuiltInRole.READ_ONLY)
    url = reverse("access-control-member-role", kwargs={"user_id": target.id})
    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.patch(url, {"role": "technician"}, content_type="application/json").status_code == 403

    TOTP.activate(installation.owner, generate_totp_secret())
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.patch(url, {"role": "technician"}, content_type="application/json").status_code == 403

    _, _, administrator = member(
        installation,
        role=BuiltInRole.ADMINISTRATOR,
        email="administrator@example.com",
    )
    assert administrator.patch(url, {"role": "technician"}, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_built_in_roles_allow_reads_and_require_permission_plus_mfa_for_mutations(installation):
    client_organization = organization(installation.tenant, "Role Client")
    people_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id},
    )
    technician, _, technician_client = member(installation, role=BuiltInRole.TECHNICIAN)
    _, _, reader_client = member(
        installation,
        role=BuiltInRole.READ_ONLY,
        email="reader@example.com",
    )

    assert technician_client.get(people_url).status_code == 200
    assert reader_client.get(people_url).status_code == 200
    payload = {"full_name": "Morgan Ellis", "kind": "employee"}
    assert technician_client.post(people_url, payload, content_type="application/json").status_code == 403
    assert reader_client.post(people_url, payload, content_type="application/json").status_code == 403

    TOTP.activate(technician, generate_totp_secret())
    assert technician_client.post(people_url, payload, content_type="application/json").status_code == 201


@pytest.mark.django_db
def test_assigned_only_mode_is_additional_fail_closed_constraint_across_discovery_and_domain_routes(
    owner_client,
    installation,
):
    open_organization = organization(installation.tenant, "Open Client")
    restricted = organization(installation.tenant, "Restricted Client", access_mode="assigned_only")
    technician, _, technician_client = member(installation, role=BuiltInRole.TECHNICIAN)
    TOTP.activate(technician, generate_totp_secret())

    search = technician_client.get(reverse("workspace-organization-search"))
    assert [item["id"] for item in search.json()["results"]] == [str(open_organization.entity_id)]
    restricted_workspace = reverse("workspace-organization", kwargs={"entity_id": restricted.entity_id})
    restricted_people = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": restricted.entity_id},
    )
    restricted_entities = reverse(
        "organization-entity-search",
        kwargs={"organization_entity_id": restricted.entity_id},
    )
    assert technician_client.get(restricted_workspace).status_code == 404
    assert technician_client.get(restricted_people).status_code == 404
    assert technician_client.get(restricted_entities).status_code == 404
    assert owner_client.get(restricted_workspace).status_code == 200


@pytest.mark.django_db
def test_owner_can_change_access_mode_but_arbitrary_and_foreign_modes_fail(
    owner_client,
    installation,
):
    record = organization(installation.tenant, "Controlled Client")
    url = reverse("access-control-organization-detail", kwargs={"organization_entity_id": record.entity_id})
    changed = owner_client.patch(url, {"access_mode": "assigned_only"}, content_type="application/json")

    assert changed.status_code == 200
    record.refresh_from_db()
    assert record.access_mode == "assigned_only"
    assert AuditEvent.objects.get(action="organization.access_mode_changed", entity_id=record.entity_id).metadata == {}
    assert owner_client.patch(url, {"access_mode": "everyone"}, content_type="application/json").status_code == 400

    foreign_tenant = Tenant.objects.create(name="Foreign", slug="foreign-access-mode")
    foreign = organization(foreign_tenant, "Foreign Client")
    assert (
        owner_client.patch(
            reverse("access-control-organization-detail", kwargs={"organization_entity_id": foreign.entity_id}),
            {"access_mode": "assigned_only"},
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_database_rejects_unknown_organization_access_mode(installation):
    record = organization(installation.tenant, "Database Guard")
    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.filter(pk=record.pk).update(access_mode="everyone")
    record.refresh_from_db()
    assert record.access_mode == "all_authorized"


@pytest.mark.django_db
def test_database_rejects_non_tenant_membership_roles(installation):
    target = User.objects.create_user(email="invalid-role@example.com", display_name="Invalid role")
    with pytest.raises(IntegrityError), transaction.atomic():
        TenantMembership.objects.create(
            tenant=installation.tenant,
            user=target,
            role=BuiltInRole.CLIENT_ADMINISTRATOR,
        )


@pytest.mark.django_db
def test_guessed_membership_identifiers_remain_non_disclosing(owner_client):
    response = owner_client.patch(
        reverse("access-control-member-role", kwargs={"user_id": uuid.uuid4()}),
        {"role": "technician"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert "email" not in str(response.content).lower()
