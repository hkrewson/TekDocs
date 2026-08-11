import csv
import io
import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState
from apps.core.network_addressing import create_subnet, create_vlan
from apps.core.network_endpoints import create_ip_address
from apps.core.network_inventory import create_rack
from apps.core.network_services import create_dns_record, create_dns_zone, create_wireless_network
from apps.core.organizations import create_organization
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Network transfer MSP",
        owner_email="network-transfer-owner@example.invalid",
        owner_display_name="Network Transfer Owner",
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


def _site(installation, organization, name):  # type: ignore[no-untyped-def]
    return create_site(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=name,
        code=name.upper().replace(" ", "-")[:24],
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )


def _rack(installation, organization, site, name):  # type: ignore[no-untyped-def]
    return create_rack(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=name,
        site_entity_id=site.entity_id,
        location_entity_id=None,
        unit_count=42,
        status="active",
    )


def _stream_bytes(response):  # type: ignore[no-untyped-def]
    return b"".join(response.streaming_content)


@pytest.mark.django_db
def test_network_search_and_export_are_exact_workspace_bounded_and_sanitized(owner_client, installation):
    selected = _organization(installation, "Selected network client")
    sibling = _organization(installation, "Sibling network client")
    selected_site = _site(installation, selected, "Selected site")
    sibling_site = _site(installation, sibling, "Sibling site")
    msp_site = _site(installation, None, "MSP site")
    selected_rack = _rack(installation, selected, selected_site, "Selected rack")
    _rack(installation, sibling, sibling_site, "Sibling secret rack")
    _rack(installation, None, msp_site, "MSP rack")
    vlan = create_vlan(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        name="Guest VLAN",
        vlan_id=44,
        description='=HYPERLINK("https://example.invalid")',
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        name="Guest subnet",
        cidr="10.44.0.0/24",
        vrf_entity_id=None,
        vlan_entity_id=vlan.entity_id,
        description="Guest address range",
    )
    address = create_ip_address(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        address="10.44.0.10",
        subnet_entity_id=subnet.entity_id,
        interface_entity_id=None,
        status="active",
        dns_name="printer.selected.example",
        description="Office printer",
    )
    create_wireless_network(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        ssid="Selected Guest",
        purpose="guest",
        security="wpa3_personal",
        status="active",
        hidden=False,
        client_isolation=True,
        site_entity_id=selected_site.entity_id,
        vlan_entity_id=vlan.entity_id,
        subnet_entity_id=subnet.entity_id,
        description="Guest wireless network",
    )
    zone = create_dns_zone(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        name="selected.example",
        description="Selected DNS zone",
    )
    create_dns_record(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        zone_entity_id=zone.entity_id,
        owner_name="printer.selected.example",
        record_type="A",
        value="10.44.0.10",
        ttl=3600,
        priority=None,
        weight=None,
        port=None,
        ip_address_entity_id=address.entity_id,
        description="Printer record",
    )
    kwargs = {"organization_entity_id": selected.entity_id}
    search_url = reverse("organization-network-search", kwargs=kwargs)

    by_cidr = owner_client.get(search_url, {"q": "10.44.0.0/24", "page_size": 10})
    assert by_cidr.status_code == 200
    assert by_cidr.json()["results"] == [
        {
            "id": str(subnet.entity_id),
            "name": "Guest subnet",
            "record_type": "network_subnet",
            "type_label": "Subnet",
            "section": "subnets",
        }
    ]
    all_records = owner_client.get(search_url, {"page": 1, "page_size": 3})
    assert all_records.status_code == 200
    assert all_records.json()["count"] == 7
    assert all_records.json()["has_more"] is True
    second_page = owner_client.get(search_url, {"page": 2, "page_size": 3}).json()
    assert not (
        {item["id"] for item in all_records.json()["results"]} & {item["id"] for item in second_page["results"]}
    )
    assert "Sibling secret rack" not in all_records.content.decode()
    assert owner_client.get(search_url, {"unknown": "value"}).status_code == 400
    assert owner_client.get(search_url, {"page_size": 101}).status_code == 400

    exported_response = owner_client.get(reverse("organization-network-export", kwargs=kwargs))
    assert exported_response.status_code == 200
    assert exported_response["Cache-Control"] == "private, no-store"
    exported = _stream_bytes(exported_response).decode()
    rows = list(csv.DictReader(io.StringIO(exported)))
    assert {row["record_type"] for row in rows} == {
        "network_rack",
        "network_vlan",
        "network_subnet",
        "network_ip_address",
        "wireless_network",
        "dns_zone",
        "dns_record",
    }
    assert all(row["schema_version"] == "tekdocs.networks.v1" for row in rows)
    assert next(row for row in rows if row["entity_id"] == str(vlan.entity_id))["description"].startswith("'=")
    assert str(selected_rack.entity_id) in exported
    assert "Sibling secret rack" not in exported
    assert "MSP rack" not in exported
    assert "credential_reference" not in exported.lower()
    assert "contract_id" not in exported.lower()

    msp_search = owner_client.get(reverse("msp-network-search"), {"q": "rack"})
    assert [item["name"] for item in msp_search.json()["results"]] == ["MSP rack"]
    msp_export = _stream_bytes(owner_client.get(reverse("msp-network-export"))).decode()
    assert "MSP rack" in msp_export
    assert "Selected rack" not in msp_export
    assert Client().get(search_url).status_code == 403
