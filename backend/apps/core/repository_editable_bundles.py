"""Workspace-scoped editable Markdown and referenced managed-file handoff."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .attachment_security import AttachmentSecurityError
from .content_profile import parse_content
from .document_attachments import copy_attachment_content
from .models import DocumentAttachment, DocumentAttachmentPurpose, WorkspaceRepository
from .rendering import attachment_ids_in_markdown
from .repository_source_exports import RepositorySourceExportError, export_repository_sources
from .repository_source_validation import RepositorySourceValidationError, verify_repository_source_snapshot

MAX_BUNDLE_ATTACHMENTS = 50
MAX_BUNDLE_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_EDITABLE_BUNDLE_BYTES = 75 * 1024 * 1024
BUNDLE_FORMAT = "tekdocs-repository-editable-bundle/v4"
PRIMARY_BUNDLE_FORMAT = "tekdocs-repository-editable-bundle/v3"
OWNER_BUNDLE_FORMAT = "tekdocs-repository-editable-bundle/v2"
LEGACY_BUNDLE_FORMAT = "tekdocs-repository-editable-bundle/v1"


class RepositoryEditableBundleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryEditableBundle:
    content: bytes
    accepted_commit: str
    source_file_count: int
    attachment_count: int
    primary_file_count: int


def referenced_source_attachments(source_content: bytes) -> tuple[dict[str, object], set[UUID], set[UUID]]:
    """Read only the already validated v3 source archive, including pinned Markdown."""

    manifest = verify_repository_source_snapshot(source_content)
    referenced: set[UUID] = set()
    document_ids: set[UUID] = set()
    with zipfile.ZipFile(io.BytesIO(source_content)) as archive:
        for item in manifest["files"] + manifest["historical_files"]:  # type: ignore[operator]
            if not isinstance(item, dict):  # pragma: no cover - verifier enforces shape
                raise RepositoryEditableBundleError("The source inventory is invalid.")
            parsed = parse_content(archive.read(item["path"]))
            referenced.update(attachment_ids_in_markdown(parsed.markdown))
            if parsed.kind == "document":
                document_ids.add(parsed.content_id)
    return manifest, referenced, document_ids


def _archive(files: dict[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, files[path])
    return target.getvalue()


def export_repository_editable_bundle(repository: WorkspaceRepository) -> RepositoryEditableBundle:
    """Include every managed file linked by current or reachable historical Markdown."""

    try:
        source = export_repository_sources(repository)
        source_manifest, referenced, source_document_ids = referenced_source_attachments(source.content)
    except (RepositorySourceExportError, RepositorySourceValidationError) as exc:
        raise RepositoryEditableBundleError("The repository source snapshot is unavailable.") from exc
    primary_versions = list(
        DocumentAttachment.objects.select_related("document__entity").filter(
            tenant_id=repository.tenant_id,
            organization=repository.workspace.organization,
            owner_workspace_id=repository.workspace_id,
            owner_content_id__in=source_document_ids,
            archived_at__isnull=True,
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
            scan_status="clean",
        ).filter(
            Q(document__isnull=True)
            | Q(
                document__tenant_id=repository.tenant_id,
                document__organization=repository.workspace.organization,
                document__entity__workspace_id=repository.workspace_id,
                document__archived_at__isnull=True,
            )
        ).order_by("owner_content_id", "version_number")
    )
    if len(referenced) + len(primary_versions) > MAX_BUNDLE_ATTACHMENTS:
        raise RepositoryEditableBundleError("The editable bundle exceeds its managed-file limit.")
    attachments = list(
        DocumentAttachment.objects.select_related("document")
        .filter(
            entity_id__in=referenced,
            tenant_id=repository.tenant_id,
            organization=repository.workspace.organization,
            archived_at__isnull=True,
            purpose=DocumentAttachmentPurpose.ATTACHMENT,
            scan_status="clean",
        )
        .filter(
            Q(
                document__tenant_id=repository.tenant_id,
                document__organization=repository.workspace.organization,
                document__entity__workspace_id=repository.workspace_id,
                document__archived_at__isnull=True,
            )
            | Q(
                document__isnull=True,
                owner_workspace_id=repository.workspace_id,
                owner_content_id__in=source_document_ids,
            )
        )
        .order_by("entity_id")
    )
    if {record.entity_id for record in attachments} != referenced:
        raise RepositoryEditableBundleError("A referenced managed file is unavailable in this Workspace.")

    files: dict[str, bytes] = {"source-snapshot.zip": source.content}
    descriptors: list[dict[str, object]] = []
    total = 0
    for record in attachments:
        if record.document_id is None:
            if (
                record.owner_workspace_id != repository.workspace_id
                or record.owner_content_id not in source_document_ids
            ):
                raise RepositoryEditableBundleError("A referenced managed file has an invalid repository owner.")
            owner = {"type": "repository_document", "id": str(record.owner_content_id)}
        else:
            owner = {"type": "legacy_document", "id": str(record.document_id)}
        if not record.file.name or record.size > MAX_BUNDLE_ATTACHMENT_BYTES - total:
            raise RepositoryEditableBundleError("The editable bundle exceeds its managed-file limit.")
        try:
            content = copy_attachment_content(record)
        except (AttachmentSecurityError, ValidationError) as exc:
            raise RepositoryEditableBundleError("A referenced managed file failed its integrity check.") from exc
        total += len(content)
        path = f"attachments/{record.entity_id}"
        files[path] = content
        descriptors.append(
            {
                "id": str(record.entity_id),
                "owner": owner,
                "path": path,
                "filename": record.original_filename,
                "media_type": record.media_type,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    primary_descriptors: list[dict[str, object]] = []
    previous_by_owner: dict[UUID, DocumentAttachment] = {}
    for record in primary_versions:
        owner_id = record.owner_content_id
        if (
            owner_id is None
            or owner_id not in source_document_ids
            or (record.document_id is not None and record.document_id != owner_id)
        ):
            raise RepositoryEditableBundleError("A primary file has an invalid repository owner.")
        owner = {
            "type": "legacy_document" if record.document_id else "repository_document",
            "id": str(owner_id),
        }
        previous = previous_by_owner.get(owner_id)
        if previous is not None and bool(previous.document_id) != bool(record.document_id):
            raise RepositoryEditableBundleError("A primary-file version chain has mixed custody.")
        expected_version = (previous.version_number or 0) + 1 if previous else 1
        if record.version_number != expected_version:
            raise RepositoryEditableBundleError("A primary-file version chain is incomplete.")
        if record.replaces_id != (previous.id if previous else None):
            raise RepositoryEditableBundleError("A primary-file version chain is invalid.")
        if not record.file.name or record.size > MAX_BUNDLE_ATTACHMENT_BYTES - total:
            raise RepositoryEditableBundleError("The editable bundle exceeds its managed-file limit.")
        try:
            content = copy_attachment_content(record)
        except (AttachmentSecurityError, ValidationError) as exc:
            raise RepositoryEditableBundleError("A primary file failed its integrity check.") from exc
        total += len(content)
        path = f"primary-files/{record.entity_id}"
        files[path] = content
        primary_descriptors.append({
            "id": str(record.entity_id),
            "owner": owner,
            "version_number": record.version_number,
            "replaces_id": str(previous.entity_id) if previous else None,
            "path": path,
            "filename": record.original_filename,
            "media_type": record.media_type,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
        previous_by_owner[owner_id] = record
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    accepted_commit = repository.accepted_commit
    if (
        accepted_commit is None
        or repository.accepted_commit_id != repository.indexed_commit_id
        or accepted_commit.object_id != source.accepted_commit
    ):
        raise RepositoryEditableBundleError("The accepted repository content changed during export.")
    manifest = {
        "format": BUNDLE_FORMAT,
        "workspace_id": str(repository.workspace_id),
        "accepted_commit": source.accepted_commit,
        "source_sha256": hashlib.sha256(source.content).hexdigest(),
        "scope": "current-and-reachable-historical-markdown-with-referenced-and-primary-files",
        "exclusions": ["database_records", "git_history", "other_unreferenced_managed_files"],
        "attachments": descriptors,
        "primary_files": primary_descriptors,
    }
    if manifest["workspace_id"] != source_manifest["workspace_id"]:
        raise RepositoryEditableBundleError("The source Workspace changed during export.")
    files["tekdocs-bundle.json"] = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    files["README.md"] = (
        b"# TekDocs editable repository bundle\n\n"
        b"Contains an exact Markdown source snapshot, managed files referenced by its current or reachable "
        b"historical Markdown, and retained primary-file versions for Git-owned and copied legacy documents. "
        b"This is unsanitized and is not a backup: "
        b"database records, Git history, and other unreferenced managed files are excluded. "
        b"Review before sharing.\n"
    )
    content = _archive(files)
    if len(content) > MAX_EDITABLE_BUNDLE_BYTES:
        raise RepositoryEditableBundleError("The editable bundle exceeds its ZIP size limit.")
    return RepositoryEditableBundle(
        content=content,
        accepted_commit=source.accepted_commit,
        source_file_count=source.file_count,
        attachment_count=len(attachments),
        primary_file_count=len(primary_versions),
    )
