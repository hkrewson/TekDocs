from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction

from apps.accounts.models import TenantMembership
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

from .models import AuditEvent, Entity, EntityVisibility, ReminderDomain, ReminderRecurrence, ReminderSchedule
from .workspaces import ResolvedWorkspace


class ReminderError(ValueError):
    pass


SOURCE_TYPES: dict[str, frozenset[str]] = {
    ReminderDomain.COMPLIANCE.value: frozenset(
        {"compliance_framework", "compliance_control", "compliance_evidence", "compliance_risk"}
    ),
    ReminderDomain.INVENTORY.value: frozenset({"client_asset", "software_license", "commercial_contract"}),
    ReminderDomain.DOMAIN.value: frozenset({"registered_domain", "managed_hostname"}),
    ReminderDomain.DOCUMENTATION.value: frozenset({"document"}),
    ReminderDomain.INVOICE.value: frozenset({"invoice"}),
}


@dataclass(frozen=True, slots=True)
class ReminderInput:
    source_entity_id: UUID
    domain: str
    kind: str
    title: str
    due_on: date
    lead_days: int = 30
    recurrence: str = ReminderRecurrence.NONE
    owner_id: UUID | None = None


def reminders_for_scope(workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    return (
        ReminderSchedule.scoped.for_scope(workspace.data_scope)
        .select_related("entity", "source_entity", "owner", "created_by")
    )


def _owner(workspace: ResolvedWorkspace, owner_id: UUID | None):  # type: ignore[no-untyped-def]
    if owner_id is None:
        return None
    try:
        membership = TenantMembership.objects.select_related("user").get(
            tenant=workspace.member.tenant, user_id=owner_id, user__is_active=True
        )
    except TenantMembership.DoesNotExist as exc:
        raise ReminderError("The selected owner is unavailable.") from exc
    context = require_installation_member(membership.user)
    if not context_has_permission(context, PermissionKey.DEADLINES_VIEW, organization=workspace.organization):
        raise ReminderError("The selected owner cannot access this deadline workspace.")
    return membership.user


def _validate(workspace: ResolvedWorkspace, value: ReminderInput):  # type: ignore[no-untyped-def]
    if value.domain not in ReminderDomain.values:
        raise ReminderError("Unknown reminder domain.")
    if value.recurrence not in ReminderRecurrence.values:
        raise ReminderError("Unknown recurrence.")
    if not value.kind or len(value.kind) > 48 or not value.kind.replace("_", "").isalnum():
        raise ReminderError("Kind must be a short machine-readable name.")
    if value.lead_days not in range(0, 3651):
        raise ReminderError("Lead days must be between 0 and 3650.")
    try:
        source = Entity.scoped.for_scope(workspace.data_scope).get(pk=value.source_entity_id, archived_at__isnull=True)
    except Entity.DoesNotExist as exc:
        raise ReminderError("The selected source is unavailable in this workspace.") from exc
    if source.entity_type not in SOURCE_TYPES[value.domain]:
        raise ReminderError("The selected source does not match the reminder domain.")
    return source


@transaction.atomic
def create_reminder(*, workspace: ResolvedWorkspace, actor_id: UUID, value: ReminderInput) -> ReminderSchedule:
    source = _validate(workspace, value)
    owner = _owner(workspace, value.owner_id)
    entity = Entity.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="reminder_schedule",
        display_name=value.title,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    reminder = ReminderSchedule.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        source_entity=source,
        domain=value.domain,
        kind=value.kind,
        title=value.title,
        due_on=value.due_on,
        lead_days=value.lead_days,
        recurrence=value.recurrence,
        owner=owner,
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=reminder.tenant,
        actor_id=actor_id,
        action="reminder.created",
        entity_id=entity.id,
        metadata={"domain": reminder.domain, "kind": reminder.kind},
    )
    return reminder


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def calendar_bytes(*, workspace: ResolvedWorkspace) -> bytes:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TekDocs//Deadlines//EN", "CALSCALE:GREGORIAN"]
    for reminder in reminders_for_scope(workspace).filter(active=True)[:5_000]:
        event = [
            "BEGIN:VEVENT",
            f"UID:{reminder.id}@tekdocs",
            f"DTSTART;VALUE=DATE:{reminder.due_on.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(reminder.title)}",
            f"CATEGORIES:{reminder.domain.upper()}",
            "TRANSP:TRANSPARENT",
        ]
        if reminder.recurrence == ReminderRecurrence.ANNUAL:
            event.append("RRULE:FREQ=YEARLY")
        event.append("END:VEVENT")
        lines.extend(event)
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
