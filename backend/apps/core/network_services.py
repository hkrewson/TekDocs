from __future__ import annotations

import ipaddress
import re
from typing import cast
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Count, QuerySet

from .models import (
    AuditEvent,
    DNSRecord,
    DNSZone,
    Entity,
    EntityVisibility,
    NetworkIPAddress,
    NetworkSubnet,
    NetworkVLAN,
    Organization,
    Site,
    Tenant,
    WirelessNetwork,
    workspace_for_owner,
)
from .scoping import DataScope


class NetworkServiceError(ValueError):
    pass


def canonical_dns_name(value: str) -> str:
    submitted = value.strip()
    candidate = submitted[:-1] if submitted.endswith(".") else submitted
    if not candidate or len(candidate) > 253:
        raise NetworkServiceError("Enter a DNS name between 1 and 253 characters.")
    try:
        labels = [label.encode("idna").decode("ascii") for label in candidate.split(".")]
    except UnicodeError as exc:
        raise NetworkServiceError("Enter a valid DNS name.") from exc
    if any(
        not label or len(label) > 63 or not re.fullmatch(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]*[A-Za-z0-9_])?", label)
        for label in labels
    ):
        raise NetworkServiceError("Enter a valid DNS name.")
    canonical = ".".join(labels).lower()
    if submitted != canonical:
        raise NetworkServiceError(f"DNS names must use canonical form; use {canonical}.")
    return canonical


def wireless_networks_for_scope(scope: DataScope) -> QuerySet[WirelessNetwork]:
    return WirelessNetwork.scoped.for_scope(scope).select_related(
        "entity", "site__entity", "vlan__entity", "subnet__entity"
    )


def dns_zones_for_scope(scope: DataScope) -> QuerySet[DNSZone]:
    return DNSZone.scoped.for_scope(scope).select_related("entity").annotate(record_count=Count("records"))


def dns_records_for_scope(scope: DataScope) -> QuerySet[DNSRecord]:
    return DNSRecord.scoped.for_scope(scope).select_related("entity", "zone__entity", "ip_address__entity")


def _create_entity(*, tenant: Tenant, organization: Organization | None, entity_type: str, name: str) -> Entity:
    return Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type=entity_type,
        display_name=name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )


def _related(scope: DataScope, model, entity_id: UUID | None, label: str):  # type: ignore[no-untyped-def]
    if entity_id is None:
        return None
    try:
        return model.scoped.for_scope(scope).get(entity_id=entity_id)
    except model.DoesNotExist as exc:
        raise NetworkServiceError(f"The selected {label} is unavailable in this Workspace.") from exc


def _lock(scope: DataScope, family: str) -> None:
    if connection.vendor == "postgresql":
        key = f"{family}:{scope.tenant_id}:{scope.organization_id or 'msp'}"
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


@transaction.atomic
def create_wireless_network(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    ssid: str,
    purpose: str,
    security: str,
    status: str,
    hidden: bool,
    client_isolation: bool,
    site_entity_id: UUID | None,
    vlan_entity_id: UUID | None,
    subnet_entity_id: UUID | None,
    description: str,
) -> WirelessNetwork:
    scope = DataScope.owner(tenant, organization)
    site = _related(scope, Site, site_entity_id, "site")
    vlan = _related(scope, NetworkVLAN, vlan_entity_id, "VLAN")
    subnet = _related(scope, NetworkSubnet, subnet_entity_id, "subnet")
    _lock(scope, "wireless")
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="wireless_network", name=ssid)
    record = WirelessNetwork(
        tenant=tenant,
        organization=organization,
        entity=entity,
        ssid=ssid,
        purpose=purpose,
        security=security,
        status=status,
        hidden=hidden,
        client_isolation=client_isolation,
        site=site,
        vlan=vlan,
        subnet=subnet,
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="wireless_network.created", entity_id=entity.id, metadata={}
    )
    return wireless_networks_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_wireless_network(*, record: WirelessNetwork, actor_id: UUID, values: dict[str, object]) -> WirelessNetwork:
    locked = (
        WirelessNetwork.objects.select_for_update().select_related("entity", "site", "vlan", "subnet").get(pk=record.pk)
    )
    scope = DataScope.owner(locked.tenant, locked.organization)
    site_id = cast(Site, locked.site).entity_id if locked.site_id else None
    vlan_id = cast(NetworkVLAN, locked.vlan).entity_id if locked.vlan_id else None
    subnet_id = cast(NetworkSubnet, locked.subnet).entity_id if locked.subnet_id else None
    locked.site = _related(scope, Site, cast(UUID | None, values.get("site_entity_id", site_id)), "site")
    locked.vlan = _related(scope, NetworkVLAN, cast(UUID | None, values.get("vlan_entity_id", vlan_id)), "VLAN")
    locked.subnet = _related(
        scope, NetworkSubnet, cast(UUID | None, values.get("subnet_entity_id", subnet_id)), "subnet"
    )
    _lock(scope, "wireless")
    for field in ("ssid", "purpose", "security", "status", "hidden", "client_isolation", "description"):
        if field in values:
            setattr(locked, field, values[field])
    locked.description = locked.description.strip()
    locked.entity.display_name = locked.ssid
    locked.full_clean()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="wireless_network.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return wireless_networks_for_scope(scope).get(pk=locked.pk)


@transaction.atomic
def create_dns_zone(
    *, tenant: Tenant, organization: Organization | None, actor_id: UUID, name: str, description: str
) -> DNSZone:
    scope = DataScope.owner(tenant, organization)
    clean_name = canonical_dns_name(name)
    _lock(scope, "dns")
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="dns_zone", name=clean_name)
    zone = DNSZone(
        tenant=tenant, organization=organization, entity=entity, name=clean_name, description=description.strip()
    )
    zone.full_clean()
    zone.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="dns_zone.created", entity_id=entity.id, metadata={}
    )
    return dns_zones_for_scope(scope).get(pk=zone.pk)


@transaction.atomic
def update_dns_zone(*, zone: DNSZone, actor_id: UUID, values: dict[str, object]) -> DNSZone:
    locked = DNSZone.objects.select_for_update().select_related("entity").get(pk=zone.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    clean_name = canonical_dns_name(str(values.get("name", locked.name)))
    _lock(scope, "dns")
    if locked.records.exists() and clean_name != locked.name:
        raise NetworkServiceError("Remove this zone's DNS records before renaming it.")
    locked.name = clean_name
    locked.description = str(values.get("description", locked.description)).strip()
    locked.entity.display_name = clean_name
    locked.full_clean()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="dns_zone.updated", entity_id=locked.entity_id, metadata={}
    )
    return dns_zones_for_scope(scope).get(pk=locked.pk)


def _validate_dns_record(
    *,
    scope: DataScope,
    zone: DNSZone,
    owner_name: str,
    record_type: str,
    value: str,
    priority: int | None,
    weight: int | None,
    port: int | None,
    ip_address_entity_id: UUID | None,
    exclude_id: UUID | None = None,
) -> tuple[str, str, NetworkIPAddress | None]:
    owner = canonical_dns_name(owner_name)
    if owner != zone.name and not owner.endswith(f".{zone.name}"):
        raise NetworkServiceError("DNS record owner must belong to the selected zone.")
    raw = value.strip()
    ip_record = _related(scope, NetworkIPAddress, ip_address_entity_id, "IP address")
    if record_type in ("A", "AAAA"):
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise NetworkServiceError(f"{record_type} records require a valid IP address.") from exc
        expected = 4 if record_type == "A" else 6
        if address.version != expected or raw != address.compressed:
            raise NetworkServiceError(f"{record_type} records require a canonical IPv{expected} address.")
        if ip_record is not None and ip_record.address != raw:
            raise NetworkServiceError("The linked IP inventory record must match the DNS value.")
        if any(item is not None for item in (priority, weight, port)):
            raise NetworkServiceError(f"{record_type} records do not use priority, weight, or port.")
    elif record_type in ("CNAME", "NS", "PTR"):
        raw = canonical_dns_name(raw)
        if ip_record is not None or any(item is not None for item in (priority, weight, port)):
            raise NetworkServiceError(f"{record_type} records accept only a DNS target.")
    elif record_type == "MX":
        raw = canonical_dns_name(raw)
        if priority is None or weight is not None or port is not None or ip_record is not None:
            raise NetworkServiceError("MX records require priority and a DNS target.")
    elif record_type == "SRV":
        raw = canonical_dns_name(raw)
        if any(item is None for item in (priority, weight, port)) or ip_record is not None:
            raise NetworkServiceError("SRV records require priority, weight, port, and a DNS target.")
    elif record_type == "CAA":
        if not re.fullmatch(r'(?:0|[1-9][0-9]{0,2}) (?:issue|issuewild|iodef) "[^\r\n]{1,512}"', raw):
            raise NetworkServiceError('CAA value must use: flags tag "value".')
        if ip_record is not None or any(item is not None for item in (priority, weight, port)):
            raise NetworkServiceError("CAA records do not use IP links, priority, weight, or port.")
    elif record_type == "TXT":
        if not raw or len(raw.encode("utf-8")) > 2048 or any(ord(char) < 32 and char not in "\t" for char in raw):
            raise NetworkServiceError("TXT value must contain 1 to 2048 safe UTF-8 bytes.")
        if ip_record is not None or any(item is not None for item in (priority, weight, port)):
            raise NetworkServiceError("TXT records do not use IP links, priority, weight, or port.")
    else:
        raise NetworkServiceError("That DNS record type is unsupported.")
    conflicts = DNSRecord.objects.filter(zone=zone, owner_name=owner)
    if exclude_id is not None:
        conflicts = conflicts.exclude(pk=exclude_id)
    if (
        record_type == "CNAME"
        and conflicts.exists()
        or record_type != "CNAME"
        and conflicts.filter(record_type="CNAME").exists()
    ):
        raise NetworkServiceError("A CNAME cannot coexist with another record at the same owner name.")
    return owner, raw, ip_record


@transaction.atomic
def create_dns_record(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    zone_entity_id: UUID,
    owner_name: str,
    record_type: str,
    value: str,
    ttl: int,
    priority: int | None,
    weight: int | None,
    port: int | None,
    ip_address_entity_id: UUID | None,
    description: str,
) -> DNSRecord:
    scope = DataScope.owner(tenant, organization)
    zone = _related(scope, DNSZone, zone_entity_id, "DNS zone")
    _lock(scope, "dns")
    owner, clean_value, ip_record = _validate_dns_record(
        scope=scope,
        zone=zone,
        owner_name=owner_name,
        record_type=record_type,
        value=value,
        priority=priority,
        weight=weight,
        port=port,
        ip_address_entity_id=ip_address_entity_id,
    )
    entity = _create_entity(
        tenant=tenant, organization=organization, entity_type="dns_record", name=f"{owner} {record_type}"
    )
    record = DNSRecord(
        tenant=tenant,
        organization=organization,
        entity=entity,
        zone=zone,
        owner_name=owner,
        record_type=record_type,
        value=clean_value,
        ttl=ttl,
        priority=priority,
        weight=weight,
        port=port,
        ip_address=ip_record,
        description=description.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="dns_record.created", entity_id=entity.id, metadata={}
    )
    return dns_records_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_dns_record(*, record: DNSRecord, actor_id: UUID, values: dict[str, object]) -> DNSRecord:
    locked = (
        DNSRecord.objects.select_for_update()
        .select_related("entity", "zone__entity", "ip_address__entity")
        .get(pk=record.pk)
    )
    scope = DataScope.owner(locked.tenant, locked.organization)
    zone_id = cast(UUID, values.get("zone_entity_id", locked.zone.entity_id))
    zone = _related(scope, DNSZone, zone_id, "DNS zone")
    linked_ip_id = cast(NetworkIPAddress, locked.ip_address).entity_id if locked.ip_address_id else None
    _lock(scope, "dns")
    owner, clean_value, ip_record = _validate_dns_record(
        scope=scope,
        zone=zone,
        owner_name=str(values.get("owner_name", locked.owner_name)),
        record_type=str(values.get("record_type", locked.record_type)),
        value=str(values.get("value", locked.value)),
        priority=cast(int | None, values.get("priority", locked.priority)),
        weight=cast(int | None, values.get("weight", locked.weight)),
        port=cast(int | None, values.get("port", locked.port)),
        ip_address_entity_id=cast(UUID | None, values.get("ip_address_entity_id", linked_ip_id)),
        exclude_id=locked.pk,
    )
    locked.zone = zone
    locked.owner_name = owner
    locked.record_type = str(values.get("record_type", locked.record_type))
    locked.value = clean_value
    locked.ttl = cast(int, values.get("ttl", locked.ttl))
    locked.priority = cast(int | None, values.get("priority", locked.priority))
    locked.weight = cast(int | None, values.get("weight", locked.weight))
    locked.port = cast(int | None, values.get("port", locked.port))
    locked.ip_address = ip_record
    locked.description = str(values.get("description", locked.description)).strip()
    locked.entity.display_name = f"{owner} {locked.record_type}"
    locked.full_clean()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="dns_record.updated", entity_id=locked.entity_id, metadata={}
    )
    return dns_records_for_scope(scope).get(pk=locked.pk)
