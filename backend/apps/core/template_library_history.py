"""Resumable custody preparation for immutable, previously applied template versions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

import yaml

from .content_index import ContentIndexError, index_repository_content
from .content_profile import parse_content
from .document_migration_publications import publication_migration_actor_allowed
from .document_template_migration import TemplateMigrationError
from .document_template_models import DocumentTemplateRevision
from .models import BlockRevision, Document, WorkspaceRepository
from .publications import canonical_json
from .repository_service import (
    MAX_COMMIT_BYTES,
    MAX_COMMIT_PATHS,
    MAX_FILE_BYTES,
    RepositoryAuditAttribution,
    RepositoryFileNotFoundError,
    commit_repository_files,
    read_accepted_repository_file,
)

MAX_TEMPLATE_HISTORY_FILES = 4096
MAX_TEMPLATE_HISTORY_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TemplateHistoryPlan:
    base_commit: str
    revision_ids: tuple[UUID, ...]
    files: tuple[tuple[str, bytes], ...]
    missing_paths: tuple[str, ...]
    plan_sha256: str

    @property
    def already_present(self) -> bool:
        return not self.missing_paths


@dataclass(frozen=True, slots=True)
class TemplateHistoryRetentionResult:
    commit: str
    indexed: bool


def template_history_files(source: Document) -> tuple[tuple[UUID, ...], tuple[tuple[str, bytes], ...]]:
    if (
        source.organization_id is not None
        or not source.is_template
        or source.archived_at is not None
        or source.entity.workspace.tenant_id != source.tenant_id
        or source.entity.workspace.organization_id is not None
    ):
        raise TemplateMigrationError("template_source_unavailable")
    files: list[tuple[str, bytes]] = []
    revisions = list(DocumentTemplateRevision.objects.filter(template=source).order_by("revision_number"))
    if not revisions:
        raise TemplateMigrationError("template_revision_invalid")
    for revision in revisions:
        manifest = revision.manifest
        if (
            not isinstance(manifest, dict)
            or revision.tenant_id != source.tenant_id
            or hashlib.sha256(canonical_json(manifest)).hexdigest() != revision.checksum
            or manifest.get("template_document_id") != str(source.entity_id)
            or not isinstance(manifest.get("blocks"), list)
            or not 1 <= len(manifest["blocks"]) <= 500
        ):
            raise TemplateMigrationError("template_revision_invalid")
        prefix = f"template-snapshots/{revision.id}"
        files.append((f"{prefix}/manifest.json", canonical_json(manifest)))
        seen: set[UUID] = set()
        try:
            for item in manifest["blocks"]:
                source_id = UUID(item["source_block_id"])
                if source_id in seen:
                    raise ValueError
                seen.add(source_id)
                retained = BlockRevision.objects.select_related("block").get(
                    id=UUID(item["source_revision_id"]),
                    tenant_id=source.tenant_id,
                    block__source_document=source,
                    block__entity_id=source_id,
                )
                if (
                    retained.checksum != item["checksum"]
                    or hashlib.sha256(retained.markdown.encode()).hexdigest() != retained.checksum
                ):
                    raise ValueError
                frontmatter = {
                    "schema": "tekdocs.content/v1",
                    "id": str(retained.block_id),
                    "kind": "fragment",
                    "title": item["name"],
                }
                encoded = (
                    "---\n"
                    + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
                    + "---\n"
                    + retained.markdown
                ).encode()
                parsed = parse_content(encoded)
                if hashlib.sha256(parsed.markdown.encode()).hexdigest() != retained.checksum:
                    raise ValueError
                files.append((f"{prefix}/fragments/{retained.block_id}.content", encoded))
        except (KeyError, TypeError, ValueError, BlockRevision.DoesNotExist) as exc:
            raise TemplateMigrationError("template_revision_invalid") from exc
        if len(files) > MAX_TEMPLATE_HISTORY_FILES:
            raise TemplateMigrationError("template_history_resource_limit")
    if (
        any(len(value) > MAX_FILE_BYTES for _path, value in files)
        or sum(len(value) for _path, value in files) > MAX_TEMPLATE_HISTORY_BYTES
    ):
        raise TemplateMigrationError("template_history_resource_limit")
    return tuple(item.id for item in revisions), tuple(sorted(files))


def prepare_template_library_history(*, source: Document, actor_id: UUID) -> TemplateHistoryPlan:
    repository = WorkspaceRepository.objects.select_related("accepted_commit").get(
        tenant_id=source.tenant_id,
        workspace_id=source.entity.workspace_id,
    )
    if not publication_migration_actor_allowed(workspace=source.entity.workspace, actor_id=actor_id):
        raise TemplateMigrationError("template_migration_not_authorized")
    revisions, files = template_history_files(source)
    if repository.accepted_commit is None:
        raise TemplateMigrationError("template_library_repository_unavailable")
    base = repository.accepted_commit.object_id
    missing = []
    for path, expected in files:
        try:
            current = read_accepted_repository_file(repository_id=repository.id, path=path, expected_commit=base)
        except RepositoryFileNotFoundError:
            missing.append(path)
        else:
            if current != expected:
                raise TemplateMigrationError("template_history_destination_conflict")
    payload = {
        "source": str(source.id),
        "actor": str(actor_id),
        "base": base,
        "files": [(path, hashlib.sha256(value).hexdigest()) for path, value in files],
    }
    return TemplateHistoryPlan(
        base, revisions, files, tuple(missing), hashlib.sha256(canonical_json(payload)).hexdigest()
    )


def retain_template_library_history(
    *,
    source: Document,
    actor_id: UUID,
    plan_sha256: str,
) -> TemplateHistoryRetentionResult:
    plan = prepare_template_library_history(source=source, actor_id=actor_id)
    if plan.plan_sha256 != plan_sha256:
        raise TemplateMigrationError("preview_changed")
    repository = source.entity.workspace.repository
    commit = plan.base_commit
    remaining = [(path, value) for path, value in plan.files if path in plan.missing_paths]
    # Historical additions never replace current authored paths. An interrupted
    # batch can be reviewed and resumed without discarding retained custody.
    while remaining:
        batch: dict[str, bytes] = {}
        total = 0
        while remaining and len(batch) < MAX_COMMIT_PATHS and total + len(remaining[0][1]) <= MAX_COMMIT_BYTES:
            path, value = remaining.pop(0)
            batch[path] = value
            total += len(value)
        result = commit_repository_files(
            repository_id=repository.id,
            expected_base=commit,
            changes=batch,
            message=f"Retain template history {source.id}",
            attribution=RepositoryAuditAttribution(actor_id=actor_id, action="content.template_history_retained"),
        )
        commit = result.object_id
    try:
        index_repository_content(repository_id=repository.id)
    except ContentIndexError:
        return TemplateHistoryRetentionResult(commit, False)
    return TemplateHistoryRetentionResult(commit, True)
