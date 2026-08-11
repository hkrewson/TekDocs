import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    CommercialContract,
    Entity,
    EntityVisibility,
    InstallationState,
    NetworkCircuit,
    workspace_for_owner,
)
from apps.core.network_circuit_views import CircuitSerializer
from apps.core.network_circuits import create_circuit
from apps.core.network_endpoints import create_interface
from apps.core.network_inventory import create_device
from apps.core.organizations import create_organization
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Circuit MSP",
        owner_email="circuit-owner@example.invalid",
        owner_display_name="Circuit Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name, classification):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=[classification],
    )


def _contract(browser, client, provider):
    return browser.post(
        reverse("organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {
            "name": "Primary internet agreement",
            "provider_id": str(provider.entity_id),
            "kind": "service",
            "status": "active",
            "starts_on": "2026-08-01",
            "ends_on": "2027-09-30",
            "renews_on": "2027-09-01",
            "auto_renew": True,
            "renewal_notice_days": 30,
        },
        content_type="application/json",
    )


def _circuit_payload(provider, contract_id=None):
    return {
        "name": "Headquarters DIA",
        "provider_id": str(provider.entity_id),
        "contract_id": contract_id,
        "service_identifier": "CKT-EXAMPLE-1000",
        "kind": "internet",
        "status": "active",
        "bandwidth_down_mbps": "1000.000",
        "bandwidth_up_mbps": "1000.000",
        "installed_on": "2026-08-05",
        "service_starts_on": "2026-08-10",
        "review_on": "2027-07-01",
        "planned_disconnect_on": None,
        "description": "Primary internet service",
    }


@pytest.mark.django_db
def test_circuit_contract_handoff_and_lifecycle_projection(owner_client, installation):
    client = _organization(installation, "Acme", "client")
    sibling = _organization(installation, "Sibling", "client")
    provider = _organization(installation, "Example Carrier", "vendor")
    contract = _contract(owner_client, client, provider)
    assert contract.status_code == 201
    collection = reverse("organization-network-circuits", kwargs={"organization_entity_id": client.entity_id})
    created = owner_client.post(
        collection, _circuit_payload(provider, contract.json()["id"]), content_type="application/json"
    )
    assert created.status_code == 201
    circuit = created.json()
    assert circuit["provider_name"] == "Example Carrier"
    assert circuit["contract"]["name"] == "Primary internet agreement"
    assert "costs" not in circuit["contract"]
    assert [item["kind"] for item in circuit["lifecycle_events"]] == [
        "review",
        "renewal_notice",
        "renewal",
        "contract_end",
    ]
    blocked_archive = owner_client.delete(
        reverse(
            "organization-commercial-contract-detail",
            kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract.json()["id"]},
        )
    )
    assert blocked_archive.status_code == 400
    assert "network circuit" in str(blocked_archive.json()["error"]["detail"])

    site = create_site(
        tenant=installation.tenant,
        organization=client,
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
    device = create_device(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.id,
        name="Edge router",
        role="router",
        status="active",
        hardware_asset_entity_id=None,
        site_entity_id=site.entity_id,
        location_entity_id=None,
        rack_entity_id=None,
        rack_unit=None,
        rack_units=1,
    )
    interface = create_interface(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.id,
        name="WAN1",
        device_entity_id=device.entity_id,
        kind="physical",
        status="active",
        description="",
    )
    handoff_url = reverse(
        "organization-network-circuit-handoffs",
        kwargs={"organization_entity_id": client.entity_id, "circuit_entity_id": circuit["id"]},
    )
    handoff = owner_client.post(
        handoff_url,
        {
            "name": "Carrier demarc",
            "side": "a",
            "media": "fiber",
            "connector": "LC",
            "provider_reference": "DEMARC-01",
            "site_id": str(site.entity_id),
            "device_id": str(device.entity_id),
            "interface_id": str(interface.entity_id),
        },
        content_type="application/json",
    )
    assert handoff.status_code == 201
    assert handoff.json()["interface_name"] == "WAN1"
    assert owner_client.get(collection).json()["results"][0]["handoffs"][0]["name"] == "Carrier demarc"
    sibling_list = owner_client.get(
        reverse("organization-network-circuits", kwargs={"organization_entity_id": sibling.entity_id})
    )
    assert sibling_list.json()["results"] == []
    hidden = owner_client.get(
        reverse(
            "organization-network-circuit-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "circuit_entity_id": circuit["id"]},
        )
    )
    assert hidden.status_code == 403


@pytest.mark.django_db
def test_contract_provider_and_handoff_workspace_edges_fail_closed(owner_client, installation):
    client = _organization(installation, "Client", "client")
    sibling = _organization(installation, "Foreign", "client")
    provider = _organization(installation, "Carrier", "vendor")
    other_provider = _organization(installation, "Other carrier", "vendor")
    contract = _contract(owner_client, client, provider).json()
    collection = reverse("organization-network-circuits", kwargs={"organization_entity_id": client.entity_id})
    mismatch = owner_client.post(
        collection, _circuit_payload(other_provider, contract["id"]), content_type="application/json"
    )
    assert mismatch.status_code == 400
    created = owner_client.post(collection, _circuit_payload(provider, contract["id"]), content_type="application/json")
    foreign_site = create_site(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        name="Foreign site",
        code="FOREIGN",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    handoff = owner_client.post(
        reverse(
            "organization-network-circuit-handoffs",
            kwargs={"organization_entity_id": client.entity_id, "circuit_entity_id": created.json()["id"]},
        ),
        {"name": "Forged demarc", "side": "a", "media": "fiber", "site_id": str(foreign_site.entity_id)},
        content_type="application/json",
    )
    assert handoff.status_code == 400


@pytest.mark.django_db
def test_circuit_contract_projection_can_be_removed_and_secret_fields_are_rejected(owner_client, installation):
    client = _organization(installation, "Projection client", "client")
    provider = _organization(installation, "Projection carrier", "vendor")
    contract = _contract(owner_client, client, provider).json()
    response = owner_client.post(
        reverse("organization-network-circuits", kwargs={"organization_entity_id": client.entity_id}),
        {**_circuit_payload(provider, contract["id"]), "password": "never-store-this"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert NetworkCircuit.objects.filter(organization=client).count() == 0
    clean = owner_client.post(
        reverse("organization-network-circuits", kwargs={"organization_entity_id": client.entity_id}),
        _circuit_payload(provider, contract["id"]),
        content_type="application/json",
    )
    record = NetworkCircuit.objects.select_related("entity", "provider__entity", "contract__entity").get(
        entity_id=clean.json()["id"]
    )
    projected = CircuitSerializer(record, context={"can_view_contracts": False}).data
    assert "contract" not in projected
    assert all(
        item["kind"] not in {"renewal", "renewal_notice", "contract_end"} for item in projected["lifecycle_events"]
    )


@pytest.mark.django_db(transaction=True)
def test_postgres_circuit_guard_rejects_direct_cross_workspace_contract(installation):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    client = _organization(installation, "Guard client", "client")
    sibling = _organization(installation, "Guard sibling", "client")
    provider = _organization(installation, "Guard carrier", "vendor")
    sibling_contract_response = Client(enforce_csrf_checks=False)
    sibling_contract_response.force_login(installation.owner)
    sibling_contract = _contract(sibling_contract_response, sibling, provider).json()
    circuit = create_circuit(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.id,
        name="Guard circuit",
        provider_entity_id=provider.entity_id,
        contract_entity_id=None,
        service_identifier="GUARD-1",
        kind="internet",
        status="active",
        bandwidth_down_mbps=None,
        bandwidth_up_mbps=None,
        installed_on=None,
        service_starts_on=None,
        review_on=None,
        planned_disconnect_on=None,
        description="",
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        NetworkCircuit.objects.filter(pk=circuit.pk).update(
            contract_id=CommercialContract.objects.get(entity_id=sibling_contract["id"]).id
        )


@pytest.mark.django_db
def test_circuit_entity_scope_cannot_be_forged(installation):
    client = _organization(installation, "Entity client", "client")
    provider = _organization(installation, "Entity carrier", "vendor")
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=client),
        organization=client,
        entity_type="network_device",
        display_name="Wrong kind",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    record = NetworkCircuit(
        tenant=installation.tenant,
        organization=client,
        entity=entity,
        provider=provider,
        service_identifier="WRONG-1",
        kind="internet",
        status="active",
    )
    with pytest.raises(ValidationError, match="entity identity"):
        record.full_clean()
