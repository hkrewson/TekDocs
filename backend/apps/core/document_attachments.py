from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID, uuid4

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import AuditEvent, Document, DocumentAttachment, Entity
from .rendering import RenderedAttachment, attachment_ids_in_markdown
from .workspaces import ResolvedWorkspace

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_MARKDOWN_IMPORT_BYTES = 1024 * 1024

_TEXT_TYPES = {
    ".cfg": "text/plain",
    ".conf": "text/plain",
    ".csv": "text/csv",
    ".ini": "text/plain",
    ".json": "application/json",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}
_BINARY_TYPES: dict[str, tuple[str, Callable[[bytes], bool]]] = {
    ".gif": ("image/gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".webp": ("image/webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
    ".zip": ("application/zip", lambda data: data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))),
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    filename: str
    content: bytes
    media_type: str
    checksum: str


def validate_attachment_upload(upload: UploadedFile) -> ValidatedUpload:
    filename = str(upload.name or "")
    if not filename or len(filename) > 240 or _CONTROL.search(filename):
        raise ValidationError({"file": "The attachment filename is invalid."})
    if PurePath(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValidationError({"file": "The attachment filename must not contain a path."})
    content = upload.read(MAX_ATTACHMENT_BYTES + 1)
    if not content:
        raise ValidationError({"file": "Empty attachments are not accepted."})
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValidationError({"file": "Attachments may not exceed 10 MiB."})

    extension = PurePath(filename).suffix.lower()
    if extension in _TEXT_TYPES:
        if b"\x00" in content:
            raise ValidationError({"file": "This text attachment contains binary data."})
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "Text attachments must use UTF-8."}) from exc
        media_type = _TEXT_TYPES[extension]
    elif extension in _BINARY_TYPES:
        media_type, validator = _BINARY_TYPES[extension]
        if not validator(content):
            raise ValidationError({"file": "The attachment contents do not match its file type."})
    else:
        raise ValidationError(
            {"file": "Allowed attachment types are PDF, PNG, JPEG, GIF, WebP, ZIP, and UTF-8 technical text files."}
        )
    return ValidatedUpload(filename, content, media_type, sha256(content).hexdigest())


def create_document_attachment(
    *, document: Document, actor_id: UUID, upload: UploadedFile, entity_id: UUID | None = None
) -> DocumentAttachment:
    validated = validate_attachment_upload(upload)
    attachment: DocumentAttachment | None = None
    stored_name = ""
    try:
        with transaction.atomic():
            entity = Entity.objects.create(
                id=entity_id or uuid4(),
                tenant=document.tenant,
                workspace=document.entity.workspace,
                organization=document.organization,
                entity_type="document_attachment",
                display_name=validated.filename,
            )
            attachment = DocumentAttachment(
                tenant=document.tenant,
                organization=document.organization,
                document=document,
                entity=entity,
                original_filename=validated.filename,
                media_type=validated.media_type,
                size=len(validated.content),
                checksum=validated.checksum,
                created_by_id=actor_id,
            )
            attachment.file.save("managed", ContentFile(validated.content), save=False)
            stored_name = attachment.file.name
            attachment.full_clean()
            attachment.save()
            AuditEvent.objects.create(
                tenant=document.tenant,
                actor_id=actor_id,
                action="document.attachment.created",
                entity_id=attachment.entity_id,
                metadata={"document_id": str(document.entity_id)},
            )
    except Exception:
        if attachment is not None and stored_name:
            attachment.file.storage.delete(stored_name)
        raise
    if attachment is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("Attachment creation completed without a record.")
    return attachment


@transaction.atomic
def archive_document_attachment(*, attachment: DocumentAttachment, actor_id: UUID) -> None:
    locked = DocumentAttachment.objects.select_for_update().get(pk=attachment.pk)
    if locked.archived_at is not None:
        return
    locked.archived_at = timezone.now()
    locked.save(update_fields=["archived_at", "updated_at"])
    Entity.objects.filter(pk=locked.entity_id, archived_at__isnull=True).update(archived_at=locked.archived_at)
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.attachment.archived",
        entity_id=locked.entity_id,
        metadata={"document_id": str(locked.document.entity_id)},
    )


def copy_attachment_content(attachment: DocumentAttachment) -> bytes:
    file_handle: BinaryIO
    with attachment.file.storage.open(attachment.file.name, "rb") as file_handle:
        content = file_handle.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) != attachment.size or sha256(content).hexdigest() != attachment.checksum:
        raise ValidationError("A template attachment failed its integrity check.")
    return content


def copy_document_attachment(
    *, attachment: DocumentAttachment, destination: Document, actor_id: UUID, entity_id: UUID
) -> DocumentAttachment:
    content = copy_attachment_content(attachment)
    uploaded = UploadedFile(
        file=ContentFile(content),
        name=attachment.original_filename,
        content_type=attachment.media_type,
        size=len(content),
    )
    return create_document_attachment(
        document=destination,
        actor_id=actor_id,
        upload=uploaded,
        entity_id=entity_id,
    )


def resolve_rendered_attachments(
    *, workspace: ResolvedWorkspace, document: Document | None, markdown: str
) -> dict[str, RenderedAttachment]:
    if document is None:
        return {}
    requested = attachment_ids_in_markdown(markdown)
    if not requested:
        return {}
    records = DocumentAttachment.objects.filter(
        tenant=workspace.member.tenant,
        document=document,
        entity_id__in=requested,
        archived_at__isnull=True,
    )
    result: dict[str, RenderedAttachment] = {}
    for attachment in records:
        kwargs: dict[str, object] = {
            "document_entity_id": document.entity_id,
            "attachment_entity_id": attachment.entity_id,
        }
        route = "msp-document-attachment-download"
        if workspace.organization is not None:
            route = "organization-document-attachment-download"
            kwargs["organization_entity_id"] = workspace.organization.entity_id
        result[str(attachment.entity_id)] = {
            "id": str(attachment.entity_id),
            "filename": attachment.original_filename,
            "size": attachment.size,
            "download_url": reverse(route, kwargs=kwargs),
        }
    return result
