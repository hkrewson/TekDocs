from __future__ import annotations

import secrets
from datetime import timedelta

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    AccessCollection,
    BuiltInRole,
    CustomRole,
    CustomRoleScope,
    Invitation,
    OrganizationAccessAssignment,
    TenantMembership,
    User,
)
from apps.accounts.policy import (
    CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS,
    PERMISSION_BY_KEY,
    PERMISSION_CATALOG,
    ROLE_BY_VALUE,
    ROLE_DEFINITIONS,
    PermissionKey,
)
from apps.core.models import Entity, InstallationState, Organization, Tenant
from apps.core.rls_contract import RLS_TABLES
from apps.core.scoping import TenantScopedManager
from apps.core.validation import (
    AUTHORIZATION_CONTROL_PLANE_TABLES,
    TENANT_MODEL_CONTRACTS,
    IsolationBoundary,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    return bootstrap_owner(
        tenant_name="Validation MSP",
        owner_email="validation-owner@example.invalid",
        owner_display_name="Validation Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )


def _tenant_models():
    return tuple(
        model
        for model in apps.get_models()
        if any(field.name == "tenant" for field in model._meta.fields)
    )


def test_every_tenant_bearing_model_has_one_reviewed_isolation_boundary():
    discovered = {model._meta.db_table for model in _tenant_models()}
    contracted = [contract.table for contract in TENANT_MODEL_CONTRACTS]

    assert len(contracted) == len(set(contracted))
    assert set(contracted) == discovered
    assert {
        contract.table
        for contract in TENANT_MODEL_CONTRACTS
        if contract.boundary == IsolationBoundary.FORCED_RLS
    } == set(RLS_TABLES)
    assert set(AUTHORIZATION_CONTROL_PLANE_TABLES).isdisjoint(RLS_TABLES)


def test_every_tenant_owned_model_uses_the_fail_closed_scoped_manager():
    exempt = {"core_installationstate"}
    for model in _tenant_models():
        if model._meta.db_table in exempt:
            continue
        assert isinstance(getattr(model, "scoped", None), TenantScopedManager), model._meta.label


def test_permission_and_role_catalogs_are_complete_unique_and_bounded():
    assert len(PERMISSION_CATALOG) == len(PermissionKey)
    assert len(PERMISSION_BY_KEY) == len(PermissionKey)
    assert {definition.key for definition in PERMISSION_CATALOG} == set(PermissionKey)
    assert len(ROLE_DEFINITIONS) == len(BuiltInRole)
    assert set(ROLE_BY_VALUE) == set(BuiltInRole)
    assert ROLE_BY_VALUE[BuiltInRole.OWNER].permissions == frozenset(PermissionKey)
    assert CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS < frozenset(PermissionKey)
    assert PermissionKey.CREDENTIAL_REFERENCES_MANAGE in CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS
    assert PermissionKey.MEMBERSHIPS_ASSIGN_ROLE not in CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS
    for definition in ROLE_DEFINITIONS:
        assert definition.permissions <= frozenset(PermissionKey)


@pytest.mark.django_db(transaction=True)
def test_postgres_control_plane_guards_reject_scope_retargeting_and_foreign_attribution(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Authorization control-plane validation requires PostgreSQL")

    foreign_tenant = Tenant.objects.create(name="Foreign validation MSP", slug="foreign-validation")
    foreign_user = User.objects.create_user(
        email="foreign-validation@example.invalid",
        display_name="Foreign Validation User",
    )
    TenantMembership.objects.create(
        tenant=foreign_tenant,
        user=foreign_user,
        role=BuiltInRole.READ_ONLY,
    )
    member_user = User.objects.create_user(
        email="member-validation@example.invalid",
        display_name="Validation Member",
    )
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=member_user,
        role=BuiltInRole.TECHNICIAN,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        TenantMembership.objects.filter(pk=membership.pk).update(tenant=foreign_tenant)
    with pytest.raises(IntegrityError), transaction.atomic():
        TenantMembership.objects.filter(pk=membership.pk).update(user=foreign_user)

    invitation = Invitation.objects.create(
        tenant=installation.tenant,
        email="invited-validation@example.invalid",
        token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
        invited_by=installation.owner,
        expires_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Invitation.objects.filter(pk=invitation.pk).update(tenant=foreign_tenant)
    with pytest.raises(IntegrityError), transaction.atomic():
        Invitation.objects.create(
            tenant=installation.tenant,
            email="foreign-actor@example.invalid",
            token_digest=Invitation.digest_token(secrets.token_urlsafe(32)),
            invited_by=foreign_user,
            expires_at=timezone.now() + timedelta(days=1),
        )

    organization_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        entity_type="organization",
        display_name="Validated client",
    )
    organization = Organization.objects.create(
        tenant=installation.tenant,
        entity=organization_entity,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAccessAssignment.objects.create(
            tenant=installation.tenant,
            organization=organization,
            membership=membership,
            created_by=foreign_user,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        AccessCollection.objects.create(
            tenant=installation.tenant,
            name="Foreign-attributed collection",
            created_by=foreign_user,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomRole.objects.create(
            tenant=installation.tenant,
            name="Foreign-attributed role",
            scope=CustomRoleScope.TENANT,
            created_by=foreign_user,
        )

    membership.refresh_from_db()
    invitation.refresh_from_db()
    assert membership.tenant_id == installation.tenant.id
    assert membership.user_id == member_user.id
    assert invitation.tenant_id == installation.tenant.id
