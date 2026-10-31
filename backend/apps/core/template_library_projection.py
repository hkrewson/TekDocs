"""Verified Git bytes projected into immutable template workflow revisions."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from .content_profile import ParsedContent, parse_content
from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentAuthority,
    RepositoryCommit,
    RepositoryCommitAudit,
    WorkspaceRepository,
)

if TYPE_CHECKING:
    from .document_migration_export import SimpleDocumentExport


@dataclass(slots=True)
class _ProjectionRead:
    document_id: UUID
    thread_id: int
    active: bool = True


_projection_read: ContextVar[_ProjectionRead | None] = ContextVar("tekdocs_template_projection_read", default=None)


def _cached_export(document: Document) -> SimpleDocumentExport:
    from .document_migration_export import build_simple_document_export

    lease = _ProjectionRead(document.id, threading.get_ident())
    token = _projection_read.set(lease)
    try:
        return build_simple_document_export(document, allow_repository_divergence=True)
    finally:
        lease.active = False
        _projection_read.reset(token)


def verify_template_source_projection(document: Document) -> None:
    """A workflow cache is readable only while actual accepted Git proves it."""
    from .documents import PlacementConflict
    from .repository_service import RepositoryServiceError, read_accepted_repository_file

    lease = _projection_read.get()
    if (
        lease is not None
        and lease.active
        and (lease.thread_id, lease.document_id) == (threading.get_ident(), document.id)
    ):
        return
    if not Document.objects.filter(pk=document.pk, tenant_id=document.tenant_id).exists():
        raise PlacementConflict("The template source is unavailable in this Workspace.")
    if not DocumentAuthority.objects.filter(
        workspace_id=document.entity.workspace_id,
        tenant_id=document.tenant_id,
        content_id=document.id,
        authority="repository",
    ).exists():
        return
    repository = WorkspaceRepository.objects.select_related("accepted_commit").get(
        tenant_id=document.tenant_id,
        workspace_id=document.entity.workspace_id,
    )
    if repository.accepted_commit is None or repository.indexed_commit_id != repository.accepted_commit_id:
        raise PlacementConflict("The Git-backed template source is not current. Retry after indexing.")
    try:
        expected = _cached_export(document)
        for path, source in expected.files:
            actual = read_accepted_repository_file(
                repository_id=repository.id,
                path=path,
                expected_commit=repository.accepted_commit.object_id,
            )
            if parse_content(actual).content_digest != parse_content(source).content_digest:
                raise ValueError("template cache differs")
    except (RepositoryServiceError, ValueError) as exc:
        raise PlacementConflict(
            "The Git-backed template source is unavailable or changed. Retry after indexing."
        ) from exc


def project_template_source_content(
    *,
    repository: WorkspaceRepository,
    commit: RepositoryCommit,
    parsed_by_path: dict[str, ParsedContent],
) -> None:
    """Run inside the index transaction, using its already verified snapshot."""
    from .content_index import ContentIndexError
    from .document_reversible_writes import ReversibleShapeError
    from .documents import _append_block_revision

    if repository.workspace.organization_id is not None:
        return
    roots = DocumentAuthority.objects.filter(
        workspace_id=repository.workspace_id,
        tenant_id=repository.tenant_id,
        authority="repository",
    ).values("content_id")
    sources = (
        Document.objects.select_for_update(of=("self",))
        .filter(
            tenant_id=repository.tenant_id,
            organization__isnull=True,
            entity__workspace_id=repository.workspace_id,
            id__in=roots,
            is_template=True,
        )
        .select_related("entity")
        .order_by("id")
    )
    actual = {path: parsed for path, parsed in parsed_by_path.items()}
    for source in sources:
        expected = _cached_export(source)
        # Compare semantic frontmatter and body, without rereading Git while the
        # index owns its database row lock. Current filenames are fixed by import.
        try:
            expected_parsed = {path: parse_content(value) for path, value in expected.files}
            if not set(expected_parsed).issubset(actual):
                raise ReversibleShapeError("template source paths changed")
            for path, before in expected_parsed.items():
                after = actual[path]
                if before.frontmatter != after.frontmatter or (
                    before.kind == "document" and before.markdown != after.markdown
                ):
                    raise ReversibleShapeError("template source metadata changed")
            changed = {
                before.content_id: actual[path].markdown
                for path, before in expected_parsed.items()
                if before.kind == "fragment" and before.markdown != actual[path].markdown
            }
        except ReversibleShapeError as exc:
            raise ContentIndexError("Template source projection requires its retained owner graph") from exc
        if not changed:
            continue
        attribution = (
            RepositoryCommitAudit.objects.select_related("audit_event")
            .filter(
                repository=repository,
                commit=commit,
                tenant_id=repository.tenant_id,
            )
            .first()
        )
        if attribution is None or attribution.audit_event.actor_id is None:
            raise ContentIndexError("Template source edit requires retained actor attribution")
        revisions = []
        for block in (
            Block.objects.select_for_update()
            .filter(
                tenant_id=repository.tenant_id,
                organization__isnull=True,
                source_document=source,
                id__in=changed,
            )
            .order_by("id")
        ):
            if block.current_revision_id is None:
                raise ContentIndexError("Template source revision is unavailable")
            revised = _append_block_revision(
                block=block,
                actor_id=attribution.audit_event.actor_id,
                markdown=changed[block.id],
                base_revision_id=block.current_revision_id,
            )
            revisions.append(str(revised.id))
        if len(revisions) != len(changed):
            raise ContentIndexError("Template source ownership is unavailable")
        AuditEvent.objects.create(
            tenant_id=repository.tenant_id,
            actor_id=attribution.audit_event.actor_id,
            action="document.template_git_snapshot_projected",
            entity_id=source.entity_id,
            metadata={"commit": commit.object_id, "block_revision_ids": revisions, "derived_from_git": True},
        )
