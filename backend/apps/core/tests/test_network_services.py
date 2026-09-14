import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from hypothesis import given
from hypothesis import strategies as st

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    DNSRecord,
    Entity,
    EntityVisibility,
    InstallationState,
    WirelessNetwork,
    workspace_for_owner,
)
from apps.core.network_addressing import create_subnet, create_vlan
from apps.core.network_endpoints import create_ip_address
from apps.core.network_services import NetworkServiceError, canonical_dns_name, create_dns_zone
from apps.core.organizations import create_organization
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Services MSP",
        owner_email="services-owner@example.invalid",
        owner_display_name="Services Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )


def _post(browser, route, organization, payload):
    return browser.post(
        reverse(route, kwargs={"organization_entity_id": organization.entity_id}),
        payload,
        content_type="application/json",
    )


@pytest.mark.django_db
def test_wireless_dns_crud_and_sibling_isolation(owner_client, installation):
    organization = _organization(installation, "Acme")
    sibling = _organization(installation, "Sibling")
    site = create_site(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Headquarters",
        code="HQ",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    vlan = create_vlan(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Corporate",
        vlan_id=20,
        description="",
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Corporate",
        cidr="192.0.2.0/24",
        vrf_entity_id=None,
        vlan_entity_id=vlan.entity_id,
        description="",
    )
    wireless = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {
            "ssid": "Acme Staff",
            "purpose": "corporate",
            "security": "wpa3_enterprise",
            "status": "active",
            "site_id": str(site.entity_id),
            "vlan_id": str(vlan.entity_id),
            "subnet_id": str(subnet.entity_id),
            "hidden": False,
            "client_isolation": False,
        },
    )
    assert wireless.status_code == 201
    assert wireless.json()["subnet_cidr"] == "192.0.2.0/24"
    updated = owner_client.patch(
        reverse(
            "organization-network-wireless-detail",
            kwargs={"organization_entity_id": organization.entity_id, "wireless_entity_id": wireless.json()["id"]},
        ),
        {"status": "disabled", "description": "Temporarily unavailable"},
        content_type="application/json",
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["site_id"] == str(site.entity_id)
    assert updated.json()["vlan_id"] == str(vlan.entity_id)
    assert updated.json()["subnet_id"] == str(subnet.entity_id)
    assert updated.json()["status"] == "disabled"

    assert (
        owner_client.get(
            reverse("organization-network-wireless", kwargs={"organization_entity_id": sibling.entity_id})
        ).json()["results"]
        == []
    )
    hidden = owner_client.get(
        reverse(
            "organization-network-wireless-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "wireless_entity_id": wireless.json()["id"]},
        )
    )
    assert hidden.status_code == 403

    zone = _post(owner_client, "organization-network-dns-zones", organization, {"name": "example.invalid"})
    assert zone.status_code == 201
    address = create_ip_address(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        address="192.0.2.10",
        subnet_entity_id=subnet.entity_id,
        interface_entity_id=None,
        status="active",
        dns_name="",
        description="",
    )
    record = _post(
        owner_client,
        "organization-network-dns-records",
        organization,
        {
            "zone_id": zone.json()["id"],
            "owner_name": "app.example.invalid",
            "record_type": "A",
            "value": "192.0.2.10",
            "ttl": 300,
            "ip_address_id": str(address.entity_id),
        },
    )
    assert record.status_code == 201
    assert record.json()["ip_address_id"] == str(address.entity_id)
    assert (
        owner_client.get(
            reverse("organization-network-dns-records", kwargs={"organization_entity_id": sibling.entity_id})
        ).json()["results"]
        == []
    )


@pytest.mark.django_db
def test_dns_type_rules_cname_conflicts_and_no_cross_workspace_edges(owner_client, installation):
    organization = _organization(installation, "DNS")
    sibling = _organization(installation, "Foreign")
    zone = _post(owner_client, "organization-network-dns-zones", organization, {"name": "example.invalid"}).json()
    assert (
        _post(
            owner_client,
            "organization-network-dns-records",
            organization,
            {
                "zone_id": zone["id"],
                "owner_name": "www.example.invalid",
                "record_type": "CNAME",
                "value": "target.example.invalid",
                "ttl": 3600,
            },
        ).status_code
        == 201
    )
    conflict = _post(
        owner_client,
        "organization-network-dns-records",
        organization,
        {
            "zone_id": zone["id"],
            "owner_name": "www.example.invalid",
            "record_type": "A",
            "value": "192.0.2.1",
            "ttl": 3600,
        },
    )
    assert conflict.status_code == 400 and "CNAME" in conflict.content.decode()
    assert (
        _post(
            owner_client,
            "organization-network-dns-records",
            organization,
            {
                "zone_id": zone["id"],
                "owner_name": "outside.invalid",
                "record_type": "TXT",
                "value": "not a secret",
                "ttl": 3600,
            },
        ).status_code
        == 400
    )
    assert (
        _post(
            owner_client,
            "organization-network-dns-records",
            sibling,
            {
                "zone_id": zone["id"],
                "owner_name": "www.example.invalid",
                "record_type": "A",
                "value": "192.0.2.2",
                "ttl": 3600,
            },
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_ssid_byte_limit_and_vlan_subnet_consistency(owner_client, installation):
    organization = _organization(installation, "Wireless")
    vlan_a = create_vlan(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="A",
        vlan_id=10,
        description="",
    )
    vlan_b = create_vlan(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="B",
        vlan_id=11,
        description="",
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="A",
        cidr="198.51.100.0/24",
        vrf_entity_id=None,
        vlan_entity_id=vlan_a.entity_id,
        description="",
    )
    too_long = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {"ssid": "é" * 17, "purpose": "guest", "security": "owe", "status": "active"},
    )
    assert too_long.status_code == 400 and "32 UTF-8 bytes" in too_long.content.decode()
    mismatch = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {
            "ssid": "Guest",
            "purpose": "guest",
            "security": "owe",
            "status": "active",
            "vlan_id": str(vlan_b.entity_id),
            "subnet_id": str(subnet.entity_id),
        },
    )
    assert mismatch.status_code == 400 and "selected VLAN" in mismatch.content.decode()


@given(st.sampled_from(["Example.COM", "example.invalid.", "", "a..example.invalid"]))
def test_dns_name_requires_canonical_input(value):
    with pytest.raises(NetworkServiceError):
        canonical_dns_name(value)


@pytest.mark.django_db(transaction=True)
def test_postgres_dns_guard_rejects_direct_foreign_zone(installation):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    owner = _organization(installation, "Owner")
    sibling = _organization(installation, "Sibling")
    zone = create_dns_zone(
        tenant=installation.tenant,
        organization=owner,
        actor_id=installation.owner.id,
        name="example.invalid",
        description="",
    )
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=sibling),
        organization=sibling,
        entity_type="dns_record",
        display_name="forged A",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    with pytest.raises(DatabaseError):
        DNSRecord.objects.create(
            tenant=installation.tenant,
            organization=sibling,
            entity=entity,
            zone=zone,
            owner_name="forged.example.invalid",
            record_type="A",
            value="192.0.2.1",
            ttl=300,
        )
    assert not DNSRecord.objects.filter(entity=entity).exists()


@pytest.mark.django_db
def test_wireless_response_never_accepts_or_returns_password_fields(owner_client, installation):
    organization = _organization(installation, "No secrets")
    response = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {
            "ssid": "Staff",
            "purpose": "corporate",
            "security": "wpa3_personal",
            "status": "active",
            "password": "do-not-store",
        },
    )
    assert response.status_code == 400
    assert WirelessNetwork.objects.filter(organization=organization).count() == 0


@pytest.mark.django_db
def test_wireless_parent_collection_search_paging_and_preferences(owner_client, installation):
    organization = _organization(installation, "Wireless collection")
    sibling = _organization(installation, "Wireless sibling")

    def parent(owner, cidr):
        return create_subnet(
            tenant=installation.tenant,
            organization=owner,
            actor_id=installation.owner.id,
            name="Office LAN",
            cidr=cidr,
            vrf_entity_id=None,
            vlan_entity_id=None,
            description="",
        )

    subnet = parent(organization, "192.0.2.0/24")
    other = parent(sibling, "198.51.100.0/24")
    url = reverse("organization-network-wireless", kwargs={"organization_entity_id": organization.entity_id})
    for index in range(31):
        response = owner_client.post(
            url,
            {
                "ssid": f"Office {index:02}",
                "subnet_id": str(subnet.entity_id),
                "status": "disabled" if index == 30 else "active",
                "description": f"Wireless purpose {index:02}",
            },
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
    query = {"subnet_id": str(subnet.entity_id), "page_size": 25, "summary": "true", "ordering": "name"}
    first = owner_client.get(url, query).json()
    assert first["count"] == 31 and first["has_more"]
    assert len(first["results"]) == 25 and first["results"][0]["ssid"] == "Office 00"
    assert all("description" not in row for row in first["results"])
    second = owner_client.get(url, {**query, "page": 2}).json()
    assert len(second["results"]) == 6 and not second["has_more"]
    found = owner_client.get(url, {**query, "q": "purpose 30", "status": "disabled"}).json()
    assert found["count"] == 1 and found["results"][0]["ssid"] == "Office 30"
    # Repeated equal-status ordering uses entity IDs to keep pages stable.
    ordered = owner_client.get(url, {**query, "ordering": "status"}).json()["results"]
    assert ordered == owner_client.get(url, {**query, "ordering": "status"}).json()["results"]
    assert len({row["id"] for row in ordered}) == 25
    assert owner_client.get(url, {**query, "subnet_id": str(other.entity_id)}).status_code == 403
    assert owner_client.get(url, {**query, "status": "invalid"}).status_code == 400
    assert owner_client.get(url, {**query, "ordering": "description"}).status_code == 400
    assert owner_client.get(url, {**query, "unknown": "x"}).status_code == 400
    assert "description" in owner_client.get(url).json()["results"][0]
    prefs = reverse(
        "organization-collection-preferences",
        kwargs={"organization_entity_id": organization.entity_id, "feature": "network-wireless"},
    )
    assert (
        owner_client.put(
            prefs, {"columns": ["name", "security"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(prefs).json()["columns"] == ["name", "security"]
    assert owner_client.delete(prefs).json()["page_size"] == 25


@pytest.mark.django_db
def test_wireless_workspace_register_includes_unassigned_records(owner_client, installation):
    organization = _organization(installation, "Wireless register")
    sibling = _organization(installation, "Other wireless register")
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Staff",
        cidr="192.0.2.0/24",
        vrf_entity_id=None,
        vlan_entity_id=None,
        description="",
    )
    linked = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {"ssid": "Linked SSID", "subnet_id": str(subnet.entity_id)},
    )
    unlinked = _post(owner_client, "organization-network-wireless", organization, {"ssid": "Unassigned SSID"})
    other = _post(owner_client, "organization-network-wireless", sibling, {"ssid": "Private sibling SSID"})
    assert linked.status_code == unlinked.status_code == other.status_code == 201
    url = reverse("organization-network-wireless", kwargs={"organization_entity_id": organization.entity_id})
    query = {"summary": "true", "ordering": "network", "page_size": 25}
    result = owner_client.get(url, query).json()
    assert result["count"] == 2
    assert {row["id"] for row in result["results"]} == {linked.json()["id"], unlinked.json()["id"]}
    assert owner_client.get(url, {**query, "association": "assigned"}).json()["results"][0]["id"] == linked.json()["id"]
    unassigned = owner_client.get(url, {**query, "association": "unassigned"}).json()
    assert unassigned["count"] == 1 and unassigned["results"][0]["id"] == unlinked.json()["id"]
    assert owner_client.get(url, {**query, "q": "192.0.2"}).json()["results"][0]["id"] == linked.json()["id"]
    assert (
        owner_client.get(url, {**query, "subnet_id": str(subnet.entity_id), "association": "unassigned"}).json()[
            "count"
        ]
        == 0
    )
    assert owner_client.get(url, {**query, "association": "invalid"}).status_code == 400
    prefs = reverse(
        "organization-collection-preferences",
        kwargs={"organization_entity_id": organization.entity_id, "feature": "wireless-register"},
    )
    assert owner_client.get(prefs).json()["columns"] == ["name", "network", "status", "security"]
    assert (
        owner_client.put(
            prefs, {"columns": ["name", "network"], "page_size": 50}, content_type="application/json"
        ).status_code
        == 200
    )
    assert owner_client.get(prefs).json()["page_size"] == 50
    assert owner_client.delete(prefs).json()["columns"] == ["name", "network", "status", "security"]


@pytest.mark.django_db
def test_wireless_parent_assignment_preserves_facts_and_rejects_foreign_parent(owner_client, installation):
    organization = _organization(installation, "Parent assignment")
    sibling = _organization(installation, "Foreign parent")
    vlan = create_vlan(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Staff",
        vlan_id=20,
        description="",
    )

    def parent(owner, cidr):
        return create_subnet(
            tenant=installation.tenant,
            organization=owner,
            actor_id=installation.owner.id,
            name="Parent",
            cidr=cidr,
            vrf_entity_id=None,
            vlan_entity_id=vlan.entity_id if owner == organization else None,
            description="",
        )

    first = parent(organization, "192.0.2.0/24")
    second = parent(organization, "198.51.100.0/24")
    foreign = parent(sibling, "203.0.113.0/24")
    created = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {
            "ssid": "Staff Wi-Fi",
            "vlan_id": str(vlan.entity_id),
            "description": "Retained facts",
        },
    )
    assert created.status_code == 201
    url = reverse(
        "organization-network-wireless-detail",
        kwargs={
            "organization_entity_id": organization.entity_id,
            "wireless_entity_id": created.json()["id"],
        },
    )
    for selected in (first, second, None):
        response = owner_client.patch(
            url, {"subnet_id": str(selected.entity_id) if selected else None}, content_type="application/json"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subnet_id"] == (str(selected.entity_id) if selected else None)
        assert body["vlan_id"] == str(vlan.entity_id)
        assert body["description"] == "Retained facts" and body["ssid"] == "Staff Wi-Fi"
    denied = owner_client.patch(url, {"subnet_id": str(foreign.entity_id)}, content_type="application/json")
    assert denied.status_code == 400
    assert owner_client.get(url).json()["subnet_id"] is None
    assert owner_client.get(url).json()["vlan_id"] == str(vlan.entity_id)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["site", "vlan"])
def test_wireless_assignment_choices_and_partial_update(owner_client, installation, kind):
    organization = _organization(installation, "Assignment client")
    sibling = _organization(installation, "Private client")

    def create(parent, index):
        common = {
            "tenant": installation.tenant,
            "organization": parent,
            "actor_id": installation.owner.id,
            "name": f"Choice {index:02}",
        }
        if kind == "vlan":
            return create_vlan(**common, vlan_id=index + 100, description="")
        return create_site(
            **common,
            code=f"S{index}",
            address_line_1="",
            address_line_2="",
            city="",
            region="",
            postal_code="",
            country_code="US",
            timezone="UTC",
            phone="",
        )

    choices = [create(organization, index) for index in range(31)]
    foreign = create(sibling, 90)
    url = reverse("organization-network-assignment-choices", kwargs={"organization_entity_id": organization.entity_id})
    response = owner_client.get(url, {"kind": kind, "page_size": 25})
    assert response.status_code == 200
    assert response.json()["count"] == 31
    assert len(response.json()["results"]) == 25
    assert len(owner_client.get(url, {"kind": kind, "page": 2}).json()["results"]) == 6
    assert owner_client.get(url, {"kind": kind, "q": "Choice 30"}).json()["results"][0]["id"] == str(
        choices[30].entity_id
    )
    assert owner_client.get(url, {"kind": kind, "q": "130" if kind == "vlan" else "S30"}).json()["count"] == 1
    assert owner_client.get(url, {"kind": kind, "q": "Choice 90"}).json()["count"] == 0
    assert owner_client.get(url, {"kind": "invalid"}).status_code == 400
    assert owner_client.get(url, {"kind": kind, "page_size": 101}).status_code == 400
    wireless = _post(
        owner_client,
        "organization-network-wireless",
        organization,
        {"ssid": "Assignment SSID", "description": "Keep these settings"},
    )
    assert wireless.status_code == 201
    detail = reverse(
        "organization-network-wireless-detail",
        kwargs={"organization_entity_id": organization.entity_id, "wireless_entity_id": wireless.json()["id"]},
    )
    for identifier in [str(choices[30].entity_id), None]:
        response = owner_client.patch(detail, {f"{kind}_id": identifier}, content_type="application/json")
        assert response.status_code == 200
        assert response.json()[f"{kind}_id"] == identifier
        assert response.json()["description"] == "Keep these settings"
    assert (
        owner_client.patch(detail, {f"{kind}_id": str(foreign.entity_id)}, content_type="application/json").status_code
        == 400
    )
    anonymous = Client()
    assert anonymous.get(url, {"kind": kind}).status_code in (401, 403)
