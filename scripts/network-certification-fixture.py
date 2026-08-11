import os

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.catalogs import create_definition, create_model, create_product
from apps.core.inventory import create_client_asset
from apps.core.models import (
    DNSRecord,
    InstallationState,
    NetBoxReference,
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkDevice,
    NetworkIPAddress,
    NetworkMACAddress,
    NetworkRack,
    NetworkSubnet,
    NetworkVLAN,
    WirelessNetwork,
)
from apps.core.netbox_reconciliation import set_reference
from apps.core.network_addressing import create_subnet, create_vlan
from apps.core.network_endpoints import create_ip_address, create_mac_address
from apps.core.network_inventory import create_rack
from apps.core.network_inventory import create_device
from apps.core.network_circuits import create_circuit, create_handoff
from apps.core.network_services import create_dns_record, create_dns_zone, create_wireless_network
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, rls_scope
from apps.core.scoping import DataScope
from apps.core.sites import create_site


def create_fixture():
    result = bootstrap_owner(
        tenant_name="Network Recovery MSP",
        owner_email="network-recovery@example.invalid",
        owner_display_name="Network Recovery Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Network Recovery Client",
            legal_name="Network Recovery Client, LLC",
            website="",
            classifications=["client"],
        )
        provider = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Network Recovery Carrier",
            legal_name="Network Recovery Carrier, Inc.",
            website="",
            classifications=["vendor"],
        )
        supplier = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Network Recovery Manufacturer",
            legal_name="Network Recovery Manufacturer, Inc.",
            website="",
            classifications=["manufacturer"],
        )
        hardware_asset_entity_id = None
        if os.environ.get("TEKDOCS_FIXTURE_LEGACY") != "true":
            bind_local_rls_scope(
                DataScope.organization(result.tenant, supplier),
                organization_mode=OrganizationRLSMode.ORGANIZATION,
            )
            definition = create_definition(
                tenant=result.tenant,
                organization=supplier,
                actor_id=result.owner.id,
                name="Recovery network hardware",
                product_kind="hardware",
                schema={"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "properties": {}},
            )
            product = create_product(
                tenant=result.tenant,
                organization=supplier,
                actor_id=result.owner.id,
                name="Recovery edge platform",
                kind="hardware",
                description="Recovery fixture",
            )
            model = create_model(
                product=product,
                actor_id=result.owner.id,
                name="Recovery edge model",
                model_number="REC-EDGE",
                specification_version=definition.versions.get(version=1),
                lifecycle="active",
                specifications={},
                notes="",
            )
            bind_local_rls_scope(
                DataScope.organization(result.tenant, client),
                organization_mode=OrganizationRLSMode.ORGANIZATION,
            )
            asset = create_client_asset(
                tenant=result.tenant,
                organization=client,
                actor_id=result.owner.id,
                model_entity_id=model.entity_id,
                name="Recovery edge device",
            )
            hardware_asset_entity_id = asset.entity_id
        bind_local_rls_scope(
            DataScope.organization(result.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        site = create_site(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery headquarters",
            code="REC-HQ",
            address_line_1="",
            address_line_2="",
            city="Madison",
            region="WI",
            postal_code="",
            country_code="US",
            timezone="America/Chicago",
            phone="",
        )
        rack = create_rack(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery core rack",
            site_entity_id=site.entity_id,
            location_entity_id=None,
            unit_count=42,
            status="active",
        )
        device = create_device(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery edge device",
            role="firewall",
            status="active",
            hardware_asset_entity_id=hardware_asset_entity_id,
            site_entity_id=None,
            location_entity_id=None,
            rack_entity_id=rack.entity_id,
            rack_unit=1,
            rack_units=1,
        )
        set_reference(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            entity_id=rack.entity_id,
            object_type="dcim.rack",
            object_id=4242,
            fingerprint="4f6f73de66cbe09f45b7897cb5c58c86b6dfe34a0f3b9a75251019e41d7b2a6e",
        )
        vlan = create_vlan(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery operations VLAN",
            vlan_id=42,
            description="Retained network recovery fixture",
        )
        subnet = create_subnet(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery operations subnet",
            cidr="192.0.2.0/24",
            vrf_entity_id=None,
            vlan_entity_id=vlan.entity_id,
            description="Retained network recovery fixture",
        )
        address = create_ip_address(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            address="192.0.2.42",
            subnet_entity_id=subnet.entity_id,
            interface_entity_id=None,
            status="active",
            dns_name="recovery.example.invalid",
            description="Retained network recovery fixture",
        )
        create_mac_address(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            address="02:00:00:00:00:42",
            interface_entity_id=None,
            description="Retained network recovery fixture",
        )
        create_wireless_network(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            ssid="Recovery Staff",
            purpose="corporate",
            security="wpa3_enterprise",
            status="active",
            hidden=False,
            client_isolation=True,
            site_entity_id=site.entity_id,
            vlan_entity_id=vlan.entity_id,
            subnet_entity_id=subnet.entity_id,
            description="Retained network recovery fixture",
        )
        zone = create_dns_zone(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="example.invalid",
            description="Retained network recovery fixture",
        )
        create_dns_record(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            zone_entity_id=zone.entity_id,
            owner_name="recovery.example.invalid",
            record_type="A",
            value="192.0.2.42",
            ttl=300,
            priority=None,
            weight=None,
            port=None,
            ip_address_entity_id=address.entity_id,
            description="Retained network recovery fixture",
        )
        circuit = create_circuit(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            name="Recovery internet circuit",
            provider_entity_id=provider.entity_id,
            contract_entity_id=None,
            service_identifier="REC-CIRCUIT-42",
            kind="internet",
            status="active",
            bandwidth_down_mbps=None,
            bandwidth_up_mbps=None,
            installed_on=None,
            service_starts_on=None,
            review_on=None,
            planned_disconnect_on=None,
            description="Retained network recovery fixture",
        )
        create_handoff(
            circuit=circuit,
            actor_id=result.owner.id,
            name="Recovery carrier handoff",
            side="a",
            media="fiber",
            connector="LC",
            provider_reference="REC-HANDOFF-42",
            site_entity_id=site.entity_id,
            location_entity_id=None,
            device_entity_id=device.entity_id,
            interface_entity_id=None,
            description="Retained network recovery fixture",
        )
    print("Network certification fixture created")


def verify_fixture():
    tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED):
        client = tenant.organizations.get(entity__display_name="Network Recovery Client")
        bind_local_rls_scope(
            DataScope.organization(tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        scope = DataScope.organization(tenant, client)
        rack = NetworkRack.scoped.for_scope(scope).get(entity__display_name="Recovery core rack")
        assert rack.entity.workspace.organization_id == client.id
        assert rack.unit_count == 42
        device = NetworkDevice.scoped.for_scope(scope).get()
        assert device.rack_id == rack.id
        assert (device.hardware_asset_id is not None) != device.legacy_unbacked
        assert NetBoxReference.scoped.for_scope(scope).get(entity=rack.entity).object_id == 4242
        assert NetworkVLAN.scoped.for_scope(scope).get(entity__display_name="Recovery operations VLAN").vlan_id == 42
        assert NetworkSubnet.scoped.for_scope(scope).get(entity__display_name="Recovery operations subnet").cidr == "192.0.2.0/24"
        retained_ip = NetworkIPAddress.scoped.for_scope(scope).get(address="192.0.2.42")
        assert retained_ip.dns_name == "recovery.example.invalid"
        retained_mac = NetworkMACAddress.scoped.for_scope(scope).get()
        assert retained_mac.address == "02:00:00:00:00:42"
        if device.hardware_asset_id is not None:
            assert retained_ip.hardware_asset_id is None
            assert retained_mac.hardware_asset_id is None
        assert WirelessNetwork.scoped.for_scope(scope).get().ssid == "Recovery Staff"
        assert DNSRecord.scoped.for_scope(scope).get().value == "192.0.2.42"
        circuit = NetworkCircuit.scoped.for_scope(scope).get()
        assert circuit.service_identifier == "REC-CIRCUIT-42"
        assert NetworkCircuitHandoff.scoped.for_scope(scope).get(circuit=circuit).device.entity.display_name == "Recovery edge device"

        from apps.core.network_transfer import NETWORK_EXPORT_SCHEMA, network_entities_for_scope, stream_network_csv

        assert network_entities_for_scope(scope, search="192.0.2.42").count() == 2
        exported = "".join(stream_network_csv(scope))
        assert NETWORK_EXPORT_SCHEMA in exported
        assert "Recovery core rack" in exported
        assert "192.0.2.42" in exported
        assert "4f6f73de66cbe09f45b7897cb5c58c86b6dfe34a0f3b9a75251019e41d7b2a6e" not in exported
    print("Network search/export, identifiers, and exact ownership verified")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
