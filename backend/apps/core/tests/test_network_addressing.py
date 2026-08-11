import ipaddress
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
from apps.core.models import Entity, EntityVisibility, InstallationState, NetworkSubnet, Tenant, workspace_for_owner
from apps.core.network_addressing import NetworkAddressingError, canonical_network, create_subnet, networks_overlap
from apps.core.organizations import create_organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Addressing MSP",
        owner_email="addressing-owner@example.invalid",
        owner_display_name="Addressing Owner",
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


def _post(browser, route_name, organization, payload):  # type: ignore[no-untyped-def]
    return browser.post(
        reverse(route_name, kwargs={"organization_entity_id": organization.entity_id}),
        payload,
        content_type="application/json",
    )


@pytest.mark.django_db
def test_vrf_vlan_subnet_crud_and_overlap_policy(owner_client, installation):
    organization = _organization(installation, "Acme")
    sibling = _organization(installation, "Sibling")
    vrf = _post(
        owner_client,
        "organization-network-vrfs",
        organization,
        {"name": "Guest", "route_distinguisher": "65000:20", "description": "Isolated guest routes"},
    )
    assert vrf.status_code == 201
    vlan = _post(
        owner_client,
        "organization-network-vlans",
        organization,
        {"name": "Guest", "vlan_id": 20, "description": "Guest access"},
    )
    assert vlan.status_code == 201
    subnet = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {
            "name": "Guest Wi-Fi",
            "cidr": "192.0.2.0/24",
            "vrf_id": vrf.json()["id"],
            "vlan_id": vlan.json()["id"],
            "description": "",
        },
    )
    assert subnet.status_code == 201
    assert subnet.json()["address_family"] == 4
    assert subnet.json()["vrf_name"] == "Guest"
    assert subnet.json()["vlan_number"] == 20

    overlap = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {"name": "Overlap", "cidr": "192.0.2.128/25", "vrf_id": vrf.json()["id"], "vlan_id": None, "description": ""},
    )
    assert overlap.status_code == 400
    assert "overlap" in overlap.content.decode().lower()

    second_vrf = _post(
        owner_client,
        "organization-network-vrfs",
        organization,
        {"name": "Tenant B", "route_distinguisher": "", "description": ""},
    )
    allowed = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {
            "name": "Reused range",
            "cidr": "192.0.2.0/24",
            "vrf_id": second_vrf.json()["id"],
            "vlan_id": None,
            "description": "",
        },
    )
    assert allowed.status_code == 201

    hidden = owner_client.get(
        reverse(
            "organization-network-subnet-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "subnet_entity_id": subnet.json()["id"]},
        )
    )
    assert hidden.status_code == 403
    sibling_list = owner_client.get(
        reverse("organization-network-subnets", kwargs={"organization_entity_id": sibling.entity_id})
    )
    assert sibling_list.status_code == 200
    assert sibling_list.json()["count"] == 0


@pytest.mark.django_db
def test_default_namespace_overlap_and_canonical_validation(owner_client, installation):
    organization = _organization(installation, "Default Route")
    first = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {"name": "LAN", "cidr": "10.10.0.0/16", "vrf_id": None, "vlan_id": None, "description": ""},
    )
    assert first.status_code == 201
    overlap = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {"name": "Child", "cidr": "10.10.1.0/24", "vrf_id": None, "vlan_id": None, "description": ""},
    )
    assert overlap.status_code == 400
    noncanonical = _post(
        owner_client,
        "organization-network-subnets",
        organization,
        {"name": "Host bits", "cidr": "10.20.1.9/24", "vrf_id": None, "vlan_id": None, "description": ""},
    )
    assert noncanonical.status_code == 400
    assert "10.20.1.0/24" in noncanonical.content.decode()
    assert NetworkSubnet.objects.count() == 1


@given(st.ip_addresses(v=4), st.integers(min_value=0, max_value=32))
def test_canonical_ipv4_property(address, prefix):  # type: ignore[no-untyped-def]
    expected = ipaddress.ip_network(f"{address}/{prefix}", strict=False).with_prefixlen
    assert canonical_network(expected).with_prefixlen == expected


@given(st.ip_addresses(v=6), st.integers(min_value=0, max_value=128))
def test_canonical_ipv6_property(address, prefix):  # type: ignore[no-untyped-def]
    expected = ipaddress.ip_network(f"{address}/{prefix}", strict=False).with_prefixlen
    assert canonical_network(expected).with_prefixlen == expected


def test_overlap_helper_is_family_aware_and_rejects_host_bits():
    assert networks_overlap("10.0.0.0/8", "10.1.0.0/16")
    assert not networks_overlap("10.0.0.0/8", "2001:db8::/32")
    with pytest.raises(NetworkAddressingError, match="network boundary"):
        canonical_network("192.0.2.4/24")


@pytest.mark.django_db(transaction=True)
def test_concurrent_overlapping_subnets_serialize_in_default_namespace(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Advisory-lock concurrency certification requires PostgreSQL")
    organization = _organization(installation, "Concurrent prefixes")
    barrier = threading.Barrier(2)

    def create(name, cidr):  # type: ignore[no-untyped-def]
        close_old_connections()
        try:
            tenant = Tenant.objects.get(pk=installation.tenant.id)
            current_organization = tenant.organizations.get(pk=organization.id)
            barrier.wait(timeout=5)
            create_subnet(
                tenant=tenant,
                organization=current_organization,
                actor_id=installation.owner.id,
                name=name,
                cidr=cidr,
                vrf_entity_id=None,
                vlan_entity_id=None,
                description="",
            )
            return "created"
        except NetworkAddressingError:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(
            executor.map(lambda args: create(*args), (("Parent", "172.20.0.0/16"), ("Child", "172.20.1.0/24")))
        )
    assert outcomes == ["created", "rejected"]
    assert NetworkSubnet.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgres_guard_rejects_noncanonical_and_overlapping_direct_subnet_writes(installation):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("Database guard requires PostgreSQL")
    organization = _organization(installation, "Direct guard")
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
        organization=organization,
        entity_type="network_subnet",
        display_name="Forged",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkSubnet.objects.create(
            tenant=installation.tenant,
            organization=organization,
            entity=entity,
            cidr="192.0.2.9/24",
            address_family=4,
        )

    create_subnet(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Existing",
        cidr="192.0.2.0/24",
        vrf_entity_id=None,
        vlan_entity_id=None,
        description="",
    )
    overlapping_entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
        organization=organization,
        entity_type="network_subnet",
        display_name="Direct overlap",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkSubnet.objects.create(
            tenant=installation.tenant,
            organization=organization,
            entity=overlapping_entity,
            cidr="192.0.2.128/25",
            address_family=4,
        )
