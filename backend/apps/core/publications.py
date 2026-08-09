from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from .documents import PlacementConflict, resolve_document
from .entity_mentions import resolve_entity_mentions
from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentAttachment,
    DocumentPlacement,
    DocumentPublication,
    Entity,
)
from .rendering import RenderedAttachment, attachment_ids_in_markdown, entity_ids_in_markdown, render_markdown
from .workspaces import ResolvedWorkspace

MANIFEST_VERSION = "tekdocs-static-publication/v1"
SIGNATURE_ALGORITHM = "Ed25519"


class PublicationConflict(Exception):
    pass


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def snapshot_payload(*, manifest: object, markdown: str, sanitized_html: str) -> bytes:
    sections = (
        (b"manifest", canonical_json(manifest)),
        (b"markdown", markdown.encode("utf-8")),
        (b"html", sanitized_html.encode("utf-8")),
    )
    payload = bytearray(b"TEKDOCS-STATIC-SNAPSHOT\x00v1\x00")
    for label, content in sections:
        payload.extend(len(label).to_bytes(2, "big"))
        payload.extend(label)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    return bytes(payload)


def _decode_signing_key(value: str) -> bytes:
    if re.fullmatch(r"[A-Za-z0-9_-]{43}=", value) is None:
        raise ImproperlyConfigured("TEKDOCS_PUBLICATION_SIGNING_KEY must be URL-safe base64 encoded")
    try:
        decoded = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ImproperlyConfigured("TEKDOCS_PUBLICATION_SIGNING_KEY must be URL-safe base64 encoded") from exc
    if len(decoded) != 32:
        raise ImproperlyConfigured("TEKDOCS_PUBLICATION_SIGNING_KEY must encode exactly 32 bytes")
    return decoded


def publication_signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_decode_signing_key(settings.TEKDOCS_PUBLICATION_SIGNING_KEY))


def _encoded_public_key(key: Ed25519PrivateKey) -> tuple[str, str]:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _resolved_attachments(
    *, document: Document, markdown: str
) -> tuple[list[dict[str, object]], dict[str, RenderedAttachment]]:
    requested = attachment_ids_in_markdown(markdown)
    records = list(
        DocumentAttachment.objects.select_for_update()
        .filter(document=document, entity_id__in=requested, archived_at__isnull=True)
        .order_by("entity_id")
    )
    if {record.entity_id for record in records} != requested:
        raise PublicationConflict("The document contains an unavailable managed attachment reference.")
    manifest_records: list[dict[str, object]] = []
    rendered: dict[str, RenderedAttachment] = {}
    for record in records:
        projection = {
            "id": str(record.entity_id),
            "filename": record.original_filename,
            "media_type": record.media_type,
            "size": record.size,
            "checksum": record.checksum,
        }
        manifest_records.append(projection)
        rendered[str(record.entity_id)] = {
            "id": str(record.entity_id),
            "filename": record.original_filename,
            "size": record.size,
        }
    return manifest_records, rendered


def _resolved_entities(*, workspace: ResolvedWorkspace, markdown: str) -> list[dict[str, str]]:
    requested = entity_ids_in_markdown(markdown)
    projections = resolve_entity_mentions(workspace=workspace, markdown=markdown)
    if {UUID(entity_id) for entity_id in projections} != requested:
        raise PublicationConflict("The document contains an unavailable entity reference.")
    return [
        {
            "id": projections[entity_id]["id"],
            "display_name": projections[entity_id]["display_name"],
            "entity_type": projections[entity_id]["entity_type"],
            "workspace_label": projections[entity_id]["workspace_label"],
        }
        for entity_id in sorted(projections)
    ]


@transaction.atomic
def publish_document(*, workspace: ResolvedWorkspace, document: Document, actor_id: UUID) -> DocumentPublication:
    locked_document = (
        Document.objects.select_for_update(of=("self",))
        .select_related("tenant", "organization", "organization__entity", "entity")
        .get(pk=document.pk)
    )
    placements = list(
        DocumentPlacement.objects.select_for_update(of=("self",))
        .filter(document=locked_document)
        .select_related("block", "block__entity", "block__current_revision", "parent", "pinned_revision")
        .order_by("id")
    )
    block_ids = sorted({placement.block_id for placement in placements}, key=str)
    list(Block.objects.select_for_update().filter(id__in=block_ids).order_by("id"))
    # Refresh the placement graph after the block locks are held. A concurrent
    # shared-block edit may have advanced current_revision while the initial
    # placement query was waiting for those locks.
    placements = list(
        DocumentPlacement.objects.select_for_update(of=("self",))
        .filter(document=locked_document)
        .select_related("block", "block__entity", "block__current_revision", "parent", "pinned_revision")
        .order_by("id")
    )
    locked_document.__dict__["active_placements"] = placements
    try:
        resolved = resolve_document(locked_document)
    except PlacementConflict as exc:
        raise PublicationConflict(str(exc)) from exc

    entity_projections = _resolved_entities(workspace=workspace, markdown=resolved.markdown)
    attachment_records, rendered_attachments = _resolved_attachments(
        document=locked_document,
        markdown=resolved.markdown,
    )
    rendered_entities = {record["id"]: record for record in entity_projections}
    sanitized_html = render_markdown(
        resolved.markdown,
        entity_mentions=rendered_entities,  # type: ignore[arg-type]
        attachments=rendered_attachments,
    )

    publication_id = uuid4()
    published_at = timezone.now()
    publication_entity = Entity.objects.create(
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        entity_type="document_publication",
        display_name=locked_document.entity.display_name,
    )
    organization = locked_document.organization
    manifest: dict[str, Any] = {
        "format": MANIFEST_VERSION,
        "publication_id": str(publication_id),
        "publication_entity_id": str(publication_entity.id),
        "source_document_id": str(locked_document.entity_id),
        "workspace": {
            "kind": "organization" if locked_document.organization_id else "msp",
            "id": str(organization.entity_id) if organization is not None else None,
        },
        "title": locked_document.entity.display_name,
        "category": locked_document.category,
        "published_by": str(actor_id),
        "published_at": _timestamp(published_at),
        "placements": [
            {
                "id": str(item.placement.id),
                "parent_id": str(item.placement.parent_id) if item.placement.parent_id else None,
                "position": item.placement.position,
                "depth": item.depth,
                "block_id": str(item.placement.block.entity_id),
                "resolution_mode": item.placement.resolution_mode,
                "revision_id": str(item.revision.id),
                "revision_number": item.revision.revision_number,
                "checksum": item.revision.checksum,
            }
            for item in resolved.placements
        ],
        "entities": entity_projections,
        "attachments": attachment_records,
    }
    payload = snapshot_payload(
        manifest=manifest,
        markdown=resolved.markdown,
        sanitized_html=sanitized_html,
    )
    digest_bytes = hashlib.sha256(payload).digest()
    key = publication_signing_key()
    public_key, key_fingerprint = _encoded_public_key(key)
    publication = DocumentPublication(
        id=publication_id,
        tenant=locked_document.tenant,
        organization=locked_document.organization,
        document=locked_document,
        entity=publication_entity,
        title=locked_document.entity.display_name,
        category=locked_document.category,
        canonical_markdown=resolved.markdown,
        sanitized_html=sanitized_html,
        manifest=manifest,
        content_digest=digest_bytes.hex(),
        signature=base64.urlsafe_b64encode(key.sign(digest_bytes)).decode("ascii"),
        signature_algorithm=SIGNATURE_ALGORITHM,
        public_key=public_key,
        key_fingerprint=key_fingerprint,
        published_by_id=actor_id,
        published_at=published_at,
    )
    publication.full_clean()
    publication.save()  # type: ignore[no-untyped-call]
    AuditEvent.objects.create(
        tenant=locked_document.tenant,
        actor_id=actor_id,
        action="document.publication.created",
        entity_id=publication.entity_id,
        metadata={"source_document_id": str(locked_document.entity_id)},
    )
    return publication


def verify_publication(publication: DocumentPublication) -> dict[str, bool]:
    payload = snapshot_payload(
        manifest=publication.manifest,
        markdown=publication.canonical_markdown,
        sanitized_html=publication.sanitized_html,
    )
    calculated = hashlib.sha256(payload).digest()
    digest_valid = calculated.hex() == publication.content_digest
    signature_valid = False
    key_fingerprint_valid = False
    try:
        raw_public_key = base64.b64decode(publication.public_key.encode("ascii"), altchars=b"-_", validate=True)
        signature = base64.b64decode(publication.signature.encode("ascii"), altchars=b"-_", validate=True)
        key_fingerprint_valid = hashlib.sha256(raw_public_key).hexdigest() == publication.key_fingerprint
        Ed25519PublicKey.from_public_bytes(raw_public_key).verify(signature, calculated)
        signature_valid = True
    except (UnicodeEncodeError, binascii.Error, ValueError, InvalidSignature):
        signature_valid = False
    valid = (
        digest_valid
        and signature_valid
        and key_fingerprint_valid
        and publication.signature_algorithm == SIGNATURE_ALGORITHM
    )
    return {
        "valid": valid,
        "digest_valid": digest_valid,
        "signature_valid": signature_valid,
        "key_fingerprint_valid": key_fingerprint_valid,
    }
