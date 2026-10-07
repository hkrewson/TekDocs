"""Read-only, deterministic inventory for the legacy-document migration.

This is a gate, not an importer. No legacy write is retired based on this report.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.db.models import Prefetch

from .document_migration_relationships import (
    DocumentMigrationRelationshipError,
    portable_document_entity_references,
)
from .document_migration_shape import DocumentMigrationShapeError, owned_placement_tree
from .document_migration_taxonomy import DocumentMigrationTaxonomyError, portable_document_taxonomies
from .document_template_models import DocumentTemplateEnrollment, DocumentTemplateRevision
from .models import (
    Block,
    ContentNode,
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    DocumentPlacement,
    DocumentPublication,
    Workspace,
    WorkspaceRepository,
)
from .topic_schemas import SCHEMA_VERSION, SCHEMAS


def inventory_legacy_documents(workspace: Workspace) -> dict[str, Any]:
    """Classify exact-owner records without reading Markdown or changing state."""

    owner = {"tenant_id": workspace.tenant_id, "organization_id": workspace.organization_id}
    repository = WorkspaceRepository.objects.filter(workspace=workspace).first()
    nodes = set(ContentNode.objects.filter(workspace=workspace).values_list("content_id", flat=True))
    placements = DocumentPlacement.objects.filter(**owner).select_related("block")
    documents = (
        Document.objects.filter(**owner)
        .order_by("id")
        .prefetch_related(Prefetch("placements", queryset=placements, to_attr="migration_placements"))
    )
    repository_blockers: list[str] = []
    if repository is None:
        repository_blockers.append("repository_missing")
    elif repository.accepted_commit_id != repository.indexed_commit_id:
        repository_blockers.append("repository_index_not_current")
    records: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for document in documents.iterator(chunk_size=200):
        document_placements = document.migration_placements
        block_ids = {placement.block_id for placement in document_placements}
        owned_block_ids = {
            placement.block_id for placement in document_placements if placement.block.source_document_id == document.id
        }
        referenced_block_ids = block_ids - owned_block_ids
        reasons: list[str] = []
        if document.id in nodes or owned_block_ids.intersection(nodes):
            reasons.append("git_identity_collision")
        if referenced_block_ids - nodes:
            reasons.append("cross_document_source_unavailable")
        if document.archived_at is not None:
            reasons.append("archived_document")
        if document.topic_type not in SCHEMAS:
            reasons.append("structured_topic_mapping_required")
        if document.topic_schema_version != SCHEMA_VERSION:
            reasons.append("topic_version_mapping_required")
        if (
            not isinstance(document.tags, list)
            or len(document.tags) > 64
            or not all(isinstance(tag, str) for tag in document.tags)
        ):
            reasons.append("legacy_tags_not_portable")
        if document.is_template or DocumentTemplateRevision.objects.filter(template=document).exists():
            reasons.append("template")
        if DocumentTemplateEnrollment.objects.filter(destination_document=document).exists():
            reasons.append("template_enrollment")
        try:
            owned_placement_tree(document, document_placements)
        except DocumentMigrationShapeError as exc:
            reasons.append(exc.reason)
        try:
            portable_document_taxonomies(document)
        except DocumentMigrationTaxonomyError:
            reasons.append("taxonomy_mapping_required")
        try:
            portable_document_entity_references(document)
        except DocumentMigrationRelationshipError:
            reasons.append("relationship_mapping_required")
        if DocumentAttachment.objects.filter(
            document=document,
            archived_at__isnull=True,
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
        ).exists():
            reasons.append("primary_file_parity_required")
        if DocumentPublication.objects.filter(document=document).exists():
            reasons.append("publication_parity_required")
        if Block.objects.filter(**owner, source_document=document).exclude(id__in=owned_block_ids).exists():
            reasons.append("unplaced_owned_block")
        disposition = "simple_candidate" if not reasons else "deferred"
        totals[disposition] += 1
        totals.update(reasons)
        records.append(
            {
                "document_id": str(document.id),
                "placement_count": len(document_placements),
                "disposition": disposition,
                "reasons": sorted(reasons),
            }
        )
    return {
        "workspace_id": str(workspace.id),
        "repository_id": str(repository.id) if repository else None,
        "repository_blockers": repository_blockers,
        "document_count": len(records),
        "counts": dict(sorted(totals.items())),
        "documents": records,
        "read_only": True,
    }
