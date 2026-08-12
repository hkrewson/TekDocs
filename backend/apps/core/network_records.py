from __future__ import annotations

import ipaddress
from typing import cast
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet

from .models import AuditEvent, Location, NetworkSubnet, Organization, Tenant
from .network_addressing import (
    NetworkAddressingError,
    _assert_no_overlap,
    _create_entity,
    _lock_routing_namespace,
    canonical_network,
)
from .scoping import DataScope
from .sites import locations_for_scope


def network_records_for_scope(scope: DataScope) -> QuerySet[NetworkSubnet]:
    return NetworkSubnet.scoped.for_scope(scope).select_related(
        "entity", "location__entity", "location__site__entity", "vlan__entity"
    )


def _location(scope: DataScope, entity_id: UUID | None) -> Location | None:
    if entity_id is None:
        return None
    try:
        return locations_for_scope(scope).select_related("site__entity").get(entity_id=entity_id)
    except Location.DoesNotExist as exc:
        raise NetworkAddressingError("The selected location is unavailable in this Workspace.") from exc


def _address(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return ipaddress.ip_address(str(value).strip()).compressed
    except ValueError as exc:
        raise NetworkAddressingError("Enter a valid IPv4 or IPv6 address.") from exc


def _range(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    *,
    use_full_range: bool,
    start: object | None,
    end: object | None,
) -> tuple[str | None, str | None]:
    if use_full_range:
        return None, None
    clean_start = _address(start)
    clean_end = _address(end)
    if clean_start is None or clean_end is None:
        raise NetworkAddressingError("Enter both the start and end of the assignable range.")
    first = ipaddress.ip_address(clean_start)
    last = ipaddress.ip_address(clean_end)
    if (
        first.version != network.version
        or last.version != network.version
        or first not in network
        or last not in network
    ):
        raise NetworkAddressingError("The assignable range must be inside the network CIDR.")
    if int(first) > int(last):
        raise NetworkAddressingError("The assignable range start must not be after its end.")
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 31:
        if first == network.network_address or last == network.broadcast_address:
            raise NetworkAddressingError("The assignable range cannot include the network or broadcast address.")
    return first.compressed, last.compressed


def network_projection(record: NetworkSubnet) -> dict[str, object]:
    network = ipaddress.ip_network(record.cidr, strict=True)
    usable_start: ipaddress.IPv4Address | ipaddress.IPv6Address
    usable_end: ipaddress.IPv4Address | ipaddress.IPv6Address
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 31:
        usable_start = network.network_address + 1
        usable_end = network.broadcast_address - 1
    else:
        usable_start = network.network_address
        usable_end = network.broadcast_address
    if record.use_full_range:
        range_start, range_end = usable_start, usable_end
    else:
        range_start = ipaddress.ip_address(cast(str, record.assignable_start))
        range_end = ipaddress.ip_address(cast(str, record.assignable_end))
    location = record.location if record.location_id else None
    legacy_vlan = record.vlan if record.vlan_id else None
    return {
        "id": record.entity_id,
        "name": record.entity.display_name,
        "location_id": location.entity_id if location else None,
        "location_name": location.entity.display_name if location else None,
        "site_name": location.site.entity.display_name if location else None,
        "description": record.description,
        "vlan": (
            record.vlan_number if record.vlan_number is not None else (legacy_vlan.vlan_id if legacy_vlan else None)
        ),
        "cidr": record.cidr,
        "gateway": usable_start.compressed,
        "use_full_range": record.use_full_range,
        "range_start": range_start.compressed,
        "range_end": range_end.compressed,
        "primary_dns": record.primary_dns,
        "secondary_dns": record.secondary_dns,
        "notes": record.notes,
    }


@transaction.atomic
def create_network_record(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    location_entity_id: UUID | None,
    description: str,
    vlan_number: int | None,
    cidr: str,
    use_full_range: bool,
    range_start: object | None,
    range_end: object | None,
    primary_dns: object | None,
    secondary_dns: object | None,
    notes: str,
) -> NetworkSubnet:
    scope = DataScope.owner(tenant, organization)
    network = canonical_network(cidr)
    location = _location(scope, location_entity_id)
    start, end = _range(network, use_full_range=use_full_range, start=range_start, end=range_end)
    _lock_routing_namespace(scope, None)
    _assert_no_overlap(scope, cidr=network.with_prefixlen, vrf=None)
    entity = _create_entity(tenant=tenant, organization=organization, entity_type="network_subnet", name=name)
    record = NetworkSubnet(
        tenant=tenant,
        organization=organization,
        entity=entity,
        location=location,
        description=description.strip(),
        vlan_number=vlan_number,
        cidr=network.with_prefixlen,
        address_family=network.version,
        use_full_range=use_full_range,
        assignable_start=start,
        assignable_end=end,
        primary_dns=_address(primary_dns),
        secondary_dns=_address(secondary_dns),
        notes=notes.strip(),
    )
    record.full_clean()
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network.created", entity_id=entity.id, metadata={}
    )
    return network_records_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_network_record(*, record: NetworkSubnet, actor_id: UUID, values: dict[str, object]) -> NetworkSubnet:
    locked = (
        NetworkSubnet.objects.select_for_update().select_related("entity", "location", "vlan", "vrf").get(pk=record.pk)
    )
    scope = DataScope.owner(locked.tenant, locked.organization)
    network = canonical_network(str(values.get("cidr", locked.cidr)))
    use_full_range = bool(values.get("use_full_range", locked.use_full_range))
    start, end = _range(
        network,
        use_full_range=use_full_range,
        start=values.get("range_start", locked.assignable_start),
        end=values.get("range_end", locked.assignable_end),
    )
    current_location = locked.location if locked.location_id else None
    location_id = values.get("location_entity_id", current_location.entity_id if current_location else None)
    location = _location(scope, cast(UUID | None, location_id))
    # The simple product surface no longer creates or exposes VRFs. Preserve the
    # routing namespace of legacy records so editing one cannot silently move it
    # into the default namespace or apply the wrong overlap rules.
    _lock_routing_namespace(scope, locked.vrf)
    _assert_no_overlap(
        scope,
        cidr=network.with_prefixlen,
        vrf=locked.vrf,
        exclude_subnet_id=locked.pk,
    )
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.location = location
    locked.description = str(values.get("description", locked.description)).strip()
    locked.vlan_number = cast(int | None, values.get("vlan_number", locked.vlan_number))
    locked.cidr = network.with_prefixlen
    locked.address_family = network.version
    locked.use_full_range = use_full_range
    locked.assignable_start = start
    locked.assignable_end = end
    locked.primary_dns = _address(values.get("primary_dns", locked.primary_dns))
    locked.secondary_dns = _address(values.get("secondary_dns", locked.secondary_dns))
    locked.notes = str(values.get("notes", locked.notes)).strip()
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="network.updated", entity_id=locked.entity_id, metadata={}
    )
    return network_records_for_scope(scope).get(pk=locked.pk)
