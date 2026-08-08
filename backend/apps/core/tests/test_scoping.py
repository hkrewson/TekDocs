import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.accounts.models import Invitation, TenantMembership
from apps.core.models import (
    AuditEvent,
    Entity,
    EntityLink,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    PersonAssociation,
    Site,
    Tenant,
)
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope, ScopeRequiredError


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    return Organization.objects.create(tenant=tenant, entity=anchor)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model",
    [
        AuditEvent,
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
    included = Entity.objects.create(tenant=first, entity_type="document", display_name="First runbook")
    Entity.objects.create(tenant=second, entity_type="document", display_name="Second runbook")

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
    msp_entity = Entity.objects.create(tenant=tenant, entity_type="document", display_name="MSP policy")
    first_entity = Entity.objects.create(
        tenant=tenant,
        organization=first_organization,
        entity_type="document",
        display_name="First client policy",
    )
    Entity.objects.create(
        tenant=tenant,
        organization=second_organization,
        entity_type="document",
        display_name="Second client policy",
    )
    Entity.objects.create(
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
                organization=foreign_organization,
                entity_type="document",
                display_name="Invalid policy",
            )

    valid_organization = _organization(first, "Valid Client")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.filter(pk=valid_organization.entity_id).update(organization=valid_organization)

    source = Entity.objects.create(tenant=first, entity_type="document", display_name="Source")
    target = Entity.objects.create(tenant=second, entity_type="document", display_name="Foreign target")
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
        scope = DataScope(tenant_id=tenant_id, organization_id=organization_id)
        bind_local_rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tekdocs_scope_matches(%s, %s), tekdocs_scope_matches(%s, %s), "
                "tekdocs_scope_matches(%s, %s)",
                [tenant_id, organization_id, other_id, organization_id, tenant_id, other_id],
            )
            assert cursor.fetchone() == (True, False, False)


@pytest.mark.django_db(transaction=True)
def test_rls_scope_binding_requires_atomic_transaction():
    if connection.vendor != "postgresql":
        pytest.skip("RLS contract requires PostgreSQL")

    with pytest.raises(RuntimeError, match="atomic transaction"):
        bind_local_rls_scope(DataScope(tenant_id=uuid.uuid4()), organization_mode=OrganizationRLSMode.MSP_ONLY)
