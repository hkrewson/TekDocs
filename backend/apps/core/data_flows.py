"""Structured data-flow records (ADR 0088).

A data flow states that some category of data moves between two parties, by some
mechanism, under some protection. That statement is evidence, so the content lives in
immutable `DataFlowRevision` rows and the `DataFlow` record carries only identity and
a pointer to the revision currently in force. Editing a flow appends; it never
rewrites what an earlier reader relied on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from uuid import UUID

from django.db import models, transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    DataFlow,
    DataFlowClassification,
    DataFlowDirection,
    DataFlowEndpointKind,
    DataFlowProtection,
    DataFlowProvenance,
    DataFlowRevision,
    DataFlowSnapshot,
    DataFlowTransfer,
    Entity,
    EntityVisibility,
)
from .scoping import DataScope
from .workspaces import ResolvedWorkspace


class DataFlowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DataFlowInput:
    """One complete statement of a flow. Every revision is written from one of these."""

    name: str
    source_kind: str
    destination_kind: str
    direction: str
    transfer_mechanism: str
    data_classification: str
    purpose: str
    crosses_trust_boundary: bool
    protection: str
    provenance: str
    source_entity_id: UUID | None = None
    source_label: str = ""
    destination_entity_id: UUID | None = None
    destination_label: str = ""
    owner_entity_id: UUID | None = None
    review_due_on: date | None = None


def data_flows_for_scope(scope: DataScope, *, query: str = "") -> QuerySet[DataFlow]:
    revisions = DataFlowRevision.objects.select_related(
        "source_entity", "destination_entity", "owner_entity", "created_by"
    )
    records = (
        DataFlow.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related(
            "entity",
            "created_by",
            "current_revision",
            "current_revision__source_entity",
            "current_revision__destination_entity",
            "current_revision__owner_entity",
        )
        .prefetch_related(Prefetch("revisions", queryset=revisions))
    )
    normalized = query.strip()[:100]
    if normalized:
        records = records.filter(
            Q(entity__display_name__icontains=normalized)
            | Q(current_revision__purpose__icontains=normalized)
            | Q(current_revision__source_label__icontains=normalized)
            | Q(current_revision__destination_label__icontains=normalized)
        )
    return records


def revisions_for_flow(flow: DataFlow) -> QuerySet[DataFlowRevision]:
    return flow.revisions.select_related("source_entity", "destination_entity", "owner_entity", "created_by").order_by(
        "-revision_number"
    )


def data_flow_choices() -> dict[str, list[dict[str, str]]]:
    """The bounded vocabularies an authoring surface may offer.

    Served from the server so the browser cannot invent a value the check constraints
    would reject, and so a new mechanism becomes available without a frontend release.
    """

    def options(choices: type[models.TextChoices]) -> list[dict[str, str]]:
        return [{"value": value, "label": label} for value, label in choices.choices]

    return {
        "endpoint_kinds": options(DataFlowEndpointKind),
        "directions": options(DataFlowDirection),
        "transfer_mechanisms": options(DataFlowTransfer),
        "data_classifications": options(DataFlowClassification),
        "protections": options(DataFlowProtection),
        "provenance_states": options(DataFlowProvenance),
    }


def _digest(value: DataFlowInput) -> str:
    payload = {key: (str(item) if isinstance(item, UUID | date) else item) for key, item in asdict(value).items()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _endpoint(workspace: ResolvedWorkspace, entity_id: UUID | None, label: str) -> Entity | None:
    if entity_id is None:
        return None
    try:
        return Entity.scoped.for_scope(workspace.data_scope).get(pk=entity_id, archived_at__isnull=True)
    except Entity.DoesNotExist as exc:
        raise DataFlowError(f"The selected {label} is unavailable in this workspace.") from exc


def _validate(workspace: ResolvedWorkspace, value: DataFlowInput) -> dict[str, Entity | None]:
    if not value.name.strip():
        raise DataFlowError("A data flow needs a name.")
    if not value.purpose.strip():
        raise DataFlowError("A data flow needs a stated purpose.")
    for field, allowed, label in (
        (value.source_kind, DataFlowEndpointKind.values, "source kind"),
        (value.destination_kind, DataFlowEndpointKind.values, "destination kind"),
        (value.direction, DataFlowDirection.values, "direction"),
        (value.transfer_mechanism, DataFlowTransfer.values, "transfer mechanism"),
        (value.data_classification, DataFlowClassification.values, "data classification"),
        (value.protection, DataFlowProtection.values, "protection"),
        (value.provenance, DataFlowProvenance.values, "provenance state"),
    ):
        if field not in allowed:
            raise DataFlowError(f"Unknown {label}.")

    # An endpoint is a record in this Workspace or a named outside party, never both and
    # never neither. The database enforces the same rule; this states it in words.
    for kind, entity_id, endpoint_label, side in (
        (value.source_kind, value.source_entity_id, value.source_label, "source"),
        (value.destination_kind, value.destination_entity_id, value.destination_label, "destination"),
    ):
        if kind == DataFlowEndpointKind.INTERNAL:
            if entity_id is None:
                raise DataFlowError(f"An internal {side} requires a TekDocs record.")
            if endpoint_label.strip():
                raise DataFlowError(f"An internal {side} is named by its record, not by a label.")
        else:
            if not endpoint_label.strip():
                raise DataFlowError(f"An external {side} requires a name.")
            if entity_id is not None:
                raise DataFlowError(f"An external {side} cannot also reference a TekDocs record.")

    return {
        "source_entity": _endpoint(workspace, value.source_entity_id, "source"),
        "destination_entity": _endpoint(workspace, value.destination_entity_id, "destination"),
        "owner_entity": _endpoint(workspace, value.owner_entity_id, "owner"),
    }


def _write_revision(
    *, flow: DataFlow, actor_id: UUID, value: DataFlowInput, endpoints: dict[str, Entity | None], number: int
) -> DataFlowRevision:
    return DataFlowRevision.objects.create(
        tenant=flow.tenant,
        workspace=flow.workspace,
        organization=flow.organization,
        data_flow=flow,
        revision_number=number,
        source_kind=value.source_kind,
        source_entity=endpoints["source_entity"],
        source_label=value.source_label.strip(),
        destination_kind=value.destination_kind,
        destination_entity=endpoints["destination_entity"],
        destination_label=value.destination_label.strip(),
        direction=value.direction,
        transfer_mechanism=value.transfer_mechanism,
        data_classification=value.data_classification,
        purpose=value.purpose.strip(),
        crosses_trust_boundary=value.crosses_trust_boundary,
        protection=value.protection,
        owner_entity=endpoints["owner_entity"],
        review_due_on=value.review_due_on,
        provenance=value.provenance,
        content_digest=_digest(value),
        created_by_id=actor_id,
    )


@transaction.atomic
def create_data_flow(*, workspace: ResolvedWorkspace, actor_id: UUID, value: DataFlowInput) -> DataFlow:
    endpoints = _validate(workspace, value)
    entity = Entity.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity_type="data_flow",
        display_name=value.name.strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    flow = DataFlow.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        created_by_id=actor_id,
    )
    revision = _write_revision(flow=flow, actor_id=actor_id, value=value, endpoints=endpoints, number=1)
    flow.current_revision = revision
    flow.save(update_fields=("current_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=flow.tenant,
        actor_id=actor_id,
        action="data_flow.created",
        entity_id=entity.id,
        metadata={"provenance": value.provenance, "data_classification": value.data_classification},
    )
    return data_flows_for_scope(workspace.data_scope).get(pk=flow.pk)


@transaction.atomic
def revise_data_flow(*, workspace: ResolvedWorkspace, flow: DataFlow, actor_id: UUID, value: DataFlowInput) -> DataFlow:
    endpoints = _validate(workspace, value)
    # `of=("self",)` because `current_revision` is nullable: the select_related left
    # outer join is not lockable, and only the flow row needs the lock.
    locked = (
        DataFlow.objects.select_for_update(of=("self",)).select_related("entity", "current_revision").get(pk=flow.pk)
    )
    current = locked.current_revision
    # An unchanged submission must not consume a revision number. Retained evidence is
    # read by revision, and a chain of identical revisions makes it unreadable.
    if current is not None and current.content_digest == _digest(value):
        return data_flows_for_scope(workspace.data_scope).get(pk=locked.pk)
    number = current.revision_number + 1 if current is not None else 1
    revision = _write_revision(flow=locked, actor_id=actor_id, value=value, endpoints=endpoints, number=number)
    if locked.entity.display_name != value.name.strip():
        locked.entity.display_name = value.name.strip()
        locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.current_revision = revision
    locked.save(update_fields=("current_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="data_flow.revised",
        entity_id=locked.entity_id,
        metadata={"revision_number": number, "provenance": value.provenance},
    )
    return data_flows_for_scope(workspace.data_scope).get(pk=locked.pk)


@transaction.atomic
def archive_data_flow(*, flow: DataFlow, actor_id: UUID) -> None:
    moment = timezone.now()
    flow.archived_at = moment
    flow.save(update_fields=("archived_at", "updated_at"))
    flow.entity.archived_at = moment
    flow.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=flow.tenant,
        actor_id=actor_id,
        action="data_flow.archived",
        entity_id=flow.entity_id,
        metadata={},
    )


#: Canonical form for anything that gets digested or exported. Byte-identical output
#: for identical content is the whole point of a snapshot: a reader comparing two
#: exports must be comparing content, not formatting.
def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _revision_projection(revision: DataFlowRevision) -> dict[str, object]:
    """One revision as retained evidence states it.

    Endpoints are projected as their resolved display name rather than as a reference,
    because a snapshot read years later must not depend on the referenced record still
    existing, or still being named the same thing.
    """

    def endpoint(record: Entity | None, label: str) -> str:
        return record.display_name if record is not None else label

    return {
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "source": endpoint(revision.source_entity, revision.source_label),
        "source_kind": revision.source_kind,
        "destination": endpoint(revision.destination_entity, revision.destination_label),
        "destination_kind": revision.destination_kind,
        "direction": revision.direction,
        "transfer_mechanism": revision.transfer_mechanism,
        "data_classification": revision.data_classification,
        "purpose": revision.purpose,
        "crosses_trust_boundary": revision.crosses_trust_boundary,
        "protection": revision.protection,
        "owner": endpoint(revision.owner_entity, ""),
        "review_due_on": revision.review_due_on.isoformat() if revision.review_due_on else None,
        "provenance": revision.provenance,
        "content_digest": revision.content_digest,
    }


def data_flow_projection(*, workspace: ResolvedWorkspace, related_visibility: str | None = None) -> dict[str, object]:
    """The authorized set of flows in force, with a digest over exactly that content.

    `related_visibility` narrows to flows whose anchor carries that visibility, which is
    how a client-visible publication excludes MSP-private flows. Flows are anchored
    MSP-private on creation, so a client publication carries none until one is
    deliberately made visible — the safe direction to be wrong in.
    """

    records = data_flows_for_scope(workspace.data_scope).select_related("entity")
    if related_visibility is not None:
        records = records.filter(entity__visibility=related_visibility)
    flows = sorted(
        (
            {
                "id": str(record.entity_id),
                "name": record.entity.display_name,
                **_revision_projection(record.current_revision),
            }
            for record in records
            if record.current_revision is not None
        ),
        key=lambda flow: str(flow["id"]),
    )
    body = {
        "workspace": {"kind": workspace.kind, "id": str(workspace.id)},
        "flows": flows,
    }
    return {**body, "digest": hashlib.sha256(canonical_json(body)).hexdigest()}


def snapshots_for_scope(scope: DataScope) -> QuerySet[DataFlowSnapshot]:
    return DataFlowSnapshot.scoped.for_scope(scope).select_related("created_by")


@transaction.atomic
def create_data_flow_snapshot(
    *, workspace: ResolvedWorkspace, actor_id: UUID, title: str, reason: str = ""
) -> DataFlowSnapshot:
    if not title.strip():
        raise DataFlowError("A snapshot needs a title.")
    projection = data_flow_projection(workspace=workspace)
    flows = projection["flows"]
    flow_count = len(flows) if isinstance(flows, list) else 0
    snapshot = DataFlowSnapshot.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        title=title.strip(),
        reason=reason.strip(),
        flows=projection,
        flow_count=flow_count,
        content_digest=str(projection["digest"]),
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=snapshot.tenant,
        actor_id=actor_id,
        action="data_flow.snapshot.created",
        entity_id=None,
        metadata={"flow_count": snapshot.flow_count},
    )
    return snapshot
