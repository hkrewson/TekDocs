"""Bounded, exact accepted-head Markdown snapshot for staff editing handoff."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import deque
from dataclasses import dataclass
from uuid import UUID

from .content_composition import ContentCompositionError, ContentCompositionResolver
from .content_index import MAX_PINNED_HISTORY_BYTES, MAX_PINNED_SNAPSHOTS
from .content_profile import ContentProfileError, ParsedContent, parse_content
from .models import WorkspaceRepository
from .repository_service import (
    MAX_PINNED_SNAPSHOT_BYTES,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)

MAX_SOURCE_FILES = 250
MAX_SOURCE_INPUT_BYTES = 32 * 1024 * 1024
MAX_SOURCE_ZIP_BYTES = 20 * 1024 * 1024


class RepositorySourceExportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RepositorySourceExport:
    content: bytes
    accepted_commit: str
    file_count: int


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _parsed_sources(files: tuple[tuple[str, bytes], ...]) -> dict[UUID, tuple[str, bytes, ParsedContent]]:
    if len(files) > MAX_SOURCE_FILES:
        raise RepositorySourceExportError("A repository source commit exceeds the file limit.")
    identities: dict[UUID, tuple[str, bytes, ParsedContent]] = {}
    for path, source in files:
        parsed = parse_content(source)
        if (parsed.kind == "fragment") != path.startswith("fragments/") or parsed.content_id in identities:
            raise RepositorySourceExportError("Repository source placement or identity is invalid.")
        identities[parsed.content_id] = (path, source, parsed)
    return identities


class _HistoricalSources:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository
        self.snapshots: dict[str, dict[UUID, tuple[str, bytes, ParsedContent]]] = {}
        self.loaded_bytes = 0

    def load(self, object_id: str) -> dict[UUID, ParsedContent]:
        if object_id not in self.snapshots:
            if len(self.snapshots) >= MAX_PINNED_SNAPSHOTS:
                raise RepositorySourceExportError("The snapshot has too many historical commits.")
            commit, files = read_repository_markdown_files_at_commit(
                repository_id=self.repository.id, object_id=object_id
            )
            if commit.object_id != object_id:
                raise RepositorySourceExportError("A historical source commit changed during export.")
            self.loaded_bytes += sum(len(source) for _path, source in files)
            if self.loaded_bytes > MAX_PINNED_HISTORY_BYTES:
                raise RepositorySourceExportError("Historical source exceeds the read limit.")
            self.snapshots[object_id] = _parsed_sources(files)
        return {content_id: item[2] for content_id, item in self.snapshots[object_id].items()}


def export_repository_sources(repository: WorkspaceRepository) -> RepositorySourceExport:
    """Package current files and reachable Markdown source dependencies, never a backup."""

    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    if repository.accepted_commit_id is None or repository.indexed_commit_id != repository.accepted_commit_id:
        raise RepositorySourceExportError("The accepted repository content is not fully indexed.")
    commit, sources = read_accepted_repository_markdown_files(
        repository_id=repository.id, max_files=MAX_SOURCE_FILES, max_bytes=MAX_PINNED_SNAPSHOT_BYTES
    )
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    if repository.accepted_commit_id != commit.id or repository.indexed_commit_id != commit.id:
        raise RepositorySourceExportError("The accepted repository content changed during export.")
    files: dict[str, bytes] = {}
    manifest_files: list[dict[str, str]] = []
    historical_files: list[dict[str, str | list[str]]] = []
    try:
        accepted = _parsed_sources(sources)
        history = _HistoricalSources(repository)
        accepted_parsed = {content_id: item[2] for content_id, item in accepted.items()}

        def load_snapshot(object_id: str) -> dict[UUID, ParsedContent]:
            return accepted_parsed if object_id == commit.object_id else history.load(object_id)

        resolver = ContentCompositionResolver(
            accepted_object_id=commit.object_id,
            accepted=accepted_parsed,
            loader=load_snapshot,
        )
        historical_roles: dict[tuple[str, UUID], set[str]] = {}
        pending: deque[tuple[str, UUID]] = deque()

        def add_reference(object_id: str, content_id: UUID, role: str, *, fragment_only: bool = False) -> None:
            target = load_snapshot(object_id).get(content_id)
            if target is None or (fragment_only and target.kind != "fragment"):
                raise RepositorySourceExportError("A referenced Markdown source is unavailable or invalid.")
            if object_id == commit.object_id:
                return
            key = (object_id, content_id)
            if key not in historical_roles:
                if len(sources) + len(historical_roles) >= MAX_SOURCE_FILES:
                    raise RepositorySourceExportError("The repository source snapshot exceeds the file limit.")
                historical_roles[key] = set()
                pending.append(key)
            historical_roles[key].add(role)

        def add_provenance(parsed: ParsedContent) -> None:
            if parsed.derived_from is not None:
                if parsed.derived_from.content_id == parsed.content_id:
                    raise RepositorySourceExportError("Copy provenance cannot refer to the same content identity.")
                add_reference(
                    parsed.derived_from.object_id,
                    parsed.derived_from.content_id,
                    "derived_from",
                    fragment_only=True,
                )
            for source in parsed.template_sources:
                add_reference(source.object_id, source.content_id, "template_source")

        for content_id in sorted(accepted, key=str):
            for dependency in resolver.resolve(content_id=content_id, audience=None).manifest:
                add_reference(str(dependency["commit"]), UUID(str(dependency["id"])), "include", fragment_only=True)
            add_provenance(accepted[content_id][2])
        while pending:
            object_id, content_id = pending.popleft()
            parsed = load_snapshot(object_id)[content_id]
            historical_resolver = ContentCompositionResolver(
                accepted_object_id=object_id,
                accepted=load_snapshot(object_id),
                loader=load_snapshot,
            )
            for dependency in historical_resolver.resolve(content_id=content_id, audience=None).manifest:
                add_reference(str(dependency["commit"]), UUID(str(dependency["id"])), "include", fragment_only=True)
            add_provenance(parsed)
        total_bytes = sum(len(source) for _path, source in sources)
        for content_id in sorted(accepted, key=str):
            path, source, parsed = accepted[content_id]
            exported_path = f"repository/{path}"
            files[exported_path] = source
            manifest_files.append(
                {
                    "path": exported_path,
                    "content_id": str(parsed.content_id),
                    "kind": parsed.kind,
                    "sha256": hashlib.sha256(source).hexdigest(),
                }
            )
        for object_id, content_id in sorted(historical_roles, key=lambda item: (item[0], str(item[1]))):
            path, source, parsed = history.snapshots[object_id][content_id]
            total_bytes += len(source)
            if total_bytes > MAX_SOURCE_INPUT_BYTES:
                raise RepositorySourceExportError("The repository source snapshot exceeds the byte limit.")
            exported_path = f"pinned/{object_id}/{path}"
            files[exported_path] = source
            historical_files.append(
                {
                    "path": exported_path,
                    "source_path": path,
                    "commit": object_id,
                    "content_id": str(parsed.content_id),
                    "kind": parsed.kind,
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "roles": sorted(historical_roles[(object_id, content_id)]),
                }
            )
    except RepositorySourceExportError:
        raise
    except (ContentProfileError, ContentCompositionError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise RepositorySourceExportError("The accepted repository source is invalid.") from exc
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    if repository.accepted_commit_id != commit.id or repository.indexed_commit_id != commit.id:
        raise RepositorySourceExportError("The accepted repository content changed during export.")
    manifest = {
        "format": "tekdocs-repository-source-snapshot/v3",
        "workspace_id": str(repository.workspace_id),
        "accepted_commit": commit.object_id,
        "object_format": commit.object_format,
        "scope": "current-files-and-reachable-markdown-dependencies",
        "exclusions": ["attachment_bytes", "database_records", "git_history"],
        "files": manifest_files,
        "historical_files": historical_files,
    }
    files["tekdocs-source.json"] = _json(manifest)
    files["README.md"] = (
        b"# TekDocs repository source snapshot\n\n"
        b"This contains exact current Markdown files and reachable include, template-source, "
        b"and copy-provenance history. It is not sanitized; review source before sharing. "
        b"Attachments, database records and Git history are excluded. "
        b"This is not a complete dependency bundle or backup.\n"
    )
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, files[path])
    content = target.getvalue()
    if len(content) > MAX_SOURCE_ZIP_BYTES:
        raise RepositorySourceExportError("The repository source snapshot exceeds 20 MiB.")
    return RepositorySourceExport(
        content=content, accepted_commit=commit.object_id, file_count=len(sources) + len(historical_files)
    )
