from __future__ import annotations

import hashlib
import json
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
    DocumentTemplateEnrollment,
    DocumentTemplateRevision,
    Entity,
    Organization,
    PlacementResolutionMode,
    Tenant,
    workspace_for_owner,
)
from .rendering import attachment_ids_in_markdown, split_markdown_sections
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


@dataclass(frozen=True)
class DocumentRestructureResult:
    status: str
    document: Document
    section_count: int


def markdown_checksum(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def _canonical_checksum(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    ).select_related("entity", "created_by", "replaces__entity")
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
        records.select_related(
            "entity",
            "organization",
            "organization__entity",
            "template_enrollment",
            "template_enrollment__source_template__entity",
            "template_enrollment__applied_revision",
        )
        .prefetch_related(Prefetch("placements", queryset=placements, to_attr="active_placements"))
        .prefetch_related(Prefetch("attachments", queryset=attachments, to_attr="active_attachments"))
        .prefetch_related(Prefetch("publications", queryset=publications, to_attr="retained_publications"))
        .distinct()
    )


def blocks_for_library(scope: DataScope) -> QuerySet[Block]:
    """Return local blocks plus explicitly published MSP library blocks."""

    records = Block.objects.filter(
        tenant_id=scope.tenant_id,
        archived_at__isnull=True,
        current_revision__isnull=False,
        source_document__archived_at__isnull=True,
    )
    if scope.organization_id is None:
        records = records.filter(organization__isnull=True)
    else:
        records = records.filter(
            Q(organization_id=scope.organization_id)
            | Q(
                organization__isnull=True,
                library_visible=True,
                source_document__library_visible=True,
            )
        )
    return records.select_related(
        "entity",
        "organization",
        "organization__entity",
        "source_document",
        "source_document__entity",
        "current_revision",
    ).distinct()


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


def _semantic_section_name(*, document: Document, position: int, markdown: str) -> str:
    first_line = next((line.strip() for line in markdown.splitlines() if line.strip()), "")
    label = first_line.lstrip("#>-* `").rstrip("# `").strip()
    if not label:
        label = f"Section {position + 1}"
    if len(label) > 100:
        label = f"{label[:97].rstrip()}…"
    return f"{document.entity.display_name} — {label}"[:240]


def document_restructure_preview(document: Document) -> dict[str, object]:
    """Describe a safe single-region conversion without changing persisted state."""

    placements = list(
        document.placements.select_related(
            "block", "block__entity", "block__current_revision", "pinned_revision", "parent"
        ).order_by("parent_id", "position", "id")
    )
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    primary = next(
        (placement for placement in placements if placement.parent_id is None and placement.position == 0),
        None,
    )
    already_converted = AuditEvent.objects.filter(
        tenant=document.tenant,
        action="document.semantic_sections_created",
        entity_id=document.entity_id,
    ).exists()
    if len(placements) != 1:
        blockers.append(
            {
                "code": "composition_not_legacy",
                "detail": "Only documents with one top-level content region can be restructured.",
            }
        )
    if primary is None or primary.block.current_revision is None:
        blockers.append({"code": "primary_unavailable", "detail": "The primary content revision is unavailable."})
    elif primary.resolution_mode != PlacementResolutionMode.LIVE:
        blockers.append({"code": "primary_pinned", "detail": "A pinned primary content region cannot be restructured."})
    if already_converted:
        blockers.append(
            {"code": "already_restructured", "detail": "This document has already been restructured."}
        )
    if document.is_template:
        blockers.append(
            {
                "code": "template_source",
                "detail": "Reusable templates must be copied or retired before restructuring.",
            }
        )
    if DocumentTemplateEnrollment.objects.filter(destination_document=document, archived_at__isnull=True).exists():
        blockers.append(
            {
                "code": "template_managed",
                "detail": "A document managed by a template rollout cannot be restructured.",
            }
        )
    if hasattr(document, "remote_source") and document.remote_source.archived_at is None:
        blockers.append(
            {
                "code": "remote_managed",
                "detail": "Remove the remote source before restructuring this document.",
            }
        )
    if (
        primary is not None
        and DocumentPlacement.objects.filter(block_id=primary.block_id).exclude(id=primary.id).exists()
    ):
        blockers.append(
            {
                "code": "shared_primary",
                "detail": "The current content is reused elsewhere. Detach those uses before restructuring.",
            }
        )

    publication_count = DocumentPublication.objects.filter(document=document).count()
    if publication_count:
        warnings.append(
            {
                "code": "retained_publications",
                "detail": f"{publication_count} retained STATIC publication(s) remain unchanged.",
            }
        )
    attachment_count = DocumentAttachment.objects.filter(document=document, archived_at__isnull=True).count()
    if attachment_count:
        warnings.append(
            {
                "code": "retained_attachments",
                "detail": f"{attachment_count} managed attachment(s) remain attached to this document.",
            }
        )

    revision = primary.block.current_revision if primary is not None else None
    sections = split_markdown_sections(revision.markdown) if revision is not None else []
    if len(sections) < 2 and not any(item["code"] == "already_restructured" for item in blockers):
        blockers.append(
            {
                "code": "no_semantic_boundaries",
                "detail": "This content does not contain multiple safe semantic sections.",
            }
        )
    return {
        "eligible": not blockers,
        "base_revision_id": revision.id if revision is not None else None,
        "base_checksum": revision.checksum if revision is not None else "",
        "section_count": len(sections),
        "sections": [
            {
                "position": position,
                "kind": kind,
                "name": _semantic_section_name(document=document, position=position, markdown=markdown),
                "markdown": markdown,
                "checksum": markdown_checksum(markdown),
            }
            for position, (kind, markdown) in enumerate(sections)
        ],
        "blockers": blockers,
        "warnings": warnings,
        "dependencies": {
            "publication_count": publication_count,
            "attachment_count": attachment_count,
            "template_managed": DocumentTemplateEnrollment.objects.filter(
                destination_document=document, archived_at__isnull=True
            ).exists(),
            "remote_managed": hasattr(document, "remote_source") and document.remote_source.archived_at is None,
            "shared_placement_count": (
                DocumentPlacement.objects.filter(block_id=primary.block_id).exclude(id=primary.id).count()
                if primary is not None
                else 0
            ),
        },
    }


@transaction.atomic
def restructure_document(
    *, document: Document, actor_id: UUID, base_revision_id: UUID
) -> DocumentRestructureResult:
    """Convert one legacy content region into ordered semantic blocks atomically."""

    locked = Document.objects.select_for_update().select_related("entity", "tenant").get(pk=document.pk)
    prior_event = AuditEvent.objects.filter(
        tenant=locked.tenant,
        action="document.semantic_sections_created",
        entity_id=locked.entity_id,
        metadata__base_revision_id=str(base_revision_id),
    ).first()
    if prior_event is not None:
        retained_section_count = prior_event.metadata.get("section_count")
        return DocumentRestructureResult(
            status="already_restructured",
            document=locked,
            section_count=(
                retained_section_count if isinstance(retained_section_count, int) else locked.placements.count()
            ),
        )

    primary = locked.placements.select_related("block", "block__entity", "block__current_revision").get(
        parent__isnull=True, position=0
    )
    primary_block = (
        Block.objects.select_for_update(of=("self",))
        .select_related("entity", "current_revision")
        .get(pk=primary.block_id)
    )
    preview = document_restructure_preview(locked)
    current_revision = primary_block.current_revision
    if current_revision is None:
        raise PlacementConflict("The primary content revision is unavailable.")
    if current_revision.id != base_revision_id:
        base_revision = BlockRevision.objects.filter(block=primary.block, id=base_revision_id).first()
        raise RevisionConflict(
            submitted_base_revision_id=base_revision_id,
            current_revision=current_revision,
            base_revision=base_revision,
        )
    blockers = cast(list[dict[str, str]], preview["blockers"])
    if blockers:
        raise PlacementConflict(blockers[0]["detail"])

    sections = cast(list[dict[str, object]], preview["sections"])
    first = sections[0]
    _append_block_revision(
        block=primary_block,
        actor_id=actor_id,
        markdown=str(first["markdown"]),
        base_revision_id=base_revision_id,
    )
    primary_block.kind = str(first["kind"])
    primary_block.entity.display_name = str(first["name"])
    primary_block.entity.save(update_fields=("display_name", "updated_at"))
    primary_block.save(update_fields=("kind", "updated_at"))

    placement_ids = [str(primary.id)]
    for position, section in enumerate(sections[1:], start=1):
        entity = Entity.objects.create(
            tenant=locked.tenant,
            workspace=locked.entity.workspace,
            organization=locked.organization,
            entity_type="document_block",
            display_name=str(section["name"]),
        )
        block = Block.objects.create(
            tenant=locked.tenant,
            organization=locked.organization,
            entity=entity,
            source_document=locked,
            kind=str(section["kind"]),
            library_visible=locked.library_visible,
        )
        revision = BlockRevision.objects.create(
            tenant=locked.tenant,
            organization=locked.organization,
            block=block,
            revision_number=1,
            markdown=str(section["markdown"]),
            checksum=str(section["checksum"]),
            created_by_id=actor_id,
        )
        block.current_revision = revision
        block.save(update_fields=("current_revision", "updated_at"))
        placement = DocumentPlacement.objects.create(
            tenant=locked.tenant,
            organization=locked.organization,
            document=locked,
            block=block,
            position=position,
            resolution_mode=PlacementResolutionMode.LIVE,
        )
        placement_ids.append(str(placement.id))

    result_checksum = markdown_checksum(
        "\n\n".join(str(section["markdown"]).strip("\n") for section in sections) + "\n"
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.semantic_sections_created",
        entity_id=locked.entity_id,
        metadata={
            "base_revision_id": str(base_revision_id),
            "source_checksum": str(preview["base_checksum"]),
            "result_checksum": result_checksum,
            "section_count": len(sections),
            "placement_ids": placement_ids,
        },
    )
    return DocumentRestructureResult(status="restructured", document=locked, section_count=len(sections))


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
    library_visible: bool = False,
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
        library_visible=library_visible,
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
        library_visible=library_visible,
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
    if is_template and organization is None:
        ensure_template_revision(source=document, actor_id=actor_id)
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
    library_visible: bool = False,
) -> BlockRevision:
    locked_document = Document.objects.select_for_update().select_related("entity").get(pk=document.pk)
    placement = locked_document.placements.select_related("block", "block__entity").get(parent__isnull=True, position=0)
    block = Block.objects.select_for_update().get(pk=placement.block_id)
    if (
        locked_document.organization_id is None
        and locked_document.library_visible
        and not library_visible
        and DocumentPlacement.objects.filter(
            block__source_document=locked_document,
            document__organization__isnull=False,
        ).exists()
    ):
        raise PlacementConflict("Detach client block reuse before removing this document from the block library.")
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
    locked_document.library_visible = library_visible
    locked_document.save(update_fields=("category", "is_template", "library_visible", "updated_at"))
    if placement.parent_id is None and placement.position == 0 and block.library_visible != library_visible:
        block.library_visible = library_visible
        block.save(update_fields=("library_visible", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.updated",
        entity_id=locked_document.entity_id,
        metadata={},
    )
    if locked_document.is_template and locked_document.organization_id is None:
        ensure_template_revision(source=locked_document, actor_id=actor_id)
    return resulting_revision


_ATTACHMENT_TARGET = "tekdocs://attachment/"


def _template_manifest(source: Document) -> dict[str, object]:
    if not source.is_template or source.organization_id is not None:
        raise PlacementConflict("Client rollout requires an MSP-owned reusable template.")
    resolved = resolve_document(source)
    return {
        "template_document_id": str(source.entity_id),
        "title": source.entity.display_name,
        "blocks": [
            {
                "source_block_id": str(item.placement.block.entity_id),
                "source_revision_id": str(item.revision.id),
                "checksum": item.revision.checksum,
                "kind": item.placement.block.kind,
                "name": item.placement.block.entity.display_name,
                "depth": item.depth,
                "attachment_ids": sorted(
                    str(value) for value in attachment_ids_in_markdown(item.revision.markdown)
                ),
            }
            for item in resolved.placements
        ],
    }


def ensure_template_revision(*, source: Document, actor_id: UUID) -> DocumentTemplateRevision:
    manifest = _template_manifest(source)
    checksum = _canonical_checksum(manifest)
    existing = DocumentTemplateRevision.objects.filter(template=source, checksum=checksum).first()
    if existing is not None:
        return existing
    revision_number = (
        DocumentTemplateRevision.objects.filter(template=source).aggregate(value=Max("revision_number"))["value"] or 0
    ) + 1
    return DocumentTemplateRevision.objects.create(
        tenant=source.tenant,
        template=source,
        revision_number=revision_number,
        manifest=manifest,
        checksum=checksum,
        created_by_id=actor_id,
    )


def _template_rule(rules: dict[str, str], source_block_id: UUID, *, primary: bool) -> str:
    rule = rules.get(str(source_block_id), "copy")
    if rule not in {"copy", "live", "pinned"}:
        raise PlacementConflict("Template placement rules must be copy, live, or pinned.")
    if primary and rule != "copy":
        raise PlacementConflict("A client document's primary block must be an independent copy.")
    return rule


@transaction.atomic
def instantiate_document_template(
    *,
    source: Document,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    title: str,
    category: str,
    placement_rules: dict[str, str] | None = None,
) -> Document:
    from .document_attachments import copy_document_attachment

    copied_attachments: list[DocumentAttachment] = []
    try:
        with transaction.atomic():
            if not source.is_template:
                raise PlacementConflict("The selected document is not a template.")
            resolved = resolve_document(source)
            if not resolved.placements:
                raise PlacementConflict("The template has no resolvable blocks.")
            rules = placement_rules or {}
            template_revision = (
                ensure_template_revision(source=source, actor_id=actor_id) if source.organization_id is None else None
            )
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
            def copied_markdown(markdown: str) -> str:
                for source_id, destination_id in replacements.items():
                    markdown = markdown.replace(
                        f"{_ATTACHMENT_TARGET}{source_id}",
                        f"{_ATTACHMENT_TARGET}{destination_id}",
                    )
                return markdown

            primary = resolved.placements[0]
            _template_rule(rules, primary.placement.block.entity_id, primary=True)
            destination = create_document(
                tenant=tenant,
                organization=organization,
                actor_id=actor_id,
                title=title,
                markdown=copied_markdown(primary.revision.markdown),
                category=category,
                is_template=False,
            )
            destination_primary = primary_placement(destination)
            placement_map: list[dict[str, object]] = [
                {
                    "source_block_id": str(primary.placement.block.entity_id),
                    "destination_block_id": str(destination_primary.block.entity_id),
                    "destination_placement_id": str(destination_primary.id),
                    "mode": "copy",
                    "applied_revision_id": str(primary.revision.id),
                }
            ]
            for item in resolved.placements[1:]:
                source_block = item.placement.block
                mode = _template_rule(rules, source_block.entity_id, primary=False)
                if mode in {"live", "pinned"}:
                    if not source.library_visible or not source_block.library_visible:
                        raise PlacementConflict(
                            "Live and pinned template blocks must be published to the client library."
                        )
                    if attachment_ids_in_markdown(item.revision.markdown):
                        raise PlacementConflict("Live and pinned template blocks cannot contain managed attachments.")
                    created_placement = add_block_placement(
                        document=destination,
                        block=source_block,
                        actor_id=actor_id,
                        resolution_mode=mode,
                        pinned_revision_id=item.revision.id if mode == "pinned" else None,
                        parent_id=None,
                    )
                    destination_block_id = source_block.entity_id
                else:
                    created_placement = create_document_block(
                        document=destination,
                        actor_id=actor_id,
                        markdown=copied_markdown(item.revision.markdown),
                        kind=source_block.kind,
                        name=source_block.entity.display_name,
                        parent_id=None,
                        position=None,
                    )
                    destination_block_id = created_placement.block.entity_id
                placement_map.append(
                    {
                        "source_block_id": str(source_block.entity_id),
                        "destination_block_id": str(destination_block_id),
                        "destination_placement_id": str(created_placement.id),
                        "mode": mode,
                        "applied_revision_id": str(item.revision.id),
                    }
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
                metadata={
                    "source_document_id": str(source.entity_id),
                    "template_revision": template_revision.revision_number if template_revision is not None else None,
                },
            )
            if organization is not None and template_revision is not None:
                DocumentTemplateEnrollment.objects.create(
                    tenant=tenant,
                    organization=organization,
                    source_template=source,
                    destination_document=destination,
                    applied_revision=template_revision,
                    placement_map=placement_map,
                    created_by_id=actor_id,
                    last_applied_by_id=actor_id,
                )
    except Exception:
        for copied in copied_attachments:
            copied.file.storage.delete(copied.file.name)
        raise
    return destination


def template_rollout_preview(
    *, enrollment: DocumentTemplateEnrollment, actor_id: UUID
) -> tuple[DocumentTemplateRevision, dict[str, object]]:
    latest = ensure_template_revision(source=enrollment.source_template, actor_id=actor_id)
    applied_blocks = {
        str(item["source_block_id"]): item
        for item in cast(list[dict[str, object]], enrollment.applied_revision.manifest.get("blocks", []))
    }
    latest_blocks = {
        str(item["source_block_id"]): item
        for item in cast(list[dict[str, object]], latest.manifest.get("blocks", []))
    }
    placement_modes = {
        str(item["source_block_id"]): str(item["mode"])
        for item in cast(list[dict[str, object]], enrollment.placement_map)
    }
    added = [value for key, value in latest_blocks.items() if key not in applied_blocks]
    removed = [value for key, value in applied_blocks.items() if key not in latest_blocks]
    changed = [
        {**latest_blocks[key], "mode": placement_modes.get(key, "copy")}
        for key in latest_blocks.keys() & applied_blocks.keys()
        if latest_blocks[key]["source_revision_id"] != applied_blocks[key]["source_revision_id"]
    ]
    conflicts = [
        {**item, "reason": "Copied client content is never overwritten automatically."}
        for item in changed
        if item["mode"] == "copy"
    ] + [
        {**item, "reason": "New template blocks with managed attachments require document re-instantiation."}
        for item in added
        if item.get("attachment_ids")
    ] + [{**item, "reason": "Template removal requires explicit client-document editing."} for item in removed]
    return latest, {
        "current_revision": enrollment.applied_revision.revision_number,
        "available_revision": latest.revision_number,
        "up_to_date": latest.id == enrollment.applied_revision_id,
        "added": added,
        "changed": changed,
        "removed": removed,
        "conflicts": conflicts,
    }


@transaction.atomic
def apply_template_rollout(
    *,
    enrollment: DocumentTemplateEnrollment,
    actor_id: UUID,
    expected_applied_revision_id: UUID,
    placement_rules: dict[str, str] | None = None,
) -> dict[str, object]:
    locked = DocumentTemplateEnrollment.objects.select_for_update().select_related(
        "source_template", "destination_document", "applied_revision"
    ).get(pk=enrollment.pk)
    if locked.applied_revision_id != expected_applied_revision_id:
        raise PlacementConflict("The client template enrollment changed after this preview loaded.")
    latest, preview = template_rollout_preview(enrollment=locked, actor_id=actor_id)
    if preview["conflicts"]:
        raise PlacementConflict("Resolve copied-block or removal conflicts before applying this rollout.")
    rules = placement_rules or {}
    placement_map = cast(list[dict[str, object]], list(locked.placement_map))
    map_by_source = {str(item["source_block_id"]): item for item in placement_map}
    latest_blocks = cast(list[dict[str, object]], latest.manifest["blocks"])
    for item in latest_blocks:
        source_id = str(item["source_block_id"])
        source_block = Block.objects.select_related("entity", "current_revision").get(
            tenant=locked.tenant, entity_id=source_id, archived_at__isnull=True
        )
        mapped = map_by_source.get(source_id)
        if mapped is None:
            mode = _template_rule(rules, source_block.entity_id, primary=False)
            if mode in {"live", "pinned"}:
                if not locked.source_template.library_visible or not source_block.library_visible:
                    raise PlacementConflict("Live and pinned template blocks must be published to the client library.")
                placement = add_block_placement(
                    document=locked.destination_document,
                    block=source_block,
                    actor_id=actor_id,
                    resolution_mode=mode,
                    pinned_revision_id=UUID(str(item["source_revision_id"])) if mode == "pinned" else None,
                    parent_id=None,
                )
                destination_block_id = source_block.entity_id
            else:
                revision = BlockRevision.objects.get(
                    id=UUID(str(item["source_revision_id"])), block=source_block
                )
                placement = create_document_block(
                    document=locked.destination_document,
                    actor_id=actor_id,
                    markdown=revision.markdown,
                    kind=source_block.kind,
                    name=source_block.entity.display_name,
                    parent_id=None,
                    position=None,
                )
                destination_block_id = placement.block.entity_id
            mapped = {
                "source_block_id": source_id,
                "destination_block_id": str(destination_block_id),
                "destination_placement_id": str(placement.id),
                "mode": mode,
                "applied_revision_id": str(item["source_revision_id"]),
            }
            placement_map.append(mapped)
            map_by_source[source_id] = mapped
        elif mapped["mode"] == "pinned" and mapped["applied_revision_id"] != item["source_revision_id"]:
            placement = DocumentPlacement.objects.get(id=UUID(str(mapped["destination_placement_id"])))
            update_document_placement(
                placement=placement,
                actor_id=actor_id,
                resolution_mode="pinned",
                pinned_revision_id=UUID(str(item["source_revision_id"])),
            )
            mapped["applied_revision_id"] = str(item["source_revision_id"])
        elif mapped["mode"] == "live":
            mapped["applied_revision_id"] = str(item["source_revision_id"])
    locked.applied_revision = latest
    locked.placement_map = placement_map
    locked.last_applied_by_id = actor_id
    locked.last_applied_at = timezone.now()
    locked.save(update_fields=("applied_revision", "placement_map", "last_applied_by", "last_applied_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.template_rollout_applied",
        entity_id=locked.destination_document.entity_id,
        metadata={"template_revision": latest.revision_number},
    )
    locked.refresh_from_db()
    _, applied_preview = template_rollout_preview(enrollment=locked, actor_id=actor_id)
    return applied_preview


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
    library_visible: bool = False,
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
        library_visible=library_visible,
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
    if source_document.pk == document.pk:
        raise PlacementConflict("A document cannot transclude its own primary block.")
    source = primary_placement(source_document)
    block = Block.objects.select_related("current_revision").get(pk=source.block_id)
    return add_block_placement(
        document=document,
        block=block,
        actor_id=actor_id,
        resolution_mode=resolution_mode,
        pinned_revision_id=pinned_revision_id,
        parent_id=parent_id,
        position=position,
    )


@transaction.atomic
def add_block_placement(
    *,
    document: Document,
    block: Block,
    actor_id: UUID,
    resolution_mode: str,
    pinned_revision_id: UUID | None,
    parent_id: UUID | None,
    position: int | None = None,
) -> DocumentPlacement:
    locked_document = Document.objects.select_for_update().get(pk=document.pk)
    if locked_document.placements.count() >= 500:
        raise PlacementConflict("Document composition cannot exceed 500 blocks.")
    block = (
        Block.objects.select_for_update(of=("self",))
        .select_related("current_revision")
        .get(pk=block.pk)
    )
    if block.tenant_id != locked_document.tenant_id or block.archived_at is not None:
        raise PlacementConflict("The selected block is unavailable in this installation.")
    if block.source_document_id == locked_document.id:
        raise PlacementConflict("A document cannot transclude one of its own blocks.")
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
