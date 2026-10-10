"""Offline self-consistency checks for a repository bundle with managed files."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from uuid import UUID

from .repository_editable_bundles import (
    BUNDLE_FORMAT,
    LEGACY_BUNDLE_FORMAT,
    MAX_BUNDLE_ATTACHMENT_BYTES,
    MAX_BUNDLE_ATTACHMENTS,
    MAX_EDITABLE_BUNDLE_BYTES,
    referenced_source_attachments,
)
from .repository_source_exports import MAX_SOURCE_ZIP_BYTES
from .repository_source_validation import RepositorySourceValidationError

MAX_BUNDLE_MANIFEST_BYTES = 64 * 1024
MAX_BUNDLE_README_BYTES = 16 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RepositoryEditableBundleValidationError(ValueError):
    pass


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise RepositoryEditableBundleValidationError("The bundle has an invalid identity.")
    try:
        result = UUID(value)
    except ValueError as exc:
        raise RepositoryEditableBundleValidationError("The bundle has an invalid identity.") from exc
    if str(result) != value:
        raise RepositoryEditableBundleValidationError("The bundle has a noncanonical identity.")
    return result


def verify_repository_editable_bundle(content: bytes) -> dict[str, object]:
    """Validate exact included bytes and reference closure, not provenance or database state."""

    if len(content) > MAX_EDITABLE_BUNDLE_BYTES:
        raise RepositoryEditableBundleValidationError("The editable bundle exceeds its ZIP size limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or len(names) > MAX_BUNDLE_ATTACHMENTS + 3:
                raise RepositoryEditableBundleValidationError("The bundle has duplicate or excessive entries.")
            if any(
                entry.compress_type != zipfile.ZIP_DEFLATED
                or entry.flag_bits & 1
                or not stat.S_ISREG(entry.external_attr >> 16)
                for entry in entries
            ):
                raise RepositoryEditableBundleValidationError("The bundle has an unsupported ZIP entry.")
            sizes = {entry.filename: entry.file_size for entry in entries}
            if (
                sizes.get("tekdocs-bundle.json", MAX_BUNDLE_MANIFEST_BYTES + 1) > MAX_BUNDLE_MANIFEST_BYTES
                or sizes.get("README.md", MAX_BUNDLE_README_BYTES + 1) > MAX_BUNDLE_README_BYTES
                or sizes.get("source-snapshot.zip", MAX_SOURCE_ZIP_BYTES + 1) > MAX_SOURCE_ZIP_BYTES
            ):
                raise RepositoryEditableBundleValidationError("The bundle has an oversized or missing entry.")
            manifest = json.loads(archive.read("tekdocs-bundle.json"))
            if not isinstance(manifest, dict) or set(manifest) != {
                "format", "workspace_id", "accepted_commit", "source_sha256", "scope", "exclusions", "attachments"
            }:
                raise RepositoryEditableBundleValidationError("The bundle manifest has an invalid shape.")
            if (
                manifest["format"] not in {BUNDLE_FORMAT, LEGACY_BUNDLE_FORMAT}
                or manifest["scope"] != "current-and-reachable-historical-markdown-with-referenced-files"
                or manifest["exclusions"] != ["database_records", "git_history", "unreferenced_managed_files"]
                or not isinstance(manifest["source_sha256"], str)
                or _SHA256.fullmatch(manifest["source_sha256"]) is None
            ):
                raise RepositoryEditableBundleValidationError("The bundle manifest contract differs.")
            _uuid(manifest["workspace_id"])
            source_content = archive.read("source-snapshot.zip")
            if hashlib.sha256(source_content).hexdigest() != manifest["source_sha256"]:
                raise RepositoryEditableBundleValidationError("The source snapshot checksum differs.")
            source_manifest, referenced, source_document_ids = referenced_source_attachments(source_content)
            if (
                manifest["workspace_id"] != source_manifest["workspace_id"]
                or manifest["accepted_commit"] != source_manifest["accepted_commit"]
            ):
                raise RepositoryEditableBundleValidationError("The bundle source identity differs.")
            descriptors = manifest["attachments"]
            if not isinstance(descriptors, list) or len(descriptors) > MAX_BUNDLE_ATTACHMENTS:
                raise RepositoryEditableBundleValidationError("The bundle attachment inventory is invalid.")
            expected = {"tekdocs-bundle.json", "README.md", "source-snapshot.zip"}
            declared_ids: list[UUID] = []
            total = 0
            for descriptor in descriptors:
                if not isinstance(descriptor, dict):
                    raise RepositoryEditableBundleValidationError("The bundle has an invalid attachment descriptor.")
                common_fields = {"id", "path", "filename", "media_type", "size", "sha256"}
                if manifest["format"] == LEGACY_BUNDLE_FORMAT:
                    if set(descriptor) != common_fields | {"document_id"}:
                        raise RepositoryEditableBundleValidationError(
                            "The bundle has an invalid attachment descriptor."
                        )
                    _uuid(descriptor["document_id"])
                else:
                    if set(descriptor) != common_fields | {"owner"}:
                        raise RepositoryEditableBundleValidationError(
                            "The bundle has an invalid attachment descriptor."
                        )
                    owner = descriptor["owner"]
                    if not isinstance(owner, dict) or set(owner) != {"type", "id"}:
                        raise RepositoryEditableBundleValidationError("The bundle has an invalid attachment owner.")
                    if owner["type"] not in {"legacy_document", "repository_document"}:
                        raise RepositoryEditableBundleValidationError("The bundle has an invalid attachment owner.")
                    owner_id = _uuid(owner["id"])
                    if owner["type"] == "repository_document" and owner_id not in source_document_ids:
                        raise RepositoryEditableBundleValidationError("The bundle has an unknown repository owner.")
                attachment_id = _uuid(descriptor["id"])
                path = f"attachments/{attachment_id}"
                if (
                    descriptor["path"] != path
                    or path in expected
                    or not isinstance(descriptor["filename"], str)
                    or not 0 < len(descriptor["filename"]) <= 240
                    or not isinstance(descriptor["media_type"], str)
                    or not 0 < len(descriptor["media_type"]) <= 120
                    or type(descriptor["size"]) is not int
                    or descriptor["size"] < 0
                    or not isinstance(descriptor["sha256"], str)
                    or _SHA256.fullmatch(descriptor["sha256"]) is None
                    or sizes.get(path) != descriptor["size"]
                ):
                    raise RepositoryEditableBundleValidationError("The bundle has an invalid attachment descriptor.")
                expected.add(path)
                declared_ids.append(attachment_id)
                total += descriptor["size"]
                if total > MAX_BUNDLE_ATTACHMENT_BYTES:
                    raise RepositoryEditableBundleValidationError("The bundle exceeds its managed-file limit.")
                if hashlib.sha256(archive.read(path)).hexdigest() != descriptor["sha256"]:
                    raise RepositoryEditableBundleValidationError("A managed-file checksum differs.")
            if declared_ids != sorted(set(referenced), key=str):
                raise RepositoryEditableBundleValidationError("The bundle managed-file closure differs from Markdown.")
            if set(names) != expected:
                raise RepositoryEditableBundleValidationError("The bundle has an unlisted or missing entry.")
            archive.read("README.md")
            return manifest
    except RepositoryEditableBundleValidationError:
        raise
    except (
        OSError, ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile, RepositorySourceValidationError
    ) as exc:
        raise RepositoryEditableBundleValidationError("The editable bundle is invalid or unreadable.") from exc
