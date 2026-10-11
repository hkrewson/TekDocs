from __future__ import annotations

from datetime import date
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import TenantMembership, User
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import (
    AuditEvent,
    ContentNode,
    Document,
    DocumentAuthority,
    DocumentAuthorityMode,
    DocumentReviewState,
    Taxonomy,
    TaxonomyBinding,
    WorkspaceRepository,
)
from .taxonomies import TaxonomyError, assign_document_terms
from .workspaces import ResolvedWorkspace


class DocumentOperationsError(ValueError):
    pass


def _reviewed_markdown(document: Document) -> str:
    from .documents import resolve_document

    authority = DocumentAuthority.objects.filter(
        workspace_id=document.entity.workspace_id,
        content_id=document.id,
    ).values_list("authority", flat=True).first()
    if authority != DocumentAuthorityMode.REPOSITORY:
        return resolve_document(document).markdown
    repository = WorkspaceRepository.objects.filter(workspace_id=document.entity.workspace_id).first()
    if (
        repository is None
        or repository.accepted_commit_id is None
        or repository.accepted_commit_id != repository.indexed_commit_id
    ):
        raise DocumentOperationsError("Repository content is not indexed; review the latest accepted content later.")
    node = ContentNode.objects.filter(
        repository=repository,
        content_id=document.id,
        indexed_commit_id=repository.accepted_commit_id,
    ).first()
    composition = node.composition_variants.get("all") if node is not None else None
    if not isinstance(composition, dict):
        raise DocumentOperationsError("The Git-authoritative document composition is unavailable for review.")
    markdown = composition.get("markdown")
    if not isinstance(markdown, str):
        raise DocumentOperationsError("The Git-authoritative document composition is unavailable for review.")
    return markdown


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


def _eligible_user(*, workspace: ResolvedWorkspace, user_id: UUID | None, permission: PermissionKey) -> User | None:
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
    taxonomy_term_ids: list[UUID] | None = None,
) -> Document:
    locked = Document.objects.select_for_update().get(pk=document.pk)
    normalized_collection = normalize_collection(collection)
    normalized_tags = normalize_tags(tags)
    repository_authoritative = DocumentAuthority.objects.filter(
        workspace_id=locked.entity.workspace_id,
        content_id=locked.id,
        authority=DocumentAuthorityMode.REPOSITORY,
    ).exists()
    if repository_authoritative and (
        taxonomy_term_ids is not None
    ):
        raise DocumentOperationsError(
            "Taxonomy terms are Git-authoritative; update the repository metadata instead."
        )
    if repository_authoritative:
        repository = WorkspaceRepository.objects.filter(workspace_id=locked.entity.workspace_id).first()
        node = (
            ContentNode.objects.filter(
                repository=repository,
                content_id=locked.id,
                indexed_commit_id=repository.accepted_commit_id,
            ).first()
            if repository is not None and repository.accepted_commit_id == repository.indexed_commit_id
            else None
        )
        properties = node.frontmatter.get("properties", {}) if node is not None else {}
        if not isinstance(properties, dict):
            properties = {}
        canonical_collection = str(properties.get("collection", ""))
        canonical_tags = properties.get("tags", [])
        if (
            normalized_collection != canonical_collection
            or not isinstance(canonical_tags, list)
            or normalized_tags != [str(item) for item in canonical_tags]
        ):
            raise DocumentOperationsError(
                "Collection and tags must match the indexed Git metadata while document authority is in Git."
            )
    owner = _eligible_user(workspace=workspace, user_id=owner_id, permission=PermissionKey.DOCUMENTS_VIEW)
    locked.owner = owner
    locked.review_due_on = review_due_on
    if not repository_authoritative:
        locked.collection = normalized_collection
    governed_tags = Taxonomy.objects.filter(
        tenant=locked.tenant, binding=TaxonomyBinding.DOCUMENT_TAGS, archived_at__isnull=True
    ).exists()
    if normalized_tags and governed_tags:
        raise DocumentOperationsError("Use governed terms instead of free-form tags for this document.")
    if not repository_authoritative:
        locked.tags = normalized_tags
    locked.save(update_fields=("owner", "review_due_on", "collection", "tags", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="document.operations_updated",
        entity_id=locked.entity_id,
        metadata={"tag_count": len(locked.tags), "has_collection": bool(locked.collection)},
    )
    if taxonomy_term_ids is not None:
        try:
            assign_document_terms(document=locked, term_ids=taxonomy_term_ids, actor_id=actor_id)
        except TaxonomyError as exc:
            raise DocumentOperationsError(str(exc)) from exc
        if locked.is_template and locked.organization_id is None:
            from .documents import ensure_template_revision

            ensure_template_revision(source=locked, actor_id=actor_id)
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
    from .documents import markdown_checksum

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
    locked.review_content_sha256 = markdown_checksum(_reviewed_markdown(locked))
    locked.reviewer = reviewer
    locked.review_decided_at = None
    locked.review_note = cleaned_note
    locked.save(
        update_fields=(
            "review_state",
            "review_requested_by",
            "review_requested_at",
            "review_content_sha256",
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
    from .documents import markdown_checksum

    locked = Document.objects.select_for_update().get(pk=document.pk)
    if locked.review_state != DocumentReviewState.PENDING:
        raise DocumentOperationsError("This document does not have a pending review.")
    if locked.review_content_sha256 is None or locked.review_content_sha256 != markdown_checksum(
        _reviewed_markdown(locked)
    ):
        raise DocumentOperationsError("The reviewed content changed. Request a new review for the current revision.")
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
