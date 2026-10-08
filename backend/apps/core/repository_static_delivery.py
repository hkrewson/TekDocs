"""Explicit authorization for repository STATIC client delivery."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import (
    AuditEvent,
    Entity,
    EntityVisibility,
    PublicationAudience,
    RepositoryStaticDeliveryAuthorization,
    RepositoryStaticPublication,
)
from .outbox import OutboxTopic, enqueue_outbox_event
from .repository_static_controls import _lock_content, repository_static_state
from .repository_static_publications import verify_repository_static_publication


class RepositoryStaticDeliveryError(RuntimeError):
    """The record cannot be approved for client delivery."""


def _client_reference_projection_safe(publication: RepositoryStaticPublication) -> bool:
    evidence = publication.authorization.package.decision.evidence
    cards = evidence.manifest.get("entity_cards")
    if not isinstance(cards, list):
        return False
    try:
        ids = {UUID(str(card["id"])) for card in cards if isinstance(card, dict)}
    except (KeyError, TypeError, ValueError):
        return False
    if len(ids) != len(cards):
        return False
    if not ids:
        return True
    visible_ids = set(
        Entity.objects.filter(
            id__in=ids,
            tenant_id=publication.tenant_id,
            organization_id=publication.organization_id,
            workspace_id=publication.workspace_id,
            visibility=EntityVisibility.CLIENT_VISIBLE,
            archived_at__isnull=True,
        ).values_list("id", flat=True)
    )
    return visible_ids == ids


def repository_static_delivery_ready(publication: RepositoryStaticPublication) -> bool:
    """Current readiness for the bounded client portal projection."""
    evidence = publication.authorization.package.decision.evidence
    return (
        evidence.audience == PublicationAudience.CLIENT_VISIBLE
        and RepositoryStaticDeliveryAuthorization.objects.filter(publication=publication).exists()
        and repository_static_state(publication) == "released"
        and verify_repository_static_publication(publication)
        and _client_reference_projection_safe(publication)
    )


@transaction.atomic
def authorize_repository_static_delivery(
    *, publication_id: UUID, reason: str, actor: User,
) -> RepositoryStaticDeliveryAuthorization:
    publication = (
        RepositoryStaticPublication.objects.select_related(
            "authorization__package__decision__evidence", "organization"
        ).select_for_update(of=("self",)).get(pk=publication_id)
    )
    member = require_permission(actor, PermissionKey.DOCUMENTS_APPROVE, organization=publication.organization)
    if member.tenant.id != publication.tenant_id:
        raise RepositoryStaticDeliveryError("Publication scope does not match actor")
    if not reason.strip():
        raise RepositoryStaticDeliveryError("A reason is required")
    evidence = publication.authorization.package.decision.evidence
    _lock_content(workspace_id=publication.workspace_id, content_id=evidence.content_id)
    if RepositoryStaticDeliveryAuthorization.objects.filter(publication=publication).exists():
        raise RepositoryStaticDeliveryError("Delivery has already been authorized for this record")
    if publication.created_by_id == actor.id or repository_static_state(publication) != "released":
        raise RepositoryStaticDeliveryError("An independent approver and active release are required")
    if (
        evidence.audience != PublicationAudience.CLIENT_VISIBLE
        or not verify_repository_static_publication(publication)
        or not _client_reference_projection_safe(publication)
    ):
        raise RepositoryStaticDeliveryError("Intact client-visible evidence and references are required")
    authorization = RepositoryStaticDeliveryAuthorization.objects.create(
        tenant_id=publication.tenant_id,
        organization_id=publication.organization_id,
        workspace_id=publication.workspace_id,
        publication=publication,
        reason=reason.strip(),
        actor=actor,
    )
    AuditEvent.objects.create(
        tenant_id=publication.tenant_id,
        actor=actor,
        action="repository.static_publication.delivery_authorized",
        entity_id=publication.id,
        metadata={"delivery_authorization_id": str(authorization.id)},
    )
    enqueue_outbox_event(
        tenant=publication.tenant,
        organization=publication.organization,
        topic=OutboxTopic.REPOSITORY_PUBLICATION_AVAILABLE,
        subject_id=publication.id,
        idempotency_key=f"repository-publication-available:{publication.id}",
        payload={"audience": PublicationAudience.CLIENT_VISIBLE},
    )
    return authorization
