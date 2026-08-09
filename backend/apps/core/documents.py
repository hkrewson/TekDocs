from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentationListingReference,
    DocumentPlacement,
    Entity,
    Organization,
    Tenant,
)
from .scoping import DataScope


def documents_for_scope(scope: DataScope) -> QuerySet[Document]:
    placements = DocumentPlacement.objects.filter(tenant_id=scope.tenant_id).select_related("block", "block__entity")
    records = Document.objects.filter(tenant_id=scope.tenant_id, archived_at__isnull=True)
    if scope.organization_id is None:
        records = records.filter(organization__isnull=True)
    else:
        records = records.filter(
            Q(organization_id=scope.organization_id)
            | Q(
                organization__isnull=True,
                listing_references__organization_id=scope.organization_id,
                listing_references__archived_at__isnull=True,
            )
        )
    return (
        records.select_related("entity", "organization", "organization__entity")
        .prefetch_related(Prefetch("placements", queryset=placements, to_attr="active_placements"))
        .distinct()
    )


@transaction.atomic
def create_document(
    *, tenant: Tenant, organization: Organization | None, actor_id: UUID, title: str, markdown: str
) -> Document:
    document_entity = Entity.objects.create(
        tenant=tenant, organization=organization, entity_type="document", display_name=title
    )
    document = Document.objects.create(tenant=tenant, organization=organization, entity=document_entity)
    block_entity = Entity.objects.create(
        tenant=tenant, organization=organization, entity_type="document_block", display_name=f"{title} — content"
    )
    block = Block.objects.create(
        tenant=tenant, organization=organization, entity=block_entity, markdown=markdown
    )
    DocumentPlacement.objects.create(
        tenant=tenant, organization=organization, document=document, block=block, position=0
    )
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="document.created", entity_id=document_entity.id, metadata={}
    )
    return document


@transaction.atomic
def update_document(*, document: Document, actor_id: UUID, title: str, markdown: str) -> None:
    placement = document.placements.select_related("block", "block__entity").get(position=0)
    document.entity.display_name = title
    document.entity.save(update_fields=("display_name", "updated_at"))
    placement.block.markdown = markdown
    placement.block.save(update_fields=("markdown", "updated_at"))
    placement.block.entity.display_name = f"{title} — content"
    placement.block.entity.save(update_fields=("display_name", "updated_at"))
    document.save(update_fields=("updated_at",))
    AuditEvent.objects.create(
        tenant=document.tenant,
        actor_id=actor_id,
        action="document.updated",
        entity_id=document.entity_id,
        metadata={},
    )


@transaction.atomic
def archive_document(*, document: Document, actor_id: UUID) -> None:
    archived_at = timezone.now()
    placements = list(document.placements.select_related("block", "block__entity"))
    for placement in placements:
        placement.block.archived_at = archived_at
        placement.block.save(update_fields=("archived_at", "updated_at"))
        placement.block.entity.archived_at = archived_at
        placement.block.entity.save(update_fields=("archived_at", "updated_at"))
    document.listing_references.filter(archived_at__isnull=True).update(
        archived_at=archived_at, updated_at=archived_at
    )
    document.archived_at = archived_at
    document.save(update_fields=("archived_at", "updated_at"))
    document.entity.archived_at = archived_at
    document.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=document.tenant,
        actor_id=actor_id,
        action="document.archived",
        entity_id=document.entity_id,
        metadata={},
    )


@transaction.atomic
def add_listing_reference(
    *, document: Document, organization: Organization, actor_id: UUID
) -> DocumentationListingReference:
    reference, created = DocumentationListingReference.objects.get_or_create(
        tenant=document.tenant,
        organization=organization,
        document=document,
        archived_at=None,
    )
    if created:
        AuditEvent.objects.create(
            tenant=document.tenant,
            actor_id=actor_id,
            action="document.reference_added",
            entity_id=document.entity_id,
            metadata={},
        )
    return reference


@transaction.atomic
def remove_listing_reference(*, reference: DocumentationListingReference, actor_id: UUID) -> None:
    reference.archived_at = timezone.now()
    reference.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=reference.tenant,
        actor_id=actor_id,
        action="document.reference_removed",
        entity_id=reference.document.entity_id,
        metadata={},
    )
