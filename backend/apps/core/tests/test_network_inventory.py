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


def _device(owner_client, organization, rack, name, unit):  # type: ignore[no-untyped-def]
    return owner_client.post(
        reverse("organization-network-devices", kwargs={"organization_entity_id": organization.entity_id}),
        {
            "name": name,
            "role": "switch",
            "status": "active",
            "hardware_asset_id": None,
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

    first = _device(owner_client, client, rack, "Core switch", 10)
    assert first.status_code == 201
    assert first.json()["site_name"] == "Headquarters"
    assert first.json()["rack_unit"] == 10
    second = _device(owner_client, client, rack, "Distribution switch", 14)
    assert second.status_code == 201
    overlap = _device(owner_client, client, rack, "Overlapping switch", 11)
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
    assert _device(owner_client, client, rack, "Edge firewall", 40).status_code == 201
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
        pytest.skip("Advisory-lock concurrency certification requires PostgreSQL")
    client = _organization(installation, "Concurrent client")
    site = _site(owner_client, client, "Concurrency site")
    rack_data = _rack(owner_client, client, site)
    rack = NetworkRack.objects.get(entity_id=rack_data["id"])
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
                hardware_asset_entity_id=None,
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
        pytest.skip("Database guard and runtime-role certification require PostgreSQL")
    first = _organization(installation, "First RLS client")
    sibling = _organization(installation, "Sibling RLS client")
    first_site = _site(owner_client, first, "First RLS site")
    sibling_site = _site(owner_client, sibling, "Sibling RLS site")
    rack_data = _rack(owner_client, first, first_site)
    rack = NetworkRack.objects.get(entity_id=rack_data["id"])

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
