import secrets
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    Entity,
    EntityVisibility,
    InstallationState,
    NetworkIPAddress,
    NetworkSubnet,
    Tenant,
    workspace_for_owner,
)
from apps.core.network_addressing import create_subnet, create_vrf
from apps.core.network_endpoints import NetworkEndpointError, canonical_host, canonical_mac, create_ip_address
from apps.core.network_inventory import create_device
from apps.core.organizations import create_organization
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Endpoint MSP",
        owner_email="endpoint-owner@example.invalid",
        owner_display_name="Endpoint Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )


def _device(installation, organization, name="Core switch"):  # type: ignore[no-untyped-def]
    asset = create_network_hardware_asset(installation=installation, organization=organization, name=name)
    return create_device(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=name,
        role="switch",
        status="active",
        hardware_asset_entity_id=asset.entity_id,
        site_entity_id=None,
        location_entity_id=None,
        rack_entity_id=None,
        rack_unit=None,
        rack_units=1,
    )


def _subnet(installation, organization, cidr="192.0.2.0/24", vrf=None):  # type: ignore[no-untyped-def]
    return create_subnet(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=cidr,
        cidr=cidr,
        vrf_entity_id=vrf.entity_id if vrf else None,
        vlan_entity_id=None,
        description="",
    )


def _post(browser, route, organization, payload):  # type: ignore[no-untyped-def]
    return browser.post(
        reverse(route, kwargs={"organization_entity_id": organization.entity_id}),
        payload,
        content_type="application/json",
    )


@pytest.mark.django_db
def test_interface_ip_mac_crud_and_workspace_isolation(owner_client, installation):
    organization = _organization(installation, "Acme")
    sibling = _organization(installation, "Sibling")
    device = _device(installation, organization)
    subnet = _subnet(installation, organization)

    interface = _post(
        owner_client,
        "organization-network-interfaces",
        organization,
        {"name": "ethernet1", "device_id": str(device.entity_id), "kind": "physical", "status": "active"},
    )
    assert interface.status_code == 201
    assert interface.json()["device_name"] == "Core switch"

    ip_address = _post(
        owner_client,
        "organization-network-ip-addresses",
        organization,
        {
            "address": "192.0.2.10",
            "subnet_id": str(subnet.entity_id),
            "hardware_asset_id": str(device.hardware_asset.entity_id),
            "status": "active",
            "dns_name": "SWITCH.EXAMPLE.INVALID",
        },
    )
    assert ip_address.status_code == 201
    assert ip_address.json()["dns_name"] == "switch.example.invalid"
    assert ip_address.json()["hardware_asset_name"] == "Core switch"
    assert ip_address.json()["interface_name"] is None

    mac = _post(
        owner_client,
        "organization-network-mac-addresses",
        organization,
        {"address": "02:00:00:00:00:01", "hardware_asset_id": str(device.hardware_asset.entity_id)},
    )
    assert mac.status_code == 201
    assert mac.json()["device_name"] == "Core switch"

    hidden = owner_client.get(
        reverse(
            "organization-network-ip-address-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "ip_address_entity_id": ip_address.json()["id"]},
        )
    )
    assert hidden.status_code == 403
    assert (
        owner_client.get(
            reverse("organization-network-ip-addresses", kwargs={"organization_entity_id": sibling.entity_id})
        ).json()["results"]
        == []
    )

    foreign_edge = _post(
        owner_client,
        "organization-network-interfaces",
        sibling,
        {"name": "forged", "device_id": str(device.entity_id), "kind": "physical", "status": "active"},
    )
    assert foreign_edge.status_code == 400

    sibling_asset = create_network_hardware_asset(
        installation=installation, organization=sibling, name="Sibling private switch"
    )
    foreign_asset = _post(
        owner_client,
        "organization-network-mac-addresses",
        organization,
        {"address": "02:00:00:00:00:09", "hardware_asset_id": str(sibling_asset.entity_id)},
    )
    assert foreign_asset.status_code == 400


@pytest.mark.django_db
def test_mac_address_is_authored_and_returned_as_a_hardware_asset_field(owner_client, installation):
    organization = _organization(installation, "Asset MAC")
    sibling = _organization(installation, "Sibling asset MAC")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Lobby AP")
    route = reverse(
        "organization-asset-mac-addresses",
        kwargs={"organization_entity_id": organization.entity_id, "asset_entity_id": asset.entity_id},
    )
    response = owner_client.post(
        route,
        {"address": "02-00-00-00-00-0a", "description": "Wi-Fi radio"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["address"] == "02:00:00:00:00:0A"

    detail = owner_client.get(
        reverse(
            "organization-client-asset-detail",
            kwargs={"organization_entity_id": organization.entity_id, "asset_entity_id": asset.entity_id},
        )
    )
    assert detail.status_code == 200
    assert detail.json()["mac_addresses"] == [
        {"id": response.json()["id"], "address": "02:00:00:00:00:0A", "description": "Wi-Fi radio"}
    ]

    hidden = owner_client.get(
        reverse(
            "organization-asset-mac-addresses",
            kwargs={"organization_entity_id": sibling.entity_id, "asset_entity_id": asset.entity_id},
        )
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_conflicts_canonical_forms_and_routing_namespaces(owner_client, installation):
    organization = _organization(installation, "Routing")
    default_subnet = _subnet(installation, organization)
    duplicate_vrf = create_vrf(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Overlapping tenant",
        route_distinguisher="65000:1",
        description="",
    )
    isolated_subnet = _subnet(installation, organization, vrf=duplicate_vrf)

    def add(address, subnet):  # type: ignore[no-untyped-def]
        return _post(
            owner_client,
            "organization-network-ip-addresses",
            organization,
            {"address": address, "subnet_id": str(subnet.entity_id), "hardware_asset_id": None, "status": "active"},
        )

    assert add("192.0.2.10", default_subnet).status_code == 201
    duplicate = add("192.0.2.10", default_subnet)
    assert duplicate.status_code == 400
    assert "already recorded" in duplicate.content.decode()
    assert add("192.0.2.10", isolated_subnet).status_code == 201
    assert add("192.0.2.0", default_subnet).status_code == 400
    assert add("192.0.2.255", default_subnet).status_code == 400

    noncanonical = add("2001:0db8::1", _subnet(installation, organization, "2001:db8::/64"))
    assert noncanonical.status_code == 400
    assert "2001:db8::1" in noncanonical.content.decode()

    first_mac = _post(
        owner_client,
        "organization-network-mac-addresses",
        organization,
        {"address": "02:00:00:00:00:02", "hardware_asset_id": None},
    )
    assert first_mac.status_code == 201
    assert (
        _post(
            owner_client,
            "organization-network-mac-addresses",
            organization,
            {"address": "02:00:00:00:00:02", "hardware_asset_id": None},
        ).status_code
        == 400
    )
    noncanonical_mac = _post(
        owner_client,
        "organization-network-mac-addresses",
        organization,
        {"address": "02-00-00-00-00-03", "hardware_asset_id": None},
    )
    assert noncanonical_mac.status_code == 400
    assert "02:00:00:00:00:03" in noncanonical_mac.content.decode()


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_ip_creation_serializes(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Advisory-lock concurrency validation requires PostgreSQL")
    organization = _organization(installation, "Concurrent endpoints")
    subnet = _subnet(installation, organization)
    barrier = threading.Barrier(2)

    def add():
        close_old_connections()
        try:
            tenant = Tenant.objects.get(pk=installation.tenant.id)
            current_organization = tenant.organizations.get(pk=organization.id)
            current_subnet = NetworkSubnet.objects.get(pk=subnet.id)
            barrier.wait(timeout=5)
            create_ip_address(
                tenant=tenant,
                organization=current_organization,
                actor_id=installation.owner.id,
                address="192.0.2.20",
                subnet_entity_id=current_subnet.entity_id,
                interface_entity_id=None,
                status="active",
                dns_name="",
                description="",
            )
            return "created"
        except NetworkEndpointError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: add(), range(2)))
    assert outcomes == ["created", "rejected"]
    assert NetworkIPAddress.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgres_guard_rejects_direct_duplicate_ip_write(installation):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("Database guard requires PostgreSQL")
    organization = _organization(installation, "Direct endpoint guard")
    subnet = _subnet(installation, organization)
    create_ip_address(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        address="192.0.2.30",
        subnet_entity_id=subnet.entity_id,
        interface_entity_id=None,
        status="active",
        dns_name="",
        description="",
    )
    duplicate_entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
        organization=organization,
        entity_type="network_ip_address",
        display_name="192.0.2.30",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkIPAddress.objects.create(
            tenant=installation.tenant,
            organization=organization,
            entity=duplicate_entity,
            subnet=subnet,
            address="192.0.2.30",
            address_family=4,
            status="active",
        )


@given(st.ip_addresses(v=4) | st.ip_addresses(v=6))
def test_canonical_host_property(address):  # type: ignore[no-untyped-def]
    assert canonical_host(address.compressed) == address


@given(st.binary(min_size=6, max_size=6))
def test_canonical_mac_property(raw):  # type: ignore[no-untyped-def]
    value = ":".join(f"{part:02x}" for part in raw)
    assert canonical_mac(value) == value
