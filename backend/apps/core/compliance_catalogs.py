from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch, QuerySet

from .models import (
    AuditEvent,
    ComplianceCatalogEntry,
    ComplianceCatalogRevision,
    ComplianceControl,
    ComplianceControlRevision,
    ComplianceFramework,
    Entity,
    EntityVisibility,
    Organization,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope

MAX_CONTROLS = 1_000


class ComplianceCatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ControlInput:
    identifier: str
    title: str
    description: str
    guidance: str
    control_id: UUID | None = None


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _control_payload(value: ControlInput) -> dict[str, str]:
    return {
        "identifier": value.identifier,
        "title": value.title,
        "description": value.description,
        "guidance": value.guidance,
    }


def frameworks_for_scope(scope: DataScope) -> QuerySet[ComplianceFramework]:
    control_revisions = ComplianceControlRevision.objects.select_related("control", "control__entity", "created_by")
    entries = ComplianceCatalogEntry.objects.select_related(
        "control_revision", "control_revision__control__entity"
    ).order_by("position")
    revisions = ComplianceCatalogRevision.objects.select_related("created_by").prefetch_related(
        Prefetch("entries", queryset=entries)
    )
    return (
        ComplianceFramework.scoped.for_scope(scope)
        .select_related("entity", "current_revision", "current_revision__created_by")
        .prefetch_related(
            Prefetch("revisions", queryset=revisions), Prefetch("controls__revisions", queryset=control_revisions)
        )
        .order_by("entity__display_name", "id")
    )


def _create_control(
    *, framework: ComplianceFramework, actor_id: UUID, value: ControlInput
) -> ComplianceControlRevision:
    entity = Entity.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        entity_type="compliance_control",
        display_name=f"{value.identifier} — {value.title}",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    control = ComplianceControl.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        framework=framework,
        entity=entity,
    )
    payload = _control_payload(value)
    return ComplianceControlRevision.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        control=control,
        revision_number=1,
        created_by_id=actor_id,
        content_digest=_digest(payload),
        **payload,
    )


def _resolve_control_revision(
    *, framework: ComplianceFramework, actor_id: UUID, value: ControlInput
) -> ComplianceControlRevision:
    if value.control_id is None:
        return _create_control(framework=framework, actor_id=actor_id, value=value)
    try:
        control = (
            ComplianceControl.objects.select_for_update()
            .select_related("entity")
            .get(entity_id=value.control_id, framework=framework)
        )
    except ComplianceControl.DoesNotExist as exc:
        raise ComplianceCatalogError("A referenced control does not belong to this framework.") from exc
    current = control.revisions.order_by("-revision_number").first()
    payload = _control_payload(value)
    digest = _digest(payload)
    if current is not None and current.content_digest == digest:
        return current
    control.entity.display_name = f"{value.identifier} — {value.title}"
    control.entity.save(update_fields=("display_name", "updated_at"))
    return ComplianceControlRevision.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        control=control,
        revision_number=(current.revision_number + 1 if current else 1),
        created_by_id=actor_id,
        content_digest=digest,
        **payload,
    )


def _catalog_payload(
    *, version_label: str, description: str, source_url: str, control_revisions: list[ComplianceControlRevision]
) -> dict[str, object]:
    return {
        "version_label": version_label,
        "description": description,
        "source_url": source_url,
        "controls": [
            {
                "control_id": str(revision.control.entity_id),
                "control_revision": revision.revision_number,
                "content_digest": revision.content_digest,
            }
            for revision in control_revisions
        ],
    }


def _validate_controls(values: list[ControlInput]) -> None:
    if len(values) > MAX_CONTROLS:
        raise ComplianceCatalogError(f"A catalog version cannot contain more than {MAX_CONTROLS} controls.")
    stable_ids = [value.control_id for value in values if value.control_id is not None]
    if len(stable_ids) != len(set(stable_ids)):
        raise ComplianceCatalogError("A control may appear only once in a catalog version.")
    identifiers = [value.identifier.casefold() for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ComplianceCatalogError("Control identifiers must be unique within a catalog version.")


def _create_catalog_revision(
    *,
    framework: ComplianceFramework,
    actor_id: UUID,
    revision_number: int,
    version_label: str,
    description: str,
    source_url: str,
    controls: list[ControlInput],
) -> ComplianceCatalogRevision:
    _validate_controls(controls)
    exact_revisions = [
        _resolve_control_revision(framework=framework, actor_id=actor_id, value=value) for value in controls
    ]
    payload = _catalog_payload(
        version_label=version_label,
        description=description,
        source_url=source_url,
        control_revisions=exact_revisions,
    )
    revision = ComplianceCatalogRevision.objects.create(
        tenant=framework.tenant,
        workspace=framework.workspace,
        organization=framework.organization,
        framework=framework,
        revision_number=revision_number,
        version_label=version_label,
        description=description,
        source_url=source_url,
        content_digest=_digest(payload),
        created_by_id=actor_id,
    )
    ComplianceCatalogEntry.objects.bulk_create(
        [
            ComplianceCatalogEntry(
                tenant=framework.tenant,
                workspace=framework.workspace,
                organization=framework.organization,
                catalog_revision=revision,
                control_revision=control_revision,
                position=position,
            )
            for position, control_revision in enumerate(exact_revisions)
        ]
    )
    return revision


@transaction.atomic
def create_framework(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    version_label: str,
    description: str,
    source_url: str,
    controls: list[ControlInput],
) -> ComplianceFramework:
    workspace = workspace_for_owner(tenant=tenant, organization=organization)
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace,
        organization=organization,
        entity_type="compliance_framework",
        display_name=name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    framework = ComplianceFramework.objects.create(
        tenant=tenant, workspace=workspace, organization=organization, entity=entity
    )
    revision = _create_catalog_revision(
        framework=framework,
        actor_id=actor_id,
        revision_number=1,
        version_label=version_label,
        description=description,
        source_url=source_url,
        controls=controls,
    )
    framework.current_revision = revision
    framework.save(update_fields=("current_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="compliance.framework.created",
        entity_id=entity.id,
        metadata={"revision_number": 1, "control_count": len(controls)},
    )
    return framework


@transaction.atomic
def create_catalog_version(
    *,
    framework: ComplianceFramework,
    actor_id: UUID,
    version_label: str,
    description: str,
    source_url: str,
    controls: list[ControlInput],
) -> ComplianceCatalogRevision:
    locked = ComplianceFramework.objects.select_for_update().get(pk=framework.pk)
    revision_number = locked.current_revision.revision_number + 1 if locked.current_revision else 1
    revision = _create_catalog_revision(
        framework=locked,
        actor_id=actor_id,
        revision_number=revision_number,
        version_label=version_label,
        description=description,
        source_url=source_url,
        controls=controls,
    )
    locked.current_revision = revision
    locked.save(update_fields=("current_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="compliance.catalog.versioned",
        entity_id=locked.entity_id,
        metadata={"revision_number": revision_number, "control_count": len(controls)},
    )
    return revision
