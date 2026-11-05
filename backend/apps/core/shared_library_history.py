"""Reviewed Git custody for immutable ordinary-library block revisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

import yaml

from .content_index import index_repository_content
from .document_migration_publications import publication_migration_actor_allowed
from .document_template_migration import TemplateMigrationError
from .models import BlockRevision, Document, WorkspaceRepository
from .publications import canonical_json
from .repository_service import (
    MAX_COMMIT_BYTES,
    MAX_COMMIT_PATHS,
    MAX_FILE_BYTES,
    RepositoryAuditAttribution,
    RepositoryFileNotFoundError,
    commit_repository_files,
    coordinated_repository_transaction,
    read_accepted_repository_file,
)


@dataclass(frozen=True, slots=True)
class SharedLibraryHistoryPlan:
    base_commit: str
    files: tuple[tuple[str, bytes], ...]
    missing_paths: tuple[str, ...]
    plan_sha256: str


def prepare_shared_library_history(*, source: Document, actor_id: UUID) -> SharedLibraryHistoryPlan:
    workspace = source.entity.workspace
    if not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id):
        raise TemplateMigrationError("library_migration_not_authorized")
    if (source.tenant_id != workspace.tenant_id or source.organization_id is not None
        or source.archived_at is not None):
        raise TemplateMigrationError("library_source_unavailable")
    repository = WorkspaceRepository.objects.select_related("accepted_commit").get(
        tenant_id=source.tenant_id, workspace=workspace,
    )
    if repository.accepted_commit is None or repository.accepted_commit_id != repository.indexed_commit_id:
        raise TemplateMigrationError("repository_not_current")
    revisions = list(BlockRevision.objects.filter(
        tenant_id=source.tenant_id, organization__isnull=True, block__source_document=source,
    ).order_by("id")[:4097])
    if not revisions or len(revisions) > 4096:
        raise TemplateMigrationError("library_history_resource_limit")
    files = []
    total = 0
    for revision in revisions:
        if hashlib.sha256(revision.markdown.encode()).hexdigest() != revision.checksum:
            raise TemplateMigrationError("library_revision_invalid")
        source_bytes = ("---\n" + yaml.safe_dump({
            "schema": "tekdocs.content/v1", "id": str(revision.block_id),
            "kind": "fragment", "title": "Retained shared block",
        }, sort_keys=False) + "---\n" + revision.markdown).encode()
        total += len(source_bytes)
        if len(source_bytes) > MAX_FILE_BYTES or total > 64 * 1024 * 1024:
            raise TemplateMigrationError("library_history_resource_limit")
        files.append((f"shared-snapshots/{revision.id}/fragments/{revision.block_id}.content", source_bytes))
    if source.is_template:
        from .template_library_history import template_history_files

        _revisions, template_files = template_history_files(source)
        files.extend(template_files)
        if len(files) > 4096 or sum(len(value) for _path, value in files) > 64 * 1024 * 1024:
            raise TemplateMigrationError("library_history_resource_limit")
    base = repository.accepted_commit.object_id
    missing = []
    for path, expected in files:
        try:
            actual = read_accepted_repository_file(repository_id=repository.id, path=path, expected_commit=base)
        except RepositoryFileNotFoundError:
            missing.append(path)
        else:
            if actual != expected:
                raise TemplateMigrationError("library_history_destination_conflict")
    payload = {
        "source": str(source.id), "actor": str(actor_id), "base": base,
        "files": [(path, hashlib.sha256(value).hexdigest()) for path, value in files],
    }
    return SharedLibraryHistoryPlan(base, tuple(sorted(files)), tuple(sorted(missing)),
                                    hashlib.sha256(canonical_json(payload)).hexdigest())


def retain_shared_library_history(*, source: Document, actor_id: UUID, plan_sha256: str) -> str:
    """Add archives only; never replace current content with old bodies."""
    with coordinated_repository_transaction():
        plan = prepare_shared_library_history(source=source, actor_id=actor_id)
        if plan.plan_sha256 != plan_sha256:
            raise TemplateMigrationError("preview_changed")
        repository = source.entity.workspace.repository
        remaining = [(path, value) for path, value in plan.files if path in plan.missing_paths]
        commit = plan.base_commit
        while remaining:
            batch: dict[str, bytes] = {}
            total = 0
            while remaining and len(batch) < MAX_COMMIT_PATHS and total + len(remaining[0][1]) <= MAX_COMMIT_BYTES:
                path, value = remaining.pop(0)
                batch[path] = value
                total += len(value)
            result = commit_repository_files(
                repository_id=repository.id, expected_base=commit, changes=batch,
                message="Retain reviewed shared-library revisions",
                attribution=RepositoryAuditAttribution(actor_id=actor_id, action="content.shared_history_retained"),
            )
            commit = result.object_id
        index_repository_content(repository_id=repository.id)
        return commit
