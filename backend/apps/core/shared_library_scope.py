"""Exact retained-placement evidence for ordinary MSP library reuse.

This is a content boundary, not a grant to browse the source Workspace. Caller
authorization and source/consumer writes continue through the policy service.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from django.db import connection

from .library_source_descriptor import LibrarySourceDescriptor
from .models import BlockRevision, Document, DocumentPlacement, WorkspaceRepository


def ordinary_library_placements(document: Document) -> tuple[DocumentPlacement, ...]:
    """Return only explicitly shared, same-tenant MSP-to-client references."""
    if document.organization_id is None or document.archived_at is not None:
        return ()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.id FROM core_documentplacement p WHERE p.tenant_id=%s AND p.document_id=%s "
            "AND tekdocs_shared_library_placement_allowed(%s, p.id)",
            [document.tenant_id, document.id, document.tenant_id],
        )
        identities = [row[0] for row in cursor.fetchall()]
    return tuple(DocumentPlacement.objects.filter(
        tenant_id=document.tenant_id, organization_id=document.organization_id,
        document=document, id__in=identities,
    ).select_related(
        "block__current_revision", "block__source_document__entity", "pinned_revision",
    ).order_by("id"))


def ordinary_library_descriptor(
    *, tenant_id: UUID, destination_document_id: UUID, library_workspace_id: UUID, source_document_id: UUID,
    source_block_id: UUID, mode: str, audience: str, revision_id: UUID | None,
) -> LibrarySourceDescriptor:
    """Recheck the sharing proof before and after reading a single Git object."""
    from .publications import canonical_json
    from .repository_service import RepositoryInputError

    destination = Document.objects.filter(
        pk=destination_document_id, tenant_id=tenant_id, archived_at__isnull=True,
    ).first()
    if destination is None:
        raise RepositoryInputError("Shared library destination is unavailable")
    matches = [item for item in ordinary_library_placements(destination) if (
        item.block_id == source_block_id and item.block.source_document_id == source_document_id
        and item.block.source_document is not None
        and item.block.source_document.entity.workspace_id == library_workspace_id
        and item.resolution_mode == mode and item.audience_profile == audience
        and (mode != "pinned" or item.pinned_revision_id == revision_id)
    )]
    if not matches or (mode == "pinned" and (revision_id is None or not BlockRevision.objects.filter(
        pk=revision_id, tenant_id=destination.tenant_id, block_id=source_block_id,
    ).exists())) or (mode == "live" and revision_id is not None):
        raise RepositoryInputError("Shared library placement or revision is unavailable")
    revision = matches[0].pinned_revision if mode == "pinned" else matches[0].block.current_revision
    repository = WorkspaceRepository.objects.select_related("accepted_commit").filter(
        tenant_id=destination.tenant_id, workspace_id=library_workspace_id,
        workspace__organization__isnull=True, lifecycle_state="active",
    ).first()
    if revision is None or repository is None or repository.accepted_commit is None:
        raise RepositoryInputError("Shared library repository or revision is unavailable")
    if repository.accepted_commit_id != repository.indexed_commit_id:
        raise RepositoryInputError("Shared library index is not current")
    fingerprint = hashlib.sha256(canonical_json([
        (str(item.id), str(item.parent_id), item.position, item.resolution_mode,
         item.audience_profile, str(item.pinned_revision_id), str(item.block.current_revision_id))
        for item in matches
    ])).hexdigest()
    return LibrarySourceDescriptor(
        repository_id=repository.id, storage_relative_path=repository.storage_relative_path,
        accepted_commit=repository.accepted_commit.object_id,
        object_format=repository.accepted_commit.object_format, body_sha256=revision.checksum,
        scope_sha256=fingerprint, revision_id=revision.id,
    )
