from __future__ import annotations

import ipaddress
import re
from typing import cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import QuerySet

from .models import (
    AuditEvent,
    Entity,
    EntityVisibility,
    NetworkDevice,
    NetworkInterface,
    NetworkIPAddress,
    NetworkMACAddress,
    NetworkSubnet,
    Organization,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope


class NetworkEndpointError(ValueError):
    pass


def canonical_host(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    submitted = value.strip()
    try:
        address = ipaddress.ip_address(submitted)
    except ValueError as exc:
        raise NetworkEndpointError("Enter a valid IPv4 or IPv6 host address.") from exc
    canonical = address.compressed
    if submitted != canonical:
        raise NetworkEndpointError(f"IP address must use canonical form; use {canonical}.")
    return address


def canonical_mac(value: str) -> str:
    submitted = value.strip()
    compact = re.sub(r"[:-]", "", submitted)
    if "." in compact:
        compact = compact.replace(".", "")
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        raise NetworkEndpointError("Enter a valid 48-bit MAC address.")
    canonical = ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
    if submitted != canonical:
        raise NetworkEndpointError(f"MAC address must use canonical form; use {canonical}.")
    return canonical


def interfaces_for_scope(scope: DataScope) -> QuerySet[NetworkInterface]:
    return NetworkInterface.scoped.for_scope(scope).select_related("entity", "device__entity")


def ip_addresses_for_scope(scope: DataScope) -> QuerySet[NetworkIPAddress]:
    return NetworkIPAddress.scoped.for_scope(scope).select_related(
        "entity", "subnet__entity", "subnet__vrf__entity", "interface__entity", "interface__device__entity"
    )


def mac_addresses_for_scope(scope: DataScope) -> QuerySet[NetworkMACAddress]:
    return NetworkMACAddress.scoped.for_scope(scope).select_related(
        "entity", "interface__entity", "interface__device__entity"
    )


def _device(scope: DataScope, entity_id: UUID) -> NetworkDevice:
    try:
        return NetworkDevice.scoped.for_scope(scope).select_related("entity").get(entity_id=entity_id)
    except NetworkDevice.DoesNotExist as exc:
        raise NetworkEndpointError("The selected device is unavailable in this Workspace.") from exc


def _interface(scope: DataScope, entity_id: UUID | None) -> NetworkInterface | None:
    if entity_id is None:
        return None
    try:
        return interfaces_for_scope(scope).get(entity_id=entity_id)
    except NetworkInterface.DoesNotExist as exc:
        raise NetworkEndpointError("The selected interface is unavailable in this Workspace.") from exc


def _subnet(scope: DataScope, entity_id: UUID) -> NetworkSubnet:
    try:
        return NetworkSubnet.scoped.for_scope(scope).select_related("entity", "vrf").get(entity_id=entity_id)
    except NetworkSubnet.DoesNotExist as exc:
        raise NetworkEndpointError("The selected subnet is unavailable in this Workspace.") from exc


def _create_entity(*, tenant: Tenant, organization: Organization | None, entity_type: str, name: str) -> Entity:
    clean_name = name.strip()
    if not clean_name:
        raise NetworkEndpointError("Name cannot be blank.")
    return Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type=entity_type,
        display_name=clean_name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )


def _lock_interface_name(device: NetworkDevice) -> None:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"interface:{device.id}"])


def _assert_interface_name_available(
    *, device: NetworkDevice, name: str, exclude_interface_id: UUID | None = None
) -> None:
    query = NetworkInterface.objects.filter(device=device, entity__display_name__iexact=name.strip())
    if exclude_interface_id is not None:
        query = query.exclude(pk=exclude_interface_id)
    if query.exists():
        raise NetworkEndpointError("That device already has an interface with this name.")


def _lock_ip_namespace(scope: DataScope, subnet: NetworkSubnet) -> None:
    if connection.vendor == "postgresql":
        key = f"{scope.tenant_id}:{scope.organization_id or 'msp'}:{subnet.vrf_id or 'default'}"
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


def _validate_host_in_subnet(address: ipaddress.IPv4Address | ipaddress.IPv6Address, subnet: NetworkSubnet) -> None:
    network = ipaddress.ip_network(subnet.cidr, strict=True)
    if address.version != network.version or address not in network:
        raise NetworkEndpointError(f"{address.compressed} is outside {network.with_prefixlen}.")
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 31:
        if address == network.network_address:
            raise NetworkEndpointError("The IPv4 network identifier cannot be assigned.")
        if address == network.broadcast_address:
            raise NetworkEndpointError("The IPv4 broadcast address cannot be assigned.")


def _assert_ip_available(
    scope: DataScope,
    *,
    subnet: NetworkSubnet,
    address: str,
    exclude_ip_id: UUID | None = None,
) -> None:
    query = ip_addresses_for_scope(scope).filter(address=address, subnet__vrf_id=subnet.vrf_id)
    if exclude_ip_id is not None:
        query = query.exclude(pk=exclude_ip_id)
    if query.exists():
        namespace = subnet.vrf.entity.display_name if subnet.vrf is not None else "the default routing table"
        raise NetworkEndpointError(f"{address} is already recorded in {namespace}.")


@transaction.atomic
def create_interface(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    device_entity_id: UUID,
    kind: str,
    status: str,
    description: str,
) -> NetworkInterface:
    scope = DataScope.owner(tenant, organization)
    device = _device(scope, device_entity_id)
    _lock_interface_name(device)
    _assert_interface_name_available(device=device, name=name)
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="network_interface", name=name)
    record = NetworkInterface(
        tenant=tenant,
        organization=organization,
        entity=entity,
        device=device,
        kind=kind,
        status=status,
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_interface.created", entity_id=entity.id, metadata={}
    )
    return interfaces_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_interface(*, record: NetworkInterface, actor_id: UUID, values: dict[str, object]) -> NetworkInterface:
    locked = NetworkInterface.objects.select_for_update().select_related("entity", "device__entity").get(pk=record.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    device = _device(scope, cast(UUID, values.get("device_entity_id", locked.device.entity_id)))
    name = str(values.get("name", locked.entity.display_name)).strip()
    _lock_interface_name(device)
    _assert_interface_name_available(device=device, name=name, exclude_interface_id=locked.pk)
    locked.entity.display_name = name
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.device = device
    locked.kind = str(values.get("kind", locked.kind))
    locked.status = str(values.get("status", locked.status))
    locked.description = str(values.get("description", locked.description)).strip()
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_interface.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return interfaces_for_scope(scope).get(pk=locked.pk)


@transaction.atomic
def create_ip_address(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    address: str,
    subnet_entity_id: UUID,
    interface_entity_id: UUID | None,
    status: str,
    dns_name: str,
    description: str,
) -> NetworkIPAddress:
    scope = DataScope.owner(tenant, organization)
    host = canonical_host(address)
    subnet = _subnet(scope, subnet_entity_id)
    interface = _interface(scope, interface_entity_id)
    _validate_host_in_subnet(host, subnet)
    _lock_ip_namespace(scope, subnet)
    _assert_ip_available(scope, subnet=subnet, address=host.compressed)
    entity = _create_entity(
        tenant=tenant, organization=organization, entity_type="network_ip_address", name=host.compressed
    )
    record = NetworkIPAddress(
        tenant=tenant,
        organization=organization,
        entity=entity,
        subnet=subnet,
        interface=interface,
        address=host.compressed,
        address_family=host.version,
        status=status,
        dns_name=dns_name.strip().lower(),
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_ip_address.created", entity_id=entity.id, metadata={}
    )
    return ip_addresses_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_ip_address(*, record: NetworkIPAddress, actor_id: UUID, values: dict[str, object]) -> NetworkIPAddress:
    locked = NetworkIPAddress.objects.select_for_update().select_related("entity", "subnet__vrf").get(pk=record.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    host = canonical_host(str(values.get("address", locked.address)))
    subnet = _subnet(scope, cast(UUID, values.get("subnet_entity_id", locked.subnet.entity_id)))
    current_interface_id = cast(NetworkInterface, locked.interface).entity_id if locked.interface_id else None
    interface = _interface(scope, cast(UUID | None, values.get("interface_entity_id", current_interface_id)))
    _validate_host_in_subnet(host, subnet)
    _lock_ip_namespace(scope, subnet)
    _assert_ip_available(scope, subnet=subnet, address=host.compressed, exclude_ip_id=locked.pk)
    locked.entity.display_name = host.compressed
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.subnet = subnet
    locked.interface = interface
    locked.address = host.compressed
    locked.address_family = host.version
    locked.status = str(values.get("status", locked.status))
    locked.dns_name = str(values.get("dns_name", locked.dns_name)).strip().lower()
    locked.description = str(values.get("description", locked.description)).strip()
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_ip_address.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return ip_addresses_for_scope(scope).get(pk=locked.pk)


@transaction.atomic
def create_mac_address(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    address: str,
    interface_entity_id: UUID | None,
    description: str,
) -> NetworkMACAddress:
    scope = DataScope.owner(tenant, organization)
    clean_address = canonical_mac(address)
    interface = _interface(scope, interface_entity_id)
    entity = _create_entity(
        tenant=tenant, organization=organization, entity_type="network_mac_address", name=clean_address
    )
    record = NetworkMACAddress(
        tenant=tenant,
        organization=organization,
        entity=entity,
        interface=interface,
        address=clean_address,
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_mac_address.created", entity_id=entity.id, metadata={}
    )
    return mac_addresses_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_mac_address(*, record: NetworkMACAddress, actor_id: UUID, values: dict[str, object]) -> NetworkMACAddress:
    locked = (
        NetworkMACAddress.objects.select_for_update().select_related("entity", "interface__entity").get(pk=record.pk)
    )
    scope = DataScope.owner(locked.tenant, locked.organization)
    clean_address = canonical_mac(str(values.get("address", locked.address)))
    current_interface_id = cast(NetworkInterface, locked.interface).entity_id if locked.interface_id else None
    interface = _interface(scope, cast(UUID | None, values.get("interface_entity_id", current_interface_id)))
    locked.entity.display_name = clean_address
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.interface = interface
    locked.address = clean_address
    locked.description = str(values.get("description", locked.description)).strip()
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_mac_address.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return mac_addresses_for_scope(scope).get(pk=locked.pk)
