from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from contextlib import nullcontext
from dataclasses import dataclass

from django.db import connection
from django.db.models import Q, QuerySet
from django.db.models.functions import Lower

from .models import (
    DNSRecord,
    DNSZone,
    Entity,
    NetBoxReference,
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkDevice,
    NetworkInterface,
    NetworkIPAddress,
    NetworkMACAddress,
    NetworkRack,
    NetworkSubnet,
    NetworkVLAN,
    NetworkVRF,
    WirelessNetwork,
)
from .rls import OrganizationRLSMode, rls_scope
from .scoping import DataScope

NETWORK_EXPORT_SCHEMA = "tekdocs.networks.v1"
NETWORK_ENTITY_SECTIONS = {
    "network_device": "devices",
    "network_rack": "racks",
    "network_interface": "devices",
    "network_ip_address": "ip-addresses",
    "network_mac_address": "mac-addresses",
    "network_subnet": "subnets",
    "network_vlan": "vlans",
    "network_vrf": "subnets",
    "network_circuit": "circuits",
    "network_circuit_handoff": "circuits",
    "wireless_network": "wireless",
    "dns_zone": "dns",
    "dns_record": "dns",
}
NETWORK_ENTITY_LABELS = {
    "network_device": "Device",
    "network_rack": "Rack",
    "network_interface": "Legacy interface",
    "network_ip_address": "IP address",
    "network_mac_address": "MAC address",
    "network_subnet": "Subnet",
    "network_vlan": "VLAN",
    "network_vrf": "Legacy VRF",
    "network_circuit": "Circuit",
    "network_circuit_handoff": "Circuit handoff",
    "wireless_network": "Wireless network",
    "dns_zone": "DNS zone",
    "dns_record": "DNS record",
}
EXPORT_FIELDS = (
    "schema_version",
    "record_type",
    "entity_id",
    "name",
    "primary_value",
    "status",
    "related_name",
    "description",
)


def network_entities_for_scope(scope: DataScope, search: str = "") -> QuerySet[Entity]:
    records = Entity.scoped.for_scope(scope).filter(
        workspace_id=scope.workspace_id,
        archived_at__isnull=True,
        entity_type__in=NETWORK_ENTITY_SECTIONS,
    )
    term = search.strip()
    if term:
        filters = (
            Q(display_name__icontains=term)
            | Q(network_rack__site__entity__display_name__icontains=term)
            | Q(network_rack__location__entity__display_name__icontains=term)
            | Q(network_device__role__icontains=term)
            | Q(network_device__status__icontains=term)
            | Q(network_device__site__entity__display_name__icontains=term)
            | Q(network_device__rack__entity__display_name__icontains=term)
            | Q(network_vrf__route_distinguisher__icontains=term)
            | Q(network_vrf__description__icontains=term)
            | Q(network_vlan__description__icontains=term)
            | Q(network_subnet__cidr__icontains=term)
            | Q(network_subnet__description__icontains=term)
            | Q(network_interface__description__icontains=term)
            | Q(network_interface__device__entity__display_name__icontains=term)
            | Q(network_ip_address__address__icontains=term)
            | Q(network_ip_address__dns_name__icontains=term)
            | Q(network_ip_address__description__icontains=term)
            | Q(network_mac_address__address__icontains=term)
            | Q(network_mac_address__description__icontains=term)
            | Q(wireless_network__ssid__icontains=term)
            | Q(wireless_network__purpose__icontains=term)
            | Q(wireless_network__security__icontains=term)
            | Q(wireless_network__description__icontains=term)
            | Q(dns_zone__name__icontains=term)
            | Q(dns_zone__description__icontains=term)
            | Q(dns_record__owner_name__icontains=term)
            | Q(dns_record__record_type__icontains=term)
            | Q(dns_record__value__icontains=term)
            | Q(dns_record__description__icontains=term)
            | Q(network_circuit__service_identifier__icontains=term)
            | Q(network_circuit__kind__icontains=term)
            | Q(network_circuit__status__icontains=term)
            | Q(network_circuit__provider__entity__display_name__icontains=term)
            | Q(network_circuit__description__icontains=term)
            | Q(network_circuit_handoff__connector__icontains=term)
            | Q(network_circuit_handoff__provider_reference__icontains=term)
            | Q(network_circuit_handoff__description__icontains=term)
            | Q(netbox_references__object_type__icontains=term, netbox_references__archived_at__isnull=True)
        )
        if term.isdecimal():
            filters |= Q(netbox_references__object_id=int(term), netbox_references__archived_at__isnull=True)
        records = records.filter(filters)
    return records.order_by(Lower("display_name"), "entity_type", "id").distinct()


@dataclass(frozen=True, slots=True)
class NetworkExportRow:
    record_type: str
    entity_id: object
    name: str
    primary_value: object = ""
    status: object = ""
    related_name: object = ""
    description: object = ""


def _for_scope(model, scope: DataScope):  # type: ignore[no-untyped-def]
    return model.scoped.for_scope(scope).filter(
        entity__workspace_id=scope.workspace_id, entity__archived_at__isnull=True
    )


def _rows(scope: DataScope) -> Iterable[NetworkExportRow]:
    for record in (
        _for_scope(NetworkDevice, scope)
        .select_related("entity", "site__entity", "rack__entity")
        .order_by("entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = (
            record.rack.entity.display_name
            if record.rack_id
            else (record.site.entity.display_name if record.site_id else "")
        )
        yield NetworkExportRow(
            "network_device", record.entity_id, record.entity.display_name, record.role, record.status, related
        )
    for record in (
        _for_scope(NetworkRack, scope)
        .select_related("entity", "site__entity", "location__entity")
        .order_by("entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = record.location.entity.display_name if record.location_id else record.site.entity.display_name
        yield NetworkExportRow(
            "network_rack",
            record.entity_id,
            record.entity.display_name,
            f"{record.unit_count}U",
            record.status,
            related,
        )
    for record in (
        _for_scope(NetworkInterface, scope)
        .select_related("entity", "device__entity")
        .order_by("entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "network_interface",
            record.entity_id,
            record.entity.display_name,
            record.kind,
            record.status,
            record.device.entity.display_name,
            record.description,
        )
    for record in (
        _for_scope(NetworkIPAddress, scope)
        .select_related("entity", "subnet", "interface__entity")
        .order_by("address_family", "address", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = record.interface.entity.display_name if record.interface_id else record.subnet.cidr
        yield NetworkExportRow(
            "network_ip_address",
            record.entity_id,
            record.entity.display_name,
            record.address,
            record.status,
            related,
            record.description,
        )
    for record in (
        _for_scope(NetworkMACAddress, scope)
        .select_related("entity", "interface__entity")
        .order_by("address", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = record.interface.entity.display_name if record.interface_id else ""
        yield NetworkExportRow(
            "network_mac_address",
            record.entity_id,
            record.entity.display_name,
            record.address,
            related_name=related,
            description=record.description,
        )
    for record in (
        _for_scope(NetworkSubnet, scope)
        .select_related("entity", "vrf__entity", "vlan__entity")
        .order_by("address_family", "cidr", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = (
            record.vrf.entity.display_name
            if record.vrf_id
            else (record.vlan.entity.display_name if record.vlan_id else "")
        )
        yield NetworkExportRow(
            "network_subnet",
            record.entity_id,
            record.entity.display_name,
            record.cidr,
            related_name=related,
            description=record.description,
        )
    for record in (
        _for_scope(NetworkVLAN, scope)
        .select_related("entity")
        .order_by("vlan_id", "entity_id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "network_vlan", record.entity_id, record.entity.display_name, record.vlan_id, description=record.description
        )
    for record in (
        _for_scope(NetworkVRF, scope)
        .select_related("entity")
        .order_by("entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "network_vrf",
            record.entity_id,
            record.entity.display_name,
            record.route_distinguisher,
            description=record.description,
        )
    for record in (
        _for_scope(NetworkCircuit, scope)
        .select_related("entity", "provider__entity")
        .order_by("entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "network_circuit",
            record.entity_id,
            record.entity.display_name,
            record.service_identifier,
            record.status,
            record.provider.entity.display_name,
            record.description,
        )
    for record in (
        _for_scope(NetworkCircuitHandoff, scope)
        .select_related("entity", "circuit__entity")
        .order_by("circuit__entity__display_name", "side", "entity__display_name", "entity_id")
        .iterator(chunk_size=500)
    ):
        primary = " / ".join(value for value in (record.side.upper(), record.media, record.connector) if value)
        yield NetworkExportRow(
            "network_circuit_handoff",
            record.entity_id,
            record.entity.display_name,
            primary,
            related_name=record.circuit.entity.display_name,
            description=record.description,
        )
    for record in (
        _for_scope(WirelessNetwork, scope)
        .select_related("entity", "site__entity")
        .order_by("ssid", "entity_id")
        .iterator(chunk_size=500)
    ):
        related = record.site.entity.display_name if record.site_id else ""
        yield NetworkExportRow(
            "wireless_network",
            record.entity_id,
            record.entity.display_name,
            record.ssid,
            record.status,
            related,
            record.description,
        )
    for record in (
        _for_scope(DNSZone, scope).select_related("entity").order_by("name", "entity_id").iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "dns_zone", record.entity_id, record.entity.display_name, record.name, description=record.description
        )
    for record in (
        _for_scope(DNSRecord, scope)
        .select_related("entity", "zone")
        .order_by("zone__name", "owner_name", "record_type", "value", "entity_id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "dns_record",
            record.entity_id,
            record.entity.display_name,
            f"{record.record_type} {record.value}",
            related_name=record.zone.name,
            description=record.description,
        )
    for record in (
        NetBoxReference.scoped.for_scope(scope)
        .filter(workspace_id=scope.workspace_id, archived_at__isnull=True)
        .select_related("entity")
        .order_by("object_type", "object_id", "id")
        .iterator(chunk_size=500)
    ):
        yield NetworkExportRow(
            "netbox_reference",
            record.entity_id,
            record.entity.display_name,
            f"{record.object_type}:{record.object_id}",
            "observed" if record.last_observed_at else "unobserved",
        )


def _spreadsheet_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


class _CsvEcho:
    def write(self, value: str) -> str:
        return value


def stream_network_csv(scope: DataScope) -> Iterator[str]:
    writer = csv.DictWriter(_CsvEcho(), fieldnames=EXPORT_FIELDS, lineterminator="\r\n")
    organization_mode = (
        OrganizationRLSMode.ORGANIZATION
        if scope.organization_id is not None
        else OrganizationRLSMode.MSP_ONLY
    )
    stream_scope = (
        rls_scope(scope, organization_mode=organization_mode)
        if connection.vendor == "postgresql"
        else nullcontext()
    )

    # StreamingHttpResponse consumes this iterator after request middleware has
    # closed its transaction. Bind an iterator-owned RLS transaction so runtime
    # database roles remain exact-Workspace and fail closed for the whole export.
    with stream_scope:
        yield writer.writeheader()
        for row in _rows(scope):
            values = {
                "schema_version": NETWORK_EXPORT_SCHEMA,
                "record_type": row.record_type,
                "entity_id": row.entity_id,
                "name": row.name,
                "primary_value": row.primary_value,
                "status": row.status,
                "related_name": row.related_name,
                "description": row.description,
            }
            yield writer.writerow({field: _spreadsheet_safe(values[field]) for field in EXPORT_FIELDS})
