"""Signed, retained Git-source evidence for a future repository STATIC publisher.

This internal record is not a distributable publication: it has no approval,
artifact, portal, or export route. Its signature binds the exact source proof
and composed Markdown without relying on live Git during verification.
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
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .content_index_models import ContentNode, ContentNodeKind
from .content_publication_sources import pinned_git_document_dependencies
from .models import AuditEvent, PublicationAudience, RepositoryPublicationEvidence, WorkspaceRepository
from .publications import (
    MAX_PUBLICATION_MARKDOWN_BYTES,
    SIGNATURE_ALGORITHM,
    canonical_json,
    publication_signing_key,
    publication_trusted_key_fingerprints,
)
from .repository_publication_preflight import PREFLIGHT_FORMAT, repository_publication_preflight

EVIDENCE_FORMAT = "tekdocs-repository-publication-evidence/v1"


class RepositoryPublicationEvidenceError(RuntimeError):
    """A repository source cannot be retained as signed evidence."""


def evidence_payload(*, manifest: dict[str, Any], markdown: str) -> bytes:
    sections = ((b"manifest", canonical_json(manifest)), (b"markdown", markdown.encode("utf-8")))
    payload = bytearray(b"TEKDOCS-REPOSITORY-PUBLICATION-EVIDENCE\x00v1\x00")
    for label, content in sections:
        payload.extend(len(label).to_bytes(2, "big"))
        payload.extend(label)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    return bytes(payload)


def retain_repository_publication_evidence(
    *, repository_id: uuid.UUID, content_id: uuid.UUID, audience: str, actor: User
) -> RepositoryPublicationEvidence:
    """Sign and insert one exact source snapshot under the accepted-head lock."""

    if audience not in PublicationAudience.values:
        raise RepositoryPublicationEvidenceError("Publication audience is unsupported")
    repository = WorkspaceRepository.objects.select_related("workspace__organization").get(pk=repository_id)
    member = require_permission(
        actor, PermissionKey.DOCUMENTS_PUBLISH, organization=repository.workspace.organization
    )
    if member.tenant.id != repository.tenant_id:
        raise RepositoryPublicationEvidenceError("Publication source belongs to another installation")
    if audience == PublicationAudience.CLIENT_VISIBLE and repository.workspace.organization_id is None:
        raise RepositoryPublicationEvidenceError("Client-visible evidence requires an organization workspace")

    with pinned_git_document_dependencies(
        repository_id=repository_id, content_id=content_id, audience=audience
    ) as source:
        repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
        if repository.accepted_commit_id is None or repository.accepted_commit_id != repository.indexed_commit_id:
            raise RepositoryPublicationEvidenceError("Repository source changed before retention")
        node = ContentNode.objects.filter(
            repository_id=repository_id,
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
        if (
            len(markdown.encode("utf-8")) > MAX_PUBLICATION_MARKDOWN_BYTES
            or hashlib.sha256(markdown.encode("utf-8")).hexdigest() != source["markdown_sha256"]
            or variant.get("digest") != source["composition_digest"]
        ):
            raise RepositoryPublicationEvidenceError("Indexed repository composition differs from its Git source")
        preflight = repository_publication_preflight(
            markdown=markdown, audience=audience, topic_type=node.topic_type
        )
        if preflight["blockers"]:
            raise RepositoryPublicationEvidenceError(
                "Repository publication preflight blocked: " + ", ".join(preflight["blockers"])
            )

        evidence_id = uuid.uuid4()
        signed_at = timezone.now()
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
            "signed_at": signed_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "signed_by": str(actor.id),
            "source": source,
            "preflight": preflight,
        }
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
        evidence.full_clean()
        evidence.save()  # type: ignore[no-untyped-call]
        AuditEvent.objects.create(
            tenant_id=repository.tenant_id,
            actor=actor,
            action="repository.publication_evidence.signed",
            entity_id=evidence.id,
            metadata={"repository_id": str(repository.id), "content_id": str(content_id)},
        )
        return evidence


def verify_repository_publication_evidence(evidence: RepositoryPublicationEvidence) -> dict[str, bool]:
    """Verify retained bytes and signature without consulting live Git."""

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
            source.get("accepted_commit") == manifest.get("source_commit"),
            source.get("markdown_sha256")
            == hashlib.sha256(evidence.canonical_markdown.encode("utf-8")).hexdigest(),
        )
    )
    preflight = manifest.get("preflight") if isinstance(manifest, dict) else None
    preflight_attested = isinstance(preflight, dict) and all(
        (
            preflight.get("format") == PREFLIGHT_FORMAT,
            preflight.get("audience") == evidence.audience,
            preflight.get("markdown_sha256")
            == hashlib.sha256(evidence.canonical_markdown.encode("utf-8")).hexdigest(),
            preflight.get("blockers") == [],
        )
    )
    if preflight is not None:
        identity_valid = identity_valid and preflight_attested
    try:
        source_commit = evidence.source_commit
        identity_valid = identity_valid and isinstance(source, dict) and (
            source_commit.object_id == manifest.get("source_commit")
            and source_commit.repository_id == evidence.repository_id
            and source_commit.object_format == source.get("object_format")
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
    )
    return {
        "valid": valid,
        "identity_valid": identity_valid,
        "digest_valid": digest_valid,
        "signature_valid": signature_valid,
        "key_fingerprint_valid": key_fingerprint_valid,
        "trusted_key": evidence.key_fingerprint in trusted,
        "preflight_attested": valid and preflight_attested,
    }
