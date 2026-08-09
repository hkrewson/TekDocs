from __future__ import annotations

import hashlib
from difflib import unified_diff
from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    Block,
    BlockRevision,
    Document,
    DocumentationListingReference,
    DocumentPlacement,
    Entity,
    Organization,
    Tenant,
)
from .scoping import DataScope


class RevisionConflict(Exception):
    def __init__(
        self,
        *,
        submitted_base_revision_id: UUID,
        current_revision: BlockRevision,
        base_revision: BlockRevision | None,
    ) -> None:
        super().__init__("The document changed after this editor loaded.")
        self.submitted_base_revision_id = submitted_base_revision_id
        self.current_revision = current_revision
        self.base_revision = base_revision


def markdown_checksum(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def revision_diff(before: BlockRevision | None, after: BlockRevision) -> str:
    before_markdown = before.markdown if before is not None else ""
    before_label = f"revision-{before.revision_number}" if before is not None else "empty"
    lines = unified_diff(
        before_markdown.splitlines(keepends=True),
        after.markdown.splitlines(keepends=True),
        fromfile=before_label,
        tofile=f"revision-{after.revision_number}",
    )
    return "".join(lines)


def documents_for_scope(scope: DataScope) -> QuerySet[Document]:
    placements = DocumentPlacement.objects.filter(tenant_id=scope.tenant_id).select_related(
        "block", "block__entity", "block__current_revision", "block__current_revision__created_by"
    )
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
    block = Block.objects.create(tenant=tenant, organization=organization, entity=block_entity)
    revision = BlockRevision.objects.create(
        tenant=tenant,
        organization=organization,
        block=block,
        revision_number=1,
        markdown=markdown,
        checksum=markdown_checksum(markdown),
        created_by_id=actor_id,
    )
    block.current_revision = revision
    block.save(update_fields=("current_revision", "updated_at"))
    DocumentPlacement.objects.create(
        tenant=tenant, organization=organization, document=document, block=block, position=0
    )
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="document.created", entity_id=document_entity.id, metadata={}
    )
    return document


@transaction.atomic
def update_document(
    *, document: Document, actor_id: UUID, title: str, markdown: str, base_revision_id: UUID
) -> BlockRevision:
    locked_document = Document.objects.select_for_update().select_related("entity").get(pk=document.pk)
    placement = locked_document.placements.select_related("block", "block__entity").get(position=0)
    block = Block.objects.select_for_update().get(pk=placement.block_id)
    if block.current_revision_id is None:
        raise RuntimeError("Document block has no current revision")
    current_revision = BlockRevision.objects.select_related("parent").get(pk=block.current_revision_id)
    if current_revision.id != base_revision_id:
        base_revision = BlockRevision.objects.filter(block=block, id=base_revision_id).first()
        raise RevisionConflict(
            submitted_base_revision_id=base_revision_id,
            current_revision=current_revision,
            base_revision=base_revision,
        )

    resulting_revision = current_revision
    if markdown != current_revision.markdown:
        resulting_revision = BlockRevision.objects.create(
            tenant=locked_document.tenant,
            organization=locked_document.organization,
            block=block,
            parent=current_revision,
            revision_number=current_revision.revision_number + 1,
            markdown=markdown,
            checksum=markdown_checksum(markdown),
            created_by_id=actor_id,
        )
        block.current_revision = resulting_revision
        block.save(update_fields=("current_revision", "updated_at"))

    locked_document.entity.display_name = title
    locked_document.entity.save(update_fields=("display_name", "updated_at"))
    block.entity.display_name = f"{title} — content"
    block.entity.save(update_fields=("display_name", "updated_at"))
    locked_document.save(update_fields=("updated_at",))
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.updated",
        entity_id=locked_document.entity_id,
        metadata={},
    )
    return resulting_revision


def revisions_for_document(document: Document) -> QuerySet[BlockRevision]:
    placement = document.placements.only("block_id").get(position=0)
    return BlockRevision.objects.filter(
        tenant=document.tenant,
        block_id=placement.block_id,
    ).select_related("created_by", "parent")


def revision_for_document(*, document: Document, revision_id: UUID) -> BlockRevision:
    return revisions_for_document(document).get(id=revision_id)


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
