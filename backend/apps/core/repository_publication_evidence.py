"""Signed, retained Git-source evidence for a future repository STATIC publisher.

This internal record is not a distributable publication: staff may review its
retained PDF and files, but no route approves or exposes them to portals. Its
signature binds the exact source proof and composed Markdown without live Git
verification.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from datetime import UTC
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.policy import (
    DataAudience,
    InstallationMemberContext,
    PermissionKey,
    entity_visible_to_audience,
    require_permission,
)

from .content_index_models import ContentNode, ContentNodeKind
from .content_publication_sources import pinned_git_document_dependencies
from .document_attachments import copy_attachment_content
from .document_key_freeze import KeyFreezeConflict, freeze_document_keys, verify_frozen_field_keys
from .document_key_models import DocumentKeyBinding
from .document_keys import key_targets_in_markdown
from .document_migration_keys import DocumentMigrationKeyError, portable_document_keys
from .entity_mentions import resolve_entity_mentions
from .models import (
    AuditEvent,
    Document,
    DocumentAttachment,
    Entity,
    PublicationAudience,
    RepositoryEvidenceAttachment,
    RepositoryPublicationEvidence,
    WorkspaceRepository,
)
from .publications import (
    MAX_PUBLICATION_MARKDOWN_BYTES,
    MAX_RETAINED_ATTACHMENT_BYTES,
    MAX_RETAINED_ATTACHMENTS,
    SIGNATURE_ALGORITHM,
    canonical_json,
    publication_signing_key,
    publication_trusted_key_fingerprints,
)
from .rendering import attachment_ids_in_markdown, entity_ids_in_markdown
from .repository_publication_preflight import PREFLIGHT_FORMAT, repository_publication_preflight
from .repository_publication_render import (
    MAX_RENDERED_PDF_BYTES,
    pdf_snapshot_matches_current_renderer,
    rendered_snapshot_matches_current_renderer,
    retained_pdf_snapshot,
    retained_rendered_snapshot,
    verify_retained_pdf_snapshot,
    verify_retained_rendered_snapshot,
)
from .topic_schemas import SCHEMAS
from .workspaces import resolve_msp_workspace, resolve_organization_workspace

EVIDENCE_FORMAT = "tekdocs-repository-publication-evidence/v1"


class RepositoryPublicationEvidenceError(RuntimeError):
    """A repository source cannot be retained as signed evidence."""


def _frozen_entity_cards(
    *,
    repository: WorkspaceRepository,
    markdown: str,
    audience: str,
    actor: User,
    member: InstallationMemberContext,
) -> list[dict[str, str]]:
    """Freeze only permission-visible, exact-Workspace entity display cards."""

    requested = entity_ids_in_markdown(markdown)
    if not requested:
        return []
    if len(requested) > 200:
        raise RepositoryPublicationEvidenceError("Repository publication preflight blocked: repository.entity.limit")
    organization = repository.workspace.organization
    workspace = (
        resolve_organization_workspace(actor, entity_id=organization.entity_id)
        if organization is not None
        else resolve_msp_workspace(actor)
    )
    projections = resolve_entity_mentions(workspace=workspace, markdown=markdown, lock=True)
    if set(projections) != {str(entity_id) for entity_id in requested}:
        raise RepositoryPublicationEvidenceError(
            "Repository publication preflight blocked: repository.entity.unavailable"
        )
    records = {
        entity.id: entity
        for entity in Entity.objects.filter(
            id__in=requested,
            tenant_id=repository.tenant_id,
            workspace_id=repository.workspace_id,
            organization=organization,
            archived_at__isnull=True,
        )
    }
    data_audience = (
        DataAudience.CLIENT_PORTAL if audience == PublicationAudience.CLIENT_VISIBLE else DataAudience.MSP_STAFF
    )
    if len(records) != len(requested) or any(
        not entity_visible_to_audience(member, records[entity_id], audience=data_audience, organization=organization)
        for entity_id in requested
        if entity_id in records
    ):
        raise RepositoryPublicationEvidenceError(
            "Repository publication preflight blocked: repository.entity.unavailable"
        )
    return [
        {
            "id": projections[str(entity_id)]["id"],
            "display_name": projections[str(entity_id)]["display_name"],
            "entity_type": projections[str(entity_id)]["entity_type"],
            "workspace_label": projections[str(entity_id)]["workspace_label"],
        }
        for entity_id in sorted(requested)
    ]


def evidence_payload(*, manifest: dict[str, Any], markdown: str) -> bytes:
    sections = ((b"manifest", canonical_json(manifest)), (b"markdown", markdown.encode("utf-8")))
    payload = bytearray(b"TEKDOCS-REPOSITORY-PUBLICATION-EVIDENCE\x00v1\x00")
    for label, content in sections:
        payload.extend(len(label).to_bytes(2, "big"))
        payload.extend(label)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    return bytes(payload)


def _frozen_key_snapshot(
    *, repository: WorkspaceRepository, node: ContentNode, document: Document | None,
    markdown: str, audience: str, actor: User, signed_at: str,
) -> dict[str, Any] | None:
    """Freeze only portable field keys whose authored bindings match the live owner."""
    if not key_targets_in_markdown(markdown):
        return None
    if document is None:
        raise RepositoryPublicationEvidenceError("Repository publication preflight blocked: repository.key.unavailable")
    # Hold active binding identities stable through portable parity and resolution.
    list(DocumentKeyBinding.objects.select_for_update().filter(document=document, archived_at__isnull=True))
    try:
        bindings, _identities = portable_document_keys(document, markdown)
        if bindings != node.frontmatter.get("key_bindings", {}):
            raise RepositoryPublicationEvidenceError(
                "Repository publication preflight blocked: repository.key.binding_mismatch"
            )
        organization = repository.workspace.organization
        workspace = (
            resolve_organization_workspace(actor, entity_id=organization.entity_id)
            if organization is not None else resolve_msp_workspace(actor)
        )
        frozen = freeze_document_keys(
            workspace=workspace,
            document=document,
            markdown=markdown,
            audience=(
                DataAudience.CLIENT_PORTAL
                if audience == PublicationAudience.CLIENT_VISIBLE
                else DataAudience.MSP_STAFF
            ),
            resolved_at=signed_at,
            lock=True,
        )
    except (DocumentMigrationKeyError, KeyFreezeConflict) as exc:
        raise RepositoryPublicationEvidenceError(
            "Repository publication preflight blocked: repository.key.unavailable"
        ) from exc
    if len(frozen.markdown.encode("utf-8")) > MAX_PUBLICATION_MARKDOWN_BYTES:
        raise RepositoryPublicationEvidenceError("Repository publication preflight blocked: repository.key.limit")
    snapshot = {
        "markdown": frozen.markdown,
        "sha256": hashlib.sha256(frozen.markdown.encode("utf-8")).hexdigest(),
        "records": list(frozen.manifest_records),
    }
    if not verify_frozen_field_keys(markdown, snapshot):
        raise RepositoryPublicationEvidenceError("Repository publication preflight blocked: repository.key.unavailable")
    return snapshot


def retain_repository_publication_evidence(
    *, repository_id: uuid.UUID, content_id: uuid.UUID, audience: str, actor: User
) -> RepositoryPublicationEvidence:
    """Sign and insert one exact source snapshot under the accepted-head lock."""

    if audience not in PublicationAudience.values:
        raise RepositoryPublicationEvidenceError("Publication audience is unsupported")
    repository = WorkspaceRepository.objects.select_related("workspace__organization").get(pk=repository_id)
    member = require_permission(actor, PermissionKey.DOCUMENTS_PUBLISH, organization=repository.workspace.organization)
    if member.tenant.id != repository.tenant_id:
        raise RepositoryPublicationEvidenceError("Publication source belongs to another installation")
    if audience == PublicationAudience.CLIENT_VISIBLE and repository.workspace.organization_id is None:
        raise RepositoryPublicationEvidenceError("Client-visible evidence requires an organization workspace")

    stored_files: list[tuple[Any, str]] = []
    try:
        return _retain_pinned_evidence(
            repository=repository,
            content_id=content_id,
            audience=audience,
            actor=actor,
            member=member,
            stored_files=stored_files,
        )
    except Exception:
        for storage, name in stored_files:
            storage.delete(name)
        raise


def _retain_pinned_evidence(
    *,
    repository: WorkspaceRepository,
    content_id: uuid.UUID,
    audience: str,
    actor: User,
    member: InstallationMemberContext,
    stored_files: list[tuple[Any, str]],
) -> RepositoryPublicationEvidence:
    with pinned_git_document_dependencies(
        repository_id=repository.id, content_id=content_id, audience=audience
    ) as source:
        repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
        if repository.accepted_commit_id is None or repository.accepted_commit_id != repository.indexed_commit_id:
            raise RepositoryPublicationEvidenceError("Repository source changed before retention")
        node = ContentNode.objects.filter(
            repository_id=repository.id,
            content_id=content_id,
            indexed_commit_id=repository.accepted_commit_id,
            kind=ContentNodeKind.DOCUMENT,
        ).first()
        if node is None:
            raise RepositoryPublicationEvidenceError("Indexed repository document is unavailable")
        variant = node.composition_variants.get(audience)
        if not isinstance(variant, dict) or not isinstance(variant.get("markdown"), str):
            raise RepositoryPublicationEvidenceError("Indexed repository composition is unavailable")
        markdown = variant["markdown"]
        signed_at = timezone.now()
        signed_at_text = signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        if (
            len(markdown.encode("utf-8")) > MAX_PUBLICATION_MARKDOWN_BYTES
            or hashlib.sha256(markdown.encode("utf-8")).hexdigest() != source["markdown_sha256"]
            or variant.get("digest") != source["composition_digest"]
        ):
            raise RepositoryPublicationEvidenceError("Indexed repository composition differs from its Git source")
        attachment_ids = attachment_ids_in_markdown(markdown)
        key_targets = key_targets_in_markdown(markdown)
        if len(attachment_ids) > MAX_RETAINED_ATTACHMENTS:
            raise RepositoryPublicationEvidenceError(
                "Repository publication preflight blocked: repository.attachment.limit"
            )
        retained: list[tuple[DocumentAttachment, bytes, uuid.UUID]] = []
        source_ids_by_attachment_id: dict[uuid.UUID, uuid.UUID] = {}
        document: Document | None = None
        if attachment_ids or key_targets:
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
            if document is None:
                raise RepositoryPublicationEvidenceError(
                    "Repository publication preflight blocked: "
                    + ("repository.attachment.unavailable" if attachment_ids else "repository.key.unavailable")
                )
        if attachment_ids:
            attachments = (
                DocumentAttachment.objects.select_for_update()
                .filter(
                    Q(entity_id__in=attachment_ids) | Q(id__in=attachment_ids),
                    document=document,
                    tenant_id=repository.tenant_id,
                    organization=repository.workspace.organization,
                    archived_at__isnull=True,
                    purpose="attachment",
                    scan_status="clean",
                )
                .order_by("id")
            )
            if attachments.count() != len(attachment_ids):
                raise RepositoryPublicationEvidenceError(
                    "Repository publication preflight blocked: repository.attachment.unavailable"
                )
            total_bytes = 0
            for attachment in attachments:
                # Public Markdown uses the attachment Entity ID. Continue to
                # accept record-ID links already present in repository sources.
                matches = attachment_ids.intersection({attachment.entity_id, attachment.id})
                if len(matches) != 1:
                    raise RepositoryPublicationEvidenceError(
                        "Repository publication preflight blocked: repository.attachment.unavailable"
                    )
                source_ids_by_attachment_id[attachment.id] = next(iter(matches))
                try:
                    content = copy_attachment_content(attachment)
                except ValidationError as exc:
                    raise RepositoryPublicationEvidenceError(
                        "Repository publication preflight blocked: repository.attachment.integrity"
                    ) from exc
                total_bytes += len(content)
                if total_bytes > MAX_RETAINED_ATTACHMENT_BYTES:
                    raise RepositoryPublicationEvidenceError(
                        "Repository publication preflight blocked: repository.attachment.limit"
                    )
                retained.append((attachment, content, uuid.uuid4()))
            if set(source_ids_by_attachment_id.values()) != attachment_ids:
                raise RepositoryPublicationEvidenceError(
                    "Repository publication preflight blocked: repository.attachment.unavailable"
                )
        key_snapshot = _frozen_key_snapshot(
            repository=repository, node=node, document=document,
            markdown=markdown, audience=audience, actor=actor, signed_at=signed_at_text,
        )
        entity_cards = _frozen_entity_cards(
            repository=repository, markdown=markdown, audience=audience, actor=actor, member=member
        )
        preflight = repository_publication_preflight(
            markdown=markdown,
            audience=audience,
            topic_type=node.topic_type,
            frozen_attachment_ids=set(source_ids_by_attachment_id.values()),
            frozen_entity_ids={uuid.UUID(item["id"]) for item in entity_cards},
            frozen_key_targets=set(key_targets) if key_snapshot is not None else None,
        )
        if preflight["blockers"]:
            raise RepositoryPublicationEvidenceError(
                "Repository publication preflight blocked: " + ", ".join(preflight["blockers"])
            )

        evidence_id = uuid.uuid4()
        source_commit = repository.accepted_commit
        if source_commit is None:  # pragma: no cover - guarded above
            raise RepositoryPublicationEvidenceError("Repository accepted commit is unavailable")
        manifest: dict[str, Any] = {
            "format": EVIDENCE_FORMAT,
            "evidence_id": str(evidence_id),
            "workspace_id": str(repository.workspace_id),
            "repository_id": str(repository.id),
            "source_commit": source_commit.object_id,
            "content_id": str(content_id),
            "audience": audience,
            "topic_type": node.topic_type,
            "title": node.title,
            "signed_at": signed_at_text,
            "signed_by": str(actor.id),
            "source": source,
            "preflight": preflight,
            "attachments": [
                {
                    "id": str(artifact_id),
                    "source_id": str(source_ids_by_attachment_id[attachment.id]),
                    "checksum": attachment.checksum,
                    "size": len(content),
                    "media_type": attachment.media_type,
                    "filename": attachment.original_filename,
                }
                for attachment, content, artifact_id in retained
            ],
            "entity_cards": entity_cards,
        }
        if key_snapshot is not None:
            manifest["key_snapshot"] = key_snapshot
        try:
            manifest["rendered_snapshot"] = retained_rendered_snapshot(markdown=markdown, manifest=manifest)
            manifest["pdf_snapshot"], pdf_content = retained_pdf_snapshot(markdown=markdown, manifest=manifest)
        except (ValueError, TypeError) as exc:
            raise RepositoryPublicationEvidenceError(
                "Repository publication preflight blocked: repository.render.unavailable"
            ) from exc
        digest = hashlib.sha256(evidence_payload(manifest=manifest, markdown=markdown)).digest()
        key = publication_signing_key()
        raw_public_key = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        evidence = RepositoryPublicationEvidence(
            id=evidence_id,
            tenant_id=repository.tenant_id,
            organization_id=repository.workspace.organization_id,
            workspace_id=repository.workspace_id,
            repository=repository,
            source_commit=source_commit,
            content_id=content_id,
            audience=audience,
            canonical_markdown=markdown,
            manifest=manifest,
            content_digest=digest.hex(),
            signature=base64.urlsafe_b64encode(key.sign(digest)).decode("ascii"),
            signature_algorithm=SIGNATURE_ALGORITHM,
            public_key=base64.urlsafe_b64encode(raw_public_key).decode("ascii"),
            key_fingerprint=hashlib.sha256(raw_public_key).hexdigest(),
            signed_by=actor,
            signed_at=signed_at,
        )
        evidence.pdf_file.save("snapshot.pdf", ContentFile(pdf_content), save=False)
        stored_files.append((evidence.pdf_file.storage, evidence.pdf_file.name))
        evidence.full_clean()
        evidence.save()  # type: ignore[no-untyped-call]
        for attachment, content, artifact_id in retained:
            artifact = RepositoryEvidenceAttachment(
                id=artifact_id,
                tenant_id=repository.tenant_id,
                organization_id=repository.workspace.organization_id,
                workspace_id=repository.workspace_id,
                evidence=evidence,
                source_attachment=attachment,
                media_type=attachment.media_type,
                size=len(content),
                checksum=attachment.checksum,
            )
            artifact.file.save("retained", ContentFile(content), save=False)
            stored_files.append((artifact.file.storage, artifact.file.name))
            artifact.full_clean()
            artifact.save()  # type: ignore[no-untyped-call]
        AuditEvent.objects.create(
            tenant_id=repository.tenant_id,
            actor=actor,
            action="repository.publication_evidence.signed",
            entity_id=evidence.id,
            metadata={"repository_id": str(repository.id), "content_id": str(content_id)},
        )
        return evidence


def verify_repository_publication_evidence(
    evidence: RepositoryPublicationEvidence, *, compare_current_renderer: bool = False
) -> dict[str, bool]:
    """Verify signed retained bytes offline; compare today's renderer only when requested."""

    manifest = evidence.manifest
    source = manifest.get("source") if isinstance(manifest, dict) else None
    identity_valid = isinstance(source, dict) and all(
        (
            manifest.get("format") == EVIDENCE_FORMAT,
            manifest.get("evidence_id") == str(evidence.id),
            manifest.get("workspace_id") == str(evidence.workspace_id),
            manifest.get("repository_id") == str(evidence.repository_id),
            manifest.get("content_id") == str(evidence.content_id),
            manifest.get("audience") == evidence.audience,
            manifest.get("signed_by") == str(evidence.signed_by_id),
            manifest.get("signed_at")
            == evidence.signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            source.get("format") == "tekdocs.git-dependencies/v1",
            source.get("workspace_id") == str(evidence.workspace_id),
            source.get("repository_id") == str(evidence.repository_id),
            source.get("content_id") == str(evidence.content_id),
            source.get("audience") == evidence.audience,
            source.get("root_title") is None or source.get("root_title") == manifest.get("title"),
            source.get("accepted_commit") == manifest.get("source_commit"),
            source.get("markdown_sha256") == hashlib.sha256(evidence.canonical_markdown.encode("utf-8")).hexdigest(),
        )
    )
    preflight = manifest.get("preflight") if isinstance(manifest, dict) else None
    preflight_attested = isinstance(preflight, dict) and all(
        (
            preflight.get("format") == PREFLIGHT_FORMAT,
            preflight.get("audience") == evidence.audience,
            preflight.get("markdown_sha256") == hashlib.sha256(evidence.canonical_markdown.encode("utf-8")).hexdigest(),
            preflight.get("blockers") == [],
        )
    )
    if preflight is not None:
        identity_valid = identity_valid and preflight_attested
    topic_type = manifest.get("topic_type") if isinstance(manifest, dict) else None
    dependency_closure_attested = False
    if isinstance(topic_type, str) and (not topic_type or topic_type in SCHEMAS) and isinstance(preflight, dict):
        descriptors = manifest.get("attachments")
        cards_for_preflight = manifest.get("entity_cards")
        if isinstance(descriptors, list) and isinstance(cards_for_preflight, list):
            attachment_targets = {
                descriptor["source_id"] for descriptor in descriptors
                if isinstance(descriptor, dict) and isinstance(descriptor.get("source_id"), str)
            }
            entity_targets = {
                card["id"] for card in cards_for_preflight
                if isinstance(card, dict) and isinstance(card.get("id"), str)
            }
            try:
                frozen_attachments = {uuid.UUID(item) for item in attachment_targets}
                frozen_entities = {uuid.UUID(item) for item in entity_targets}
            except ValueError:
                pass
            else:
                key_targets = key_targets_in_markdown(evidence.canonical_markdown)
                dependency_closure_attested = (
                    len(attachment_targets) == len(descriptors)
                    and len(entity_targets) == len(cards_for_preflight)
                    and preflight == repository_publication_preflight(
                        markdown=evidence.canonical_markdown,
                        audience=evidence.audience,
                        topic_type=topic_type,
                        frozen_attachment_ids=frozen_attachments,
                        frozen_entity_ids=frozen_entities,
                        frozen_key_targets=set(key_targets) if manifest.get("key_snapshot") is not None else None,
                    )
                )
    requested_entities = entity_ids_in_markdown(evidence.canonical_markdown)
    cards = manifest.get("entity_cards") if isinstance(manifest, dict) else None
    entity_cards_valid = (
        not requested_entities
        if cards is None
        else (
            isinstance(cards, list)
            and len(cards) <= 200
            and all(
                isinstance(card, dict)
                and set(card) == {"id", "display_name", "entity_type", "workspace_label"}
                and all(isinstance(card[field], str) and card[field] for field in card)
                for card in cards
            )
            and [card["id"] for card in cards] == [str(entity_id) for entity_id in sorted(requested_entities)]
        )
    )
    key_snapshot = manifest.get("key_snapshot") if isinstance(manifest, dict) else None
    key_snapshot_valid = (
        not key_targets_in_markdown(evidence.canonical_markdown)
        if key_snapshot is None else verify_frozen_field_keys(evidence.canonical_markdown, key_snapshot)
    )
    rendered_snapshot = manifest.get("rendered_snapshot") if isinstance(manifest, dict) else None
    rendered_snapshot_valid = (
        rendered_snapshot is None
        or verify_retained_rendered_snapshot(manifest=manifest)
    )
    rendered_snapshot_reproducible = (
        compare_current_renderer
        and rendered_snapshot_valid
        and rendered_snapshot is not None
        and rendered_snapshot_matches_current_renderer(markdown=evidence.canonical_markdown, manifest=manifest)
    )
    pdf_snapshot = manifest.get("pdf_snapshot") if isinstance(manifest, dict) else None
    pdf_snapshot_valid = pdf_snapshot is None and not evidence.pdf_file.name
    pdf_snapshot_reproducible = False
    if pdf_snapshot is not None and evidence.pdf_file.name:
        try:
            with evidence.pdf_file.storage.open(evidence.pdf_file.name, "rb") as stream:
                pdf_content = bytes(stream.read(MAX_RENDERED_PDF_BYTES + 1))
            pdf_snapshot_valid = verify_retained_pdf_snapshot(
                manifest=manifest, content=pdf_content
            )
            if compare_current_renderer and pdf_snapshot_valid:
                pdf_snapshot_reproducible = pdf_snapshot_matches_current_renderer(
                    markdown=evidence.canonical_markdown, manifest=manifest, content=pdf_content
                )
        except (OSError, ValueError, TypeError):
            pdf_snapshot_valid = False
    attachments_valid = True
    descriptors = manifest.get("attachments") if isinstance(manifest, dict) else None
    if descriptors is not None:
        if not isinstance(descriptors, list) or len(descriptors) > MAX_RETAINED_ATTACHMENTS:
            attachments_valid = False
        else:
            requested_attachments = {str(item) for item in attachment_ids_in_markdown(evidence.canonical_markdown)}
            descriptor_sources = [item.get("source_id") for item in descriptors if isinstance(item, dict)]
            if (
                len(descriptor_sources) != len(descriptors)
                or not all(isinstance(item, str) for item in descriptor_sources)
                or set(descriptor_sources) != requested_attachments
            ):
                attachments_valid = False
            artifacts = {str(item.id): item for item in evidence.attachments.all()}
            if len(artifacts) != len(descriptors):
                attachments_valid = False
            for descriptor in descriptors:
                if not isinstance(descriptor, dict):
                    attachments_valid = False
                    continue
                descriptor_id = descriptor.get("id")
                artifact = artifacts.get(descriptor_id) if isinstance(descriptor_id, str) else None
                if artifact is None or any(
                    (
                        descriptor.get("source_id") not in {
                            str(artifact.source_attachment_id), str(artifact.source_attachment.entity_id)
                        },
                        descriptor.get("checksum") != artifact.checksum,
                        descriptor.get("size") != artifact.size,
                        descriptor.get("media_type") != artifact.media_type,
                        artifact.evidence_id != evidence.id,
                        artifact.workspace_id != evidence.workspace_id,
                    )
                ):
                    attachments_valid = False
                    continue
                if artifact.size > MAX_RETAINED_ATTACHMENT_BYTES:
                    attachments_valid = False
                    continue
                try:
                    with artifact.file.storage.open(artifact.file.name, "rb") as stream:
                        content = bytes(stream.read(artifact.size + 1))
                    if len(content) != artifact.size or hashlib.sha256(content).hexdigest() != artifact.checksum:
                        attachments_valid = False
                except (OSError, ValueError, TypeError):
                    attachments_valid = False
    try:
        source_commit = evidence.source_commit
        identity_valid = (
            identity_valid
            and isinstance(source, dict)
            and (
                source_commit.object_id == manifest.get("source_commit")
                and source_commit.repository_id == evidence.repository_id
                and source_commit.object_format == source.get("object_format")
            )
        )
    except (AttributeError, TypeError):
        identity_valid = False

    digest_valid = False
    signature_valid = False
    key_fingerprint_valid = False
    try:
        payload = evidence_payload(manifest=manifest, markdown=evidence.canonical_markdown)
        digest = hashlib.sha256(payload).digest()
        digest_valid = digest.hex() == evidence.content_digest
        raw_public_key = base64.b64decode(evidence.public_key.encode("ascii"), altchars=b"-_", validate=True)
        signature = base64.b64decode(evidence.signature.encode("ascii"), altchars=b"-_", validate=True)
        key_fingerprint_valid = hashlib.sha256(raw_public_key).hexdigest() == evidence.key_fingerprint
        Ed25519PublicKey.from_public_bytes(raw_public_key).verify(signature, digest)
        signature_valid = True
    except (UnicodeEncodeError, binascii.Error, ValueError, InvalidSignature, TypeError):
        pass
    _current, trusted = publication_trusted_key_fingerprints()
    valid = (
        identity_valid
        and digest_valid
        and signature_valid
        and key_fingerprint_valid
        and evidence.key_fingerprint in trusted
        and evidence.signature_algorithm == SIGNATURE_ALGORITHM
        and attachments_valid
        and entity_cards_valid
        and key_snapshot_valid
        and rendered_snapshot_valid
        and pdf_snapshot_valid
        and (topic_type is None or preflight is None or dependency_closure_attested)
    )
    return {
        "valid": valid,
        "identity_valid": identity_valid,
        "digest_valid": digest_valid,
        "signature_valid": signature_valid,
        "key_fingerprint_valid": key_fingerprint_valid,
        "trusted_key": evidence.key_fingerprint in trusted,
        "preflight_attested": valid and preflight_attested,
        "attachments_valid": attachments_valid,
        "entity_cards_valid": entity_cards_valid,
        "key_snapshot_valid": key_snapshot_valid,
        "renderer_comparison_performed": compare_current_renderer,
        "rendered_snapshot_attested": valid and rendered_snapshot is not None and rendered_snapshot_valid,
        "rendered_snapshot_reproducible": valid and rendered_snapshot_reproducible,
        "pdf_snapshot_attested": valid and pdf_snapshot is not None and pdf_snapshot_valid,
        "pdf_snapshot_reproducible": valid and pdf_snapshot_reproducible,
        "dependency_closure_attested": valid and dependency_closure_attested,
    }
