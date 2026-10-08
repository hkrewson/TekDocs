"""Build and verify an internal package candidate from reviewed Git evidence.

The package only hands exact retained artifacts to a future publisher. It has
no client route, approval state, or authority to distribute them.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import (
    AuditEvent,
    PublicationAudience,
    RepositoryEvidenceReviewDecision,
    RepositoryPublicationPackage,
)
from .publications import canonical_json
from .repository_publication_evidence import verify_repository_publication_evidence

PACKAGE_FORMAT = "tekdocs-repository-publication-package/v1"


class RepositoryPublicationPackageError(RuntimeError):
    """The exact reviewed evidence cannot be packaged."""


def _manifest(
    *, package_id: uuid.UUID, decision: RepositoryEvidenceReviewDecision,
    actor: User, created_at: datetime,
) -> dict[str, object]:
    evidence = decision.evidence
    source = evidence.manifest
    return {
        "format": PACKAGE_FORMAT,
        "package_id": str(package_id),
        "decision_id": str(decision.id),
        "evidence_id": str(evidence.id),
        "workspace_id": str(evidence.workspace_id),
        "source_commit": evidence.source_commit.object_id,
        "evidence_digest": evidence.content_digest,
        "html_sha256": source["rendered_snapshot"]["sha256"],
        "pdf_sha256": source["pdf_snapshot"]["sha256"],
        "attachments": [
            {"id": item["id"], "checksum": item["checksum"], "size": item["size"]}
            for item in source["attachments"]
        ],
        "created_by": str(actor.id),
        "created_at": created_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
    }


def verify_repository_publication_package(package: RepositoryPublicationPackage) -> bool:
    """Recheck the immutable handoff and all retained artifact bytes offline."""
    decision = package.decision
    evidence = decision.evidence
    organization_id = evidence.organization_id
    if (
        decision.outcome != RepositoryEvidenceReviewDecision.Outcome.ACCEPTED_FOR_PACKAGING
        or evidence.audience != PublicationAudience.CLIENT_VISIBLE
        or organization_id is None
        or evidence.signed_by_id == decision.actor_id
        or (package.tenant_id, package.organization_id, package.workspace_id)
        != (decision.tenant_id, decision.organization_id, decision.workspace_id)
        or (package.tenant_id, package.organization_id, package.workspace_id)
        != (evidence.tenant_id, evidence.organization_id, evidence.workspace_id)
        or not verify_repository_publication_evidence(evidence)["valid"]
    ):
        return False
    try:
        expected = _manifest(
            package_id=package.id, decision=decision,
            actor=package.created_by, created_at=package.created_at,
        )
        return (
            package.manifest == expected
            and hashlib.sha256(canonical_json(expected)).hexdigest() == package.manifest_digest
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


@transaction.atomic
def create_repository_publication_package(
    *, decision_id: uuid.UUID, actor: User,
) -> RepositoryPublicationPackage:
    decision = (
        RepositoryEvidenceReviewDecision.objects.select_related(
            "evidence__source_commit", "evidence__workspace__organization"
        )
        .select_for_update(of=("self",))
        .get(pk=decision_id)
    )
    evidence = decision.evidence
    organization_id = evidence.organization_id
    member = require_permission(actor, PermissionKey.DOCUMENTS_PUBLISH, organization=evidence.organization)
    if member.tenant.id != evidence.tenant_id:
        raise RepositoryPublicationPackageError("Package scope does not match actor")
    if RepositoryPublicationPackage.objects.filter(decision=decision).exists():
        raise RepositoryPublicationPackageError("Review decision already has a package")
    if (
        decision.outcome != RepositoryEvidenceReviewDecision.Outcome.ACCEPTED_FOR_PACKAGING
        or evidence.audience != PublicationAudience.CLIENT_VISIBLE
        or organization_id is None
        or evidence.signed_by_id == decision.actor_id
        or not verify_repository_publication_evidence(evidence)["valid"]
    ):
        raise RepositoryPublicationPackageError("Accepted, intact client evidence is required")
    if not isinstance(evidence.manifest.get("rendered_snapshot"), dict) or not isinstance(
        evidence.manifest.get("pdf_snapshot"), dict
    ):
        raise RepositoryPublicationPackageError("Retained HTML and PDF are required")
    package_id = uuid.uuid4()
    created_at = timezone.now()
    manifest = _manifest(package_id=package_id, decision=decision, actor=actor, created_at=created_at)
    package = RepositoryPublicationPackage.objects.create(
        id=package_id,
        tenant_id=evidence.tenant_id,
        organization_id=organization_id,
        workspace_id=evidence.workspace_id,
        decision=decision,
        manifest=manifest,
        manifest_digest=hashlib.sha256(canonical_json(manifest)).hexdigest(),
        created_by=actor,
        created_at=created_at,
    )
    AuditEvent.objects.create(
        tenant_id=evidence.tenant_id,
        actor=actor,
        action="repository.publication_package.created",
        entity_id=package.id,
        metadata={"evidence_id": str(evidence.id), "decision_id": str(decision.id)},
    )
    return package
