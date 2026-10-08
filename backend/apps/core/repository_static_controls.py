"""Internal release and withdrawal gates for signed repository STATIC records."""

from __future__ import annotations

from uuid import UUID

from django.db import connection, transaction

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import (
    AuditEvent,
    PublicationAudience,
    RepositoryStaticDeliveryAuthorization,
    RepositoryStaticPublication,
    RepositoryStaticPublicationControlEvent,
)
from .outbox import OutboxTopic, enqueue_outbox_event
from .repository_static_publications import verify_repository_static_publication


class RepositoryStaticControlError(RuntimeError):
    """The requested internal publication transition is not valid."""


def _lock_content(*, workspace_id: UUID, content_id: UUID) -> None:
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"repository-static-content:{workspace_id}:{content_id}"],
        )


def repository_static_state(publication: RepositoryStaticPublication) -> str:
    actions = set(publication.control_events.values_list("action", flat=True))
    if RepositoryStaticPublicationControlEvent.Action.WITHDRAWN in actions:
        return "withdrawn"
    if RepositoryStaticPublicationControlEvent.objects.filter(
        supersedes=publication, action=RepositoryStaticPublicationControlEvent.Action.RELEASED
    ).exists():
        return "superseded"
    if RepositoryStaticPublicationControlEvent.Action.RELEASED in actions:
        return "released"
    return "recorded"


@transaction.atomic
def record_repository_static_control(
    *, publication_id: UUID, action: str, reason: str, actor: User, supersedes_id: UUID | None = None,
) -> RepositoryStaticPublicationControlEvent:
    publication = (
        RepositoryStaticPublication.objects.select_related(
            "authorization__package__decision__evidence", "organization"
        ).select_for_update(of=("self",)).get(pk=publication_id)
    )
    member = require_permission(actor, PermissionKey.DOCUMENTS_APPROVE, organization=publication.organization)
    if member.tenant.id != publication.tenant_id:
        raise RepositoryStaticControlError("Publication scope does not match actor")
    if action not in RepositoryStaticPublicationControlEvent.Action.values or not reason.strip():
        raise RepositoryStaticControlError("Action and reason are required")
    content_id = publication.authorization.package.decision.evidence.content_id
    audience = publication.authorization.package.decision.evidence.audience
    _lock_content(workspace_id=publication.workspace_id, content_id=content_id)
    state = repository_static_state(publication)
    if action == RepositoryStaticPublicationControlEvent.Action.RELEASED:
        if state != "recorded":
            raise RepositoryStaticControlError("Publication has already received a release decision")
        if publication.created_by_id == actor.id:
            raise RepositoryStaticControlError("Publication creator cannot release their own record")
        if not verify_repository_static_publication(publication):
            raise RepositoryStaticControlError("Signed publication or retained artifacts failed verification")
        active = RepositoryStaticPublicationControlEvent.objects.filter(
            action=RepositoryStaticPublicationControlEvent.Action.RELEASED,
            publication__workspace_id=publication.workspace_id,
            publication__authorization__package__decision__evidence__content_id=content_id,
        ).exclude(publication__control_events__action=RepositoryStaticPublicationControlEvent.Action.WITHDRAWN)
        active_publications = [
            event.publication for event in active if repository_static_state(event.publication) == "released"
        ]
        if [current.id for current in active_publications] != ([supersedes_id] if supersedes_id else []):
            raise RepositoryStaticControlError("Supersession must name the current active release")
        if active_publications and (
            active_publications[0].authorization.package.decision.evidence.audience != audience
        ):
            raise RepositoryStaticControlError("Supersession audience must match the active release")
        if supersedes_id == publication.id:
            raise RepositoryStaticControlError("A publication cannot supersede itself")
    else:
        if supersedes_id is not None:
            raise RepositoryStaticControlError("Withdrawal cannot supersede a publication")
        if state != "released":
            raise RepositoryStaticControlError("Only a released publication can be withdrawn")
    event = RepositoryStaticPublicationControlEvent.objects.create(
        tenant_id=publication.tenant_id,
        organization_id=publication.organization_id,
        workspace_id=publication.workspace_id,
        publication=publication,
        supersedes_id=supersedes_id,
        action=action,
        reason=reason.strip(),
        actor=actor,
    )
    AuditEvent.objects.create(
        tenant_id=publication.tenant_id,
        actor=actor,
        action=f"repository.static_publication.{action}",
        entity_id=publication.id,
        metadata={"control_event_id": str(event.id), "supersedes_id": str(supersedes_id) if supersedes_id else None},
    )
    unavailable_id = (
        supersedes_id if action == RepositoryStaticPublicationControlEvent.Action.RELEASED else publication.id
    )
    if unavailable_id is not None and RepositoryStaticDeliveryAuthorization.objects.filter(
        publication_id=unavailable_id,
        tenant_id=publication.tenant_id,
        organization_id=publication.organization_id,
        workspace_id=publication.workspace_id,
    ).exists():
        enqueue_outbox_event(
            tenant=publication.tenant,
            organization=publication.organization,
            topic=OutboxTopic.REPOSITORY_PUBLICATION_ACCESS_CHANGED,
            subject_id=unavailable_id,
            idempotency_key=f"repository-publication-access-changed:{unavailable_id}",
            payload={"audience": PublicationAudience.CLIENT_VISIBLE},
        )
    return event
