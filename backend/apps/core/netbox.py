from __future__ import annotations

import ipaddress
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.utils import timezone

from .catalogs import create_definition, create_model, create_product
from .inventory import create_client_asset
from .models import (
    CatalogModel,
    CatalogModelLifecycle,
    CatalogProduct,
    CatalogProductKind,
    CatalogSpecificationDefinition,
    CatalogSpecificationDefinitionVersion,
    ClientAsset,
    IntegrationConflict,
    IntegrationConflictStatus,
    IntegrationEntityMapping,
    IntegrationObservation,
    IntegrationSyncJob,
    NetBoxObjectType,
    NetBoxReference,
    NetworkDevice,
    NetworkDeviceRole,
    NetworkDeviceStatus,
    NetworkSubnet,
    Organization,
    OrganizationKind,
)
from .network_addressing import create_subnet
from .network_inventory import create_device, update_device
from .organizations import create_organization
from .scoping import DataScope

GENERIC_MANUFACTURER = "NetBox imported"
PRODUCT_NAME = "Network devices"
DEFINITION_NAME = "NetBox observed hardware"


def _text(value: object, *, maximum: int = 500) -> str:
    return value.strip()[:maximum] if isinstance(value, str) else ""


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _decimal(value: object) -> Decimal | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.1"))
    except InvalidOperation:
        return None


def _actor_id(job: IntegrationSyncJob) -> UUID:
    return job.requested_by_id or job.connection.created_by_id


def _mapping(job: IntegrationSyncJob, observation: IntegrationObservation) -> IntegrationEntityMapping | None:
    return IntegrationEntityMapping.objects.filter(
        connection=job.connection,
        remote_type=observation.remote_type,
        remote_id=observation.remote_id,
    ).first()


def _link_available(job: IntegrationSyncJob, observation: IntegrationObservation, *, entity_id: UUID) -> bool:
    existing = NetBoxReference.objects.filter(
        workspace=job.workspace,
        entity_id=entity_id,
        archived_at__isnull=True,
    ).first()
    return existing is None or (
        existing.object_type == observation.remote_type and existing.object_id == int(observation.remote_id)
    )


def _link(job: IntegrationSyncJob, observation: IntegrationObservation, *, entity_id: UUID) -> None:
    now = timezone.now()
    IntegrationEntityMapping.objects.update_or_create(
        connection=job.connection,
        remote_type=observation.remote_type,
        remote_id=observation.remote_id,
        defaults={
            "tenant": job.tenant,
            "workspace": job.workspace,
            "organization": job.organization,
            "local_entity_id": entity_id,
            "observed_fingerprint": observation.fingerprint,
            "last_observed_at": now,
        },
    )
    NetBoxReference.objects.update_or_create(
        workspace=job.workspace,
        object_type=observation.remote_type,
        object_id=int(observation.remote_id),
        archived_at__isnull=True,
        defaults={
            "tenant": job.tenant,
            "organization": job.organization,
            "entity_id": entity_id,
            "observed_fingerprint": observation.fingerprint,
            "last_observed_at": now,
        },
    )
    IntegrationConflict.objects.filter(
        connection=job.connection,
        remote_type=observation.remote_type,
        remote_id=observation.remote_id,
        status=IntegrationConflictStatus.OPEN,
    ).update(status=IntegrationConflictStatus.ACCEPT_REMOTE, resolved_at=now)


def _project_prefix(job: IntegrationSyncJob, observation: IntegrationObservation) -> bool:
    values = observation.safe_projection
    cidr = _text(values.get("prefix"), maximum=49)
    try:
        network = ipaddress.ip_network(cidr, strict=True)
    except ValueError:
        return False
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    mapping = _mapping(job, observation)
    record = (
        NetworkSubnet.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
        if mapping is not None
        else None
    )
    if record is None:
        matches = list(NetworkSubnet.scoped.for_scope(scope).filter(cidr=network.with_prefixlen)[:2])
        if len(matches) > 1:
            return False
        record = (
            matches[0]
            if matches
            else create_subnet(
                tenant=job.tenant,
                organization=job.organization,
                actor_id=_actor_id(job),
                name=network.with_prefixlen,
                cidr=network.with_prefixlen,
                vrf_entity_id=None,
                vlan_entity_id=None,
                description=_text(values.get("description"), maximum=4000),
            )
        )
    if not _link_available(job, observation, entity_id=record.entity_id):
        return False
    vlan_number = _integer(values.get("vlan_id"))
    if vlan_number is not None and not 1 <= vlan_number <= 4094:
        vlan_number = None
    description = _text(values.get("description"), maximum=4000)
    changed: list[str] = []
    if record.vlan_number != vlan_number:
        record.vlan_number = vlan_number
        changed.append("vlan_number")
    if description and record.description != description:
        record.description = description
        changed.append("description")
    if changed:
        record.full_clean()
        record.save(update_fields=(*changed, "updated_at"))
    _link(job, observation, entity_id=record.entity_id)
    return True


def _supplier(job: IntegrationSyncJob, name: str) -> Organization:
    supplier = (
        Organization.objects.filter(
            tenant=job.tenant,
            entity__display_name__iexact=name,
            classifications__kind=OrganizationKind.MANUFACTURER,
        )
        .distinct()
        .first()
    )
    return supplier or create_organization(
        tenant=job.tenant,
        actor_id=_actor_id(job),
        name=name,
        legal_name=name,
        website="",
        classifications=[OrganizationKind.MANUFACTURER],
    )


def _catalog_model(job: IntegrationSyncJob, manufacturer: str, model_number: str) -> CatalogModel:
    supplier = _supplier(job, manufacturer)
    product = (
        CatalogProduct.objects.filter(
            tenant=job.tenant,
            organization=supplier,
            entity__display_name=PRODUCT_NAME,
            archived_at__isnull=True,
        )
        .select_related("entity")
        .first()
    )
    if product is None:
        product = create_product(
            tenant=job.tenant,
            organization=supplier,
            actor_id=_actor_id(job),
            name=PRODUCT_NAME,
            kind=CatalogProductKind.HARDWARE,
            description="Network hardware models observed through NetBox.",
        )
    model = (
        CatalogModel.objects.filter(product=product, model_number=model_number, archived_at__isnull=True)
        .select_related("entity", "product")
        .first()
    )
    if model is not None:
        return model
    definition = CatalogSpecificationDefinition.objects.filter(
        tenant=job.tenant,
        organization=supplier,
        name=DEFINITION_NAME,
        product_kind=CatalogProductKind.HARDWARE,
        archived_at__isnull=True,
    ).first()
    if definition is None:
        definition = create_definition(
            tenant=job.tenant,
            organization=supplier,
            actor_id=_actor_id(job),
            name=DEFINITION_NAME,
            product_kind=CatalogProductKind.HARDWARE,
            schema={"type": "object", "additionalProperties": False, "properties": {}},
        )
    version = CatalogSpecificationDefinitionVersion.objects.filter(definition=definition).order_by("-version").first()
    if version is None:
        raise ValueError("netbox_catalog_definition_invalid")
    return create_model(
        product=product,
        actor_id=_actor_id(job),
        name=model_number,
        model_number=model_number,
        specification_version=version,
        lifecycle=CatalogModelLifecycle.ACTIVE,
        specifications={},
        notes="Created from an observed NetBox device type.",
    )


def _role(value: str) -> str:
    normalized = value.lower().replace("-", "_")
    if "access" in normalized and "point" in normalized:
        return NetworkDeviceRole.ACCESS_POINT
    if "switch" in normalized:
        return NetworkDeviceRole.SWITCH
    if "firewall" in normalized:
        return NetworkDeviceRole.FIREWALL
    if "router" in normalized or "gateway" in normalized:
        return NetworkDeviceRole.ROUTER
    if "wireless" in normalized and "controller" in normalized:
        return NetworkDeviceRole.WIRELESS_CONTROLLER
    return NetworkDeviceRole.OTHER


def _status(value: str) -> str:
    normalized = value.lower()
    if normalized in {"planned", "staged", "inventory"}:
        return NetworkDeviceStatus.PLANNED
    if normalized in {"offline", "failed"}:
        return NetworkDeviceStatus.OFFLINE
    if normalized in {"decommissioning", "retired"}:
        return NetworkDeviceStatus.RETIRED
    return NetworkDeviceStatus.ACTIVE


def _project_device(job: IntegrationSyncJob, observation: IntegrationObservation) -> bool:
    values = observation.safe_projection
    name = _text(values.get("name"), maximum=200)
    manufacturer = _text(values.get("manufacturer"), maximum=200) or GENERIC_MANUFACTURER
    model_number = _text(values.get("model"), maximum=160) or "Unknown NetBox model"
    if not name:
        return False
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    mapping = _mapping(job, observation)
    asset = (
        ClientAsset.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
        if mapping is not None
        else None
    )
    if asset is None:
        candidates = list(
            ClientAsset.scoped.for_scope(scope).filter(
                archived_at__isnull=True,
                entity__display_name__iexact=name,
                model__model_number__iexact=model_number,
            )[:2]
        )
        if len(candidates) > 1:
            return False
        asset = (
            candidates[0]
            if candidates
            else create_client_asset(
                tenant=job.tenant,
                organization=job.organization,
                actor_id=_actor_id(job),
                model_entity_id=_catalog_model(job, manufacturer, model_number).entity_id,
                name=name,
            )
        )
    if not _link_available(job, observation, entity_id=asset.entity_id):
        return False
    if asset.entity.display_name != name:
        asset.entity.display_name = name
        asset.entity.save(update_fields=("display_name", "updated_at"))
    serial = _text(values.get("serial"), maximum=160)
    if serial and asset.hardware.serial_number != serial:
        asset.hardware.serial_number = serial
        asset.hardware.save(update_fields=("serial_number", "updated_at"))
    role = _role(_text(values.get("role"), maximum=100))
    status = _status(_text(values.get("status"), maximum=40))
    device = NetworkDevice.scoped.for_scope(scope).filter(hardware_asset=asset).first()
    if device is None:
        device = create_device(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            name=name,
            role=role,
            status=status,
            hardware_asset_entity_id=asset.entity_id,
            site_entity_id=None,
            location_entity_id=None,
            rack_entity_id=None,
            rack_unit=None,
            rack_units=1,
        )
    elif device.entity.display_name != name or device.role != role or device.status != status:
        device = update_device(
            device=device,
            actor_id=_actor_id(job),
            values={"name": name, "role": role, "status": status},
        )
    source_values = {
        "source_rack_name": _text(values.get("rack"), maximum=200),
        "source_rack_position": _decimal(values.get("position")),
        "source_rack_units": _integer(values.get("height")),
    }
    if any(getattr(device, field) != value for field, value in source_values.items()):
        for field, value in source_values.items():
            setattr(device, field, value)
        device.full_clean()
        device.save(update_fields=(*source_values, "updated_at"))
    _link(job, observation, entity_id=asset.entity_id)
    return True


def project_netbox_observations(job: IntegrationSyncJob, observations: list[IntegrationObservation]) -> None:
    for observation in observations:
        if observation.state != "observed":
            continue
        if observation.remote_type == NetBoxObjectType.PREFIX:
            _project_prefix(job, observation)
        elif observation.remote_type == NetBoxObjectType.DEVICE:
            _project_device(job, observation)
