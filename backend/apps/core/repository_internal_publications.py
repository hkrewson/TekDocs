"""Staff-only publication over retained signed Git evidence; never portal access."""

from uuid import UUID

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import AuditEvent, PublicationAudience, RepositoryInternalPublicationEvent, RepositoryPublicationEvidence
from .repository_publication_evidence import verify_repository_publication_evidence
from .repository_static_controls import _lock_content


class InternalPublicationError(RuntimeError):
    """A staff publication transition cannot be completed safely."""


def internal_publication_state(evidence: RepositoryPublicationEvidence) -> str:
    actions = set(evidence.internal_events.values_list("action", flat=True))
    if "withdrawn" in actions:
        return "withdrawn"
    if RepositoryInternalPublicationEvent.objects.filter(supersedes=evidence).exists():
        return "superseded"
    return "released" if "released" in actions else "recorded"


def active_internal_publication(evidence: RepositoryPublicationEvidence) -> RepositoryPublicationEvidence | None:
    candidates = (
        RepositoryPublicationEvidence.objects.filter(
            workspace_id=evidence.workspace_id,
            content_id=evidence.content_id,
            audience=PublicationAudience.MSP_INTERNAL,
            internal_events__action="released",
        )
        .exclude(internal_events__action="withdrawn")
        .exclude(internal_supersession__isnull=False)
    )
    return candidates.first()


@transaction.atomic
def record_internal_publication(
    *,
    evidence: RepositoryPublicationEvidence,
    action: str,
    reason: str,
    actor: User,
    supersedes_id: UUID | None = None,
) -> RepositoryInternalPublicationEvent:
    permission = PermissionKey.DOCUMENTS_PUBLISH if action == "released" else PermissionKey.DOCUMENTS_APPROVE
    member = require_permission(actor, permission, organization=evidence.organization)
    if member.tenant.id != evidence.tenant_id or evidence.audience != PublicationAudience.MSP_INTERNAL:
        raise InternalPublicationError("Staff-only publication scope is required")
    if action not in {"released", "withdrawn"} or not reason.strip():
        raise InternalPublicationError("Action and reason are required")
    _lock_content(workspace_id=evidence.workspace_id, content_id=evidence.content_id)
    state = internal_publication_state(evidence)
    if action == "released":
        active = active_internal_publication(evidence)
        if state != "recorded" or (active.id if active else None) != supersedes_id or supersedes_id == evidence.id:
            raise InternalPublicationError("Correction must name the current staff publication")
        if not verify_repository_publication_evidence(evidence)["valid"]:
            raise InternalPublicationError("Signed publication or retained files failed verification")
    elif supersedes_id is not None or state != "released":
        raise InternalPublicationError("Only the current staff publication can be withdrawn")
    event = RepositoryInternalPublicationEvent.objects.create(
        tenant_id=evidence.tenant_id,
        organization_id=evidence.organization_id,
        workspace_id=evidence.workspace_id,
        evidence=evidence,
        supersedes_id=supersedes_id,
        action=action,
        reason=reason.strip(),
        actor=actor,
    )
    AuditEvent.objects.create(
        tenant_id=evidence.tenant_id,
        actor=actor,
        action=f"repository.internal_publication.{action}",
        entity_id=evidence.id,
        metadata={"event_id": str(event.id)},
    )
    return event
