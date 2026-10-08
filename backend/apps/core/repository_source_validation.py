"""Offline, self-consistency validation for an editable Markdown source snapshot."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import PurePosixPath
from uuid import UUID

from .content_profile import ContentProfileError, parse_content
from .repository_source_exports import MAX_SOURCE_FILES, MAX_SOURCE_INPUT_BYTES, MAX_SOURCE_ZIP_BYTES

MAX_MANIFEST_BYTES = 256 * 1024
MAX_README_BYTES = 16 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROLES = {"include", "template_source", "derived_from"}


class RepositorySourceValidationError(ValueError):
    pass


def _object_id(value: object, object_format: str) -> str:
    length = 40 if object_format == "sha1" else 64
    if not isinstance(value, str) or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        raise RepositorySourceValidationError("The source snapshot has an invalid Git commit identity.")
    return value


def _content_id(value: object) -> UUID:
    if not isinstance(value, str):
        raise RepositorySourceValidationError("The source snapshot has an invalid content identity.")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise RepositorySourceValidationError("The source snapshot has an invalid content identity.") from exc
    if str(parsed) != value:
        raise RepositorySourceValidationError("The source snapshot has a noncanonical content identity.")
    return parsed


def _source_path(value: object) -> str:
    if not isinstance(value, str) or not value.endswith(".md") or "\\" in value:
        raise RepositorySourceValidationError("The source snapshot has an invalid Markdown path.")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in value.split("/")):
        raise RepositorySourceValidationError("The source snapshot has an unsafe Markdown path.")
    return value


def _descriptor(value: object, *, historical: bool, object_format: str) -> tuple[str, UUID, str, str]:
    if not isinstance(value, dict):
        raise RepositorySourceValidationError("The source snapshot has an invalid file descriptor.")
    required = {"path", "content_id", "kind", "sha256"}
    if historical:
        required |= {"source_path", "commit", "roles"}
    if set(value) != required:
        raise RepositorySourceValidationError("The source snapshot has an invalid file descriptor.")
    content_id = _content_id(value["content_id"])
    kind = value["kind"]
    if kind not in {"document", "fragment"}:
        raise RepositorySourceValidationError("The source snapshot has an invalid content kind.")
    digest = value["sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise RepositorySourceValidationError("The source snapshot has an invalid checksum.")
    if historical:
        commit = _object_id(value["commit"], object_format)
        source_path = _source_path(value["source_path"])
        expected_path = f"pinned/{commit}/{source_path}"
        roles = value["roles"]
        if not isinstance(roles, list) or not roles or roles != sorted(set(roles)) or not set(roles) <= _ROLES:
            raise RepositorySourceValidationError("The source snapshot has invalid dependency roles.")
    else:
        source_path = _source_path(str(value["path"])[len("repository/") :])
        expected_path = f"repository/{source_path}"
    if value["path"] != expected_path or (kind == "fragment") != source_path.startswith("fragments/"):
        raise RepositorySourceValidationError("The source snapshot has invalid source placement.")
    return expected_path, content_id, kind, digest


def verify_repository_source_snapshot(content: bytes) -> dict[str, object]:
    """Check ZIP structure, manifest identities, and exact Markdown bytes.

    This does not authenticate the manifest against Git or make the ZIP a backup.
    """

    if len(content) > MAX_SOURCE_ZIP_BYTES:
        raise RepositorySourceValidationError("The source snapshot exceeds the ZIP size limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            if len(names) != len(set(names)) or len(names) > MAX_SOURCE_FILES + 2:
                raise RepositorySourceValidationError("The source snapshot has duplicate or excessive entries.")
            if any(
                item.compress_type != zipfile.ZIP_DEFLATED
                or item.flag_bits & 1
                or not stat.S_ISREG(item.external_attr >> 16)
                for item in entries
            ):
                raise RepositorySourceValidationError("The source snapshot contains an unsupported ZIP entry.")
            entry_sizes = {item.filename: item.file_size for item in entries}
            if entry_sizes.get("tekdocs-source.json", MAX_MANIFEST_BYTES + 1) > MAX_MANIFEST_BYTES:
                raise RepositorySourceValidationError("The source snapshot manifest is too large or missing.")
            if entry_sizes.get("README.md", MAX_README_BYTES + 1) > MAX_README_BYTES:
                raise RepositorySourceValidationError("The source snapshot README is too large or missing.")
            manifest = json.loads(archive.read("tekdocs-source.json"))
            if not isinstance(manifest, dict) or set(manifest) != {
                "format",
                "workspace_id",
                "accepted_commit",
                "object_format",
                "scope",
                "exclusions",
                "files",
                "historical_files",
            }:
                raise RepositorySourceValidationError("The source snapshot manifest has an invalid shape.")
            if (
                manifest["format"] != "tekdocs-repository-source-snapshot/v3"
                or manifest["scope"] != "current-files-and-reachable-markdown-dependencies"
            ):
                raise RepositorySourceValidationError("The source snapshot format is unsupported.")
            if manifest["exclusions"] != ["attachment_bytes", "database_records", "git_history"]:
                raise RepositorySourceValidationError("The source snapshot exclusions are invalid.")
            _content_id(manifest["workspace_id"])
            object_format = manifest["object_format"]
            if object_format not in {"sha1", "sha256"}:
                raise RepositorySourceValidationError("The source snapshot Git object format is invalid.")
            _object_id(manifest["accepted_commit"], object_format)
            current = manifest["files"]
            historical = manifest["historical_files"]
            if (
                not isinstance(current, list)
                or not isinstance(historical, list)
                or len(current) + len(historical) > MAX_SOURCE_FILES
            ):
                raise RepositorySourceValidationError("The source snapshot file inventory is invalid.")
            expected = {"README.md", "tekdocs-source.json"}
            identities: set[tuple[str, UUID]] = set()
            source_bytes = 0
            for item in current + historical:
                is_historical = item in historical
                path, content_id, kind, digest = _descriptor(
                    item, historical=is_historical, object_format=object_format
                )
                identity = (item["commit"] if is_historical else manifest["accepted_commit"], content_id)
                if path in expected or identity in identities or path not in entry_sizes:
                    raise RepositorySourceValidationError("The source snapshot has duplicate or missing Markdown.")
                expected.add(path)
                identities.add(identity)
                source_bytes += entry_sizes[path]
                if source_bytes > MAX_SOURCE_INPUT_BYTES:
                    raise RepositorySourceValidationError("The source snapshot exceeds the Markdown byte limit.")
                source = archive.read(path)
                if hashlib.sha256(source).hexdigest() != digest:
                    raise RepositorySourceValidationError("The source snapshot Markdown checksum differs.")
                parsed = parse_content(source)
                if parsed.content_id != content_id or parsed.kind != kind:
                    raise RepositorySourceValidationError("The source snapshot Markdown identity differs.")
            if set(names) != expected:
                raise RepositorySourceValidationError("The source snapshot contains an unlisted entry.")
            archive.read("README.md")
            return manifest
    except RepositorySourceValidationError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError, ValueError, TypeError, ContentProfileError) as exc:
        raise RepositorySourceValidationError("The source snapshot is invalid or unreadable.") from exc
