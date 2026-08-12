from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch

from .models import (
    AuditEvent,
    ComplianceControlAssignment,
    ComplianceEvidence,
    ComplianceEvidenceKind,
    ComplianceEvidenceLink,
    ComplianceEvidenceReview,
    ComplianceEvidenceStatus,
    Entity,
    EntityVisibility,
)
from .scoping import DataScope
from .workspaces import ResolvedWorkspace


class ComplianceEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    title: str
    kind: str
    summary: str = ""
    source_url: str = ""
    source_entity_id: UUID | None = None
    collection_start: date | None = None
    collection_end: date | None = None


def evidence_for_scope(scope: DataScope):  # type: ignore[no-untyped-def]
    reviews = ComplianceEvidenceReview.objects.select_related("reviewed_by")
    return (
        ComplianceEvidence.scoped.for_scope(scope)
        .select_related("entity", "source_entity", "created_by")
        .prefetch_related(Prefetch("reviews", queryset=reviews), "control_links__assignment__control__entity")
    )


def evidence_links_for_assignment(assignment: ComplianceControlAssignment):  # type: ignore[no-untyped-def]
    return (
        ComplianceEvidenceLink.objects.filter(assignment=assignment)
        .select_related("evidence__entity", "control_revision", "linked_by")
        .prefetch_related("evidence__reviews__reviewed_by")
    )


def _validate_input(workspace: ResolvedWorkspace, value: EvidenceInput) -> Entity | None:
    if value.kind not in ComplianceEvidenceKind.values:
        raise ComplianceEvidenceError("Unknown evidence kind.")
    if value.collection_start and value.collection_end and value.collection_end < value.collection_start:
        raise ComplianceEvidenceError("Collection end cannot precede collection start.")
    if value.kind == ComplianceEvidenceKind.URL and not value.source_url:
        raise ComplianceEvidenceError("URL evidence requires a source URL.")
    if value.kind != ComplianceEvidenceKind.URL and value.source_url:
        raise ComplianceEvidenceError("Only URL evidence accepts a source URL.")
    if value.kind == ComplianceEvidenceKind.ENTITY and value.source_entity_id is None:
        raise ComplianceEvidenceError("Entity evidence requires a TekDocs entity.")
    if value.kind != ComplianceEvidenceKind.ENTITY and value.source_entity_id is not None:
        raise ComplianceEvidenceError("Only entity evidence accepts a TekDocs entity.")
    if value.source_entity_id is None:
        return None
    try:
        return Entity.scoped.for_scope(workspace.data_scope).get(pk=value.source_entity_id, archived_at__isnull=True)
    except Entity.DoesNotExist as exc:
        raise ComplianceEvidenceError("The selected source is unavailable in this workspace.") from exc


@transaction.atomic
def create_evidence(*, workspace: ResolvedWorkspace, actor_id: UUID, value: EvidenceInput) -> ComplianceEvidence:
    source_entity = _validate_input(workspace, value)
    entity = Entity.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="compliance_evidence",
        display_name=value.title,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    evidence = ComplianceEvidence.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        kind=value.kind,
        source_url=value.source_url,
        source_entity=source_entity,
        summary=value.summary,
        collection_start=value.collection_start,
        collection_end=value.collection_end,
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor_id=actor_id,
        action="compliance.evidence.created",
        entity_id=entity.id,
        metadata={"kind": value.kind},
    )
    return evidence


@transaction.atomic
def link_evidence(
    *, assignment: ComplianceControlAssignment, evidence: ComplianceEvidence, actor_id: UUID
) -> ComplianceEvidenceLink:
    if evidence.workspace_id != assignment.workspace_id:
        raise ComplianceEvidenceError("The selected evidence is unavailable in this workspace.")
    link, _ = ComplianceEvidenceLink.objects.get_or_create(
        assignment=assignment,
        evidence=evidence,
        control_revision=assignment.control_revision,
        defaults={
            "tenant": assignment.tenant,
            "workspace": assignment.workspace,
            "organization": assignment.organization,
            "linked_by_id": actor_id,
        },
    )
    return link


@transaction.atomic
def review_evidence(
    *, evidence: ComplianceEvidence, actor_id: UUID, status: str, decision: str, note: str = ""
) -> ComplianceEvidenceReview:
    if status not in ComplianceEvidenceStatus.values:
        raise ComplianceEvidenceError("Unknown evidence review status.")
    review = ComplianceEvidenceReview.objects.create(
        tenant=evidence.tenant,
        workspace=evidence.workspace,
        organization=evidence.organization,
        evidence=evidence,
        status=status,
        decision=decision,
        note=note,
        reviewed_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=evidence.tenant,
        actor_id=actor_id,
        action="compliance.evidence.reviewed",
        entity_id=evidence.entity_id,
        metadata={"status": status},
    )
    return review
