import secrets
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    AuditEvent,
    Entity,
    InstallationState,
    NetworkDevice,
    NetworkRack,
    Organization,
    OrganizationClassification,
    Site,
    Tenant,
)
from apps.core.network_inventory import NetworkInventoryError, create_device
from apps.core.network_inventory_views import NetworkDeviceSerializer
from apps.core.organizations import create_organization
from apps.core.rls_contract import RUNTIME_ROLE
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Network MSP",
        owner_email="network-owner@example.invalid",
        owner_display_name="Network Owner",
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


def _site(owner_client, organization, name):  # type: ignore[no-untyped-def]
    response = owner_client.post(
        reverse("organization-site-list-create", kwargs={"organization_entity_id": organization.entity_id}),
        {
            "name": name,
            "code": name.upper().replace(" ", "-"),
            "address_line_1": "1 Main Street",
            "address_line_2": "",
            "city": "Madison",
            "region": "WI",
            "postal_code": "53703",
            "country_code": "US",
            "timezone": "America/Chicago",
            "phone": "",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


def _rack(owner_client, organization, site, name="Core rack"):  # type: ignore[no-untyped-def]
    response = owner_client.post(
        reverse("organization-network-racks", kwargs={"organization_entity_id": organization.entity_id}),
        {"name": name, "site_id": site["id"], "location_id": None, "unit_count": 42, "status": "active"},
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


def _device(owner_client, installation, organization, rack, name, unit):  # type: ignore[no-untyped-def]
    asset = create_network_hardware_asset(installation=installation, organization=organization, name=name)
    return owner_client.post(
        reverse("organization-network-devices", kwargs={"organization_entity_id": organization.entity_id}),
        {
            "name": name,
            "role": "switch",
            "status": "active",
            "hardware_asset_id": str(asset.entity_id),
            "site_id": None,
            "location_id": None,
            "rack_id": rack["id"],
            "rack_unit": unit,
            "rack_units": 2,
        },
        content_type="application/json",
    )


@pytest.mark.django_db
def test_racks_devices_placement_relationships_and_workspace_idor(owner_client, installation):
    client = _organization(installation, "Acme Dental")
    sibling = _organization(installation, "Sibling Dental")
    site = _site(owner_client, client, "Headquarters")
    sibling_site = _site(owner_client, sibling, "Sibling office")
    rack = _rack(owner_client, client, site)
    sibling_rack = _rack(owner_client, sibling, sibling_site, "Sibling rack")

    first = _device(owner_client, installation, client, rack, "Core switch", 10)
    assert first.status_code == 201
    assert first.json()["site_name"] == "Headquarters"
    assert first.json()["rack_unit"] == 10
    second = _device(owner_client, installation, client, rack, "Distribution switch", 14)
    assert second.status_code == 201
    overlap = _device(owner_client, installation, client, rack, "Overlapping switch", 11)
    assert overlap.status_code == 400
    assert "overlap" in overlap.content.decode().lower()

    client_list = owner_client.get(
        reverse("organization-network-devices", kwargs={"organization_entity_id": client.entity_id})
    )
    assert [item["name"] for item in client_list.json()["results"]] == ["Core switch", "Distribution switch"]
    assert owner_client.get(reverse("msp-network-devices")).json()["results"] == []
    guessed = owner_client.get(
        reverse(
            "organization-network-rack-detail",
            kwargs={"organization_entity_id": client.entity_id, "rack_entity_id": sibling_rack["id"]},
        )
    )
    assert guessed.status_code == 403

    foreign_tenant = Tenant.objects.create(name="Foreign Network MSP", slug="foreign-network-msp")
    foreign_anchor = Entity.objects.create_owned(
        tenant=foreign_tenant,
        entity_type="organization",
        display_name="Foreign Network Client",
    )
    foreign_organization = Organization.objects.create(tenant=foreign_tenant, entity=foreign_anchor)
    OrganizationClassification.objects.create(
        tenant=foreign_tenant,
        organization=foreign_organization,
        kind="client",
    )
    foreign_site_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        organization=foreign_organization,
        entity_type="site",
        display_name="Foreign site",
    )
    foreign_site = Site.objects.create(
        tenant=foreign_tenant,
        organization=foreign_organization,
        entity=foreign_site_entity,
    )
    foreign_rack_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        organization=foreign_organization,
        entity_type="network_rack",
        display_name="Foreign rack",
    )
    foreign_rack = NetworkRack.objects.create(
        tenant=foreign_tenant,
        organization=foreign_organization,
        entity=foreign_rack_entity,
        site=foreign_site,
        unit_count=42,
        status="active",
    )
    foreign_guess = owner_client.get(
        reverse(
            "organization-network-rack-detail",
            kwargs={"organization_entity_id": client.entity_id, "rack_entity_id": foreign_rack.entity_id},
        )
    )
    assert foreign_guess.status_code == 403

    link = owner_client.post(
        reverse(
            "organization-entity-relationship-list-create",
            kwargs={"organization_entity_id": client.entity_id, "entity_id": first.json()["id"]},
        ),
        {"target_id": second.json()["id"], "link_type": "connected_to"},
        content_type="application/json",
    )
    assert link.status_code == 201
    assert link.json()["link_type"] == "connected_to"
    backlink = owner_client.get(
        reverse(
            "organization-entity-relationship-list-create",
            kwargs={"organization_entity_id": client.entity_id, "entity_id": second.json()["id"]},
        )
    ).json()["relationships"]
    assert backlink[0]["link_type"] == "connected_to"
    assert backlink[0]["related_entity"]["id"] == first.json()["id"]


@pytest.mark.django_db
def test_rack_update_rejects_move_or_shrink_around_placed_devices(owner_client, installation):
    client = _organization(installation, "Placement client")
    first_site = _site(owner_client, client, "First site")
    second_site = _site(owner_client, client, "Second site")
    rack = _rack(owner_client, client, first_site)
    assert _device(owner_client, installation, client, rack, "Edge firewall", 40).status_code == 201
    detail = reverse(
        "organization-network-rack-detail",
        kwargs={"organization_entity_id": client.entity_id, "rack_entity_id": rack["id"]},
    )
    moved = owner_client.patch(detail, {"site_id": second_site["id"]}, content_type="application/json")
    assert moved.status_code == 400
    shortened = owner_client.patch(detail, {"unit_count": 40}, content_type="application/json")
    assert shortened.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_concurrent_device_placement_serializes_on_the_rack(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Advisory-lock concurrency validation requires PostgreSQL")
    client = _organization(installation, "Concurrent client")
    site = _site(owner_client, client, "Concurrency site")
    rack_data = _rack(owner_client, client, site)
    rack = NetworkRack.objects.get(entity_id=rack_data["id"])
    assets = {
        name: create_network_hardware_asset(installation=installation, organization=client, name=name)
        for name in ("First", "Second")
    }
    barrier = threading.Barrier(2)

    def place(name):  # type: ignore[no-untyped-def]
        close_old_connections()
        try:
            tenant = Tenant.objects.get(pk=installation.tenant.id)
            organization = tenant.organizations.get(pk=client.id)
            barrier.wait(timeout=5)
            create_device(
                tenant=tenant,
                organization=organization,
                actor_id=installation.owner.id,
                name=name,
                role="switch",
                status="active",
                hardware_asset_entity_id=assets[name].entity_id,
                site_entity_id=None,
                location_entity_id=None,
                rack_entity_id=rack.entity_id,
                rack_unit=20,
                rack_units=2,
            )
            return "created"
        except NetworkInventoryError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(place, ("First", "Second")))
    assert outcomes == ["created", "rejected"]
    assert NetworkDevice.objects.filter(rack=rack).count() == 1


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def _bind(cursor, tenant_id, organization_id):  # type: ignore[no-untyped-def]
    cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(tenant_id)])
    cursor.execute(
        "SELECT id FROM core_workspace WHERE tenant_id=%s AND organization_id=%s",
        [tenant_id, organization_id],
    )
    cursor.execute("SELECT set_config('tekdocs.workspace_id', %s, true)", [str(cursor.fetchone()[0])])
    cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(organization_id)])
    cursor.execute("SELECT set_config('tekdocs.organization_mode', 'organization', true)")


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_and_forced_rls_reject_cross_workspace_network_writes(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Database guard and runtime-role validation require PostgreSQL")
    first = _organization(installation, "First RLS client")
    sibling = _organization(installation, "Sibling RLS client")
    first_site = _site(owner_client, first, "First RLS site")
    sibling_site = _site(owner_client, sibling, "Sibling RLS site")
    rack_data = _rack(owner_client, first, first_site)
    rack = NetworkRack.objects.get(entity_id=rack_data["id"])

    unbacked_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=first,
        entity_type="network_device",
        display_name="Forbidden unbacked device",
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkDevice.objects.create(
            tenant=installation.tenant,
            organization=first,
            entity=unbacked_entity,
            role="switch",
            status="active",
        )

    sibling_site_record = Site.objects.get(entity_id=sibling_site["id"])
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkRack.objects.filter(pk=rack.pk).update(site_id=sibling_site_record.id)

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, installation.tenant.id, sibling.id)
        cursor.execute("SELECT id FROM core_networkrack")
        assert cursor.fetchall() == []
        cursor.execute("UPDATE core_networkrack SET status='retired' WHERE id=%s", [rack.id])
        assert cursor.rowcount == 0


def test_network_device_serializer_does_not_disclose_linked_asset_without_asset_permission():
    asset_entity = type("AssetEntity", (), {"display_name": "Private firewall asset"})()
    linked_asset = type(
        "LinkedAsset",
        (),
        {"entity_id": "2cf06899-dd0d-4b9b-9695-b888c3e364c2", "entity": asset_entity},
    )()
    device = type("Device", (), {"hardware_asset_id": linked_asset.entity_id, "hardware_asset": linked_asset})()

    hidden = NetworkDeviceSerializer(context={"can_view_assets": False})
    visible = NetworkDeviceSerializer(context={"can_view_assets": True})

    assert hidden.get_hardware_asset_id(device) is None
    assert hidden.get_hardware_asset_name(device) is None
    assert str(visible.get_hardware_asset_id(device)) == linked_asset.entity_id
    assert visible.get_hardware_asset_name(device) == "Private firewall asset"


@pytest.mark.django_db
def test_inventory_collections_search_paging_order_and_parent_boundaries(owner_client, installation):
    organization = _organization(installation, "Collection workspace")
    sibling = _organization(installation, "Collection sibling")
    site = _site(owner_client, organization, "Collection site")
    other_site = _site(owner_client, sibling, "Other site")
    other_rack = _rack(owner_client, sibling, other_site, "Outside rack")
    racks = [_rack(owner_client, organization, site, f"Rack {index:02}") for index in range(31)]
    for index, rack in enumerate(racks):
        response = _device(owner_client, installation, organization, rack, f"Device {index:02}", 1)
        assert response.status_code == 201, response.content
    kwargs = {"organization_entity_id": organization.entity_id}
    for kind in ("racks", "devices"):
        url = reverse(f"organization-network-{kind}", kwargs=kwargs)
        first = owner_client.get(url, {"page_size": 25}).json()
        second = owner_client.get(url, {"page_size": 25, "page": 2}).json()
        assert first["count"] == 31 and first["has_more"] and len(first["results"]) == 25
        assert len(second["results"]) == 6 and not second["has_more"]
        assert not ({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        found = owner_client.get(url, {"q": "30", "status": "active"}).json()
        assert found["count"] == 1 and found["results"][0]["name"].endswith("30")
        assert owner_client.get(url).json()["page_size"] == 50  # Existing public default.
        assert owner_client.get(url, {"q": "COLLECTION-SITE"}).json()["count"] == 31
        assert owner_client.get(url, {"status": "retired"}).json()["count"] == 0
        assert owner_client.get(url, {"site_id": site["id"]}).json()["count"] == 31
        assert owner_client.get(url, {"site_id": other_site["id"]}).status_code == 403
        assert owner_client.get(reverse(f"msp-network-{kind}"), {"q": "30"}).json()["count"] == 0
        for invalid in ({"status": "invalid"}, {"ordering": "hardware_asset_name"}, {"page_size": 101}, {"typo": "x"}):
            assert owner_client.get(url, invalid).status_code == 400
        # Equal status values use entity identity as a deterministic tie-breaker.
        ordered = owner_client.get(url, {"ordering": "-status", "page_size": 100}).json()["results"]
        assert [r["id"] for r in ordered] == sorted(r["id"] for r in ordered)
        reverse_names = owner_client.get(url, {"ordering": "-name"}).json()["results"]
        assert reverse_names[0]["name"].endswith("30")
    rack_rows = owner_client.get(
        reverse("organization-network-racks", kwargs=kwargs), {"ordering": "device_count"}
    ).json()["results"]
    assert all(row["device_count"] == 1 for row in rack_rows)
    devices_url = reverse("organization-network-devices", kwargs=kwargs)
    selected = owner_client.get(devices_url, {"rack_id": racks[-1]["id"], "role": "switch"}).json()
    assert selected["count"] == 1 and selected["results"][0]["name"] == "Device 30"
    assert owner_client.get(devices_url, {"role": "router"}).json()["count"] == 0
    assert owner_client.get(devices_url, {"role": "invalid"}).status_code == 400
    assert owner_client.get(devices_url, {"rack_id": other_rack["id"]}).status_code == 403
    owner_client.logout()
    assert owner_client.get(devices_url, {"q": "30"}).status_code == 403


@pytest.mark.django_db
def test_device_collection_asset_search_respects_asset_permission(owner_client, installation, monkeypatch):
    from apps.accounts.policy import PermissionKey
    from apps.core import network_inventory_views

    organization = _organization(installation, "Permission workspace")
    site = _site(owner_client, organization, "Permission site")
    rack = _rack(owner_client, organization, site)
    response = _device(owner_client, installation, organization, rack, "Visible device", 1)
    assert response.status_code == 201
    device = NetworkDevice.objects.select_related("hardware_asset__entity").get(entity_id=response.json()["id"])
    entity = device.hardware_asset.entity
    entity.display_name = "Restricted asset identifier"
    entity.save(update_fields=["display_name"])
    url = reverse("organization-network-devices", kwargs={"organization_entity_id": organization.entity_id})
    assert owner_client.get(url, {"q": "Restricted asset"}).json()["count"] == 1
    original = network_inventory_views.context_has_permission
    monkeypatch.setattr(
        network_inventory_views,
        "context_has_permission",
        lambda member, permission, **kwargs: permission != PermissionKey.ASSETS_VIEW
        and original(member, permission, **kwargs),
    )
    assert owner_client.get(url, {"q": "Restricted asset"}).json()["count"] == 0
    result = owner_client.get(url, {"q": "Visible device"}).json()["results"][0]
    assert result["hardware_asset_name"] is None and result["hardware_asset_id"] is None


@pytest.mark.django_db
def test_rack_location_choices_and_preferences_are_bounded_and_scoped(owner_client, installation):
    organization = _organization(installation, "Rack editor")
    other = _organization(installation, "Other rack editor")
    site = _site(owner_client, organization, "Rack campus")
    other_site = _site(owner_client, other, "Other campus")
    location_url = reverse(
        "organization-location-list-create",
        kwargs={"organization_entity_id": organization.entity_id, "site_entity_id": site["id"]},
    )
    for index in range(31):
        response = owner_client.post(
            location_url,
            {"name": f"Room {index:02}", "kind": "room", "code": f"R{index:02}", "parent_id": None},
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
    url = reverse("organization-network-assignment-choices", kwargs={"organization_entity_id": organization.entity_id})
    query = {"kind": "location", "site_id": site["id"]}
    first = owner_client.get(url, query).json()
    assert first["page_size"] == 25 and first["count"] == 31 and first["has_more"]
    assert len(owner_client.get(url, {**query, "page": 2}).json()["results"]) == 6
    assert owner_client.get(url, {**query, "q": "R30"}).json()["results"][0]["name"] == "Room 30"
    assert owner_client.get(url, {"kind": "location"}).status_code == 400
    assert owner_client.get(url, {"kind": "site", "site_id": site["id"]}).status_code == 400
    assert owner_client.get(url, {**query, "site_id": other_site["id"]}).status_code == 403
    pref = reverse(
        "organization-collection-preferences",
        kwargs={"organization_entity_id": organization.entity_id, "feature": "network-racks"},
    )
    defaults = owner_client.get(pref).json()
    assert defaults["columns"] == ["name", "site", "location", "status", "unit_count", "device_count"]
    assert (
        owner_client.put(
            pref, {"columns": ["name", "status"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(pref).json()["columns"] == ["name", "status"]
    assert owner_client.delete(pref).json()["page_size"] == 25


@pytest.mark.django_db
def test_device_creation_choices_and_preferences_are_scoped(owner_client, installation):
    organization = _organization(installation, "Device choices")
    sibling = _organization(installation, "Other device choices")
    for index in range(31):
        create_network_hardware_asset(
            installation=installation, organization=organization, name=f"Available {index:02}"
        )
    create_network_hardware_asset(installation=installation, organization=sibling, name="Outside asset")
    kwargs = {"organization_entity_id": organization.entity_id}
    url = reverse("organization-network-assignment-choices", kwargs=kwargs)
    first = owner_client.get(url, {"kind": "hardware_asset"}).json()
    assert first["count"] == 31 and first["page_size"] == 25 and first["has_more"]
    second = owner_client.get(url, {"kind": "hardware_asset", "page": 2}).json()
    assert len(second["results"]) == 6 and not second["has_more"]
    found = owner_client.get(url, {"kind": "hardware_asset", "q": "Available 30"}).json()
    assert found["count"] == 1
    assert owner_client.get(url, {"kind": "hardware_asset", "q": "Outside"}).json()["count"] == 0
    device_url = reverse("organization-network-devices", kwargs=kwargs)
    capabilities = owner_client.get(device_url).json()
    assert capabilities["can_create"] is True and capabilities["can_rebind_hardware"] is True
    created = owner_client.post(
        device_url,
        {"name": "New device", "role": "switch", "hardware_asset_id": found["results"][0]["id"]},
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    assert owner_client.get(url, {"kind": "hardware_asset", "q": "Available 30"}).json()["count"] == 0
    pref = reverse("organization-collection-preferences", kwargs={**kwargs, "feature": "network-devices"})
    assert owner_client.get(pref).json()["columns"] == ["name", "role", "status", "site", "rack", "rack_unit"]
    assert (
        owner_client.put(
            pref, {"columns": ["name", "status"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(pref).json()["columns"] == ["name", "status"]
    assert owner_client.delete(pref).json()["page_size"] == 25


@pytest.mark.django_db
def test_device_hardware_rebinding_is_scoped_conflict_safe_and_separate(owner_client, installation):
    organization = _organization(installation, "Hardware replacement")
    sibling = _organization(installation, "Other hardware replacement")
    site = _site(owner_client, organization, "Replacement campus")
    rack = _rack(owner_client, organization, site)
    created = _device(owner_client, installation, organization, rack, "Bound switch", 3)
    assert created.status_code == 201
    original_asset_id = created.json()["hardware_asset_id"]
    replacement = create_network_hardware_asset(
        installation=installation, organization=organization, name="Replacement chassis"
    )
    occupied = create_network_hardware_asset(
        installation=installation, organization=organization, name="Occupied chassis"
    )
    other_device = owner_client.post(
        reverse("organization-network-devices", kwargs={"organization_entity_id": organization.entity_id}),
        {"name": "Other device", "role": "switch", "hardware_asset_id": str(occupied.entity_id)},
        content_type="application/json",
    )
    assert other_device.status_code == 201
    outside = create_network_hardware_asset(
        installation=installation, organization=sibling, name="Outside chassis"
    )
    detail = reverse(
        "organization-network-device-detail",
        kwargs={"organization_entity_id": organization.entity_id, "device_entity_id": created.json()["id"]},
    )
    replaced = owner_client.patch(
        detail,
        {
            "hardware_asset_id": str(replacement.entity_id),
            "expected_hardware_asset_id": original_asset_id,
        },
        content_type="application/json",
    )
    assert replaced.status_code == 200, replaced.content
    assert replaced.json()["hardware_asset_name"] == "Replacement chassis"
    assert replaced.json()["rack_id"] == rack["id"] and replaced.json()["rack_unit"] == 3
    assert AuditEvent.objects.filter(
        entity_id=created.json()["id"], action="network_device.updated"
    ).count() == 1

    stale = owner_client.patch(
        detail,
        {"hardware_asset_id": original_asset_id, "expected_hardware_asset_id": original_asset_id},
        content_type="application/json",
    )
    assert stale.status_code == 409 and "changed" in stale.json()["detail"].lower()
    same = owner_client.patch(
        detail,
        {
            "hardware_asset_id": str(replacement.entity_id),
            "expected_hardware_asset_id": str(replacement.entity_id),
        },
        content_type="application/json",
    )
    assert same.status_code == 409 and "different" in same.json()["detail"].lower()
    for unavailable in (occupied.entity_id, outside.entity_id):
        denied = owner_client.patch(
            detail,
            {
                "hardware_asset_id": str(unavailable),
                "expected_hardware_asset_id": str(replacement.entity_id),
            },
            content_type="application/json",
        )
        assert denied.status_code == 400
    mixed = owner_client.patch(
        detail,
        {
            "name": "Mixed edit",
            "hardware_asset_id": original_asset_id,
            "expected_hardware_asset_id": str(replacement.entity_id),
        },
        content_type="application/json",
    )
    assert mixed.status_code == 400
    assert owner_client.get(detail).json()["hardware_asset_name"] == "Replacement chassis"


@pytest.mark.django_db
def test_asset_denial_blocks_device_creation_choices_but_not_ordinary_edits(owner_client, installation, monkeypatch):
    from rest_framework.exceptions import PermissionDenied

    from apps.accounts.policy import PermissionKey
    from apps.core import network_inventory_views

    organization = _organization(installation, "Restricted devices")
    site = _site(owner_client, organization, "Restricted campus")
    rack = _rack(owner_client, organization, site)
    created = _device(owner_client, installation, organization, rack, "Existing device", 1)
    assert created.status_code == 201
    original_context = network_inventory_views.context_has_permission
    original_require = network_inventory_views.require_permission
    monkeypatch.setattr(
        network_inventory_views,
        "context_has_permission",
        lambda member, permission, **kwargs: permission != PermissionKey.ASSETS_VIEW
        and original_context(member, permission, **kwargs),
    )

    def require(user, permission, **kwargs):
        if permission == PermissionKey.ASSETS_VIEW:
            raise PermissionDenied("Asset access denied.")
        return original_require(user, permission, **kwargs)

    monkeypatch.setattr(network_inventory_views, "require_permission", require)
    kwargs = {"organization_entity_id": organization.entity_id}
    url = reverse("organization-network-assignment-choices", kwargs=kwargs)
    assert owner_client.get(url, {"kind": "hardware_asset"}).status_code == 403
    listing = owner_client.get(reverse("organization-network-devices", kwargs=kwargs)).json()
    assert listing["can_create"] is False and listing["can_manage"] is True
    assert listing["can_rebind_hardware"] is False
    assert listing["results"][0]["hardware_asset_name"] is None
    detail = reverse("organization-network-device-detail", kwargs={**kwargs, "device_entity_id": created.json()["id"]})
    updated = owner_client.patch(
        detail, {"name": "Renamed", "role": "router", "status": "offline"}, content_type="application/json"
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["rack_id"] == rack["id"] and updated.json()["rack_unit"] == 1
    assert owner_client.patch(
        detail,
        {
            "hardware_asset_id": created.json()["hardware_asset_id"],
            "expected_hardware_asset_id": created.json()["hardware_asset_id"],
        },
        content_type="application/json",
    ).status_code == 403
