"""Read one permission-checked content-key target from current accepted Git."""

from __future__ import annotations

import hashlib
from typing import cast
from uuid import UUID

from .content_authoring import ContentAuthoringError, read_authored_content
from .document_key_resolution import (
    KeyResolutionKind,
    ResolutionState,
    ResolvedKey,
    UnresolvableReason,
    ValueProvenance,
)
from .models import Block, ContentNode, Entity, WorkspaceRepository
from .repository_service import RepositoryServiceError


def resolve_repository_content_key(
    *, repository: WorkspaceRepository, entity: Entity, expression: str,
) -> ResolvedKey:
    """Caller authorizes the Entity first; SQL supplies identity, never block text."""
    unavailable = ResolvedKey(
        expression=expression, state=ResolutionState.UNRESOLVABLE,
        label="Content", reason=UnresolvableReason.NOT_ADDRESSABLE,
    )
    commit = repository.accepted_commit
    if (
        entity.tenant_id != repository.tenant_id
        or entity.workspace_id != repository.workspace_id
        or entity.organization_id != repository.workspace.organization_id
        or entity.archived_at is not None
        or commit is None
        or repository.accepted_commit_id != repository.indexed_commit_id
    ):
        return unavailable
    block = Block.objects.filter(
        entity=entity, tenant_id=repository.tenant_id,
        organization_id=cast(UUID, repository.workspace.organization_id), archived_at__isnull=True,
        source_document__entity__workspace_id=repository.workspace_id,
        source_document__archived_at__isnull=True,
    ).only("id").first()
    if block is None:
        return unavailable
    try:
        authored = read_authored_content(repository=repository, content_id=block.id)
    except (ContentAuthoringError, RepositoryServiceError):
        return unavailable
    if (
        authored.kind != "fragment"
        or authored.accepted_commit != commit.object_id
        or authored.indexed_commit != authored.accepted_commit
        or not authored.markdown.strip()
        or not ContentNode.objects.filter(
            repository=repository, workspace_id=repository.workspace_id,
            content_id=block.id, kind="fragment", indexed_commit=commit,
            source_path=authored.path, markdown=authored.markdown,
        ).exists()
    ):
        return unavailable
    return ResolvedKey(
        expression=expression, state=ResolutionState.RESOLVED, label="Content",
        kind=KeyResolutionKind.CONTENT, value=authored.markdown,
        provenance=ValueProvenance.LOCAL, source_entity_id=entity.id,
        source_entity_type=entity.entity_type,
        source_fingerprint=hashlib.sha256(authored.markdown.encode()).hexdigest(),
        source_state_at=commit.created_at,
        source_git={
            "content_id": str(block.id), "workspace_id": str(repository.workspace_id),
            "repository_id": str(repository.id), "commit": authored.accepted_commit,
            "object_format": commit.object_format, "blob": authored.source_blob,
            "path": authored.path, "source": authored.source,
        },
    )
