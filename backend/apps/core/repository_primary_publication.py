"""Prepare a complete, verified primary-file publication input in memory.

The caller must still retain and sign these bytes before publication. Preparing
the input alone does not make a primary-file document publishable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .attachment_security import AttachmentSecurityError
from .content_index_models import ContentNode, ContentNodeKind
from .document_attachments import copy_attachment_content
from .models import Document, DocumentAttachment, DocumentAttachmentPurpose, WorkspaceRepository
from .publications import MAX_RETAINED_ATTACHMENT_BYTES, MAX_RETAINED_ATTACHMENTS


class RepositoryPrimaryPublicationError(ValueError):
    """The exact primary-file chain cannot be frozen for publication."""


@dataclass(frozen=True, slots=True)
class PreparedPrimaryVersion:
    source: DocumentAttachment
    content: bytes
    descriptor: dict[str, object]


@dataclass(frozen=True, slots=True)
class PreparedPrimarySnapshot:
    selected_entity_id: UUID
    versions: tuple[PreparedPrimaryVersion, ...]


@transaction.atomic
def prepare_repository_primary_publication(
    *, repository: WorkspaceRepository, content_id: UUID, expected_current_entity_id: UUID
) -> PreparedPrimarySnapshot:
    """Lock the owner and prove every version, including the selected current one.

    An explicit expected version makes stale review selections fail closed. The
    repository lock also serializes Git-only primary-file uploads.
    """

    repository = WorkspaceRepository.objects.select_for_update().select_related("workspace").get(pk=repository.pk)
    if (
        repository.accepted_commit_id is None
        or repository.accepted_commit_id != repository.indexed_commit_id
        or not ContentNode.objects.filter(
            repository=repository,
            content_id=content_id,
            indexed_commit_id=repository.accepted_commit_id,
            kind=ContentNodeKind.DOCUMENT,
        ).exists()
    ):
        raise RepositoryPrimaryPublicationError("repository.primary_file.source_unavailable")
    document = (
        Document.objects.select_for_update()
        .filter(
            id=content_id,
            tenant_id=repository.tenant_id,
            organization=repository.workspace.organization,
            entity__workspace_id=repository.workspace_id,
            archived_at__isnull=True,
        )
        .first()
    )
    records = list(
        DocumentAttachment.objects.select_for_update()
        .filter(
            tenant_id=repository.tenant_id,
            organization=repository.workspace.organization,
            owner_workspace_id=repository.workspace_id,
            owner_content_id=content_id,
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
        )
        .order_by("version_number", "id")
    )
    if not records or len(records) > MAX_RETAINED_ATTACHMENTS:
        raise RepositoryPrimaryPublicationError("repository.primary_file.history_unavailable")
    prepared: list[PreparedPrimaryVersion] = []
    previous: DocumentAttachment | None = None
    total = 0
    for record in records:
        if (
            record.document_id != (document.id if document else None)
            or record.archived_at is not None
            or record.scan_status != "clean"
            or not record.file.name
            or record.version_number != ((previous.version_number or 0) + 1 if previous else 1)
            or record.replaces_id != (previous.id if previous else None)
            or record.size > MAX_RETAINED_ATTACHMENT_BYTES - total
        ):
            raise RepositoryPrimaryPublicationError("repository.primary_file.history_unavailable")
        try:
            content = copy_attachment_content(record)
        except (AttachmentSecurityError, ValidationError) as exc:
            raise RepositoryPrimaryPublicationError("repository.primary_file.storage_unavailable") from exc
        total += len(content)
        prepared.append(
            PreparedPrimaryVersion(
                source=record,
                content=content,
                descriptor={
                    "id": str(record.entity_id),
                    "owner": {
                        "type": "legacy_document" if document else "repository_document",
                        "id": str(content_id),
                    },
                    "version_number": record.version_number,
                    "replaces_id": str(previous.entity_id) if previous else None,
                    "filename": record.original_filename,
                    "media_type": record.media_type,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            )
        )
        previous = record
    selected = prepared[-1].source.entity_id
    if selected != expected_current_entity_id:
        raise RepositoryPrimaryPublicationError("repository.primary_file.selection_changed")
    return PreparedPrimarySnapshot(selected_entity_id=selected, versions=tuple(prepared))
