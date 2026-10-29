"""Bounded file custody for ordinary Git snapshots; retained verification is offline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from rest_framework.exceptions import ValidationError

from .document_attachments import copy_attachment_content
from .document_migration_attachments import portable_document_attachments
from .models import Document, DocumentAttachment
from .publications import MAX_RETAINED_ATTACHMENT_BYTES, MAX_RETAINED_ATTACHMENTS, PendingArtifact

FILE_GIT_STATIC_FORMAT = "tekdocs-static-publication/v6"


@dataclass(frozen=True)
class PublicationFile:
    artifact: PendingArtifact
    descriptor: dict[str, Any]


def prepare_publication_files(*, document: Document, markdown: str) -> tuple[PublicationFile, ...]:
    # Callers hold the repository and document locks, shared with upload/replace.
    portable_document_attachments(document, markdown)
    records = list(
        DocumentAttachment.objects.select_for_update(of=("self",))
        .filter(document=document, archived_at__isnull=True)
        .select_related("replaces")
        .order_by("purpose", "version_number", "entity_id")
    )
    if len(records) > MAX_RETAINED_ATTACHMENTS:
        raise ValueError("Publication file count exceeds its retained limit")
    result = []
    total = 0
    for record in records:
        try:
            content = copy_attachment_content(record)
        except ValidationError as exc:
            raise ValueError("Publication file custody is unavailable") from exc
        total += len(content)
        if total > MAX_RETAINED_ATTACHMENT_BYTES:
            raise ValueError("Publication file bytes exceed their retained limit")
        artifact = PendingArtifact(
            id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            kind="attachment",
            filename=record.original_filename,
            media_type=record.media_type,
            content=content,
            checksum=record.checksum,
            source_attachment=record,
        )
        result.append(
            PublicationFile(
                artifact,
                {
                    "id": str(record.entity_id),
                    "artifact_id": str(artifact.entity_id),
                    "owner": {"type": "repository_document", "id": str(document.id)},
                    "purpose": record.purpose,
                    "version_number": record.version_number,
                    "replaces_id": str(record.replaces.entity_id) if record.replaces is not None else None,
                    "filename": record.original_filename,
                    "media_type": record.media_type,
                    "size": record.size,
                    "checksum": record.checksum,
                },
            )
        )
    return tuple(result)


def verify_publication_file_manifest(manifest: dict[str, Any], content_id: uuid.UUID) -> bool:
    """Bind every signed file descriptor to one retained artifact, not today's files."""
    try:
        files = manifest["managed_files"]
        artifacts = manifest["artifacts"]
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_RETAINED_ATTACHMENTS:
            return False
        if len(artifacts) != len(files) + 1 or sum(a["kind"] == "pdf" for a in artifacts) != 1:
            return False
        by_id = {a["entity_id"]: a for a in artifacts if a["kind"] == "attachment"}
        if len(by_id) != len(files) or len({f["id"] for f in files}) != len(files):
            return False
        primary = []
        total = 0
        for item in files:
            artifact = by_id.pop(item["artifact_id"], None)
            if artifact is None or item["owner"] != {"type": "repository_document", "id": str(content_id)}:
                return False
            if artifact["source_attachment_id"] != item["id"] or any(
                artifact[key] != item[key] for key in ("filename", "media_type", "size", "checksum")
            ):
                return False
            total += item["size"]
            if item["purpose"] == "primary_file":
                primary.append(item)
            elif (
                item["purpose"] != "attachment" or item["version_number"] is not None or item["replaces_id"] is not None
            ):
                return False
        previous = None
        for number, item in enumerate(sorted(primary, key=lambda f: f["version_number"]), 1):
            if item["version_number"] != number or item["replaces_id"] != previous:
                return False
            previous = item["id"]
        projections = [{key: f[key] for key in ("id", "filename", "media_type", "size", "checksum")} for f in files]
        return not by_id and total <= MAX_RETAINED_ATTACHMENT_BYTES and manifest["attachments"] == projections
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
