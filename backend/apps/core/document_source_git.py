"""Reviewed monitored updates through the coordinated Git authoring boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any, cast
from uuid import UUID

from .content_authoring import AuthoredContent, ContentAuthoringError, author_content, read_authored_content
from .document_authority_handoff import prepare_rollback_markdown_projection
from .document_migration_publications import publication_migration_actor_allowed
from .document_source_models import DocumentRemoteObservation, DocumentRemoteSource
from .document_source_state import MonitoredSourceStateError, monitored_source_fingerprint
from .documents import PlacementConflict, primary_placement
from .models import AuditEvent, Document, DocumentAuthority, WorkspaceRepository
from .repository_service import (
    RepositoryServiceError,
    _active_repository_transaction,
    coordinated_repository_transaction,
)


@contextmanager
def locked_remote_source(
    source_id: UUID,
) -> Iterator[tuple[DocumentRemoteSource, Document, WorkspaceRepository | None]]:
    """Use the handoff lock order: repository, document, then source workflow."""
    original = DocumentRemoteSource.objects.select_related("document__entity").get(pk=source_id)
    repository = WorkspaceRepository.objects.filter(
        workspace_id=original.document.entity.workspace_id, tenant_id=original.tenant_id,
    ).first()
    with coordinated_repository_transaction():
        active = _active_repository_transaction()
        if active is None:
            raise PlacementConflict("The coordinated source update is unavailable.")
        if repository is not None:
            # Acquire the Git lock without requiring a Git mutation. Legacy
            # apply remains SQL-nestable; the authoring writer enforces outer
            # transaction ownership if dispatch actually reaches a Git write.
            active.enlist(repository.id, write=False)
            repository = WorkspaceRepository.objects.select_for_update().get(pk=repository.id)
        document = Document.objects.select_for_update(of=("self",)).select_related("entity__workspace").get(
            pk=original.document_id, tenant_id=original.tenant_id, organization_id=cast(UUID, original.organization_id),
        )
        source = DocumentRemoteSource.objects.select_for_update().get(pk=source_id, document=document)
        if document.archived_at is not None or source.archived_at is not None:
            raise PlacementConflict("The monitored document is unavailable.")
        yield source, document, repository


def source_uses_git(source: DocumentRemoteSource) -> bool:
    return DocumentAuthority.objects.filter(
        tenant_id=source.tenant_id, workspace_id=source.document.entity.workspace_id,
        content_id=source.document_id, authority="repository",
    ).exists()


@dataclass(frozen=True)
class _SourceReviewSnapshot:
    fingerprint: str
    authored: AuthoredContent
    prior_markdown: str | None


def _source_review_snapshot(
    source: DocumentRemoteSource, document: Document, repository: WorkspaceRepository | None,
) -> _SourceReviewSnapshot:
    if (
        repository is None or repository.accepted_commit_id is None
        or repository.indexed_commit_id != repository.accepted_commit_id or not source_uses_git(source)
    ):
        raise PlacementConflict("The Git-backed document is unavailable or its index is not current.")
    state = monitored_source_fingerprint(document)
    placement = primary_placement(document)
    if placement.block.source_document_id != document.id or placement.resolution_mode != "live":
        raise PlacementConflict("The source update requires an owned, live primary section.")
    projection = prepare_rollback_markdown_projection(workspace=document.entity.workspace, document=document)
    if placement.block.current_revision is None:
        raise PlacementConflict("The primary section is unavailable.")
    authored = read_authored_content(repository=repository, content_id=placement.block_id)
    if authored.kind != "fragment" or authored.markdown != projection.get(
        placement.block_id, placement.block.current_revision.markdown,
    ):
        raise PlacementConflict("The primary section is unavailable.")
    prior = source.last_applied_observation
    fingerprint = hashlib.sha256(json.dumps({
        "source_state": state, "document": str(document.id),
        "fragment": str(placement.block_id), "commit": authored.accepted_commit,
        "blob": authored.source_blob, "authority": [
            (str(identity), mode, changed.isoformat())
            for identity, mode, changed in DocumentAuthority.objects.filter(
                tenant_id=source.tenant_id, workspace_id=document.entity.workspace_id,
                content_id__in=(document.id, placement.block_id),
            ).order_by("content_id").values_list("content_id", "authority", "updated_at")
        ],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return _SourceReviewSnapshot(fingerprint, authored, prior.canonical_markdown if prior else None)


def _observation_review(snapshot: _SourceReviewSnapshot, observation: DocumentRemoteObservation) -> dict[str, Any]:
    if observation.state == "failed" or not observation.canonical_markdown:
        raise PlacementConflict("Only a successful retained source observation can be applied.")
    authored = snapshot.authored
    local_changes = authored.markdown != observation.canonical_markdown and (
        snapshot.prior_markdown is None or authored.markdown != snapshot.prior_markdown
    )
    return {
        "fingerprint": hashlib.sha256(f"{snapshot.fingerprint}:{observation.id}".encode()).hexdigest(),
        "blocker": "local_edits_require_integration" if local_changes else "",
        "diff": "".join(unified_diff(
            authored.markdown.splitlines(keepends=True), observation.canonical_markdown.splitlines(keepends=True),
            fromfile="current-document", tofile="observed",
        )),
    }


def preview_remote_observation(*, observation: DocumentRemoteObservation) -> dict[str, Any] | None:
    return preview_remote_observations(source=observation.source, observations=[observation])[observation.id]


def preview_remote_observations(
    *, source: DocumentRemoteSource, observations: list[DocumentRemoteObservation],
) -> dict[UUID, dict[str, Any] | None]:
    if not source_uses_git(source):
        return {item.id: None for item in observations}
    unavailable = {"fingerprint": "", "blocker": "source_review_unavailable", "diff": ""}
    try:
        with locked_remote_source(source.id) as (locked, document, repository):
            snapshot = _source_review_snapshot(locked, document, repository)
            retained = {item.id: item for item in locked.observations.filter(id__in=[item.id for item in observations])}
            result: dict[UUID, dict[str, Any] | None] = {}
            for item in observations:
                try:
                    result[item.id] = _observation_review(snapshot, retained[item.id])
                except (PlacementConflict, KeyError):
                    result[item.id] = unavailable
            return result
    except (PlacementConflict, MonitoredSourceStateError, RepositoryServiceError, ValueError):
        return {item.id: unavailable for item in observations}


def apply_git_observation(
    *, source: DocumentRemoteSource, document: Document, repository: WorkspaceRepository | None,
    observation: DocumentRemoteObservation, actor_id: UUID, review_fingerprint: str | None,
) -> None:
    if not publication_migration_actor_allowed(workspace=document.entity.workspace, actor_id=actor_id):
        raise PlacementConflict("Source changes require permission to edit this Workspace.")
    try:
        retained = source.observations.get(pk=observation.id)
        snapshot = _source_review_snapshot(source, document, repository)
        review = _observation_review(snapshot, retained)
        authored = snapshot.authored
        if not review_fingerprint or review_fingerprint != review["fingerprint"]:
            raise PlacementConflict("The source or document changed after review. Close and reopen Web source.")
        if review["blocker"]:
            raise PlacementConflict(
                "Local edits must be integrated in the document editor before applying this source."
            )
        if repository is None:
            raise PlacementConflict("The Git-backed document is unavailable.")
        result = author_content(
            repository=repository, actor_id=actor_id, request_id=None, operation="update",
            content_id=authored.content_id, base_commit=authored.accepted_commit, base_blob=authored.source_blob,
            kind=None, path=None, title=None, markdown=retained.canonical_markdown, metadata_patch={},
        )
        if result.accepted_commit != result.indexed_commit or result.markdown != retained.canonical_markdown:
            raise PlacementConflict("The updated document could not be verified. Review it again.")
    except (MonitoredSourceStateError, ContentAuthoringError, RepositoryServiceError, ValueError) as exc:
        raise PlacementConflict("The source update is unavailable. Review the document and source again.") from exc
    source.last_applied_observation = retained
    source.save(update_fields=("last_applied_observation", "updated_at"))
    AuditEvent.objects.create(
        tenant=source.tenant, actor_id=actor_id, action="document.remote_source_applied",
        entity_id=document.entity_id,
        metadata={"observation_id": str(retained.id), "commit": result.accepted_commit},
    )
