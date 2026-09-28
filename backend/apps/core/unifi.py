from __future__ import annotations

import ipaddress
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
    IntegrationEntityMapping,
    IntegrationObservation,
    IntegrationSyncJob,
    NetworkDevice,
    NetworkDeviceRole,
    NetworkDeviceStatus,
    NetworkIPAddress,
    NetworkIPAddressStatus,
    NetworkSubnet,
    Organization,
    OrganizationKind,
    WirelessNetwork,
    WirelessNetworkPurpose,
    WirelessNetworkSecurity,
    WirelessNetworkStatus,
)
from .network_addressing import create_subnet
from .network_endpoints import create_ip_address, update_ip_address
from .network_inventory import create_device, update_device
from .network_services import create_wireless_network, update_wireless_network
from .organizations import create_organization
from .scoping import DataScope

UNIFI_CATALOG_NAME = "Ubiquiti"
UNIFI_PRODUCT_NAME = "UniFi Network Device"
UNIFI_DEFINITION_NAME = "UniFi observed hardware"


def _text(value: object, *, maximum: int = 500) -> str:
    return value.strip()[:maximum] if isinstance(value, str) else ""


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _mapping(job: IntegrationSyncJob, observation: IntegrationObservation) -> IntegrationEntityMapping | None:
    return IntegrationEntityMapping.objects.filter(
        connection=job.connection,
        remote_type=observation.remote_type,
        remote_id=observation.remote_id,
    ).first()


def _link(job: IntegrationSyncJob, observation: IntegrationObservation, *, entity_id: UUID) -> None:
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
            "last_observed_at": timezone.now(),
        },
    )


def _actor_id(job: IntegrationSyncJob) -> UUID:
    return job.requested_by_id or job.connection.created_by_id


def _project_network(job: IntegrationSyncJob, observation: IntegrationObservation) -> None:
    values = observation.safe_projection
    cidr = _text(values.get("cidr"), maximum=49)
    if not cidr:
        return
    try:
        network = ipaddress.ip_network(cidr, strict=True)
    except ValueError:
        return
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    mapping = _mapping(job, observation)
    record = None
    if mapping is not None:
        record = NetworkSubnet.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
    if record is None:
        matches = list(NetworkSubnet.scoped.for_scope(scope).filter(cidr=network.with_prefixlen)[:2])
        if len(matches) > 1:
            return
        record = matches[0] if matches else create_subnet(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            name=network.with_prefixlen,
            cidr=network.with_prefixlen,
            vrf_entity_id=None,
            vlan_entity_id=None,
            description="",
        )
    retained = {
        "vlan_number": _integer(values.get("vlan_id")),
        "dhcp_server": _text(values.get("dhcp_server_ip"), maximum=45) or None,
        "primary_dns": _text(values.get("dns_server_1"), maximum=45) or None,
        "secondary_dns": _text(values.get("dns_server_2"), maximum=45) or None,
    }
    if any(getattr(record, field) != value for field, value in retained.items()):
        for field, value in retained.items():
            setattr(record, field, value)
        record.full_clean()
        record.save(update_fields=(*retained, "updated_at"))
    _link(job, observation, entity_id=record.entity_id)


def _supplier(job: IntegrationSyncJob) -> Organization:
    supplier = (
        Organization.objects.filter(
            tenant=job.tenant,
            entity__display_name__iexact=UNIFI_CATALOG_NAME,
            classifications__kind=OrganizationKind.MANUFACTURER,
        )
        .distinct()
        .first()
    )
    if supplier is not None:
        return supplier
    return create_organization(
        tenant=job.tenant,
        actor_id=_actor_id(job),
        name=UNIFI_CATALOG_NAME,
        legal_name="Ubiquiti Inc.",
        website="https://ui.com/",
        classifications=[OrganizationKind.MANUFACTURER],
    )


def _catalog_model(job: IntegrationSyncJob, model_number: str) -> CatalogModel:
    supplier = _supplier(job)
    product = (
        CatalogProduct.objects.filter(
            tenant=job.tenant,
            organization=supplier,
            entity__display_name=UNIFI_PRODUCT_NAME,
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
            name=UNIFI_PRODUCT_NAME,
            kind=CatalogProductKind.HARDWARE,
            description="Hardware model observed through the UniFi Network API.",
        )
    model = (
        CatalogModel.objects.filter(product=product, model_number=model_number, archived_at__isnull=True)
        .select_related("entity", "product")
        .first()
    )
    if model is not None:
        return model
    definition = (
        CatalogSpecificationDefinition.objects.filter(
            tenant=job.tenant,
            organization=supplier,
            name=UNIFI_DEFINITION_NAME,
            product_kind=CatalogProductKind.HARDWARE,
            archived_at__isnull=True,
        )
        .prefetch_related("versions")
        .first()
    )
    if definition is None:
        definition = create_definition(
            tenant=job.tenant,
            organization=supplier,
            actor_id=_actor_id(job),
            name=UNIFI_DEFINITION_NAME,
            product_kind=CatalogProductKind.HARDWARE,
            schema={"type": "object", "additionalProperties": False, "properties": {}},
        )
    version = CatalogSpecificationDefinitionVersion.objects.filter(definition=definition).order_by("-version").first()
    if version is None:
        raise ValueError("unifi_catalog_definition_invalid")
    return create_model(
        product=product,
        actor_id=_actor_id(job),
        name=model_number,
        model_number=model_number,
        specification_version=version,
        lifecycle=CatalogModelLifecycle.ACTIVE,
        specifications={},
        notes="Created from an adopted UniFi infrastructure observation.",
    )


def _device_role(features: str) -> str:
    values = {item.strip() for item in features.split(",")}
    if "accessPoint" in values:
        return NetworkDeviceRole.ACCESS_POINT
    if "switching" in values:
        return NetworkDeviceRole.SWITCH
    if "gateway" in values:
        return NetworkDeviceRole.ROUTER
    return NetworkDeviceRole.OTHER


def _project_device(job: IntegrationSyncJob, observation: IntegrationObservation) -> None:
    values = observation.safe_projection
    name = _text(values.get("name"), maximum=200) or f"UniFi device {observation.remote_id[:8]}"
    model_number = _text(values.get("model"), maximum=160) or "Unknown UniFi model"
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    mapping = _mapping(job, observation)
    asset = None
    if mapping is not None:
        asset = ClientAsset.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
    if asset is None:
        candidates = ClientAsset.scoped.for_scope(scope).filter(
            archived_at__isnull=True,
            entity__display_name=name,
            model__model_number=model_number,
        )[:2]
        matches = list(candidates)
        if len(matches) > 1:
            return
        asset = matches[0] if matches else create_client_asset(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            model_entity_id=_catalog_model(job, model_number).entity_id,
            name=name,
        )
    if asset.entity.display_name != name:
        asset.entity.display_name = name
        asset.entity.save(update_fields=("display_name", "updated_at"))
    serial = _text(values.get("serial"), maximum=160)
    if serial and not asset.hardware.serial_number:
        asset.hardware.serial_number = serial
        asset.hardware.save(update_fields=("serial_number", "updated_at"))
    state = _text(values.get("state"), maximum=40)
    device = NetworkDevice.scoped.for_scope(scope).filter(hardware_asset=asset).first()
    if device is None:
        create_device(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            name=name,
            role=_device_role(_text(values.get("features"))),
            status=NetworkDeviceStatus.ACTIVE if state == "ONLINE" else NetworkDeviceStatus.OFFLINE,
            hardware_asset_entity_id=asset.entity_id,
            site_entity_id=None,
            location_entity_id=None,
            rack_entity_id=None,
            rack_unit=None,
            rack_units=1,
        )
    else:
        device_role = _device_role(_text(values.get("features")))
        device_status = NetworkDeviceStatus.ACTIVE if state == "ONLINE" else NetworkDeviceStatus.OFFLINE
        if (
            device.entity.display_name != name
            or device.role != device_role
            or device.status != device_status
        ):
            update_device(
                device=device,
                actor_id=_actor_id(job),
                values={"name": name, "role": device_role, "status": device_status},
            )
    _link(job, observation, entity_id=asset.entity_id)


def _subnet_for_address(scope: DataScope, address: str) -> NetworkSubnet | None:
    try:
        host = ipaddress.ip_address(address)
    except ValueError:
        return None
    matches = [
        record
        for record in NetworkSubnet.scoped.for_scope(scope).filter(address_family=host.version)
        if host in ipaddress.ip_network(record.cidr, strict=True)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: ipaddress.ip_network(item.cidr).prefixlen, reverse=True)
    return matches[0]


def _project_client(job: IntegrationSyncJob, observation: IntegrationObservation) -> None:
    values = observation.safe_projection
    address = _text(values.get("ip_address"), maximum=45)
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    subnet = _subnet_for_address(scope, address)
    if subnet is None:
        return
    dns_name = _text(values.get("name"), maximum=253).lower()
    mapping = _mapping(job, observation)
    record = None
    if mapping is not None:
        record = NetworkIPAddress.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
    if record is None:
        matches = list(
            NetworkIPAddress.scoped.for_scope(scope).filter(subnet=subnet, address=address).select_related("entity")[:2]
        )
        if len(matches) > 1:
            return
        record = matches[0] if matches else create_ip_address(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            address=address,
            subnet_entity_id=subnet.entity_id,
            interface_entity_id=None,
            hardware_asset_entity_id=None,
            status=NetworkIPAddressStatus.DHCP,
            dns_name=_text(values.get("name"), maximum=253),
            description="Observed as a connected UniFi client.",
        )
    if record is not None and (
        record.address != address
        or record.subnet_id != subnet.id
        or record.dns_name != dns_name
        or record.status != NetworkIPAddressStatus.DHCP
    ):
        record = update_ip_address(
            record=record,
            actor_id=_actor_id(job),
            values={
                "address": address,
                "subnet_entity_id": subnet.entity_id,
                "dns_name": dns_name,
                "status": NetworkIPAddressStatus.DHCP,
            },
        )
    _link(job, observation, entity_id=record.entity_id)


SECURITY_MAP = {
    "OPEN": WirelessNetworkSecurity.OPEN,
    "WPA2_PERSONAL": WirelessNetworkSecurity.WPA2_PERSONAL,
    "WPA3_PERSONAL": WirelessNetworkSecurity.WPA3_PERSONAL,
    "WPA2_WPA3_PERSONAL": WirelessNetworkSecurity.MIXED_PERSONAL,
    "WPA2_ENTERPRISE": WirelessNetworkSecurity.WPA2_ENTERPRISE,
    "WPA3_ENTERPRISE": WirelessNetworkSecurity.WPA3_ENTERPRISE,
    "WPA2_WPA3_ENTERPRISE": WirelessNetworkSecurity.MIXED_ENTERPRISE,
}


def _project_wireless(job: IntegrationSyncJob, observation: IntegrationObservation) -> None:
    values = observation.safe_projection
    ssid = _text(values.get("name"), maximum=128)
    if not ssid:
        return
    scope = DataScope(job.tenant_id, job.workspace_id, job.organization_id)
    subnet_id = None
    network_id = _text(values.get("network_id"), maximum=160)
    if network_id:
        network_mapping = IntegrationEntityMapping.objects.filter(
            connection=job.connection,
            remote_type="unifi.network",
            remote_id=network_id,
        ).first()
        subnet_id = network_mapping.local_entity_id if network_mapping else None
    mapping = _mapping(job, observation)
    record = None
    if mapping is not None:
        record = WirelessNetwork.scoped.for_scope(scope).filter(entity_id=mapping.local_entity_id).first()
    security = SECURITY_MAP.get(_text(values.get("security")), WirelessNetworkSecurity.OPEN)
    status = WirelessNetworkStatus.ACTIVE if values.get("enabled") is True else WirelessNetworkStatus.DISABLED
    if record is None:
        matches = list(WirelessNetwork.scoped.for_scope(scope).filter(ssid=ssid, site__isnull=True)[:2])
        if len(matches) > 1:
            return
        record = matches[0] if matches else create_wireless_network(
            tenant=job.tenant,
            organization=job.organization,
            actor_id=_actor_id(job),
            ssid=ssid,
            purpose=WirelessNetworkPurpose.CORPORATE,
            security=security,
            status=status,
            hidden=False,
            client_isolation=False,
            site_entity_id=None,
            vlan_entity_id=None,
            subnet_entity_id=subnet_id,
            description="Observed through the UniFi Network API.",
        )
    elif (
        record.ssid != ssid
        or record.security != security
        or record.status != status
        or (record.subnet.entity_id if record.subnet is not None else None) != subnet_id
    ):
        record = update_wireless_network(
            record=record,
            actor_id=_actor_id(job),
            values={"ssid": ssid, "security": security, "status": status, "subnet_entity_id": subnet_id},
        )
    _link(job, observation, entity_id=record.entity_id)


def project_unifi_observations(job: IntegrationSyncJob, observations: list[IntegrationObservation]) -> None:
    """Promote only the documented deterministic UniFi projection into supported records."""

    handlers = {
        "unifi.network": _project_network,
        "unifi.device": _project_device,
        "unifi.client": _project_client,
        "unifi.wifi": _project_wireless,
    }
    priority = {"unifi.network": 0, "unifi.device": 1, "unifi.client": 2, "unifi.wifi": 3}
    for observation in sorted(observations, key=lambda item: priority.get(item.remote_type, 99)):
        if observation.state != "observed":
            continue
        handler = handlers.get(observation.remote_type)
        if handler is not None:
            handler(job, observation)
