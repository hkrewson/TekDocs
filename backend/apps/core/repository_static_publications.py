"""Sign an authorized repository package without granting client delivery."""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import AuditEvent, RepositoryPackageAuthorization, RepositoryStaticPublication
from .publications import canonical_json, publication_signing_key, publication_trusted_key_fingerprints
from .repository_publication_packages import verify_repository_publication_package

STATIC_FORMAT = "tekdocs-repository-static-publication/v1"
_DOMAIN = b"TEKDOCS-REPOSITORY-STATIC-PUBLICATION\x00v1\x00"


class RepositoryStaticPublicationError(RuntimeError):
    """An authorized package cannot be recorded as an internal STATIC artifact."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _manifest(
    *, publication_id: uuid.UUID, authorization: RepositoryPackageAuthorization,
    actor: User, created_at: datetime,
) -> dict[str, object]:
    package = authorization.package
    evidence = package.decision.evidence
    return {
        "format": STATIC_FORMAT,
        "publication_id": str(publication_id),
        "workspace_id": str(package.workspace_id),
        "organization_id": str(package.organization_id),
        "authorization_id": str(authorization.id),
        "authorization_outcome": authorization.outcome,
        "package_id": str(package.id),
        "package_digest": package.manifest_digest,
        "evidence_id": str(evidence.id),
        "evidence_digest": evidence.content_digest,
        "source_commit": package.manifest["source_commit"],
        "html_sha256": package.manifest["html_sha256"],
        "pdf_sha256": package.manifest["pdf_sha256"],
        "attachments": package.manifest["attachments"],
        "created_by": str(actor.id),
        "created_at": _timestamp(created_at),
    }


def verify_repository_static_publication(publication: RepositoryStaticPublication) -> bool:
    """Verify the signature, source chain, and retained bytes without live Git."""
    try:
        authorization = publication.authorization
        package = authorization.package
        if (
            authorization.outcome != RepositoryPackageAuthorization.Outcome.AUTHORIZED_FOR_PUBLICATION
            or (publication.tenant_id, publication.organization_id, publication.workspace_id)
            != (authorization.tenant_id, authorization.organization_id, authorization.workspace_id)
            or (publication.tenant_id, publication.organization_id, publication.workspace_id)
            != (package.tenant_id, package.organization_id, package.workspace_id)
            or not verify_repository_publication_package(package)
        ):
            return False
        expected = _manifest(
            publication_id=publication.id, authorization=authorization,
            actor=publication.created_by, created_at=publication.created_at,
        )
        digest = hashlib.sha256(_DOMAIN + canonical_json(expected)).digest()
        raw_key = base64.b64decode(publication.public_key.encode("ascii"), altchars=b"-_", validate=True)
        signature = base64.b64decode(publication.signature.encode("ascii"), altchars=b"-_", validate=True)
        _current, trusted = publication_trusted_key_fingerprints()
        Ed25519PublicKey.from_public_bytes(raw_key).verify(signature, digest)
        return (
            publication.manifest == expected
            and publication.content_digest == digest.hex()
            and publication.signature_algorithm == "Ed25519"
            and hashlib.sha256(raw_key).hexdigest() == publication.key_fingerprint
            and publication.key_fingerprint in trusted
        )
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error, InvalidSignature):
        return False


@transaction.atomic
def create_repository_static_publication(
    *, authorization_id: uuid.UUID, actor: User,
) -> RepositoryStaticPublication:
    authorization = (
        RepositoryPackageAuthorization.objects.select_related(
            "package__decision__evidence__source_commit", "package__organization"
        ).select_for_update(of=("self",)).get(pk=authorization_id)
    )
    package = authorization.package
    member = require_permission(actor, PermissionKey.DOCUMENTS_PUBLISH, organization=package.organization)
    if member.tenant.id != package.tenant_id:
        raise RepositoryStaticPublicationError("Publication scope does not match actor")
    if RepositoryStaticPublication.objects.filter(authorization=authorization).exists():
        raise RepositoryStaticPublicationError("Authorization already has a STATIC record")
    if (
        authorization.outcome != RepositoryPackageAuthorization.Outcome.AUTHORIZED_FOR_PUBLICATION
        or not verify_repository_publication_package(package)
    ):
        raise RepositoryStaticPublicationError("Authorized, intact retained package is required")
    publication_id = uuid.uuid4()
    created_at = timezone.now()
    manifest = _manifest(
        publication_id=publication_id, authorization=authorization, actor=actor, created_at=created_at,
    )
    digest = hashlib.sha256(_DOMAIN + canonical_json(manifest)).digest()
    key = publication_signing_key()
    raw_key = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    publication = RepositoryStaticPublication.objects.create(
        id=publication_id,
        tenant_id=package.tenant_id,
        organization_id=package.organization_id,
        workspace_id=package.workspace_id,
        authorization=authorization,
        manifest=manifest,
        content_digest=digest.hex(),
        signature=base64.urlsafe_b64encode(key.sign(digest)).decode("ascii"),
        signature_algorithm="Ed25519",
        public_key=base64.urlsafe_b64encode(raw_key).decode("ascii"),
        key_fingerprint=hashlib.sha256(raw_key).hexdigest(),
        created_by=actor,
        created_at=created_at,
    )
    AuditEvent.objects.create(
        tenant_id=package.tenant_id,
        actor=actor,
        action="repository.static_publication.created",
        entity_id=publication.id,
        metadata={"package_id": str(package.id), "authorization_id": str(authorization.id)},
    )
    return publication
