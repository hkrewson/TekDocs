import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    AccessCollection,
    AccessCollectionOrganization,
    BuiltInRole,
    CustomRole,
    CustomRolePermission,
    CustomRoleScope,
    OrganizationAccessAssignment,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)
from apps.accounts.policy import (
    DataAudience,
    PermissionKey,
    SensitiveField,
    accessible_organizations,
    context_has_permission,
    entity_visible_to_audience,
    project_authorized_fields,
    require_installation_member,
)
from apps.core.models import (
    AuditEvent,
    Entity,
    EntityVisibility,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Scoped Roles MSP",
        owner_email="role-owner@example.com",
        owner_display_name="Role Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def member(installation, email="reader@example.com"):
    user = User.objects.create_user(email=email, display_name="Scoped Reader")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=user,
        role=BuiltInRole.READ_ONLY,
    )
    client = Client()
    client.force_login(user)
    return user, membership, client


def organization(tenant, name, access_mode="all_authorized"):
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity, access_mode=access_mode)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def create_role(owner_client, *, name="Document publisher", scope="tenant", permissions=None):
    return owner_client.post(
        reverse("custom-role-list-create"),
        {
            "name": name,
            "description": "Publishes approved documentation.",
            "scope": scope,
            "permissions": permissions or ["documents.publish"],
        },
        content_type="application/json",
    )


@pytest.mark.django_db
def test_owner_creates_updates_lists_and_archives_a_bounded_custom_role(owner_client, installation):
    created = create_role(owner_client)
    assert created.status_code == 201
    role_id = created.json()["id"]
    assert created.json()["scope"] == "tenant"
    assert created.json()["permissions"] == ["documents.publish"]

    updated = owner_client.patch(
        reverse("custom-role-detail", kwargs={"role_id": role_id}),
        {
            "name": "Documentation lead",
            "description": "Publishes and edits documentation.",
            "permissions": ["documents.publish", "documents.edit"],
        },
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["scope"] == "tenant"
    assert updated.json()["permissions"] == ["documents.edit", "documents.publish"]
    assert owner_client.get(reverse("custom-role-list-create")).json()[0]["name"] == "Documentation lead"

    archived = owner_client.delete(reverse("custom-role-detail", kwargs={"role_id": role_id}))
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert {event.action for event in AuditEvent.objects.filter(tenant=installation.tenant, entity_id=role_id)} == {
        "custom_role.created",
        "custom_role.updated",
        "custom_role.archived",
    }
    assert all(not event.metadata for event in AuditEvent.objects.filter(entity_id=role_id))


@pytest.mark.django_db
def test_custom_role_rejects_privilege_ceiling_duplicate_and_cross_tenant_ids(owner_client, installation):
    assert create_role(owner_client, permissions=["memberships.assign_role"]).status_code == 400
    assert create_role(owner_client, permissions=["secrets.reveal"]).status_code == 400
    assert create_role(owner_client).status_code == 201
    assert create_role(owner_client, name="  DOCUMENT   PUBLISHER ").status_code == 400

    foreign = Tenant.objects.create(name="Foreign", slug="foreign-custom-role")
    TenantMembership.objects.create(
        tenant=foreign,
        user=installation.owner,
        role=BuiltInRole.READ_ONLY,
    )
    role = CustomRole.objects.create(
        tenant=foreign,
        name="Foreign role",
        scope=CustomRoleScope.TENANT,
        created_by=installation.owner,
    )
    assert (
        owner_client.patch(
            reverse("custom-role-detail", kwargs={"role_id": role.id}),
            {"name": "Guessed", "description": "", "permissions": ["documents.edit"]},
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_tenant_and_organization_assignments_add_permissions_without_bypassing_reachability(owner_client, installation):
    user, membership, _ = member(installation)
    open_client = organization(installation.tenant, "Open client")
    restricted_client = organization(installation.tenant, "Restricted client", "assigned_only")
    sibling = organization(installation.tenant, "Sibling client")
    tenant_role = create_role(owner_client, name="Tenant editor", permissions=["documents.edit"]).json()
    organization_role = create_role(
        owner_client,
        name="Client publisher",
        scope="organization",
        permissions=["documents.publish"],
    ).json()

    tenant_assignment = owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {"user_id": user.id, "role_id": tenant_role["id"]},
        content_type="application/json",
    )
    organization_assignment = owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {
            "user_id": user.id,
            "role_id": organization_role["id"],
            "organization_id": restricted_client.entity_id,
        },
        content_type="application/json",
    )
    assert tenant_assignment.status_code == 201
    assert organization_assignment.status_code == 201

    context = require_installation_member(user)
    assert context_has_permission(context, PermissionKey.DOCUMENTS_EDIT)
    assert context_has_permission(context, PermissionKey.DOCUMENTS_EDIT, organization=open_client)
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=sibling)
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=restricted_client)
    assert not accessible_organizations(context, PermissionKey.DOCUMENTS_PUBLISH).exists()

    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=restricted_client,
        membership=membership,
        created_by=installation.owner,
    )
    assert context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=restricted_client)
    assert list(accessible_organizations(context, PermissionKey.DOCUMENTS_PUBLISH)) == [restricted_client]

    owner_client.delete(reverse("custom-role-detail", kwargs={"role_id": organization_role["id"]}))
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=restricted_client)


@pytest.mark.django_db
def test_assignment_scope_validation_owner_mfa_csrf_and_idempotency(owner_client, installation):
    user, _, unprivileged_client = member(installation)
    record = organization(installation.tenant, "Client")
    tenant_role = create_role(owner_client, name="Tenant role").json()
    organization_role = create_role(owner_client, name="Client role", scope="organization").json()
    url = reverse("scoped-role-assignment-list-create")

    assert (
        owner_client.post(
            url,
            {"user_id": installation.owner.id, "role_id": tenant_role["id"]},
            content_type="application/json",
        ).status_code
        == 400
    )

    assert (
        owner_client.post(
            url,
            {"user_id": user.id, "role_id": organization_role["id"]},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        owner_client.post(
            url,
            {"user_id": user.id, "role_id": tenant_role["id"], "organization_id": record.entity_id},
            content_type="application/json",
        ).status_code
        == 400
    )
    first = owner_client.post(
        url,
        {"user_id": user.id, "role_id": tenant_role["id"]},
        content_type="application/json",
    )
    repeated = owner_client.post(
        url,
        {"user_id": user.id, "role_id": tenant_role["id"]},
        content_type="application/json",
    )
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert ScopedRoleAssignment.objects.count() == 1
    assert (
        unprivileged_client.post(
            url,
            {"user_id": user.id, "role_id": tenant_role["id"]},
            content_type="application/json",
        ).status_code
        == 403
    )

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert create_role(owner_client, name="No MFA").status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert (
        csrf_client.post(
            url,
            {"user_id": user.id, "role_id": tenant_role["id"]},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_postgresql_guards_custom_permission_and_assignment_scope(installation):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL trigger contract")
    user, membership, _ = member(installation)
    role = CustomRole.objects.create(
        tenant=installation.tenant,
        name="Guarded role",
        scope=CustomRoleScope.TENANT,
        created_by=installation.owner,
    )
    foreign = Tenant.objects.create(name="Foreign", slug="foreign-role-guard")

    with pytest.raises(IntegrityError), transaction.atomic():
        CustomRolePermission.objects.create(
            tenant=foreign,
            role=role,
            permission="documents.edit",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomRolePermission.objects.create(
            tenant=installation.tenant,
            role=role,
            permission="memberships.assign_role",
        )
    assignment = ScopedRoleAssignment.objects.create(
        tenant=installation.tenant,
        membership=membership,
        role=role,
        created_by=installation.owner,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ScopedRoleAssignment.objects.filter(pk=assignment.pk).update(tenant=foreign)
    assignment.refresh_from_db()
    assert assignment.membership.user_id == user.id

    owner_membership = TenantMembership.objects.get(
        tenant=installation.tenant,
        user=installation.owner,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ScopedRoleAssignment.objects.create(
            tenant=installation.tenant,
            membership=owner_membership,
            role=role,
            created_by=installation.owner,
        )


@pytest.mark.django_db
def test_collection_crud_and_assignment_compose_with_restricted_client_access(owner_client, installation):
    user, membership, _ = member(installation, "collection-reader@example.com")
    included = organization(installation.tenant, "Included", "assigned_only")
    sibling = organization(installation.tenant, "Sibling")
    created = owner_client.post(
        reverse("access-collection-list-create"),
        {
            "name": " Priority Clients ",
            "description": "Primary support group",
            "organization_ids": [included.entity_id],
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Priority Clients"
    assert created.json()["organizations"] == [{"id": str(included.entity_id), "name": "Included"}]
    collection_id = created.json()["id"]
    role = create_role(
        owner_client,
        name="Collection publisher",
        scope="collection",
        permissions=["documents.publish"],
    ).json()
    assigned = owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {"user_id": user.id, "role_id": role["id"], "collection_id": collection_id},
        content_type="application/json",
    )
    assert assigned.status_code == 201
    assert assigned.json()["collection_name"] == "Priority Clients"

    context = require_installation_member(user)
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=included)
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=included,
        membership=membership,
        created_by=installation.owner,
    )
    assert context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=included)
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=sibling)

    updated = owner_client.patch(
        reverse("access-collection-detail", kwargs={"collection_id": collection_id}),
        {"name": "Priority Clients", "description": "Changed", "organization_ids": [sibling.entity_id]},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=included)
    assert context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=sibling)

    archived = owner_client.delete(reverse("access-collection-detail", kwargs={"collection_id": collection_id}))
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert not context_has_permission(context, PermissionKey.DOCUMENTS_PUBLISH, organization=sibling)
    actions = set(
        AuditEvent.objects.filter(tenant=installation.tenant, entity_id=collection_id).values_list(
            "action", flat=True
        )
    )
    assert actions == {"access_collection.created", "access_collection.updated", "access_collection.archived"}


@pytest.mark.django_db
def test_collection_api_enforces_mfa_csrf_scope_and_non_disclosure(owner_client, installation):
    own = organization(installation.tenant, "Own")
    foreign_tenant = Tenant.objects.create(name="Foreign", slug="foreign-collection-api")
    foreign = organization(foreign_tenant, "Foreign")
    url = reverse("access-collection-list-create")
    assert owner_client.post(
        url,
        {"name": "Mixed", "description": "", "organization_ids": [own.entity_id, foreign.entity_id]},
        content_type="application/json",
    ).status_code == 404
    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.post(
        url,
        {"name": "No MFA", "description": "", "organization_ids": []},
        content_type="application/json",
    ).status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.post(
        url,
        {"name": "No CSRF", "description": "", "organization_ids": []},
        content_type="application/json",
    ).status_code == 403


@pytest.mark.django_db
def test_msp_private_visibility_and_cost_projection_are_hard_policy_boundaries(installation):
    user, _, _ = member(installation, "field-reader@example.com")
    client = organization(installation.tenant, "Client")
    sibling = organization(installation.tenant, "Sibling")
    private = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client,
        entity_type="document",
        display_name="Private runbook",
    )
    visible = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client,
        entity_type="document",
        display_name="Client guide",
        visibility=EntityVisibility.CLIENT_VISIBLE,
    )
    context = require_installation_member(user)
    assert not entity_visible_to_audience(context, private, audience=DataAudience.CLIENT_PORTAL, organization=client)
    assert entity_visible_to_audience(context, visible, audience=DataAudience.CLIENT_PORTAL, organization=client)
    assert not entity_visible_to_audience(context, visible, audience=DataAudience.CLIENT_PORTAL, organization=sibling)
    values = {"name": "Switch", "cost": "1200.00"}
    assert project_authorized_fields(context, values, {"cost": SensitiveField.COST}, organization=client) == {
        "name": "Switch"
    }


@pytest.mark.django_db
def test_collection_scoped_cost_permission_projects_only_member_organizations(owner_client, installation):
    user, _, _ = member(installation, "cost-reader@example.com")
    included = organization(installation.tenant, "Cost client")
    sibling = organization(installation.tenant, "No cost client")
    collection = owner_client.post(
        reverse("access-collection-list-create"),
        {"name": "Cost access", "description": "", "organization_ids": [included.entity_id]},
        content_type="application/json",
    ).json()
    role = create_role(
        owner_client,
        name="Cost viewer",
        scope="collection",
        permissions=["costs.view"],
    ).json()
    owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {"user_id": user.id, "role_id": role["id"], "collection_id": collection["id"]},
        content_type="application/json",
    )
    context = require_installation_member(user)
    values = {"name": "Firewall", "cost": "900.00"}
    assert project_authorized_fields(context, values, {"cost": SensitiveField.COST}, organization=included) == values
    assert project_authorized_fields(context, values, {"cost": SensitiveField.COST}, organization=sibling) == {
        "name": "Firewall"
    }


@pytest.mark.django_db
def test_postgresql_collection_guards_reject_cross_tenant_edges_and_wrong_scope(installation):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL trigger contract")
    user, membership, _ = member(installation, "guard-reader@example.com")
    own = organization(installation.tenant, "Guard own")
    foreign_tenant = Tenant.objects.create(name="Foreign", slug="foreign-collection-guard")
    foreign = organization(foreign_tenant, "Guard foreign")
    collection = AccessCollection.objects.create(
        tenant=installation.tenant,
        name="Guarded collection",
        created_by=installation.owner,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AccessCollectionOrganization.objects.create(
            tenant=installation.tenant,
            collection=collection,
            organization=foreign,
            created_by=installation.owner,
        )
    AccessCollectionOrganization.objects.create(
        tenant=installation.tenant,
        collection=collection,
        organization=own,
        created_by=installation.owner,
    )
    role = CustomRole.objects.create(
        tenant=installation.tenant,
        name="Collection guard role",
        scope=CustomRoleScope.COLLECTION,
        created_by=installation.owner,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ScopedRoleAssignment.objects.create(
            tenant=installation.tenant,
            membership=membership,
            role=role,
            organization=own,
            created_by=installation.owner,
        )
    assignment = ScopedRoleAssignment.objects.create(
        tenant=installation.tenant,
        membership=membership,
        role=role,
        collection=collection,
        created_by=installation.owner,
    )
    assert assignment.membership.user_id == user.id
