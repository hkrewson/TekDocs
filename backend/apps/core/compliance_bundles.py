from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import transaction
from django.utils import timezone

from .compliance_evidence import evidence_for_scope
from .compliance_operations import assignments_for_scope
from .compliance_risks import risks_for_scope
from .models import AuditEvent, ComplianceEvidenceBundle, Entity, EntityVisibility
from .publications import _encoded_public_key, publication_signing_key
from .workspaces import ResolvedWorkspace


class ComplianceBundleError(ValueError):
    pass


def bundles_for_scope(scope):  # type: ignore[no-untyped-def]
    return ComplianceEvidenceBundle.scoped.for_scope(scope).select_related("entity", "created_by")


def canonical_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@transaction.atomic
def create_bundle(*, workspace: ResolvedWorkspace, actor_id: UUID, title: str, reason: str, audience: str):
    if audience not in {"msp_internal", "client_auditor"}:
        raise ComplianceBundleError("Unknown evidence bundle audience.")
    assignments = list(assignments_for_scope(workspace.data_scope).order_by("control__entity_id"))
    evidence = list(evidence_for_scope(workspace.data_scope).order_by("entity_id"))
    risks = list(risks_for_scope(workspace.data_scope).order_by("entity_id"))
    if any(len(records) > 5_000 for records in (assignments, evidence, risks)):
        raise ComplianceBundleError("An evidence bundle is limited to 5,000 records of each type.")
    bundle_id = uuid.uuid4()
    created_at = timezone.now()
    manifest: dict[str, object] = {
        "format": "tekdocs-compliance-evidence/v1",
        "bundle_id": str(bundle_id),
        "title": title,
        "workspace_id": str(workspace.data_scope.workspace_id),
        "created_by": str(actor_id),
        "created_at": created_at.isoformat(),
        "reason": reason,
        "audience": audience,
        "assignments": [
            {
                "id": str(item.id),
                "control_id": str(item.control.entity_id),
                "control_revision": item.control_revision.revision_number,
                "applicability": item.applicability,
                "status": item.implementation_status,
                "reviews": [
                    {
                        "control_revision": review.control_revision.revision_number,
                        "applicability": review.applicability,
                        "status": review.implementation_status,
                        "decision": review.decision,
                        "note": review.note,
                        "reviewed_by": str(review.reviewed_by_id),
                        "reviewed_at": review.reviewed_at.isoformat(),
                    }
                    for review in item.reviews.all()
                ],
            }
            for item in assignments
        ],
        "evidence": [
            {
                "id": str(item.entity_id),
                "kind": item.kind,
                "collection_start": item.collection_start.isoformat() if item.collection_start else None,
                "collection_end": item.collection_end.isoformat() if item.collection_end else None,
                "links": [
                    {
                        "assignment_id": str(link.assignment_id),
                        "control_revision": link.control_revision.revision_number,
                    }
                    for link in item.control_links.all()
                ],
                "reviews": [
                    {
                        "status": review.status,
                        "decision": review.decision,
                        "note": review.note,
                        "reviewed_by": str(review.reviewed_by_id),
                        "reviewed_at": review.reviewed_at.isoformat(),
                    }
                    for review in item.reviews.all()
                ],
            }
            for item in evidence
        ],
        "risks": [
            {
                "id": str(item.entity_id),
                "score": item.score,
                "band": item.reporting_band,
                "status": item.status,
                "treatment": item.treatment,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "events": [
                    {
                        "control_revision": event.control_revision.revision_number
                        if event.control_revision
                        else None,
                        "score": event.likelihood * event.impact,
                        "status": event.status,
                        "treatment": event.treatment,
                        "decision": event.decision,
                        "note": event.note,
                        "recorded_by": str(event.recorded_by_id),
                        "recorded_at": event.recorded_at.isoformat(),
                    }
                    for event in item.events.all()
                ],
            }
            for item in risks
        ],
    }
    payload = canonical_manifest_bytes(manifest)
    digest = hashlib.sha256(payload).digest()
    key = publication_signing_key()
    public_key, fingerprint = _encoded_public_key(key)
    entity = Entity.objects.create(
        id=bundle_id,
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="compliance_evidence_bundle",
        display_name=title,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    bundle = ComplianceEvidenceBundle.objects.create(
        id=bundle_id,
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        reason=reason,
        audience=audience,
        manifest=manifest,
        content_digest=digest.hex(),
        signature=base64.urlsafe_b64encode(key.sign(digest)).decode("ascii"),
        public_key=public_key,
        key_fingerprint=fingerprint,
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=bundle.tenant,
        actor_id=actor_id,
        action="compliance.bundle.created",
        entity_id=entity.id,
        metadata={"audience": audience},
    )
    return bundle


def verify_bundle(bundle: ComplianceEvidenceBundle) -> bool:
    digest = hashlib.sha256(canonical_manifest_bytes(bundle.manifest)).digest()
    try:
        raw_key = base64.urlsafe_b64decode(bundle.public_key)
        signature = base64.urlsafe_b64decode(bundle.signature)
        Ed25519PublicKey.from_public_bytes(raw_key).verify(signature, digest)
        return digest.hex() == bundle.content_digest and hashlib.sha256(raw_key).hexdigest() == bundle.key_fingerprint
    except (binascii.Error, ValueError, InvalidSignature):
        return False
