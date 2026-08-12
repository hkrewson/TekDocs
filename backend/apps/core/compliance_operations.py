from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction

from apps.accounts.models import TenantMembership
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import (
    AuditEvent,
    ComplianceApplicability,
    ComplianceAssignmentReview,
    ComplianceControl,
    ComplianceControlAssignment,
    ComplianceControlRevision,
    ComplianceFramework,
    ComplianceImplementationStatus,
)
from .scoping import DataScope


class ComplianceOperationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AssignmentInput:
    applicability: str
    implementation_status: str
    decision: str
    note: str = ""
    owner_id: UUID | None = None
    review_due_date: date | None = None


def assignments_for_scope(scope: DataScope):  # type: ignore[no-untyped-def]
    return (
        ComplianceControlAssignment.scoped.for_scope(scope)
        .select_related("framework__entity", "control__entity", "control_revision", "owner")
        .prefetch_related("reviews__reviewed_by", "reviews__control_revision")
    )


def owner_choices_for_framework(framework: ComplianceFramework) -> list[dict[str, str]]:
    memberships = (
        TenantMembership.scoped.for_tenant(framework.tenant).filter(user__is_active=True).select_related("user")
    )
    return [
        {"id": str(member.user_id), "display_name": member.user.display_name}
        for member in memberships
        if context_has_permission(
            require_installation_member(member.user),
            PermissionKey.COMPLIANCE_VIEW,
            organization=framework.organization,
        )
    ]


def _owner_membership(framework: ComplianceFramework, owner_id: UUID | None) -> TenantMembership | None:
    if owner_id is None:
        return None
    try:
        member = TenantMembership.objects.select_related("user").get(
            tenant=framework.tenant, user_id=owner_id, user__is_active=True
        )
    except TenantMembership.DoesNotExist as exc:
        raise ComplianceOperationError("The selected owner is not an active member of this MSP.") from exc
    if not context_has_permission(
        require_installation_member(member.user), PermissionKey.COMPLIANCE_VIEW, organization=framework.organization
    ):
        raise ComplianceOperationError("The selected owner cannot access this compliance workspace.")
    return member


def _current_revision(framework: ComplianceFramework, control: ComplianceControl) -> ComplianceControlRevision:
    current_revision = framework.current_revision
    if current_revision is None:
        raise ComplianceOperationError("The framework has no current catalog version.")
    entry = (
        current_revision.entries.select_related("control_revision")
        .filter(control_revision__control=control)
        .first()
    )
    if entry is None:
        raise ComplianceOperationError("The control is not present in the current catalog version.")
    return entry.control_revision


@transaction.atomic
def record_assignment_review(
    *, framework: ComplianceFramework, control_entity_id: UUID, actor_id: UUID, value: AssignmentInput
) -> ComplianceControlAssignment:
    if value.applicability not in ComplianceApplicability.values:
        raise ComplianceOperationError("Unknown applicability state.")
    if value.implementation_status not in ComplianceImplementationStatus.values:
        raise ComplianceOperationError("Unknown implementation status.")
    try:
        control = ComplianceControl.objects.select_for_update().get(framework=framework, entity_id=control_entity_id)
    except ComplianceControl.DoesNotExist as exc:
        raise ComplianceOperationError("The control does not belong to this framework.") from exc
    owner = _owner_membership(framework, value.owner_id)
    revision = _current_revision(framework, control)
    assignment, _ = ComplianceControlAssignment.objects.select_for_update().get_or_create(
        workspace=framework.workspace,
        control=control,
        defaults={
            "tenant": framework.tenant,
            "organization": framework.organization,
            "framework": framework,
            "control_revision": revision,
        },
    )
    assignment.control_revision = revision
    assignment.applicability = value.applicability
    assignment.implementation_status = value.implementation_status
    assignment.owner_id = owner.user_id if owner else None
    assignment.review_due_date = value.review_due_date
    assignment.save(
        update_fields=(
            "control_revision",
            "applicability",
            "implementation_status",
            "owner",
            "review_due_date",
            "updated_at",
        )
    )
    ComplianceAssignmentReview.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        assignment=assignment,
        control_revision=revision,
        applicability=value.applicability,
        implementation_status=value.implementation_status,
        decision=value.decision,
        note=value.note,
        reviewed_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=framework.tenant,
        actor_id=actor_id,
        action="compliance.assignment.reviewed",
        entity_id=control.entity_id,
        metadata={"applicability": value.applicability, "implementation_status": value.implementation_status},
    )
    return assignment
