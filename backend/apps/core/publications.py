from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from .data_flows import data_flow_projection
from .diagram_exports import (
    DiagramExportArtifact,
    diagram_manifest,
    diagram_sources,
    embed_diagrams_in_html,
    render_diagram_exports,
)
from .document_attachments import copy_attachment_content
from .document_keys import KEY_TARGET_SCHEME, keys_in_markdown
from .documents import PlacementConflict, resolve_document
from .entity_mentions import resolve_entity_mentions
from .models import (
    AuditEvent,
    Block,
    Document,
    DocumentAttachment,
    DocumentPlacement,
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    EntityVisibility,
    PublicationArtifactKind,
    PublicationAudience,
    PublicationControlAction,
)
from .outbox import OutboxTopic, enqueue_outbox_event
from .relationships import relationship_graph_projection
from .rendering import (
    RenderedAttachment,
    attachment_ids_in_markdown,
    entity_ids_in_markdown,
    render_markdown,
    render_pdf,
)
from .workspaces import ResolvedWorkspace

MANIFEST_VERSION = "tekdocs-static-publication/v2"
SIGNATURE_ALGORITHM = "Ed25519"
MAX_PUBLICATION_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_RETAINED_ATTACHMENTS = 50
MAX_RETAINED_ATTACHMENT_BYTES = 50 * 1024 * 1024


class PublicationConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PendingArtifact:
    id: UUID
    entity_id: UUID
    kind: str
    filename: str
    media_type: str
    content: bytes
    checksum: str
    source_attachment: DocumentAttachment | None = None


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


def _refuse_unfrozen_keys(markdown: str) -> None:
    """Refuse to publish content that still contains unresolved key expressions.

    Publication signs and retains exactly what a reader will see. Until publish-time
    resolution exists (ADR 0089, `0.8.39`), a key would be frozen into signed evidence
    as a visible "unresolved" marker — a permanent record of a value that was never
    resolved, in the artifact TekDocs offers as proof. Refusing is the fail-closed
    behaviour the record already commits to; the refusal disappears when the freeze
    lands, without weakening anything in the meantime.
    """
    keys, unparsable = keys_in_markdown(markdown)
    named = [key.expression for key in keys] + [target.removeprefix(KEY_TARGET_SCHEME) for target in unparsable]
    if named:
        raise PublicationConflict(
            "This document resolves keys from linked records, which cannot yet be frozen into a "
            f"STATIC publication: {', '.join(sorted(set(named)))}."
        )


def _resolved_attachments(
    *, document: Document, markdown: str
) -> tuple[list[dict[str, object]], dict[str, RenderedAttachment], list[DocumentAttachment]]:
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
    return manifest_records, rendered, records


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


def _artifact_descriptor(artifact: PendingArtifact) -> dict[str, object]:
    return {
        "id": str(artifact.id),
        "entity_id": str(artifact.entity_id),
        "kind": artifact.kind,
        "filename": artifact.filename,
        "media_type": artifact.media_type,
        "size": len(artifact.content),
        "checksum": artifact.checksum,
        "source_attachment_id": (
            str(artifact.source_attachment.entity_id) if artifact.source_attachment is not None else None
        ),
    }


def publish_document(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    actor_id: UUID,
    reason: str,
    audience: str,
    retention: str,
    retention_review_on: date | None,
    supersedes_entity_id: UUID | None = None,
) -> DocumentPublication:
    stored_artifacts: list[tuple[object, str]] = []
    try:
        with transaction.atomic():
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
            if len(resolved.markdown.encode("utf-8")) > MAX_PUBLICATION_MARKDOWN_BYTES:
                raise PublicationConflict("The resolved publication exceeds the 2 MiB rendering limit.")

            supersedes = None
            if supersedes_entity_id is not None:
                supersedes = (
                    DocumentPublication.objects.select_for_update()
                    .select_related("entity", "document")
                    .filter(entity_id=supersedes_entity_id)
                    .first()
                )
                if supersedes is None or (
                    supersedes.document_id != locked_document.id
                    or supersedes.tenant_id != locked_document.tenant_id
                    or supersedes.organization_id != locked_document.organization_id
                    or supersedes.audience != audience
                    or supersedes.lifecycle_state not in {"published", "review_due", "withdrawn"}
                ):
                    raise PublicationConflict("The selected STATIC publication cannot be superseded.")

            _refuse_unfrozen_keys(resolved.markdown)
            entity_projections = _resolved_entities(workspace=workspace, markdown=resolved.markdown)
            attachment_records, rendered_attachments, source_attachments = _resolved_attachments(
                document=locked_document,
                markdown=resolved.markdown,
            )
            if len(source_attachments) > MAX_RETAINED_ATTACHMENTS:
                raise PublicationConflict("A publication may retain at most 50 referenced attachments.")
            rendered_entities = {record["id"]: record for record in entity_projections}
            try:
                diagrams = render_diagram_exports(resolved.markdown, required=True)
            except ValueError as exc:
                # `render_diagram_exports` now names which of its failures occurred;
                # repeating that is what lets an author tell a renderer timeout from a
                # diagram the sanitizer refused.
                raise PublicationConflict(str(exc)) from exc
            sanitized_html = render_markdown(
                resolved.markdown,
                entity_mentions=rendered_entities,  # type: ignore[arg-type]
                attachments=rendered_attachments,
            )
            sanitized_html = embed_diagrams_in_html(sanitized_html, diagrams)

            publication_id = uuid4()
            publication_entity_id = uuid4()
            published_at = timezone.now()
            encoded_timestamp = _timestamp(published_at)
            pdf_content = render_pdf(
                resolved.markdown,
                title=locked_document.entity.display_name,
                publication_id=str(publication_entity_id),
                published_at=encoded_timestamp,
                audience=audience,
                reason=reason,
                diagrams=diagrams,
            )
            pending_artifacts = [
                PendingArtifact(
                    id=uuid4(),
                    entity_id=uuid4(),
                    kind=PublicationArtifactKind.PDF,
                    filename=f"{slugify(locked_document.entity.display_name) or 'publication'}-static.pdf",
                    media_type="application/pdf",
                    content=pdf_content,
                    checksum=hashlib.sha256(pdf_content).hexdigest(),
                )
            ]
            diagram_records: list[dict[str, object]] = []
            for item, record in zip(diagrams, diagram_manifest(diagrams), strict=True):
                if item.svg is None or item.png is None:
                    raise PublicationConflict("A required diagram artifact is unavailable.")
                svg_artifact = PendingArtifact(
                    id=uuid4(),
                    entity_id=uuid4(),
                    kind=PublicationArtifactKind.DIAGRAM_SVG,
                    filename=f"diagram-{item.source.index:03d}.svg",
                    media_type="image/svg+xml",
                    content=item.svg,
                    checksum=item.svg_checksum or "",
                )
                png_artifact = PendingArtifact(
                    id=uuid4(),
                    entity_id=uuid4(),
                    kind=PublicationArtifactKind.DIAGRAM_PNG,
                    filename=f"diagram-{item.source.index:03d}.png",
                    media_type="image/png",
                    content=item.png,
                    checksum=item.png_checksum or "",
                )
                pending_artifacts.extend((svg_artifact, png_artifact))
                diagram_records.append(
                    {
                        **record,
                        "svg_artifact_id": str(svg_artifact.entity_id),
                        "svg_filename": svg_artifact.filename,
                        "png_artifact_id": str(png_artifact.entity_id),
                        "png_filename": png_artifact.filename,
                    }
                )
            retained_size = 0
            for attachment in source_attachments:
                try:
                    content = copy_attachment_content(attachment)
                except ValidationError as exc:
                    raise PublicationConflict(
                        "A referenced attachment failed its retained-copy integrity check."
                    ) from exc
                retained_size += len(content)
                if retained_size > MAX_RETAINED_ATTACHMENT_BYTES:
                    raise PublicationConflict("Retained attachment bytes may not exceed 50 MiB per publication.")
                pending_artifacts.append(
                    PendingArtifact(
                        id=uuid4(),
                        entity_id=uuid4(),
                        kind=PublicationArtifactKind.ATTACHMENT,
                        filename=attachment.original_filename,
                        media_type=attachment.media_type,
                        content=content,
                        checksum=attachment.checksum,
                        source_attachment=attachment,
                    )
                )

            organization = locked_document.organization
            # Retained evidence states where data went at the moment of publication.
            # A client-visible artifact carries only flows whose anchor is itself
            # client-visible; flows are anchored MSP-private on creation, so this
            # excludes by default rather than including by default.
            data_flows_projection = data_flow_projection(
                workspace=workspace,
                related_visibility=(
                    EntityVisibility.CLIENT_VISIBLE if audience == PublicationAudience.CLIENT_VISIBLE else None
                ),
            )
            relationship_graph = relationship_graph_projection(
                workspace=workspace,
                family="document",
                root_entity_id=locked_document.entity_id,
                depth=3,
                edge_limit=200,
                related_visibility=(
                    EntityVisibility.CLIENT_VISIBLE if audience == PublicationAudience.CLIENT_VISIBLE else None
                ),
            )
            manifest: dict[str, Any] = {
                "format": MANIFEST_VERSION,
                "publication_id": str(publication_id),
                "publication_entity_id": str(publication_entity_id),
                "source_document_id": str(locked_document.entity_id),
                "workspace": {
                    "kind": "organization" if locked_document.organization_id else "msp",
                    "id": str(organization.entity_id) if organization is not None else None,
                },
                "title": locked_document.entity.display_name,
                "category": locked_document.category,
                "reason": reason,
                "audience": audience,
                "retention": retention,
                "retention_review_on": retention_review_on.isoformat() if retention_review_on else None,
                "supersedes_id": str(supersedes.entity_id) if supersedes is not None else None,
                "published_by": str(actor_id),
                "published_at": encoded_timestamp,
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
                "diagrams": diagram_records,
                "relationship_graph": relationship_graph,
                "data_flows": data_flows_projection,
                "artifacts": [_artifact_descriptor(artifact) for artifact in pending_artifacts],
            }
            payload = snapshot_payload(manifest=manifest, markdown=resolved.markdown, sanitized_html=sanitized_html)
            digest_bytes = hashlib.sha256(payload).digest()
            key = publication_signing_key()
            public_key, key_fingerprint = _encoded_public_key(key)
            visibility = (
                EntityVisibility.CLIENT_VISIBLE
                if audience == PublicationAudience.CLIENT_VISIBLE
                else EntityVisibility.MSP_PRIVATE
            )
            publication_entity = Entity.objects.create(
                id=publication_entity_id,
                tenant=locked_document.tenant,
                workspace=locked_document.entity.workspace,
                organization=locked_document.organization,
                entity_type="document_publication",
                display_name=locked_document.entity.display_name,
                visibility=visibility,
            )
            publication = DocumentPublication(
                id=publication_id,
                tenant=locked_document.tenant,
                organization=locked_document.organization,
                document=locked_document,
                entity=publication_entity,
                title=locked_document.entity.display_name,
                category=locked_document.category,
                reason=reason,
                audience=audience,
                retention=retention,
                retention_review_on=retention_review_on,
                supersedes=supersedes,
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
            submitted = DocumentPublicationControlEvent(
                tenant=publication.tenant,
                organization=publication.organization,
                publication=publication,
                action=PublicationControlAction.SUBMITTED,
                reason=reason,
                actor_id=actor_id,
                occurred_at=published_at,
            )
            submitted.full_clean()
            submitted.save()  # type: ignore[no-untyped-call]
            if audience == PublicationAudience.MSP_INTERNAL:
                approved = DocumentPublicationControlEvent(
                    tenant=publication.tenant,
                    organization=publication.organization,
                    publication=publication,
                    action=PublicationControlAction.APPROVED,
                    reason="Approved for MSP-internal distribution at publication time.",
                    actor_id=actor_id,
                    occurred_at=published_at + timedelta(microseconds=1),
                )
                approved.full_clean()
                approved.save()  # type: ignore[no-untyped-call]
            for pending in pending_artifacts:
                artifact_entity = Entity.objects.create(
                    id=pending.entity_id,
                    tenant=publication.tenant,
                    workspace=publication.entity.workspace,
                    organization=publication.organization,
                    entity_type="document_publication_artifact",
                    display_name=pending.filename,
                    visibility=visibility,
                )
                artifact = DocumentPublicationArtifact(
                    id=pending.id,
                    tenant=publication.tenant,
                    organization=publication.organization,
                    publication=publication,
                    entity=artifact_entity,
                    kind=pending.kind,
                    source_attachment=pending.source_attachment,
                    original_filename=pending.filename,
                    media_type=pending.media_type,
                    size=len(pending.content),
                    checksum=pending.checksum,
                    created_at=published_at,
                )
                artifact.file.save("retained", ContentFile(pending.content), save=False)
                stored_artifacts.append((artifact.file.storage, artifact.file.name))
                artifact.full_clean()
                artifact.save()  # type: ignore[no-untyped-call]
            AuditEvent.objects.create(
                tenant=locked_document.tenant,
                actor_id=actor_id,
                action=(
                    "document.publication.correction_submitted"
                    if supersedes is not None
                    else "document.publication.submitted"
                ),
                entity_id=publication.entity_id,
                metadata={"source_document_id": str(locked_document.entity_id)},
            )
            return publication
    except Exception:
        for storage, stored_name in stored_artifacts:
            storage.delete(stored_name)  # type: ignore[attr-defined]
        raise


def _append_control_event(
    *,
    publication: DocumentPublication,
    action: PublicationControlAction,
    actor_id: UUID,
    reason: str,
) -> DocumentPublicationControlEvent:
    event = DocumentPublicationControlEvent(
        tenant=publication.tenant,
        organization=publication.organization,
        publication=publication,
        action=action,
        reason=reason,
        actor_id=actor_id,
    )
    event.full_clean()
    event.save()  # type: ignore[no-untyped-call]
    return event


def _lock_publication_controls(*publication_ids: UUID) -> None:
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        for publication_id in sorted(set(publication_ids), key=str):
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"publication-control:{publication_id}"],
            )


def _client_reference_projection_safe(publication: DocumentPublication) -> bool:
    manifest_entities = publication.manifest.get("entities", [])
    if not isinstance(manifest_entities, list):
        return False
    try:
        reference_ids = {UUID(str(item["id"])) for item in manifest_entities if isinstance(item, dict)}
    except (KeyError, TypeError, ValueError):
        return False
    if len(reference_ids) != len(manifest_entities):
        return False
    visible_ids = set(
        Entity.objects.filter(
            id__in=reference_ids,
            tenant=publication.tenant,
            organization=publication.organization,
            visibility=EntityVisibility.CLIENT_VISIBLE,
        ).values_list("id", flat=True)
    )
    return visible_ids == reference_ids


@transaction.atomic
def approve_publication(*, publication: DocumentPublication, actor_id: UUID, reason: str) -> DocumentPublication:
    control_ids = [publication.id]
    if publication.supersedes_id is not None:
        control_ids.append(publication.supersedes_id)
    _lock_publication_controls(*control_ids)
    locked = DocumentPublication.objects.select_related("document", "entity", "published_by", "supersedes").get(
        pk=publication.pk
    )
    events = list(locked.control_events.order_by("occurred_at", "id"))
    actions = {event.action for event in events}
    if PublicationControlAction.WITHDRAWN in actions:
        raise PublicationConflict("A withdrawn publication cannot be approved.")
    if PublicationControlAction.APPROVED in actions:
        raise PublicationConflict("This publication is already approved.")
    if locked.audience != PublicationAudience.CLIENT_VISIBLE:
        raise PublicationConflict("MSP-internal publications are approved when they are created.")
    if not _client_reference_projection_safe(locked):
        raise PublicationConflict(
            "Client-visible publications may reference only client-visible records in this organization."
        )
    if locked.published_by_id == actor_id:
        raise PublicationConflict("Client-visible publication approval requires a different authorized user.")
    if locked.supersedes_id is not None:
        competing_successors = DocumentPublication.objects.filter(supersedes_id=locked.supersedes_id).exclude(
            pk=locked.pk
        )
        if DocumentPublicationControlEvent.objects.filter(
            publication__in=competing_successors,
            action=PublicationControlAction.APPROVED,
        ).exists():
            raise PublicationConflict("Another correction has already superseded the selected publication.")
    _append_control_event(
        publication=locked,
        action=PublicationControlAction.APPROVED,
        actor_id=actor_id,
        reason=reason,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.publication.approved",
        entity_id=locked.entity_id,
        metadata={"source_document_id": str(locked.document.entity_id)},
    )
    enqueue_outbox_event(
        tenant=locked.tenant,
        organization=locked.organization,
        topic=OutboxTopic.PUBLICATION_AVAILABLE,
        subject_id=locked.id,
        idempotency_key=f"publication-available:{locked.id}",
        payload={"audience": locked.audience},
    )
    return locked


@transaction.atomic
def withdraw_publication(*, publication: DocumentPublication, actor_id: UUID, reason: str) -> DocumentPublication:
    _lock_publication_controls(publication.id)
    locked = DocumentPublication.objects.select_related(
        "document", "document__entity", "entity", "published_by", "supersedes"
    ).get(pk=publication.pk)
    events = list(locked.control_events.order_by("occurred_at", "id"))
    actions = {event.action for event in events}
    if PublicationControlAction.WITHDRAWN in actions:
        raise PublicationConflict("This publication is already withdrawn.")
    if DocumentPublicationControlEvent.objects.filter(
        publication__supersedes=locked,
        action=PublicationControlAction.APPROVED,
    ).exists():
        raise PublicationConflict("A superseded publication cannot be withdrawn.")
    _append_control_event(
        publication=locked,
        action=PublicationControlAction.WITHDRAWN,
        actor_id=actor_id,
        reason=reason,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.publication.withdrawn",
        entity_id=locked.entity_id,
        metadata={"source_document_id": str(locked.document.entity_id)},
    )
    if locked.audience == PublicationAudience.CLIENT_VISIBLE:
        enqueue_outbox_event(
            tenant=locked.tenant,
            organization=locked.organization,
            topic=OutboxTopic.PUBLICATION_WITHDRAWN,
            subject_id=locked.id,
            idempotency_key=f"publication-withdrawn:{locked.id}",
            payload={"audience": locked.audience},
        )
    return locked


def publication_trusted_key_fingerprints() -> tuple[str, frozenset[str]]:
    _public_key, current_fingerprint = _encoded_public_key(publication_signing_key())
    retired = frozenset(getattr(settings, "TEKDOCS_PUBLICATION_RETIRED_KEY_FINGERPRINTS", ()))
    return current_fingerprint, retired | {current_fingerprint}


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
    current_key_fingerprint, trusted_fingerprints = publication_trusted_key_fingerprints()
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
        and publication.key_fingerprint in trusted_fingerprints
        and publication.signature_algorithm == SIGNATURE_ALGORITHM
    )
    return {
        "valid": valid,
        "digest_valid": digest_valid,
        "signature_valid": signature_valid,
        "key_fingerprint_valid": key_fingerprint_valid,
        "trusted_key": publication.key_fingerprint in trusted_fingerprints,
    }


def read_publication_artifact(artifact: DocumentPublicationArtifact) -> bytes:
    try:
        with artifact.file.storage.open(artifact.file.name, "rb") as stream:
            content = bytes(stream.read(artifact.size + 1))
    except OSError as exc:
        raise PublicationConflict("The retained publication artifact is unavailable.") from exc
    if len(content) != artifact.size or hashlib.sha256(content).hexdigest() != artifact.checksum:
        raise PublicationConflict("The retained publication artifact failed its integrity check.")
    return content


def retained_publication_diagrams(
    publication: DocumentPublication,
) -> tuple[DiagramExportArtifact, ...]:
    sources = diagram_sources(publication.canonical_markdown)
    if "diagrams" not in publication.manifest:
        return tuple(
            DiagramExportArtifact(
                source=source,
                state="text_fallback",
                renderer_version="legacy-static-text-fallback",
            )
            for source in sources
        )
    records = publication.manifest.get("diagrams", [])
    if not sources and records in (None, []):
        return ()
    if not isinstance(records, list) or len(records) != len(sources):
        raise PublicationConflict("The retained diagram manifest is invalid.")
    artifact_by_entity = {str(item.entity_id): item for item in publication.artifacts.all()}
    values: list[DiagramExportArtifact] = []
    try:
        for source, record in zip(sources, records, strict=True):
            if not isinstance(record, dict) or record.get("source_checksum") != source.source_checksum:
                raise PublicationConflict("The retained diagram manifest is invalid.")
            svg_artifact = artifact_by_entity[str(record["svg_artifact_id"])]
            png_artifact = artifact_by_entity[str(record["png_artifact_id"])]
            if (
                svg_artifact.kind != PublicationArtifactKind.DIAGRAM_SVG
                or png_artifact.kind != PublicationArtifactKind.DIAGRAM_PNG
            ):
                raise PublicationConflict("The retained diagram manifest is invalid.")
            svg = read_publication_artifact(svg_artifact)
            png = read_publication_artifact(png_artifact)
            value = DiagramExportArtifact(
                source=source,
                state="rendered",
                renderer_version=str(record["renderer_version"]),
                svg=svg,
                png=png,
            )
            if value.svg_checksum != record.get("svg_checksum") or value.png_checksum != record.get("png_checksum"):
                raise PublicationConflict("A retained diagram failed its integrity check.")
            values.append(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicationConflict("The retained diagram manifest is invalid.") from exc
    return tuple(values)
