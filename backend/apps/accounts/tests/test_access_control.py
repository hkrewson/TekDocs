import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.accounts.policy import PERMISSION_CATALOG, ROLE_DEFINITIONS, PermissionKey
from apps.core.models import (
    AuditEvent,
    CredentialReference,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
)


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
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
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
def test_assigned_only_boundaries_cover_msp_entity_search_mentions_and_record_types(
    owner_client,
    installation,
):
    assigned = organization(installation.tenant, "Assigned Search Client", access_mode="assigned_only")
    restricted = organization(installation.tenant, "Restricted Search Client", access_mode="assigned_only")
    _technician, membership, technician_client = member(installation, role=BuiltInRole.READ_ONLY)
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=assigned,
        membership=membership,
        created_by=installation.owner,
    )
    assigned_contact = owner_client.post(
        reverse(
            "organization-people-list-create",
            kwargs={"organization_entity_id": assigned.entity_id},
        ),
        {"full_name": "Visible Assigned Contact", "kind": "contact"},
        content_type="application/json",
    )
    restricted_contact = owner_client.post(
        reverse(
            "organization-people-list-create",
            kwargs={"organization_entity_id": restricted.entity_id},
        ),
        {"full_name": "Hidden Restricted Contact", "kind": "contact"},
        content_type="application/json",
    )
    assert assigned_contact.status_code == 201
    assert restricted_contact.status_code == 201

    credential_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=assigned,
        entity_type="credential_reference",
        display_name="Hidden Credential Reference Title",
    )
    CredentialReference.objects.create(
        tenant=installation.tenant,
        organization=assigned,
        entity=credential_entity,
        provider="onepassword",
        reference_url=(
            "https://start.1password.com/open/i?"
            "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
            "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
        ),
    )

    people = technician_client.get(reverse("msp-entity-search"), {"entity_type": "person"})
    organizations = technician_client.get(reverse("msp-entity-search"), {"entity_type": "organization"})
    untyped = technician_client.get(reverse("msp-entity-search"))
    mentions = technician_client.get(reverse("msp-document-mention-search"))

    assert people.status_code == 200
    assert people.json()["results"] == []
    assert [item["display_name"] for item in organizations.json()["results"]] == ["Assigned Search Client"]
    assert "Restricted Search Client" not in {item["display_name"] for item in mentions.json()["results"]}
    assert "Visible Assigned Contact" not in {item["display_name"] for item in mentions.json()["results"]}
    assert "Hidden Restricted Contact" not in {item["display_name"] for item in mentions.json()["results"]}
    assert "Hidden Credential Reference Title" not in {item["display_name"] for item in untyped.json()["results"]}
    assert "Hidden Credential Reference Title" not in {item["display_name"] for item in mentions.json()["results"]}


@pytest.mark.django_db
def test_explicit_staff_assignment_unlocks_only_the_assigned_organization_without_granting_permissions(
    owner_client,
    installation,
):
    assigned = organization(installation.tenant, "Assigned Client", access_mode="assigned_only")
    sibling = organization(installation.tenant, "Sibling Client", access_mode="assigned_only")
    technician, _, technician_client = member(installation, role=BuiltInRole.TECHNICIAN)
    reader, _, reader_client = member(installation, role=BuiltInRole.READ_ONLY, email="assigned-reader@example.com")
    assignment_url = reverse(
        "access-control-organization-staff",
        kwargs={"organization_entity_id": assigned.entity_id},
    )

    created = owner_client.post(assignment_url, {"user_id": technician.id}, content_type="application/json")
    repeated = owner_client.post(assignment_url, {"user_id": technician.id}, content_type="application/json")
    owner_client.post(assignment_url, {"user_id": reader.id}, content_type="application/json")

    assert created.status_code == 201
    assert repeated.status_code == 200
    assert {item["id"] for item in created.json()["assigned_staff"]} == {str(technician.id)}
    assert OrganizationAccessAssignment.objects.filter(organization=assigned).count() == 2
    assert AuditEvent.objects.filter(action="organization.staff_assigned", entity_id=assigned.entity_id).count() == 2
    assert technician_client.get(
        reverse("workspace-organization", kwargs={"entity_id": assigned.entity_id})
    ).status_code == 200
    assert technician_client.get(
        reverse("workspace-organization", kwargs={"entity_id": sibling.entity_id})
    ).status_code == 404
    people_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": assigned.entity_id},
    )
    assert reader_client.get(people_url).status_code == 200
    assert reader_client.post(
        people_url,
        {"full_name": "Not authorized", "kind": "employee"},
        content_type="application/json",
    ).status_code == 403


@pytest.mark.django_db
def test_staff_assignment_removal_is_idempotent_and_immediately_revokes_discovery(
    owner_client,
    installation,
):
    restricted = organization(installation.tenant, "Removal Client", access_mode="assigned_only")
    target, _, target_client = member(installation, role=BuiltInRole.READ_ONLY)
    collection_url = reverse(
        "access-control-organization-staff",
        kwargs={"organization_entity_id": restricted.entity_id},
    )
    detail_url = reverse(
        "access-control-organization-staff-detail",
        kwargs={"organization_entity_id": restricted.entity_id, "user_id": target.id},
    )
    owner_client.post(collection_url, {"user_id": target.id}, content_type="application/json")

    removed = owner_client.delete(detail_url)
    repeated = owner_client.delete(detail_url)

    assert removed.status_code == 200
    assert repeated.status_code == 200
    assert removed.json()["assigned_staff"] == []
    assert not OrganizationAccessAssignment.objects.filter(organization=restricted).exists()
    assert (
        AuditEvent.objects.filter(action="organization.staff_unassigned", entity_id=restricted.entity_id).count() == 1
    )
    assert target_client.get(reverse("workspace-organization-search")).json()["results"] == []
    assert target_client.get(
        reverse("workspace-organization", kwargs={"entity_id": restricted.entity_id})
    ).status_code == 404


@pytest.mark.django_db
def test_staff_assignment_rejects_owner_foreign_members_and_unprivileged_or_unprotected_requests(
    owner_client,
    installation,
):
    restricted = organization(installation.tenant, "Protected Client", access_mode="assigned_only")
    target, _, administrator = member(installation, role=BuiltInRole.ADMINISTRATOR)
    TOTP.activate(target, generate_totp_secret())
    url = reverse("access-control-organization-staff", kwargs={"organization_entity_id": restricted.entity_id})
    assert owner_client.post(
        url,
        {"user_id": installation.owner.id},
        content_type="application/json",
    ).status_code == 400
    assert administrator.post(url, {"user_id": target.id}, content_type="application/json").status_code == 403

    foreign_tenant = Tenant.objects.create(name="Foreign", slug="foreign-assignment")
    foreign_user = User.objects.create_user(email="foreign-assignment@example.com", display_name="Foreign")
    TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_user, role=BuiltInRole.TECHNICIAN)
    assert owner_client.post(url, {"user_id": foreign_user.id}, content_type="application/json").status_code == 404

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.post(url, {"user_id": target.id}, content_type="application/json").status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.post(url, {"user_id": target.id}, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_postgresql_rejects_cross_tenant_or_mutated_staff_assignments(installation):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL trigger contract")
    target, membership, _ = member(installation, role=BuiltInRole.TECHNICIAN)
    client_organization = organization(installation.tenant, "Guarded assignment")
    assignment = OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        membership=membership,
        created_by=installation.owner,
    )
    foreign_tenant = Tenant.objects.create(name="Foreign guard", slug="foreign-assignment-guard")
    foreign_organization = organization(foreign_tenant, "Foreign guarded assignment")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAccessAssignment.objects.create(
            tenant=installation.tenant,
            organization=foreign_organization,
            membership=membership,
            created_by=installation.owner,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAccessAssignment.objects.filter(pk=assignment.pk).update(organization=foreign_organization)
    assignment.refresh_from_db()
    assert assignment.membership.user_id == target.id
    assert assignment.organization_id == client_organization.id


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
