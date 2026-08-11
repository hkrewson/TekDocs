from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from .models import (
    AuditEvent,
    CatalogProductKind,
    ClientAsset,
    Entity,
    EntityVisibility,
    Location,
    NetworkDevice,
    NetworkRack,
    Organization,
    Site,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope


class NetworkInventoryError(ValueError):
    pass


def racks_for_scope(scope: DataScope) -> QuerySet[NetworkRack]:
    return (
        NetworkRack.scoped.for_scope(scope)
        .select_related("entity", "site__entity", "location__entity")
        .prefetch_related("network_devices__entity")
    )


def devices_for_scope(scope: DataScope) -> QuerySet[NetworkDevice]:
    return NetworkDevice.scoped.for_scope(scope).select_related(
        "entity",
        "site__entity",
        "location__entity",
        "rack__entity",
        "hardware_asset__entity",
        "hardware_asset__product",
    )


def _site(scope: DataScope, entity_id: UUID | None) -> Site | None:
    if entity_id is None:
        return None
    try:
        return Site.scoped.for_scope(scope).get(entity_id=entity_id, archived_at__isnull=True)
    except Site.DoesNotExist as exc:
        raise NetworkInventoryError("The selected site is unavailable in this Workspace.") from exc


def _location(scope: DataScope, entity_id: UUID | None, site: Site | None) -> Location | None:
    if entity_id is None:
        return None
    if site is None:
        raise NetworkInventoryError("Choose a site before choosing a location.")
    try:
        return Location.scoped.for_scope(scope).get(
            entity_id=entity_id,
            site=site,
            archived_at__isnull=True,
        )
    except Location.DoesNotExist as exc:
        raise NetworkInventoryError("The selected location is unavailable in that site and Workspace.") from exc


def _hardware_asset(scope: DataScope, entity_id: UUID | None) -> ClientAsset | None:
    if entity_id is None:
        return None
    try:
        return ClientAsset.scoped.for_scope(scope).select_related("product").get(
            entity_id=entity_id,
            product__kind=CatalogProductKind.HARDWARE,
            archived_at__isnull=True,
            entity__archived_at__isnull=True,
        )
    except ClientAsset.DoesNotExist as exc:
        raise NetworkInventoryError("The selected hardware asset is unavailable in this Workspace.") from exc


def _rack(scope: DataScope, entity_id: UUID | None, *, lock: bool = False) -> NetworkRack | None:
    if entity_id is None:
        return None
    query = NetworkRack.scoped.for_scope(scope)
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        return query.select_related("site", "location").get(entity_id=entity_id)
    except NetworkRack.DoesNotExist as exc:
        raise NetworkInventoryError("The selected rack is unavailable in this Workspace.") from exc


def _assert_rack_capacity(
    *, rack: NetworkRack, rack_unit: int, rack_units: int, exclude_device_id: UUID | None = None
) -> None:
    if rack_unit < 1 or rack_units < 1 or rack_unit + rack_units - 1 > rack.unit_count:
        raise NetworkInventoryError(f"Placement must fit within rack units 1 through {rack.unit_count}.")
    occupied = NetworkDevice.objects.filter(rack=rack)
    if exclude_device_id is not None:
        occupied = occupied.exclude(pk=exclude_device_id)
    end = rack_unit + rack_units - 1
    if occupied.filter(rack_unit__lte=end).extra(
        where=["rack_unit + rack_units - 1 >= %s"], params=[rack_unit]
    ).exists():
        raise NetworkInventoryError("Those rack units overlap an existing device placement.")


def _placement(
    *,
    scope: DataScope,
    site_entity_id: UUID | None,
    location_entity_id: UUID | None,
    rack_entity_id: UUID | None,
    rack_unit: int | None,
    rack_units: int,
    exclude_device_id: UUID | None = None,
) -> tuple[Site | None, Location | None, NetworkRack | None, int | None, int]:
    rack = _rack(scope, rack_entity_id, lock=True)
    if rack is not None:
        if rack_unit is None:
            raise NetworkInventoryError("Choose a starting rack unit for a rack placement.")
        _assert_rack_capacity(
            rack=rack,
            rack_unit=rack_unit,
            rack_units=rack_units,
            exclude_device_id=exclude_device_id,
        )
        return rack.site, rack.location, rack, rack_unit, rack_units
    if rack_unit is not None or rack_units != 1:
        raise NetworkInventoryError("Rack units are accepted only when a rack is selected.")
    site = _site(scope, site_entity_id)
    location = _location(scope, location_entity_id, site)
    return site, location, None, None, 1


@transaction.atomic
def create_rack(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    site_entity_id: UUID,
    location_entity_id: UUID | None,
    unit_count: int,
    status: str,
) -> NetworkRack:
    scope = DataScope.owner(tenant, organization)
    site = _site(scope, site_entity_id)
    if site is None:
        raise NetworkInventoryError("A rack requires a site.")
    location = _location(scope, location_entity_id, site)
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="network_rack",
        display_name=name.strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    rack = NetworkRack(
        tenant=tenant,
        organization=organization,
        entity=entity,
        site=site,
        location=location,
        unit_count=unit_count,
        status=status,
    )
    rack.full_clean()
    rack.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_rack.created", entity_id=entity.id, metadata={}
    )
    return racks_for_scope(scope).get(pk=rack.pk)


@transaction.atomic
def update_rack(*, rack: NetworkRack, actor_id: UUID, values: dict[str, object]) -> NetworkRack:
    locked = NetworkRack.objects.select_for_update().select_related("entity").get(pk=rack.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    site_entity_id = cast(UUID, values.get("site_entity_id", locked.site.entity_id))
    site = _site(scope, site_entity_id)
    if site is None:
        raise NetworkInventoryError("A rack requires a site.")
    current_location = locked.location if locked.location_id else None
    location_value = cast(
        UUID | None,
        values.get("location_entity_id", current_location.entity_id if current_location is not None else None),
    )
    location = _location(scope, location_value, site)
    unit_count = cast(int, values.get("unit_count", locked.unit_count))
    placed = NetworkDevice.objects.filter(rack=locked)
    if placed.exists() and (site.id != locked.site_id or (location.id if location else None) != locked.location_id):
        raise NetworkInventoryError("Move or unplace rack devices before changing the rack location.")
    highest = max((item.rack_unit + item.rack_units - 1 for item in placed), default=0)  # type: ignore[operator]
    if highest > unit_count:
        raise NetworkInventoryError("The rack cannot be shortened below an occupied unit.")
    locked.site = site
    locked.location = location
    locked.unit_count = unit_count
    locked.status = str(values.get("status", locked.status))
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.full_clean()
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant, actor_id=actor_id, action="network_rack.updated", entity_id=locked.entity_id, metadata={}
    )
    return racks_for_scope(scope).get(pk=locked.pk)


@transaction.atomic
def create_device(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    role: str,
    status: str,
    hardware_asset_entity_id: UUID | None,
    site_entity_id: UUID | None,
    location_entity_id: UUID | None,
    rack_entity_id: UUID | None,
    rack_unit: int | None,
    rack_units: int,
) -> NetworkDevice:
    scope = DataScope.owner(tenant, organization)
    site, location, rack, rack_unit, rack_units = _placement(
        scope=scope,
        site_entity_id=site_entity_id,
        location_entity_id=location_entity_id,
        rack_entity_id=rack_entity_id,
        rack_unit=rack_unit,
        rack_units=rack_units,
    )
    asset = _hardware_asset(scope, hardware_asset_entity_id)
    if asset is not None and NetworkDevice.objects.filter(hardware_asset=asset).exists():
        raise NetworkInventoryError("That hardware asset already has a network-device record.")
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="network_device",
        display_name=name.strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    device = NetworkDevice(
        tenant=tenant,
        organization=organization,
        entity=entity,
        role=role,
        status=status,
        hardware_asset=asset,
        site=site,
        location=location,
        rack=rack,
        rack_unit=rack_unit,
        rack_units=rack_units,
    )
    device.full_clean()
    try:
        device.save()
    except IntegrityError as exc:
        raise NetworkInventoryError("That hardware asset already has a network-device record.") from exc
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_device.created", entity_id=entity.id, metadata={}
    )
    return devices_for_scope(scope).get(pk=device.pk)


@transaction.atomic
def update_device(*, device: NetworkDevice, actor_id: UUID, values: dict[str, object]) -> NetworkDevice:
    locked = NetworkDevice.objects.select_for_update().select_related("entity").get(pk=device.pk)
    scope = DataScope.owner(locked.tenant, locked.organization)
    current_site = locked.site if locked.site_id else None
    current_location = locked.location if locked.location_id else None
    current_rack = locked.rack if locked.rack_id else None
    site, location, rack, rack_unit, rack_units = _placement(
        scope=scope,
        site_entity_id=cast(
            UUID | None,
            values.get("site_entity_id", current_site.entity_id if current_site is not None else None),
        ),
        location_entity_id=cast(
            UUID | None,
            values.get(
                "location_entity_id", current_location.entity_id if current_location is not None else None
            ),
        ),
        rack_entity_id=cast(
            UUID | None,
            values.get("rack_entity_id", current_rack.entity_id if current_rack is not None else None),
        ),
        rack_unit=cast(int | None, values.get("rack_unit", locked.rack_unit)),
        rack_units=cast(int, values.get("rack_units", locked.rack_units)),
        exclude_device_id=locked.id,
    )
    current_asset = locked.hardware_asset if locked.hardware_asset_id else None
    asset_value = cast(
        UUID | None,
        values.get(
            "hardware_asset_entity_id", current_asset.entity_id if current_asset is not None else None
        ),
    )
    hardware_asset = _hardware_asset(scope, asset_value)
    if hardware_asset is not None and NetworkDevice.objects.filter(hardware_asset=hardware_asset).exclude(
        pk=locked.pk
    ).exists():
        raise NetworkInventoryError("That hardware asset already has a network-device record.")
    locked.hardware_asset = hardware_asset
    locked.site, locked.location, locked.rack = site, location, rack
    locked.rack_unit, locked.rack_units = rack_unit, rack_units
    locked.role = str(values.get("role", locked.role))
    locked.status = str(values.get("status", locked.status))
    locked.entity.display_name = str(values.get("name", locked.entity.display_name)).strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.full_clean()
    try:
        locked.save()
    except IntegrityError as exc:
        raise NetworkInventoryError("That hardware asset already has a network-device record.") from exc
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_device.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return devices_for_scope(scope).get(pk=locked.pk)
