from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AuditEvent,
    CatalogProduct,
    CatalogSpecificationDefinition,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    OrganizationKind,
    Tenant,
    workspace_for_owner,
)
from .rls import OrganizationRLSMode, system_rls_scope_if_postgresql
from .scoping import DataScope

SUPPLIER_KINDS = {OrganizationKind.VENDOR, OrganizationKind.MANUFACTURER}


def _replace_classifications(
    *,
    organization: Organization,
    classifications: Iterable[OrganizationKind],
) -> None:
    kinds = tuple(dict.fromkeys(classifications))
    scope = DataScope.organization(organization.tenant, organization)
    if not SUPPLIER_KINDS.intersection(kinds) and (
        CatalogProduct.scoped.for_scope(scope).exists()
        or CatalogSpecificationDefinition.scoped.for_scope(scope).exists()
    ):
        raise ValidationError(
            "An organization with catalog records must remain classified as a vendor or manufacturer."
        )

    existing = OrganizationClassification.scoped.for_tenant(organization.tenant).filter(
        organization=organization
    )
    existing_kinds = set(existing.values_list("kind", flat=True))
    OrganizationClassification.objects.bulk_create(
        [
            OrganizationClassification(
                tenant=organization.tenant,
                organization=organization,
                kind=kind,
            )
            for kind in kinds
            if kind not in existing_kinds
        ]
    )
    existing.exclude(kind__in=kinds).delete()


@transaction.atomic
def create_organization(
    *,
    tenant: Tenant,
    actor_id: UUID,
    name: str,
    legal_name: str,
    website: str,
    classifications: Iterable[OrganizationKind],
) -> Organization:
    with system_rls_scope_if_postgresql(
        DataScope.tenant(tenant),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
    ):
        entity = Entity.objects.create(
            tenant=tenant,
            workspace=workspace_for_owner(tenant=tenant, organization=None),
            entity_type="organization",
            display_name=name,
        )
        organization = Organization.objects.create(
            tenant=tenant,
            entity=entity,
            legal_name=legal_name,
            website=website,
        )
        # New organizations fail closed. Give an authorized MSP creator explicit
        # access so administrators do not create a workspace they cannot reopen.
        from apps.accounts.models import OrganizationAccessAssignment, TenantMembership

        creator_membership = TenantMembership.objects.filter(
            tenant=tenant,
            user_id=actor_id,
            organization__isnull=True,
        ).first()
        creator_is_owner = InstallationState.objects.filter(tenant=tenant, owner_id=actor_id).exists()
        if creator_membership is not None and not creator_is_owner:
            OrganizationAccessAssignment.objects.get_or_create(
                tenant=tenant,
                organization=organization,
                membership=creator_membership,
                defaults={"created_by_id": actor_id},
            )
        _replace_classifications(organization=organization, classifications=classifications)
        AuditEvent.objects.create(
            tenant=tenant,
            actor_id=actor_id,
            action="organization.created",
            entity_id=entity.id,
            metadata={},
        )
        return organization


@transaction.atomic
def update_organization(
    *,
    organization: Organization,
    actor_id: UUID,
    name: str,
    legal_name: str,
    website: str,
    classifications: Iterable[OrganizationKind],
) -> Organization:
    organization.entity.display_name = name
    organization.entity.save(update_fields=("display_name", "updated_at"))
    organization.legal_name = legal_name
    organization.website = website
    organization.save(update_fields=("legal_name", "website", "updated_at"))
    _replace_classifications(organization=organization, classifications=classifications)
    AuditEvent.objects.create(
        tenant=organization.tenant,
        actor_id=actor_id,
        action="organization.updated",
        entity_id=organization.entity_id,
        metadata={},
    )
    return organization


@transaction.atomic
def archive_organization(*, organization: Organization, actor_id: UUID) -> None:
    organization.entity.archived_at = timezone.now()
    organization.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=organization.tenant,
        actor_id=actor_id,
        action="organization.archived",
        entity_id=organization.entity_id,
        metadata={},
    )
