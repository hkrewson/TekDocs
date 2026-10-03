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
    billing_contact_name: str = "",
    billing_email: str = "",
    billing_phone: str = "",
    billing_address_line_1: str = "",
    billing_address_line_2: str = "",
    billing_city: str = "",
    billing_region: str = "",
    billing_postal_code: str = "",
    billing_country_code: str = "",
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
        organization = Organization(
            tenant=tenant,
            entity=entity,
            legal_name=legal_name,
            website=website,
            billing_contact_name=billing_contact_name,
            billing_email=billing_email,
            billing_phone=billing_phone,
            billing_address_line_1=billing_address_line_1,
            billing_address_line_2=billing_address_line_2,
            billing_city=billing_city,
            billing_region=billing_region,
            billing_postal_code=billing_postal_code,
            billing_country_code=billing_country_code,
        )
        organization.full_clean()
        organization.save()
        from .repository_storage import schedule_workspace_repository_initialization

        schedule_workspace_repository_initialization(organization.ownership_workspace.id)
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
        from .repository_manifests import schedule_tenant_manifest_synchronization

        schedule_tenant_manifest_synchronization(tenant.id)
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
    billing_contact_name: str | None = None,
    billing_email: str | None = None,
    billing_phone: str | None = None,
    billing_address_line_1: str | None = None,
    billing_address_line_2: str | None = None,
    billing_city: str | None = None,
    billing_region: str | None = None,
    billing_postal_code: str | None = None,
    billing_country_code: str | None = None,
) -> Organization:
    organization.entity.display_name = name
    organization.entity.save(update_fields=("display_name", "updated_at"))
    organization.legal_name = legal_name
    organization.website = website
    billing_changes = {
        "billing_contact_name": billing_contact_name,
        "billing_email": billing_email,
        "billing_phone": billing_phone,
        "billing_address_line_1": billing_address_line_1,
        "billing_address_line_2": billing_address_line_2,
        "billing_city": billing_city,
        "billing_region": billing_region,
        "billing_postal_code": billing_postal_code,
        "billing_country_code": billing_country_code,
    }
    for field, value in billing_changes.items():
        if value is not None:
            setattr(organization, field, value)
    organization.full_clean()
    organization.save(update_fields=(
        "legal_name", "website", "billing_contact_name", "billing_email", "billing_phone",
        "billing_address_line_1", "billing_address_line_2", "billing_city", "billing_region",
        "billing_postal_code", "billing_country_code", "updated_at",
    ))
    _replace_classifications(organization=organization, classifications=classifications)
    AuditEvent.objects.create(
        tenant=organization.tenant,
        actor_id=actor_id,
        action="organization.updated",
        entity_id=organization.entity_id,
        metadata={},
    )
    from .repository_manifests import schedule_tenant_manifest_synchronization

    schedule_tenant_manifest_synchronization(organization.tenant_id)
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
