from __future__ import annotations

import hashlib
from dataclasses import dataclass
from difflib import unified_diff
from typing import cast
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Max, Prefetch, Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    Block,
    BlockKind,
    BlockRevision,
    Document,
    DocumentationListingReference,
    DocumentAttachment,
    DocumentCategory,
    DocumentPlacement,
    DocumentPublication,
    Entity,
    Organization,
    PlacementResolutionMode,
    Tenant,
    workspace_for_owner,
)
from .rendering import attachment_ids_in_markdown
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


class PlacementConflict(Exception):
    pass


@dataclass(frozen=True)
class ResolvedPlacement:
    placement: DocumentPlacement
    revision: BlockRevision
    depth: int


@dataclass(frozen=True)
class ResolvedDocument:
    markdown: str
    placements: tuple[ResolvedPlacement, ...]


def markdown_checksum(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def _append_block_revision(*, block: Block, actor_id: UUID, markdown: str, base_revision_id: UUID) -> BlockRevision:
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
    if markdown == current_revision.markdown:
        return current_revision
    resulting_revision = BlockRevision.objects.create(
        tenant=block.tenant,
        organization=block.organization,
        block=block,
        parent=current_revision,
        revision_number=current_revision.revision_number + 1,
        markdown=markdown,
        checksum=markdown_checksum(markdown),
        created_by_id=actor_id,
    )
    block.current_revision = resulting_revision
    block.save(update_fields=("current_revision", "updated_at"))
    return resulting_revision


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
        "block",
        "block__entity",
        "block__current_revision",
        "block__current_revision__created_by",
        "parent",
        "pinned_revision",
    )
    attachments = DocumentAttachment.objects.filter(
        tenant_id=scope.tenant_id,
        archived_at__isnull=True,
    ).select_related("entity", "created_by")
    publications = DocumentPublication.objects.filter(tenant_id=scope.tenant_id).select_related(
        "entity", "document", "document__entity", "published_by"
    ).prefetch_related("control_events__actor", "successors__control_events")
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
        .prefetch_related(Prefetch("attachments", queryset=attachments, to_attr="active_attachments"))
        .prefetch_related(Prefetch("publications", queryset=publications, to_attr="retained_publications"))
        .distinct()
    )


def resolve_document(document: Document) -> ResolvedDocument:
    placements = list(getattr(document, "active_placements", ()))
    if not placements:
        placements = list(
            document.placements.select_related(
                "block", "block__entity", "block__current_revision", "parent", "pinned_revision"
            )
        )
    if len(placements) > 500:
        raise PlacementConflict("Document composition exceeds the 500-placement resolution limit.")

    children: dict[UUID | None, list[DocumentPlacement]] = {}
    for placement in placements:
        children.setdefault(placement.parent_id, []).append(placement)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.position, item.id.int))

    resolved: list[ResolvedPlacement] = []

    def visit(placement: DocumentPlacement, *, depth: int, ancestor_blocks: frozenset[UUID]) -> None:
        if depth >= 32:
            raise PlacementConflict("Document composition exceeds the 32-level transclusion limit.")
        if placement.block_id in ancestor_blocks:
            raise PlacementConflict("Circular block transclusion detected.")
        revision = (
            placement.block.current_revision
            if placement.resolution_mode == PlacementResolutionMode.LIVE
            else placement.pinned_revision
        )
        if revision is None or revision.block_id != placement.block_id:
            raise PlacementConflict("A document placement does not resolve to a valid block revision.")
        resolved.append(ResolvedPlacement(placement=placement, revision=revision, depth=depth))
        next_ancestors = ancestor_blocks | {placement.block_id}
        for child in children.get(placement.id, ()):
            visit(child, depth=depth + 1, ancestor_blocks=next_ancestors)

    for root in children.get(None, ()):
        visit(root, depth=0, ancestor_blocks=frozenset())
    if len(resolved) != len(placements):
        raise PlacementConflict("Document composition contains an unreachable or circular placement.")

    parts = [item.revision.markdown.strip("\n") for item in resolved]
    markdown = "\n\n".join(parts)
    if markdown:
        markdown += "\n"
    return ResolvedDocument(markdown=markdown, placements=tuple(resolved))


def primary_placement(document: Document) -> DocumentPlacement:
    placements = cast(tuple[DocumentPlacement, ...], getattr(document, "active_placements", ()))
    for placement in placements:
        if placement.parent_id is None and placement.position == 0:
            return placement
    return document.placements.select_related("block", "block__entity", "block__current_revision").get(
        parent__isnull=True, position=0
    )


@transaction.atomic
def create_document(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    title: str,
    markdown: str,
    category: str = DocumentCategory.GENERAL,
    is_template: bool = False,
) -> Document:
    document_entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="document",
        display_name=title,
    )
    document = Document.objects.create(
        tenant=tenant,
        organization=organization,
        entity=document_entity,
        category=category,
        is_template=is_template,
    )
    block_entity = Entity.objects.create(
        tenant=tenant,
        workspace=document_entity.workspace,
        organization=organization,
        entity_type="document_block",
        display_name=f"{title} — content",
    )
    block = Block.objects.create(
        tenant=tenant,
        organization=organization,
        entity=block_entity,
        source_document=document,
    )
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
    *,
    document: Document,
    actor_id: UUID,
    title: str,
    markdown: str,
    base_revision_id: UUID,
    category: str = DocumentCategory.GENERAL,
    is_template: bool = False,
) -> BlockRevision:
    locked_document = Document.objects.select_for_update().select_related("entity").get(pk=document.pk)
    placement = locked_document.placements.select_related("block", "block__entity").get(parent__isnull=True, position=0)
    block = Block.objects.select_for_update().get(pk=placement.block_id)
    resulting_revision = _append_block_revision(
        block=block,
        actor_id=actor_id,
        markdown=markdown,
        base_revision_id=base_revision_id,
    )

    locked_document.entity.display_name = title
    locked_document.entity.save(update_fields=("display_name", "updated_at"))
    block.entity.display_name = f"{title} — content"
    block.entity.save(update_fields=("display_name", "updated_at"))
    locked_document.category = category
    locked_document.is_template = is_template
    locked_document.save(update_fields=("category", "is_template", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.updated",
        entity_id=locked_document.entity_id,
        metadata={},
    )
    return resulting_revision


_ATTACHMENT_TARGET = "tekdocs://attachment/"


def instantiate_document_template(
    *,
    source: Document,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    title: str,
    category: str,
) -> Document:
    from .document_attachments import copy_document_attachment

    copied_attachments: list[DocumentAttachment] = []
    try:
        with transaction.atomic():
            if not source.is_template:
                raise PlacementConflict("The selected document is not a template.")
            resolved = resolve_document(source)
            attachment_ids = attachment_ids_in_markdown(resolved.markdown)
            source_attachments = list(
                DocumentAttachment.objects.filter(
                    tenant=source.tenant,
                    document=source,
                    entity_id__in=attachment_ids,
                    archived_at__isnull=True,
                ).select_related("entity")
            )
            if {item.entity_id for item in source_attachments} != attachment_ids:
                raise PlacementConflict("The template contains an unavailable managed attachment reference.")

            replacements = {item.entity_id: uuid4() for item in source_attachments}
            markdown = resolved.markdown
            for source_id, destination_id in replacements.items():
                markdown = markdown.replace(
                    f"{_ATTACHMENT_TARGET}{source_id}",
                    f"{_ATTACHMENT_TARGET}{destination_id}",
                )
            destination = create_document(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                title=title,
                markdown=markdown,
                category=category,
                is_template=False,
            )
            for attachment in source_attachments:
                copied_attachments.append(
                    copy_document_attachment(
                        attachment=attachment,
                        destination=destination,
                        actor_id=actor_id,
                        entity_id=replacements[attachment.entity_id],
                    )
                )
            AuditEvent.objects.create(
                tenant=tenant,
                actor_id=actor_id,
                action="document.template_instantiated",
                entity_id=destination.entity_id,
                metadata={"source_document_id": str(source.entity_id)},
            )
    except Exception:
        for copied in copied_attachments:
            copied.file.storage.delete(copied.file.name)
        raise
    return destination


@transaction.atomic
def update_shared_block(
    *, placement: DocumentPlacement, actor_id: UUID, markdown: str, base_revision_id: UUID
) -> BlockRevision:
    locked = DocumentPlacement.objects.select_for_update().select_related("block").get(pk=placement.pk)
    block = Block.objects.select_for_update().get(pk=locked.block_id)
    revision = _append_block_revision(
        block=block,
        actor_id=actor_id,
        markdown=markdown,
        base_revision_id=base_revision_id,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.shared_block_updated",
        entity_id=locked.document.entity_id,
        metadata={},
    )
    return revision


@transaction.atomic
def detach_document_placement(*, placement: DocumentPlacement, actor_id: UUID) -> DocumentPlacement:
    locked = (
        DocumentPlacement.objects.select_for_update(of=("self",))
        .select_related(
            "document", "document__entity", "block", "block__entity", "block__current_revision", "pinned_revision"
        )
        .get(pk=placement.pk)
    )
    if locked.parent_id is None and locked.position == 0:
        raise PlacementConflict("The primary document block cannot be detached.")
    revision = (
        locked.block.current_revision
        if locked.resolution_mode == PlacementResolutionMode.LIVE
        else locked.pinned_revision
    )
    if revision is None:
        raise PlacementConflict("The selected placement does not resolve to a revision.")
    source_name = locked.block.entity.display_name.removesuffix(" — content")
    entity = Entity.objects.create(
        tenant=locked.tenant,
        workspace=locked.document.entity.workspace,
        organization=locked.document.organization,
        entity_type="document_block",
        display_name=f"{source_name} — detached content",
    )
    block = Block.objects.create(
        tenant=locked.tenant,
        organization=locked.document.organization,
        entity=entity,
        source_document=locked.document,
    )
    detached_revision = BlockRevision.objects.create(
        tenant=locked.tenant,
        organization=locked.document.organization,
        block=block,
        revision_number=1,
        markdown=revision.markdown,
        checksum=markdown_checksum(revision.markdown),
        created_by_id=actor_id,
    )
    block.current_revision = detached_revision
    block.save(update_fields=("current_revision", "updated_at"))
    locked.block = block
    locked.resolution_mode = PlacementResolutionMode.LIVE
    locked.pinned_revision = None
    locked.save(update_fields=("block", "resolution_mode", "pinned_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.placement_detached",
        entity_id=locked.document.entity_id,
        metadata={},
    )
    return locked


def revisions_for_document(document: Document) -> QuerySet[BlockRevision]:
    placement = document.placements.only("block_id").get(parent__isnull=True, position=0)
    return BlockRevision.objects.filter(
        tenant=document.tenant,
        block_id=placement.block_id,
    ).select_related("created_by", "parent")


def revision_for_document(*, document: Document, revision_id: UUID) -> BlockRevision:
    return revisions_for_document(document).get(id=revision_id)


def _placement_parent(*, document: Document, parent_id: UUID | None) -> DocumentPlacement | None:
    if parent_id is None:
        return None
    parent = document.placements.select_for_update().filter(id=parent_id).first()
    if parent is None:
        raise PlacementConflict("The parent placement is not part of this document.")
    return parent


def _placement_position(
    *, document: Document, parent: DocumentPlacement | None, requested_position: int | None
) -> int:
    siblings = document.placements.select_for_update().filter(parent=parent)
    last_position = siblings.aggregate(value=Max("position"))["value"]
    minimum = 1 if parent is None else 0
    appended = minimum if last_position is None else last_position + 1
    if requested_position is None:
        return appended
    if requested_position < minimum or requested_position > appended:
        raise PlacementConflict(f"Block position must be between {minimum} and {appended}.")
    for sibling in siblings.filter(position__gte=requested_position).order_by("-position", "-id"):
        sibling.position += 1
        sibling.save(update_fields=("position", "updated_at"))
    return requested_position


@transaction.atomic
def create_document_block(
    *,
    document: Document,
    actor_id: UUID,
    markdown: str,
    kind: str,
    name: str,
    parent_id: UUID | None,
    position: int | None,
) -> DocumentPlacement:
    locked_document = Document.objects.select_for_update().select_related("entity").get(pk=document.pk)
    if locked_document.placements.count() >= 500:
        raise PlacementConflict("Document composition cannot exceed 500 blocks.")
    if kind not in BlockKind.values:
        raise PlacementConflict("The selected block type is not supported.")
    parent = _placement_parent(document=locked_document, parent_id=parent_id)
    resolved_position = _placement_position(
        document=locked_document,
        parent=parent,
        requested_position=position,
    )
    label = name.strip() or f"{locked_document.entity.display_name} — block {locked_document.placements.count() + 1}"
    entity = Entity.objects.create(
        tenant=locked_document.tenant,
        workspace=locked_document.entity.workspace,
        organization=locked_document.organization,
        entity_type="document_block",
        display_name=label,
    )
    block = Block.objects.create(
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        entity=entity,
        kind=kind,
        source_document=locked_document,
    )
    revision = BlockRevision.objects.create(
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        block=block,
        revision_number=1,
        markdown=markdown,
        checksum=markdown_checksum(markdown),
        created_by_id=actor_id,
    )
    block.current_revision = revision
    block.save(update_fields=("current_revision", "updated_at"))
    placement = DocumentPlacement.objects.create(
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        document=locked_document,
        block=block,
        parent=parent,
        position=resolved_position,
        resolution_mode=PlacementResolutionMode.LIVE,
    )
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.block_created",
        entity_id=locked_document.entity_id,
        metadata={},
    )
    return placement


@transaction.atomic
def add_document_placement(
    *,
    document: Document,
    source_document: Document,
    actor_id: UUID,
    resolution_mode: str,
    pinned_revision_id: UUID | None,
    parent_id: UUID | None,
    position: int | None = None,
) -> DocumentPlacement:
    locked_document = Document.objects.select_for_update().get(pk=document.pk)
    if locked_document.placements.count() >= 500:
        raise PlacementConflict("Document composition cannot exceed 500 blocks.")
    if source_document.pk == locked_document.pk:
        raise PlacementConflict("A document cannot transclude its own primary block.")
    source = primary_placement(source_document)
    block = Block.objects.select_related("current_revision").get(pk=source.block_id)
    parent = _placement_parent(document=locked_document, parent_id=parent_id)
    if parent is not None:
        ancestor: DocumentPlacement | None = parent
        seen: set[UUID] = set()
        while ancestor is not None:
            if ancestor.id in seen or ancestor.block_id == block.id:
                raise PlacementConflict("Circular block transclusion detected.")
            seen.add(ancestor.id)
            ancestor = (
                locked_document.placements.select_related("parent").filter(id=ancestor.parent_id).first()
                if ancestor.parent_id
                else None
            )
    pinned_revision = None
    if resolution_mode == PlacementResolutionMode.PINNED:
        if pinned_revision_id is None:
            raise PlacementConflict("Pinned placements require an exact revision.")
        pinned_revision = BlockRevision.objects.filter(block=block, id=pinned_revision_id).first()
        if pinned_revision is None:
            raise PlacementConflict("The pinned revision does not belong to the selected block.")
    elif resolution_mode != PlacementResolutionMode.LIVE or pinned_revision_id is not None:
        raise PlacementConflict("Live placements cannot specify a pinned revision.")

    resolved_position = _placement_position(
        document=locked_document,
        parent=parent,
        requested_position=position,
    )
    placement = DocumentPlacement.objects.create(
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        document=locked_document,
        block=block,
        parent=parent,
        position=resolved_position,
        resolution_mode=resolution_mode,
        pinned_revision=pinned_revision,
    )
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.placement_added",
        entity_id=locked_document.entity_id,
        metadata={},
    )
    return placement


@transaction.atomic
def update_document_placement(
    *, placement: DocumentPlacement, actor_id: UUID, resolution_mode: str, pinned_revision_id: UUID | None
) -> DocumentPlacement:
    locked = DocumentPlacement.objects.select_for_update().select_related("block").get(pk=placement.pk)
    if locked.parent_id is None and locked.position == 0:
        raise PlacementConflict("The primary document block must remain live.")
    pinned_revision = None
    if resolution_mode == PlacementResolutionMode.PINNED:
        if pinned_revision_id is None:
            raise PlacementConflict("Pinned placements require an exact revision.")
        pinned_revision = BlockRevision.objects.filter(block=locked.block, id=pinned_revision_id).first()
        if pinned_revision is None:
            raise PlacementConflict("The pinned revision does not belong to the placed block.")
    elif resolution_mode != PlacementResolutionMode.LIVE or pinned_revision_id is not None:
        raise PlacementConflict("Live placements cannot specify a pinned revision.")
    locked.resolution_mode = resolution_mode
    locked.pinned_revision = pinned_revision
    locked.save(update_fields=("resolution_mode", "pinned_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.placement_updated",
        entity_id=locked.document.entity_id,
        metadata={},
    )
    return locked


@transaction.atomic
def remove_document_placement(*, placement: DocumentPlacement, actor_id: UUID) -> None:
    locked = DocumentPlacement.objects.select_for_update().select_related("block", "block__entity").get(pk=placement.pk)
    if locked.parent_id is None and locked.position == 0:
        raise PlacementConflict("The primary document block cannot be removed.")
    if locked.children.exists():
        raise PlacementConflict("Remove nested placements before removing their parent.")
    tenant = locked.tenant
    document_entity_id = locked.document.entity_id
    owned_block = locked.block if locked.block.source_document_id == locked.document_id else None
    if owned_block is not None and DocumentPlacement.objects.filter(block=owned_block).exclude(pk=locked.pk).exists():
        raise PlacementConflict("Remove block transclusions before removing their source placement.")
    locked.delete()
    if owned_block is not None:
        archived_at = timezone.now()
        owned_block.archived_at = archived_at
        owned_block.save(update_fields=("archived_at", "updated_at"))
        owned_block.entity.archived_at = archived_at
        owned_block.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="document.placement_removed",
        entity_id=document_entity_id,
        metadata={},
    )


@transaction.atomic
def archive_document(*, document: Document, actor_id: UUID) -> None:
    archived_at = timezone.now()
    owned_blocks = Block.objects.select_for_update().filter(source_document=document, archived_at__isnull=True)
    if DocumentPlacement.objects.filter(block__in=owned_blocks).exclude(document=document).exists():
        raise PlacementConflict("Remove document transclusions before archiving their source document.")
    owned_block_ids = list(owned_blocks.values_list("id", flat=True))
    Block.objects.filter(id__in=owned_block_ids).update(archived_at=archived_at, updated_at=archived_at)
    Entity.objects.filter(block_record__id__in=owned_block_ids).update(archived_at=archived_at, updated_at=archived_at)
    document.listing_references.filter(archived_at__isnull=True).update(archived_at=archived_at, updated_at=archived_at)
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
    source_block_ids = reference.document.owned_blocks.values_list("id", flat=True)
    if DocumentPlacement.objects.filter(
        tenant=reference.tenant,
        organization=reference.organization,
        block_id__in=source_block_ids,
    ).exists():
        raise PlacementConflict("Remove client document transclusions before removing this listing reference.")
    reference.archived_at = timezone.now()
    reference.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=reference.tenant,
        actor_id=actor_id,
        action="document.reference_removed",
        entity_id=reference.document.entity_id,
        metadata={},
    )
