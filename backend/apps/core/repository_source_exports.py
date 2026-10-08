"""Bounded, exact accepted-head Markdown snapshot for staff editing handoff."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from .content_profile import ContentProfileError, parse_content
from .models import WorkspaceRepository
from .repository_service import MAX_PINNED_SNAPSHOT_BYTES, read_accepted_repository_markdown_files

MAX_SOURCE_FILES = 250
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


def export_repository_sources(repository: WorkspaceRepository) -> RepositorySourceExport:
    """Package exact current Markdown bytes, never a sanitized or restorable backup."""

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
    try:
        for path, source in sources:
            parsed = parse_content(source)
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
    except (ContentProfileError, UnicodeError, ValueError, TypeError) as exc:
        raise RepositorySourceExportError("The accepted repository source is invalid.") from exc
    manifest = {
        "format": "tekdocs-repository-source-snapshot/v1",
        "workspace_id": str(repository.workspace_id),
        "accepted_commit": commit.object_id,
        "object_format": commit.object_format,
        "current_files_only": True,
        "exclusions": ["pinned_historical_objects", "attachment_bytes", "database_records", "git_history"],
        "files": manifest_files,
    }
    files["tekdocs-source.json"] = _json(manifest)
    files["README.md"] = (
        b"# TekDocs repository source snapshot\n\n"
        b"This contains exact current Markdown files and portable frontmatter from one accepted Git commit. "
        b"It is not sanitized; review source before sharing. Historical pinned objects, attachments, "
        b"database records and Git history are excluded. This is not a complete dependency bundle or backup.\n"
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
    return RepositorySourceExport(content=content, accepted_commit=commit.object_id, file_count=len(sources))
