"""Attachment parity for a legacy document copy; file bytes stay outside Git."""

from __future__ import annotations

import hashlib
import json
import uuid

from rest_framework.exceptions import ValidationError

from .attachment_security import AttachmentSecurityError
from .document_attachments import copy_attachment_content
from .models import Document, DocumentAttachment, DocumentAttachmentPurpose
from .rendering import attachment_ids_in_markdown


class DocumentMigrationAttachmentError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def portable_primary_file_versions(
    document: Document, *, verify_content: bool = False
) -> tuple[tuple[uuid.UUID, str], ...]:
    """Prove the retained legacy chain without changing file custody or writing bytes to Git."""

    versions = DocumentAttachment.objects.filter(
        document=document, purpose=DocumentAttachmentPurpose.PRIMARY_FILE
    ).order_by("version_number", "id")
    previous: DocumentAttachment | None = None
    manifest: list[tuple[uuid.UUID, str]] = []
    for record in versions:
        if (
            record.tenant_id != document.tenant_id
            or record.organization_id != document.organization_id
            or record.owner_workspace_id != document.entity.workspace_id
            or record.owner_content_id != document.id
            or record.archived_at is not None
            or record.scan_status != "clean"
            or not record.file.name
            or record.version_number != ((previous.version_number or 0) + 1 if previous else 1)
            or record.replaces_id != (previous.id if previous else None)
        ):
            raise DocumentMigrationAttachmentError("primary_file_history_invalid")
        if verify_content:
            try:
                copy_attachment_content(record)
            except (AttachmentSecurityError, ValidationError) as exc:
                raise DocumentMigrationAttachmentError("primary_file_storage_unavailable") from exc
        payload = [
            str(record.id), str(record.entity_id), record.version_number,
            str(record.replaces_id) if record.replaces_id else None,
            record.original_filename, record.media_type, record.size, record.checksum,
            record.storage_provider, record.file.name,
        ]
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        manifest.append((record.entity_id, digest))
        previous = record
    return tuple(manifest)


def portable_document_attachments(
    document: Document, markdown: str, *, verify_content: bool = False
) -> tuple[tuple[uuid.UUID, str], ...]:
    """Bind active file identities and metadata without exporting file bytes."""

    records = list(DocumentAttachment.objects.filter(document=document, archived_at__isnull=True).order_by("entity_id"))
    primary = portable_primary_file_versions(document, verify_content=verify_content)
    available: set[uuid.UUID] = set()
    manifest: list[tuple[uuid.UUID, str]] = []
    for record in records:
        if record.purpose != DocumentAttachmentPurpose.ATTACHMENT:
            continue
        if (
            record.tenant_id != document.tenant_id
            or record.organization_id != document.organization_id
            or record.scan_status != "clean"
            or not record.file.name
        ):
            raise DocumentMigrationAttachmentError("attachment_reference_unavailable")
        if verify_content:
            try:
                copy_attachment_content(record)
            except (AttachmentSecurityError, ValidationError) as exc:
                raise DocumentMigrationAttachmentError("attachment_storage_unavailable") from exc
        available.add(record.entity_id)
        payload = [
            str(record.id),
            str(record.entity_id),
            record.original_filename,
            record.media_type,
            record.size,
            record.checksum,
            record.storage_provider,
            record.file.name,
        ]
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        manifest.append((record.entity_id, digest))
    if attachment_ids_in_markdown(markdown) - available:
        raise DocumentMigrationAttachmentError("attachment_reference_unavailable")
    return (*manifest, *primary)
