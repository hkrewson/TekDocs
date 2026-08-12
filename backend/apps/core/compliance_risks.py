from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import TenantMembership
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import (
    AuditEvent,
    ComplianceControlAssignment,
    ComplianceRisk,
    ComplianceRiskEvent,
    ComplianceRiskStatus,
    ComplianceRiskTreatment,
    Entity,
    EntityVisibility,
)
from .scoping import DataScope
from .workspaces import ResolvedWorkspace


class ComplianceRiskError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RiskInput:
    title: str
    description: str
    likelihood: int
    impact: int
    status: str
    treatment: str
    decision: str
    treatment_plan: str = ""
    note: str = ""
    assignment_id: UUID | None = None
    owner_id: UUID | None = None
    due_date: date | None = None


def risks_for_scope(scope: DataScope):  # type: ignore[no-untyped-def]
    return (
        ComplianceRisk.scoped.for_scope(scope)
        .select_related("entity", "assignment__control__entity", "owner", "accepted_by")
        .prefetch_related("events__recorded_by", "events__control_revision")
    )


def risk_owner_choices(workspace: ResolvedWorkspace) -> list[dict[str, str]]:
    members = (
        TenantMembership.scoped.for_tenant(workspace.member.tenant).filter(user__is_active=True).select_related("user")
    )
    return [
        {"id": str(member.user_id), "display_name": member.user.display_name}
        for member in members
        if context_has_permission(
            require_installation_member(member.user),
            PermissionKey.COMPLIANCE_VIEW,
            organization=workspace.organization,
        )
    ]


def _owner(workspace: ResolvedWorkspace, owner_id: UUID | None) -> UUID | None:
    if owner_id is None:
        return None
    if str(owner_id) not in {choice["id"] for choice in risk_owner_choices(workspace)}:
        raise ComplianceRiskError("The selected owner cannot access this compliance workspace.")
    return owner_id


def _assignment(workspace: ResolvedWorkspace, assignment_id: UUID | None) -> ComplianceControlAssignment | None:
    if assignment_id is None:
        return None
    try:
        return (
            ComplianceControlAssignment.scoped.for_scope(workspace.data_scope)
            .select_related("control_revision")
            .get(pk=assignment_id)
        )
    except ComplianceControlAssignment.DoesNotExist as exc:
        raise ComplianceRiskError("The selected control assignment is unavailable in this workspace.") from exc


def _validate(value: RiskInput) -> None:
    if value.likelihood not in range(1, 6) or value.impact not in range(1, 6):
        raise ComplianceRiskError("Likelihood and impact must each be between 1 and 5.")
    if value.status not in ComplianceRiskStatus.values:
        raise ComplianceRiskError("Unknown risk status.")
    if value.treatment not in ComplianceRiskTreatment.values:
        raise ComplianceRiskError("Unknown risk treatment.")
    if value.status == ComplianceRiskStatus.ACCEPTED and value.treatment != ComplianceRiskTreatment.ACCEPT:
        raise ComplianceRiskError("Accepted risks must use the accept treatment.")
    if value.treatment == ComplianceRiskTreatment.ACCEPT and value.status != ComplianceRiskStatus.ACCEPTED:
        raise ComplianceRiskError("The accept treatment requires explicit accepted status.")


def _append_event(risk: ComplianceRisk, actor_id: UUID, value: RiskInput) -> None:
    ComplianceRiskEvent.objects.create(
        tenant=risk.tenant,
        workspace=risk.workspace,
        organization=risk.organization,
        risk=risk,
        control_revision=risk.assignment.control_revision if risk.assignment else None,
        likelihood=value.likelihood,
        impact=value.impact,
        status=value.status,
        treatment=value.treatment,
        treatment_plan=value.treatment_plan,
        due_date=value.due_date,
        decision=value.decision,
        note=value.note,
        recorded_by_id=actor_id,
    )


@transaction.atomic
def create_risk(*, workspace: ResolvedWorkspace, actor_id: UUID, value: RiskInput) -> ComplianceRisk:
    _validate(value)
    assignment = _assignment(workspace, value.assignment_id)
    owner_id = _owner(workspace, value.owner_id)
    entity = Entity.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="compliance_risk",
        display_name=value.title,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    accepted = value.status == ComplianceRiskStatus.ACCEPTED
    risk = ComplianceRisk.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        assignment=assignment,
        description=value.description,
        likelihood=value.likelihood,
        impact=value.impact,
        status=value.status,
        treatment=value.treatment,
        treatment_plan=value.treatment_plan,
        owner_id=owner_id,
        due_date=value.due_date,
        accepted_by_id=actor_id if accepted else None,
        accepted_at=timezone.now() if accepted else None,
    )
    _append_event(risk, actor_id, value)
    AuditEvent.objects.create(
        tenant=risk.tenant,
        actor_id=actor_id,
        action="compliance.risk.created",
        entity_id=entity.id,
        metadata={"status": value.status, "treatment": value.treatment, "score": risk.score},
    )
    return risk


@transaction.atomic
def review_risk(
    *, risk: ComplianceRisk, workspace: ResolvedWorkspace, actor_id: UUID, value: RiskInput
) -> ComplianceRisk:
    _validate(value)
    locked = ComplianceRisk.objects.select_for_update().get(pk=risk.pk)
    assignment = _assignment(workspace, value.assignment_id)
    owner_id = _owner(workspace, value.owner_id)
    locked.entity.display_name = value.title
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.assignment = assignment
    locked.description = value.description
    locked.likelihood = value.likelihood
    locked.impact = value.impact
    locked.status = value.status
    locked.treatment = value.treatment
    locked.treatment_plan = value.treatment_plan
    locked.owner_id = owner_id
    locked.due_date = value.due_date
    if value.status == ComplianceRiskStatus.ACCEPTED:
        locked.accepted_by_id = actor_id
        locked.accepted_at = timezone.now()
    else:
        locked.accepted_by_id = None
        locked.accepted_at = None
    locked.save()
    _append_event(locked, actor_id, value)
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="compliance.risk.reviewed",
        entity_id=locked.entity_id,
        metadata={"status": value.status, "treatment": value.treatment, "score": locked.score},
    )
    return locked


def risk_summary(scope: DataScope) -> dict[str, object]:
    today = timezone.localdate()
    queryset = ComplianceRisk.scoped.for_scope(scope)
    counts = {row["status"]: row["count"] for row in queryset.values("status").annotate(count=Count("id"))}
    bands = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    for likelihood, impact in queryset.values_list("likelihood", "impact"):
        score = likelihood * impact
        band = "critical" if score >= 16 else "high" if score >= 10 else "moderate" if score >= 5 else "low"
        bands[band] += 1
    overdue = (
        queryset.filter(due_date__lt=today)
        .exclude(status__in=(ComplianceRiskStatus.CLOSED, ComplianceRiskStatus.ACCEPTED))
        .count()
    )
    return {"total": sum(counts.values()), "by_status": counts, "by_band": bands, "overdue": overdue}
