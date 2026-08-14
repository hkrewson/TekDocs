import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.models import Invitation, TenantMembership
from apps.core.models import (
    AuditEvent,
    CustomFieldDefinition,
    CustomFieldDefinitionVersion,
    Entity,
    EntityLink,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    PersonAssociation,
    Site,
    Tenant,
    Workspace,
    WorkspaceKind,
)
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope, ScopeRequiredError


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    return Organization.objects.create(tenant=tenant, entity=anchor)


@pytest.mark.django_db
def test_workspace_ownership_is_explicit_unique_and_retained_through_archive():
    tenant = Tenant.objects.create(name="Ownership MSP", slug="ownership")
    msp_workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    organization = _organization(tenant, "Retained Client")
    organization_workspace = Workspace.objects.get(organization=organization)
    document = Entity.objects.create_owned(
        tenant=tenant,
        organization=organization,
        entity_type="document",
        display_name="Retained runbook",
    )

    assert Workspace.objects.filter(tenant=tenant, kind=WorkspaceKind.MSP).count() == 1
    assert organization_workspace.tenant_id == tenant.id
    assert document.workspace_id == organization_workspace.id

    organization.entity.archived_at = timezone.now()
    organization.entity.save(update_fields=("archived_at", "updated_at"))
    document.refresh_from_db()
    assert document.workspace_id == organization_workspace.id
    assert document.organization_id == organization.id

    organization_workspace.kind = WorkspaceKind.MSP
    with pytest.raises(ValidationError, match="immutable"):
        organization_workspace.save()
    organization_workspace.kind = WorkspaceKind.ORGANIZATION

    document.workspace = msp_workspace
    document.organization = None
    with pytest.raises(ValidationError, match="immutable"):
        document.save()

    with pytest.raises(ProtectedError):
        organization.delete()
    msp_workspace.refresh_from_db()


@pytest.mark.django_db
def test_entity_creation_omission_and_cross_workspace_ownership_fail_closed():
    tenant = Tenant.objects.create(name="Strict MSP", slug="strict")
    organization = _organization(tenant, "Strict Client")
    with pytest.raises(IntegrityError), transaction.atomic():
        Entity.objects.create(tenant=tenant, entity_type="document", display_name="Owner omitted")

    mismatched = Entity(
        tenant=tenant,
        workspace=Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP),
        organization=organization,
        entity_type="document",
        display_name="Wrong owner",
    )
    with pytest.raises(ValidationError, match="workspace"):
        mismatched.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model",
    [
        AuditEvent,
        CustomFieldDefinition,
        CustomFieldDefinitionVersion,
        Entity,
        EntityLink,
        Location,
        Invitation,
        Organization,
        OrganizationClassification,
        Person,
        PersonAssociation,
        Site,
        TenantMembership,
    ],
)
def test_scoped_manager_fails_closed_without_explicit_tenant(model):
    with pytest.raises(ScopeRequiredError, match="for_tenant"):
        model.scoped.all()
    with pytest.raises(ValueError, match="tenant UUID"):
        Entity.scoped.for_tenant(None)


@pytest.mark.django_db
def test_tenant_scope_never_returns_another_tenants_rows():
    first = Tenant.objects.create(name="First MSP", slug="first")
    second = Tenant.objects.create(name="Second MSP", slug="second")
    included = Entity.objects.create_owned(tenant=first, entity_type="document", display_name="First runbook")
    Entity.objects.create_owned(tenant=second, entity_type="document", display_name="Second runbook")

    result = list(Entity.scoped.for_tenant(first))

    assert result == [included]
    assert list(Entity.scoped.for_scope(DataScope.tenant(second)).values_list("display_name", flat=True)) == [
        "Second runbook"
    ]


@pytest.mark.django_db
def test_organization_scope_requires_exact_tenant_and_organization():
    tenant = Tenant.objects.create(name="Example MSP", slug="example")
    other_tenant = Tenant.objects.create(name="Other MSP", slug="other")
    first_organization = _organization(tenant, "First Client")
    second_organization = _organization(tenant, "Second Client")
    foreign_organization = _organization(other_tenant, "Foreign Client")
    msp_entity = Entity.objects.create_owned(tenant=tenant, entity_type="document", display_name="MSP policy")
    first_entity = Entity.objects.create_owned(
        tenant=tenant,
        organization=first_organization,
        entity_type="document",
        display_name="First client policy",
    )
    Entity.objects.create_owned(
        tenant=tenant,
        organization=second_organization,
        entity_type="document",
        display_name="Second client policy",
    )
    Entity.objects.create_owned(
        tenant=other_tenant,
        organization=foreign_organization,
        entity_type="document",
        display_name="Foreign client policy",
    )

    msp_ids = set(Entity.scoped.for_scope(DataScope.tenant(tenant)).values_list("id", flat=True))
    first_ids = set(
        Entity.scoped.for_scope(DataScope.organization(tenant, first_organization)).values_list("id", flat=True)
    )

    assert msp_entity.id in msp_ids
    assert first_entity.id not in msp_ids
    assert first_ids == {first_entity.id}


@pytest.mark.django_db
def test_model_validation_rejects_cross_tenant_organization_scope():
    first = Tenant.objects.create(name="First MSP", slug="first")
    second = Tenant.objects.create(name="Second MSP", slug="second")
    foreign_organization = _organization(second, "Foreign Client")
    entity = Entity(
        tenant=first,
        organization=foreign_organization,
        entity_type="document",
        display_name="Invalid policy",
    )

    with pytest.raises(ValidationError, match="Organization scope"):
        entity.full_clean()
    with pytest.raises(ValueError, match="selected tenant"):
        DataScope.organization(first, foreign_organization)


@pytest.mark.django_db(transaction=True)
def test_postgres_constraints_reject_scope_bypass_through_direct_writes():
    if connection.vendor != "postgresql":
        pytest.skip("Database scope triggers require PostgreSQL")
    first = Tenant.objects.create(name="First MSP", slug="first")
    second = Tenant.objects.create(name="Second MSP", slug="second")
    foreign_organization = _organization(second, "Foreign Client")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.create(
                tenant=first,
                workspace=foreign_organization.ownership_workspace,
                organization=foreign_organization,
                entity_type="document",
                display_name="Invalid policy",
            )

    valid_organization = _organization(first, "Valid Client")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Workspace.objects.filter(pk=valid_organization.ownership_workspace.id).update(
                tenant=second
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM core_workspace WHERE id = %s",
                    [str(valid_organization.ownership_workspace.id)],
                )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.filter(pk=valid_organization.entity_id).update(organization=valid_organization)

    source = Entity.objects.create_owned(tenant=first, entity_type="document", display_name="Source")
    target = Entity.objects.create_owned(tenant=second, entity_type="document", display_name="Foreign target")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.create(tenant=first, source=source, target=target, link_type="invalid")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            OrganizationClassification.objects.create(
                tenant=second,
                organization=valid_organization,
                kind="client",
            )


@pytest.mark.django_db(transaction=True)
def test_postgres_rls_scope_function_denies_missing_cross_tenant_and_cross_organization_context():
    if connection.vendor != "postgresql":
        pytest.skip("RLS contract requires PostgreSQL")
    tenant_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    other_id = uuid.uuid4()

    with connection.cursor() as cursor:
        cursor.execute("SELECT tekdocs_scope_matches(%s, NULL)", [tenant_id])
        assert cursor.fetchone() == (False,)

    with transaction.atomic():
        scope = DataScope(tenant_id=tenant_id, workspace_id=uuid.uuid4(), organization_id=organization_id)
        bind_local_rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tekdocs_scope_matches(%s, %s), tekdocs_scope_matches(%s, %s), tekdocs_scope_matches(%s, %s)",
                [tenant_id, organization_id, other_id, organization_id, tenant_id, other_id],
            )
            assert cursor.fetchone() == (True, False, False)


@pytest.mark.django_db(transaction=True)
def test_rls_scope_binding_requires_atomic_transaction():
    if connection.vendor != "postgresql":
        pytest.skip("RLS contract requires PostgreSQL")

    with pytest.raises(RuntimeError, match="atomic transaction"):
        bind_local_rls_scope(
            DataScope(tenant_id=uuid.uuid4(), workspace_id=uuid.uuid4()),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
        )


@pytest.mark.django_db(transaction=True)
def test_runtime_role_scoped_queries_compose_with_database_workspace_isolation(django_runtime_role):  # type: ignore[no-untyped-def]
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role scoped-query validation requires PostgreSQL")

    tenant = Tenant.objects.create(name="Runtime Scope MSP", slug="runtime-scope")
    foreign_tenant = Tenant.objects.create(name="Runtime Foreign MSP", slug="runtime-foreign")
    selected = _organization(tenant, "Runtime Selected Client")
    sibling = _organization(tenant, "Runtime Sibling Client")
    foreign = _organization(foreign_tenant, "Runtime Foreign Client")
    selected_entity = Entity.objects.create_owned(
        tenant=tenant,
        organization=selected,
        entity_type="document",
        display_name="Runtime selected document",
    )
    sibling_entity = Entity.objects.create_owned(
        tenant=tenant,
        organization=sibling,
        entity_type="document",
        display_name="Runtime sibling document",
    )
    Entity.objects.create_owned(
        tenant=foreign_tenant,
        organization=foreign,
        entity_type="document",
        display_name="Runtime foreign document",
    )
    selected_scope = DataScope.organization(tenant, selected)
    sibling_scope = DataScope.organization(tenant, sibling)

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(selected_scope, organization_mode=OrganizationRLSMode.ORGANIZATION)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == ("tekdocs_runtime",)
        assert list(
            Entity.scoped.for_scope(selected_scope).values_list("id", flat=True)
        ) == [selected_entity.id]
        assert not Entity.scoped.for_scope(sibling_scope).exists()
        assert list(
            Entity.objects.filter(entity_type="document").values_list("display_name", flat=True)
        ) == ["Runtime selected document"]
        assert Entity.objects.filter(pk=sibling_entity.id).update(display_name="Scope bypass") == 0
