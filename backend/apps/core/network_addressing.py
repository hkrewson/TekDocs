from __future__ import annotations

import ipaddress
from typing import cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import QuerySet

from .models import (
    AuditEvent,
    Entity,
    EntityVisibility,
    NetworkSubnet,
    NetworkVLAN,
    NetworkVRF,
    Organization,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope


class NetworkAddressingError(ValueError):
    pass


def canonical_network(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise NetworkAddressingError("Enter a valid IPv4 or IPv6 CIDR prefix.") from exc
    canonical = network.with_prefixlen
    if value.strip() != canonical:
        raise NetworkAddressingError(f"CIDR must identify the network boundary; use {canonical}.")
    return network


def networks_overlap(left: str, right: str) -> bool:
    first = ipaddress.ip_network(left, strict=True)
    second = ipaddress.ip_network(right, strict=True)
    return first.version == second.version and first.overlaps(second)


def vrfs_for_scope(scope: DataScope) -> QuerySet[NetworkVRF]:
    return NetworkVRF.scoped.for_scope(scope).select_related("entity")


def vlans_for_scope(scope: DataScope) -> QuerySet[NetworkVLAN]:
    return NetworkVLAN.scoped.for_scope(scope).select_related("entity")


def subnets_for_scope(scope: DataScope) -> QuerySet[NetworkSubnet]:
    return NetworkSubnet.scoped.for_scope(scope).select_related("entity", "vrf__entity", "vlan__entity")


def _vrf(scope: DataScope, entity_id: UUID | None) -> NetworkVRF | None:
    if entity_id is None:
        return None
    try:
        return NetworkVRF.scoped.for_scope(scope).select_related("entity").get(entity_id=entity_id)
    except NetworkVRF.DoesNotExist as exc:
        raise NetworkAddressingError("The selected VRF is unavailable in this Workspace.") from exc


def _vlan(scope: DataScope, entity_id: UUID | None) -> NetworkVLAN | None:
    if entity_id is None:
        return None
    try:
        return NetworkVLAN.scoped.for_scope(scope).select_related("entity").get(entity_id=entity_id)
    except NetworkVLAN.DoesNotExist as exc:
        raise NetworkAddressingError("The selected VLAN is unavailable in this Workspace.") from exc


def _lock_routing_namespace(scope: DataScope, vrf: NetworkVRF | None) -> None:
    if connection.vendor == "postgresql":
        key = f"{scope.tenant_id}:{scope.organization_id or 'msp'}:{vrf.id if vrf else 'default'}"
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


def _assert_no_overlap(
    scope: DataScope,
    *,
    cidr: str,
    vrf: NetworkVRF | None,
    exclude_subnet_id: UUID | None = None,
) -> None:
    query = NetworkSubnet.scoped.for_scope(scope).filter(vrf=vrf)
    if exclude_subnet_id is not None:
        query = query.exclude(pk=exclude_subnet_id)
    for existing in query.only("cidr"):
        if networks_overlap(cidr, existing.cidr):
            label = vrf.entity.display_name if vrf is not None else "the default routing table"
            raise NetworkAddressingError(f"{cidr} overlaps {existing.cidr} in {label}.")


def _create_entity(*, tenant: Tenant, organization: Organization | None, entity_type: str, name: str) -> Entity:
    clean_name = name.strip()
    if not clean_name:
        raise NetworkAddressingError("Name cannot be blank.")
    return Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type=entity_type,
        display_name=clean_name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )


@transaction.atomic
def create_vrf(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    route_distinguisher: str,
    description: str,
) -> NetworkVRF:
    scope = DataScope.owner(tenant, organization)
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="network_vrf", name=name)
    record = NetworkVRF(
        tenant=tenant,
        organization=organization,
        entity=entity,
        route_distinguisher=route_distinguisher.strip(),
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_vrf.created", entity_id=entity.id, metadata={}
    )
    return vrfs_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_vrf(*, record: NetworkVRF, actor_id: UUID, values: dict[str, object]) -> NetworkVRF:
    locked = NetworkVRF.objects.select_for_update().select_related("entity").get(pk=record.pk)
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.route_distinguisher = str(values.get("route_distinguisher", locked.route_distinguisher)).strip()
    locked.description = str(values.get("description", locked.description)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="network_vrf.updated", entity_id=locked.entity_id, metadata={}
    )
    return vrfs_for_scope(DataScope.owner(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def create_vlan(
    *, tenant: Tenant, organization: Organization | None, actor_id: UUID, name: str, vlan_id: int, description: str
) -> NetworkVLAN:
    scope = DataScope.owner(tenant, organization)
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="network_vlan", name=name)
    record = NetworkVLAN(
        tenant=tenant, organization=organization, entity=entity, vlan_id=vlan_id, description=description.strip()
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_vlan.created", entity_id=entity.id, metadata={}
    )
    return vlans_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_vlan(*, record: NetworkVLAN, actor_id: UUID, values: dict[str, object]) -> NetworkVLAN:
    locked = NetworkVLAN.objects.select_for_update().select_related("entity").get(pk=record.pk)
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.vlan_id = cast(int, values.get("vlan_id", locked.vlan_id))
    locked.description = str(values.get("description", locked.description)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="network_vlan.updated", entity_id=locked.entity_id, metadata={}
    )
    return vlans_for_scope(DataScope.owner(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def create_subnet(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    cidr: str,
    vrf_entity_id: UUID | None,
    vlan_entity_id: UUID | None,
    description: str,
) -> NetworkSubnet:
    scope = DataScope.owner(tenant, organization)
    network = canonical_network(cidr)
    vrf = _vrf(scope, vrf_entity_id)
    vlan = _vlan(scope, vlan_entity_id)
    _lock_routing_namespace(scope, vrf)
    _assert_no_overlap(scope, cidr=network.with_prefixlen, vrf=vrf)
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="network_subnet", name=name)
    record = NetworkSubnet(
        tenant=tenant,
        organization=organization,
        entity=entity,
        cidr=network.with_prefixlen,
        address_family=network.version,
        vrf=vrf,
        vlan=vlan,
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_subnet.created", entity_id=entity.id, metadata={}
    )
    return subnets_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_subnet(*, record: NetworkSubnet, actor_id: UUID, values: dict[str, object]) -> NetworkSubnet:
    locked = NetworkSubnet.objects.select_for_update().select_related("entity", "vrf", "vlan").get(pk=record.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    network = canonical_network(str(values.get("cidr", locked.cidr)))
    current_vrf_id = locked.vrf.entity_id if locked.vrf is not None else None
    current_vlan_id = locked.vlan.entity_id if locked.vlan is not None else None
    vrf = _vrf(scope, cast(UUID | None, values.get("vrf_entity_id", current_vrf_id)))
    vlan = _vlan(
        scope, cast(UUID | None, values.get("vlan_entity_id", current_vlan_id))
    )
    _lock_routing_namespace(scope, vrf)
    _assert_no_overlap(scope, cidr=network.with_prefixlen, vrf=vrf, exclude_subnet_id=locked.pk)
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.cidr = network.with_prefixlen
    locked.address_family = network.version
    locked.vrf = vrf
    locked.vlan = vlan
    locked.description = str(values.get("description", locked.description)).strip()
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_subnet.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return subnets_for_scope(scope).get(pk=locked.pk)
