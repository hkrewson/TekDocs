from __future__ import annotations

from datetime import date
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import TenantMembership, User
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import AuditEvent, Document, DocumentReviewState
from .workspaces import ResolvedWorkspace


class DocumentOperationsError(ValueError):
    pass


def normalize_collection(value: str) -> str:
    result = " ".join(value.split())
    if len(result) > 120 or any(ord(character) < 32 for character in result):
        raise DocumentOperationsError("Collection must be a plain name of at most 120 characters.")
    return result


def normalize_tags(values: list[str]) -> list[str]:
    if len(values) > 20:
        raise DocumentOperationsError("A document may have at most 20 tags.")
    normalized: list[str] = []
    for value in values:
        tag = " ".join(value.strip().lower().split())
        if not tag or len(tag) > 40 or any(ord(character) < 32 for character in tag):
            raise DocumentOperationsError("Tags must be plain names of 1 to 40 characters.")
        if tag not in normalized:
            normalized.append(tag)
    return normalized


def _eligible_user(
    *, workspace: ResolvedWorkspace, user_id: UUID | None, permission: PermissionKey
) -> User | None:
    if user_id is None:
        return None
    try:
        membership = TenantMembership.objects.select_related("user").get(
            tenant=workspace.member.tenant,
            user_id=user_id,
            user__is_active=True,
        )
    except TenantMembership.DoesNotExist as exc:
        raise DocumentOperationsError("The selected person is unavailable.") from exc
    context = require_installation_member(membership.user)
    if not context_has_permission(context, permission, organization=workspace.organization):
        raise DocumentOperationsError("The selected person cannot access this documentation workspace.")
    return membership.user


@transaction.atomic
def update_document_operations(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    actor_id: UUID,
    owner_id: UUID | None,
    review_due_on: date | None,
    collection: str,
    tags: list[str],
) -> Document:
    locked = Document.objects.select_for_update().get(pk=document.pk)
    owner = _eligible_user(workspace=workspace, user_id=owner_id, permission=PermissionKey.DOCUMENTS_VIEW)
    locked.owner = owner
    locked.review_due_on = review_due_on
    locked.collection = normalize_collection(collection)
    locked.tags = normalize_tags(tags)
    locked.save(update_fields=("owner", "review_due_on", "collection", "tags", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.operations_updated",
        entity_id=locked.entity_id,
        metadata={"tag_count": len(locked.tags), "has_collection": bool(locked.collection)},
    )
    return locked


@transaction.atomic
def request_document_review(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    actor_id: UUID,
    reviewer_id: UUID,
    note: str,
) -> Document:
    locked = Document.objects.select_for_update().get(pk=document.pk)
    reviewer = _eligible_user(
        workspace=workspace,
        user_id=reviewer_id,
        permission=PermissionKey.DOCUMENTS_APPROVE,
    )
    if reviewer is None:
        raise DocumentOperationsError("A reviewer is required.")
    cleaned_note = " ".join(note.split())
    if len(cleaned_note) > 500:
        raise DocumentOperationsError("The review note may not exceed 500 characters.")
    now = timezone.now()
    locked.review_state = DocumentReviewState.PENDING
    locked.review_requested_by_id = actor_id
    locked.review_requested_at = now
    locked.reviewer = reviewer
    locked.review_decided_at = None
    locked.review_note = cleaned_note
    locked.save(
        update_fields=(
            "review_state",
            "review_requested_by",
            "review_requested_at",
            "reviewer",
            "review_decided_at",
            "review_note",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.review_requested",
        entity_id=locked.entity_id,
        metadata={},
    )
    return locked


@transaction.atomic
def decide_document_review(
    *,
    document: Document,
    actor_id: UUID,
    decision: str,
    note: str,
) -> Document:
    locked = Document.objects.select_for_update().get(pk=document.pk)
    if locked.review_state != DocumentReviewState.PENDING:
        raise DocumentOperationsError("This document does not have a pending review.")
    if locked.reviewer_id != actor_id:
        raise DocumentOperationsError("This review is assigned to another person.")
    if decision not in {DocumentReviewState.APPROVED, DocumentReviewState.CHANGES_REQUESTED}:
        raise DocumentOperationsError("Decision must approve the document or request changes.")
    cleaned_note = " ".join(note.split())
    if not cleaned_note or len(cleaned_note) > 500:
        raise DocumentOperationsError("A review decision note of at most 500 characters is required.")
    now = timezone.now()
    locked.review_state = decision
    locked.review_decided_at = now
    locked.review_note = cleaned_note
    if decision == DocumentReviewState.APPROVED:
        locked.last_reviewed_by_id = actor_id
        locked.last_reviewed_at = now
    locked.save(
        update_fields=(
            "review_state",
            "review_decided_at",
            "review_note",
            "last_reviewed_by",
            "last_reviewed_at",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action=f"document.review_{decision}",
        entity_id=locked.entity_id,
        metadata={},
    )
    return locked
