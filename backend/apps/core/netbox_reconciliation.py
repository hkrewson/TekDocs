from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    CatalogProductKind,
    ClientAsset,
    Entity,
    NetBoxObjectType,
    NetBoxReference,
    Organization,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope

NETBOX_ENTITY_TYPES: dict[str, str] = {
    NetBoxObjectType.RACK: "network_rack",
    NetBoxObjectType.DEVICE: "client_asset",
    NetBoxObjectType.MAC_ADDRESS: "network_mac_address",
    NetBoxObjectType.VLAN: "network_vlan",
    NetBoxObjectType.PREFIX: "network_subnet",
    NetBoxObjectType.IP_ADDRESS: "network_ip_address",
}


class NetBoxReferenceError(ValueError):
    pass


class NetBoxObservation(TypedDict):
    object_type: str
    object_id: int
    fingerprint: str


class ReconciliationItem(TypedDict):
    object_type: str
    object_id: int
    status: str
    entity_id: UUID | None
    entity_name: str
    entity_type: str


@dataclass(frozen=True, slots=True)
class ReconciliationPreview:
    results: list[ReconciliationItem]
    counts: dict[str, int]


def references_for_scope(scope: DataScope) -> QuerySet[NetBoxReference]:
    return (
        NetBoxReference.scoped.for_scope(scope)
        .filter(workspace_id=scope.workspace_id, archived_at__isnull=True)
        .select_related("entity")
        .order_by("object_type", "object_id", "id")
    )


def eligible_entities(scope: DataScope) -> QuerySet[Entity]:
    entities = (
        Entity.scoped.for_tenant(scope.tenant_id)
        .filter(
            workspace_id=scope.workspace_id,
            archived_at__isnull=True,
            entity_type__in=set(NETBOX_ENTITY_TYPES.values()),
        )
    )
    if scope.organization_id is None:
        entities = entities.filter(organization__isnull=True)
    else:
        entities = entities.filter(organization_id=scope.organization_id)
    return entities.order_by("entity_type", "display_name", "id")


def _eligible_entity(scope: DataScope, *, entity_id: UUID, object_type: str) -> Entity:
    expected_type = NETBOX_ENTITY_TYPES.get(object_type)
    if expected_type is None:
        raise NetBoxReferenceError("That NetBox object type is not supported by the lightweight inventory boundary.")
    try:
        entity = eligible_entities(scope).get(id=entity_id, entity_type=expected_type)
    except Entity.DoesNotExist as exc:
        raise NetBoxReferenceError("The selected TekDocs record is unavailable for this NetBox object type.") from exc
    if (
        object_type == NetBoxObjectType.DEVICE
        and not ClientAsset.scoped.for_scope(scope)
        .filter(
            entity=entity,
            archived_at__isnull=True,
            product__kind=CatalogProductKind.HARDWARE,
        )
        .exists()
    ):
        raise NetBoxReferenceError("A NetBox device can link only to an active hardware asset.")
    return entity


@transaction.atomic
def set_reference(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    entity_id: UUID,
    object_type: str,
    object_id: int,
    fingerprint: str,
) -> NetBoxReference:
    scope = DataScope.owner(tenant, organization)
    entity = _eligible_entity(scope, entity_id=entity_id, object_type=object_type)
    conflict = (
        references_for_scope(scope)
        .select_for_update()
        .filter(
            object_type=object_type,
            object_id=object_id,
        )
        .exclude(entity=entity)
    )
    if conflict.exists():
        raise NetBoxReferenceError("That NetBox object is already linked inside this Workspace.")
    reference = references_for_scope(scope).select_for_update().filter(entity=entity).first()
    if reference is None:
        reference = NetBoxReference(
            tenant=tenant,
            workspace=workspace_for_owner(tenant=tenant, organization=organization),
            organization=organization,
            entity=entity,
        )
    reference.object_type = object_type
    reference.object_id = object_id
    reference.observed_fingerprint = fingerprint
    reference.last_observed_at = timezone.now() if fingerprint else None
    reference.full_clean()
    reference.save()
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="netbox_reference.set",
        entity_id=entity.id,
        metadata={"object_type": object_type},
    )
    return references_for_scope(scope).get(pk=reference.pk)


@transaction.atomic
def archive_reference(*, reference: NetBoxReference, actor_id: UUID) -> None:
    locked = references_for_scope(DataScope.owner(reference.tenant, reference.organization)).select_for_update().get(
        pk=reference.pk
    )
    if locked.archived_at is not None:
        return
    locked.archived_at = timezone.now()
    locked.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="netbox_reference.archived",
        entity_id=locked.entity_id,
        metadata={"object_type": locked.object_type},
    )


def reconciliation_preview(scope: DataScope, observations: list[NetBoxObservation]) -> ReconciliationPreview:
    remote_keys: set[tuple[str, int]] = set()
    for observation in observations:
        key = (observation["object_type"], observation["object_id"])
        if key in remote_keys:
            raise NetBoxReferenceError("A reconciliation preview cannot contain duplicate NetBox objects.")
        remote_keys.add(key)

    references = list(references_for_scope(scope))
    by_remote = {(item.object_type, item.object_id): item for item in references}
    results: list[ReconciliationItem] = []
    for observation in sorted(observations, key=lambda item: (item["object_type"], item["object_id"])):
        reference = by_remote.get((observation["object_type"], observation["object_id"]))
        if reference is None:
            results.append(
                {
                    "object_type": observation["object_type"],
                    "object_id": observation["object_id"],
                    "status": "unmatched",
                    "entity_id": None,
                    "entity_name": "",
                    "entity_type": "",
                }
            )
            continue
        status = (
            "current"
            if reference.observed_fingerprint and reference.observed_fingerprint == observation["fingerprint"]
            else "changed"
        )
        results.append(
            {
                "object_type": observation["object_type"],
                "object_id": observation["object_id"],
                "status": status,
                "entity_id": reference.entity_id,
                "entity_name": reference.entity.display_name,
                "entity_type": reference.entity.entity_type,
            }
        )
    for reference in references:
        if (reference.object_type, reference.object_id) not in remote_keys:
            results.append(
                {
                    "object_type": reference.object_type,
                    "object_id": reference.object_id,
                    "status": "missing_remote",
                    "entity_id": reference.entity_id,
                    "entity_name": reference.entity.display_name,
                    "entity_type": reference.entity.entity_type,
                }
            )
    results.sort(key=lambda item: (item["object_type"], item["object_id"], item["status"]))
    return ReconciliationPreview(results=results, counts=dict(Counter(item["status"] for item in results)))
