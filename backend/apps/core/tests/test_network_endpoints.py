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


@pytest.mark.django_db
def test_parent_address_collection_is_bounded_searchable_and_scope_checked(owner_client, installation):
    organization = _organization(installation, "Address collection")
    sibling = _organization(installation, "Other address workspace")
    subnet = _subnet(installation, organization)
    other = _subnet(installation, sibling, cidr="198.51.100.0/24")
    for index in range(1, 32):
        create_ip_address(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            address=f"192.0.2.{index}",
            subnet_entity_id=subnet.entity_id,
            interface_entity_id=None,
            status="reserved" if index == 31 else "active",
            dns_name=f"host-{index}.example.invalid",
            description="Selected detail only",
        )
    url = reverse("organization-network-ip-addresses", kwargs={"organization_entity_id": organization.entity_id})
    query = {"subnet_id": str(subnet.entity_id), "page_size": 25, "ordering": "name", "summary": "true"}
    first = owner_client.get(url, query)
    assert first.status_code == 200, first.content
    payload = first.json()
    assert payload["count"] == 31 and payload["has_more"]
    assert [item["address"] for item in payload["results"][:3]] == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
    assert all("description" not in item for item in payload["results"])
    second = owner_client.get(url, {**query, "page": 2}).json()
    assert len(second["results"]) == 6 and not second["has_more"]
    found = owner_client.get(url, {**query, "q": "host-31", "status": "reserved"}).json()
    assert found["count"] == 1 and found["results"][0]["address"] == "192.0.2.31"
    assert owner_client.get(url, {**query, "subnet_id": str(other.entity_id)}).status_code == 403
    assert owner_client.get(url, {**query, "status": "invalid"}).status_code == 400
    assert owner_client.get(url, {**query, "ordering": "hardware_asset_name"}).status_code == 400
    assert "description" in owner_client.get(url).json()["results"][0]
    preferences = reverse(
        "organization-collection-preferences",
        kwargs={"organization_entity_id": organization.entity_id, "feature": "network-addresses"},
    )
    assert (
        owner_client.put(
            preferences, {"columns": ["name", "status"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(preferences).json()["columns"] == ["name", "status"]
    assert owner_client.delete(preferences).json()["page_size"] == 25


@pytest.mark.django_db
def test_address_status_edit_preserves_parent_and_assignment(owner_client, installation):
    organization = _organization(installation, "Address edit")
    subnet = _subnet(installation, organization)
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Address hardware")
    record = create_ip_address(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        address="192.0.2.10",
        subnet_entity_id=subnet.entity_id,
        interface_entity_id=None,
        hardware_asset_entity_id=asset.entity_id,
        status="active",
        dns_name="original.example.invalid",
        description="",
    )
    url = reverse(
        "organization-network-ip-address-detail",
        kwargs={"organization_entity_id": organization.entity_id, "ip_address_entity_id": record.entity_id},
    )
    response = owner_client.patch(
        url, {"status": "reserved", "dns_name": "updated.example.invalid"}, content_type="application/json"
    )
    assert response.status_code == 200, response.content
    record.refresh_from_db()
    assert record.status == "reserved" and record.dns_name == "updated.example.invalid"
    assert record.hardware_asset_id == asset.pk and record.subnet_id == subnet.pk


@pytest.mark.django_db
def test_interface_collection_search_paging_parent_scope_and_partial_edit(owner_client, installation):
    from apps.core.network_endpoints import create_interface

    organization = _organization(installation, "Interface client")
    sibling = _organization(installation, "Other interface client")
    device = _device(installation, organization)
    other = _device(installation, organization, "Other switch")
    outside = _device(installation, sibling, "Outside switch")
    interfaces = []
    for index in range(31):
        interfaces.append(
            create_interface(
                tenant=installation.tenant,
                organization=organization,
                actor_id=installation.owner.id,
                name=f"Port {index:02}",
                device_entity_id=device.entity_id,
                kind="physical",
                status="active",
                description=f"Cable destination {index:02}",
            )
        )
    create_interface(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Other port",
        device_entity_id=other.entity_id,
        kind="virtual",
        status="disabled",
        description="",
    )
    kwargs = {"organization_entity_id": organization.entity_id}
    url = reverse("organization-network-interfaces", kwargs=kwargs)
    first = owner_client.get(url, {"device_id": device.entity_id, "page_size": 25, "summary": "true"}).json()
    assert first["count"] == 31 and len(first["results"]) == 25 and first["has_more"]
    assert "description" not in first["results"][0]
    second = owner_client.get(url, {"device_id": device.entity_id, "page_size": 25, "page": 2}).json()
    assert len(second["results"]) == 6 and not second["has_more"]
    assert second["results"][-1]["description"] == "Cable destination 30"
    found = owner_client.get(url, {"device_id": device.entity_id, "q": "destination 30"}).json()
    assert found["count"] == 1 and found["results"][0]["id"] == str(interfaces[-1].entity_id)
    descending = owner_client.get(url, {"device_id": device.entity_id, "ordering": "-name"}).json()
    assert descending["results"][0]["name"] == "Port 30"
    assert owner_client.get(url, {"device_id": device.entity_id, "kind": "virtual"}).json()["count"] == 0
    assert owner_client.get(url, {"device_id": device.entity_id, "status": "disabled"}).json()["count"] == 0
    assert owner_client.get(url, {"device_id": outside.entity_id}).status_code == 403
    assert owner_client.get(url, {"ordering": "description"}).status_code == 400
    assert owner_client.get(url, {"unknown": "filter"}).status_code == 400
    legacy = owner_client.get(url).json()
    assert legacy["count"] == 32 and legacy["page_size"] == 50
    assert "description" in legacy["results"][0]
    detail = reverse(
        "organization-network-interface-detail", kwargs={**kwargs, "interface_entity_id": interfaces[-1].entity_id}
    )
    assert owner_client.get(detail).json()["description"] == "Cable destination 30"
    edited = owner_client.patch(
        detail, {"status": "disabled", "description": "Updated cable"}, content_type="application/json"
    )
    assert edited.status_code == 200, edited.content
    assert edited.json()["device_id"] == str(device.entity_id)
    pref = reverse("organization-collection-preferences", kwargs={**kwargs, "feature": "network-interfaces"})
    assert owner_client.get(pref).json()["columns"] == ["name", "kind", "status"]
    assert (
        owner_client.put(
            pref, {"columns": ["name", "status"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(pref).json()["columns"] == ["name", "status"]
    assert owner_client.delete(pref).json()["page_size"] == 25


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["ip", "mac"])
def test_interface_endpoint_assignment_is_bounded_and_compare_checked(owner_client, installation, kind, monkeypatch):
    from rest_framework.exceptions import PermissionDenied

    from apps.accounts.policy import PermissionKey
    from apps.core import network_endpoint_views
    from apps.core.models import AuditEvent
    from apps.core.network_endpoints import create_interface, create_mac_address

    organization = _organization(installation, "Assignment client")
    sibling = _organization(installation, "Other assignment client")
    device = _device(installation, organization)
    outside_device = _device(installation, sibling)
    interface = create_interface(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Uplink",
        device_entity_id=device.entity_id,
        kind="physical",
        status="active",
        description="",
    )
    outside = create_interface(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        name="Other uplink",
        device_entity_id=outside_device.entity_id,
        kind="physical",
        status="active",
        description="",
    )
    subnet = _subnet(installation, organization)
    rows = []
    for index in range(1, 32):
        common = dict(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            interface_entity_id=None,
            description=f"Cable {index:02}",
        )
        rows.append(
            create_ip_address(
                **common, address=f"192.0.2.{index}", subnet_entity_id=subnet.entity_id, status="active", dns_name=""
            )
            if kind == "ip"
            else create_mac_address(**common, address=f"02:00:00:00:00:{index:02x}")
        )
    kwargs = {"organization_entity_id": organization.entity_id}
    url = reverse(f"organization-network-{kind}-addresses", kwargs=kwargs)
    first = owner_client.get(url, {"unassigned": "true", "summary": "true", "page_size": 25}).json()
    assert first["count"] == 31 and len(first["results"]) == 25 and first["has_more"]
    assert "description" not in first["results"][0]
    assert len(owner_client.get(url, {"unassigned": "true", "page_size": 25, "page": 2}).json()["results"]) == 6
    found = owner_client.get(url, {"unassigned": "true", "q": "Cable 31"}).json()
    assert found["count"] == 1 and found["results"][0]["id"] == str(rows[-1].entity_id)
    assert owner_client.get(url, {"interface_id": outside.entity_id}).status_code == 403
    assert owner_client.get(url, {"interface_id": interface.entity_id, "unassigned": "true"}).status_code == 400
    detail = reverse(
        f"organization-network-{kind}-address-detail",
        kwargs={**kwargs, f"{kind}_address_entity_id": rows[-1].entity_id},
    )

    def patch(payload):
        return owner_client.patch(detail, payload, content_type="application/json")

    assert patch({"interface_id": str(interface.entity_id)}).status_code == 400
    assert (
        patch(
            {"interface_id": str(interface.entity_id), "expected_interface_id": None, "description": "mixed"}
        ).status_code
        == 400
    )
    assert patch({"interface_id": str(outside.entity_id), "expected_interface_id": None}).status_code == 400
    assigned = patch({"interface_id": str(interface.entity_id), "expected_interface_id": None})
    assert assigned.status_code == 200, assigned.content
    assert assigned.json()["interface_id"] == str(interface.entity_id)
    assert owner_client.get(url, {"unassigned": "true"}).json()["count"] == 30
    assert owner_client.get(url, {"interface_id": interface.entity_id}).json()["count"] == 1
    assert patch({"interface_id": None, "expected_interface_id": None}).status_code == 409
    assert patch({"description": "Updated cable"}).status_code == 200
    rows[-1].refresh_from_db()
    assert rows[-1].interface_id == interface.pk and rows[-1].description == "Updated cable"
    audit_action = f"network_{kind}_address.updated"
    assert AuditEvent.objects.filter(entity_id=rows[-1].entity_id, action=audit_action).count() == 2
    assert patch({"interface_id": None, "expected_interface_id": str(interface.entity_id)}).status_code == 200
    assert AuditEvent.objects.filter(entity_id=rows[-1].entity_id, action=audit_action).count() == 3
    # An interface assignment must never replace a protected hardware binding.
    rows[-1].hardware_asset = device.hardware_asset
    rows[-1].save(update_fields=["hardware_asset"])
    assert patch({"interface_id": str(interface.entity_id), "expected_interface_id": None}).status_code == 409
    rows[-1].refresh_from_db()
    assert rows[-1].hardware_asset_id == device.hardware_asset_id and rows[-1].interface_id is None
    original = network_endpoint_views.require_permission

    def require(user, permission, **kw):
        if permission == PermissionKey.NETWORKS_EDIT:
            raise PermissionDenied("Network editing denied.")
        return original(user, permission, **kw)

    monkeypatch.setattr(network_endpoint_views, "require_permission", require)
    assert patch({"interface_id": str(interface.entity_id), "expected_interface_id": None}).status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["ip", "mac"])
def test_endpoint_assignment_concurrent_claim_has_one_winner(installation, kind):
    from apps.core.network_endpoints import (
        NetworkAssignmentConflict,
        create_interface,
        create_mac_address,
        update_ip_address,
        update_mac_address,
    )

    organization = _organization(installation, "Concurrent assignment")
    device = _device(installation, organization)
    interfaces = [
        create_interface(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            name=f"Port {index}",
            device_entity_id=device.entity_id,
            kind="physical",
            status="active",
            description="",
        )
        for index in range(2)
    ]
    common = dict(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        interface_entity_id=None,
        description="Concurrent cable",
    )
    record = (
        create_ip_address(
            **common,
            address="192.0.2.70",
            subnet_entity_id=_subnet(installation, organization).entity_id,
            status="active",
            dns_name="",
        )
        if kind == "ip"
        else create_mac_address(**common, address="02:00:00:00:00:70")
    )
    barrier = threading.Barrier(2)
    actor_id = installation.owner.id

    def claim(interface_id):
        close_old_connections()
        try:
            stale = type(record).objects.get(pk=record.pk)
            barrier.wait(timeout=15)
            update = update_ip_address if kind == "ip" else update_mac_address
            update(
                record=stale,
                actor_id=actor_id,
                values={"interface_entity_id": interface_id, "expected_interface_entity_id": None},
            )
            return "assigned"
        except NetworkAssignmentConflict:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, [item.entity_id for item in interfaces]))
    assert sorted(outcomes) == ["assigned", "conflict"]
    record.refresh_from_db()
    assert record.interface_id in [item.pk for item in interfaces]


@pytest.mark.django_db(transaction=True)
def test_waiting_ip_assignment_preserves_concurrent_subnet_change(installation):
    import time

    from apps.core.network_endpoints import create_interface, update_ip_address

    organization = _organization(installation, "Concurrent namespace")
    device = _device(installation, organization)
    interface = create_interface(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Uplink",
        device_entity_id=device.entity_id,
        kind="physical",
        status="active",
        description="",
    )
    original = _subnet(installation, organization)
    vrf = create_vrf(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Moved namespace",
        route_distinguisher="65000:99",
        description="",
    )
    destination = _subnet(installation, organization, vrf=vrf)
    record = create_ip_address(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        address="192.0.2.80",
        subnet_entity_id=original.entity_id,
        interface_entity_id=None,
        status="active",
        dns_name="",
        description="Concurrent namespace cable",
    )
    changed = threading.Event()
    release = threading.Event()

    def move():
        close_old_connections()
        try:
            with transaction.atomic():
                update_ip_address(
                    record=record, actor_id=installation.owner.id, values={"subnet_entity_id": destination.entity_id}
                )
                changed.set()
                assert release.wait(15)
        finally:
            close_old_connections()

    def assign():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET application_name = 'endpoint_namespace_waiter'")
            return update_ip_address(
                record=record,
                actor_id=installation.owner.id,
                values={"interface_entity_id": interface.entity_id, "expected_interface_entity_id": None},
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        moving = executor.submit(move)
        assert changed.wait(15)
        assigning = executor.submit(assign)
        try:
            deadline = time.monotonic() + 10
            blocked = False
            while time.monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                        "WHERE application_name = 'endpoint_namespace_waiter' AND wait_event_type = 'Lock')"
                    )
                    blocked = cursor.fetchone()[0]
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "Assignment must actually wait on the concurrent namespace update"
        finally:
            release.set()
        moving.result(timeout=15)
        assigning.result(timeout=15)
    record.refresh_from_db()
    assert record.interface_id == interface.pk
    assert record.subnet_id == destination.pk
