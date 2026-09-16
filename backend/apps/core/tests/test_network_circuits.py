import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.models import (
    AuditEvent,
    CommercialContract,
    Entity,
    EntityVisibility,
    InstallationState,
    NetworkCircuit,
    Organization,
    OrganizationClassification,
    Tenant,
    workspace_for_owner,
)
from apps.core.network_circuit_views import CircuitSerializer
from apps.core.network_circuits import create_circuit, create_handoff
from apps.core.network_endpoints import create_interface
from apps.core.network_inventory import create_device
from apps.core.organizations import create_organization
from apps.core.sites import create_site
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset


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
    hardware_asset = create_network_hardware_asset(installation=installation, organization=client, name="Edge router")
    device = create_device(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.id,
        name="Edge router",
        role="router",
        status="active",
        hardware_asset_entity_id=hardware_asset.entity_id,
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
    detail_url = reverse(
        "organization-network-circuit-handoff-detail",
        kwargs={
            "organization_entity_id": client.entity_id,
            "circuit_entity_id": circuit["id"],
            "handoff_entity_id": handoff.json()["id"],
        },
    )
    edited = owner_client.patch(
        detail_url, {"connector": "SC", "description": "Verified demarc"}, content_type="application/json"
    )
    assert edited.status_code == 200
    assert edited.json()["connector"] == "SC"
    assert edited.json()["site_id"] == str(site.entity_id)
    assert edited.json()["interface_id"] == str(interface.entity_id)
    duplicate = owner_client.post(
        handoff_url,
        {
            "name": "Conflicting demarc",
            "side": "z",
            "media": "fiber",
            "device_id": str(device.entity_id),
            "interface_id": str(interface.entity_id),
        },
        content_type="application/json",
    )
    assert duplicate.status_code == 400
    mismatch = owner_client.patch(detail_url, {"device_id": None}, content_type="application/json")
    assert mismatch.status_code == 400
    assert owner_client.get(detail_url).json()["device_id"] == str(device.entity_id)
    cleared = owner_client.patch(detail_url, {"device_id": None, "interface_id": None}, content_type="application/json")
    assert cleared.status_code == 200
    assert cleared.json()["device_id"] is None and cleared.json()["interface_id"] is None
    assert cleared.json()["site_id"] == str(site.entity_id)
    assert cleared.json()["description"] == "Verified demarc"
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


@pytest.mark.django_db
def test_circuit_summary_search_paging_handoffs_and_legacy_compatibility(owner_client, installation):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = _organization(installation, "Layout client", "client")
    sibling = _organization(installation, "Layout sibling", "client")
    provider = _organization(installation, "Layout carrier", "vendor")
    collection = reverse("organization-network-circuits", kwargs={"organization_entity_id": client.entity_id})
    records = []
    for index in range(31):
        payload = {
            **_circuit_payload(provider),
            "name": f"Circuit {index:02}",
            "service_identifier": f"SERVICE-{index:02}",
        }
        created = owner_client.post(collection, payload, content_type="application/json")
        assert created.status_code == 201
        records.append(created.json())
    with CaptureQueriesContext(connection) as queries:
        summary = owner_client.get(collection, {"summary": "true", "page_size": 25, "ordering": "name"}).json()
    assert summary["count"] == 31 and summary["has_more"]
    assert len(summary["results"]) == 25
    assert not {"description", "handoffs", "contract", "lifecycle_events"} & summary["results"][0].keys()
    assert not any('FROM "core_networkcircuithandoff"' in query["sql"] for query in queries)
    assert (
        owner_client.get(collection, {"summary": "true", "q": "SERVICE-30"}).json()["results"][0]["id"]
        == records[-1]["id"]
    )
    page = owner_client.get(collection, {"summary": "true", "page_size": 25, "page": 2, "ordering": "name"}).json()
    assert len(page["results"]) == 6 and not page["has_more"]
    assert owner_client.get(collection, {"status": "disconnected"}).json()["count"] == 0
    assert owner_client.get(collection, {"kind": "voice"}).json()["count"] == 0
    tied = owner_client.get(collection, {"ordering": "status"}).json()["results"]
    assert [row["id"] for row in tied] == sorted(row["id"] for row in tied)
    for query in ({"ordering": "contract"}, {"status": "invalid"}, {"page_size": 101}):
        assert owner_client.get(collection, query).status_code == 400
    circuit_id = records[0]["id"]
    detail = reverse(
        "organization-network-circuit-detail",
        kwargs={"organization_entity_id": client.entity_id, "circuit_entity_id": circuit_id},
    )
    handoffs = reverse(
        "organization-network-circuit-handoffs",
        kwargs={"organization_entity_id": client.entity_id, "circuit_entity_id": circuit_id},
    )
    with CaptureQueriesContext(connection) as empty_detail_queries:
        assert owner_client.get(detail).status_code == 200
    for index in range(31):
        created = owner_client.post(
            handoffs,
            {"name": f"Handoff {index:02}", "side": "a", "media": "fiber", "provider_reference": f"DEMARC-{index:02}"},
            content_type="application/json",
        )
        assert created.status_code == 201
    last_id = created.json()["id"]
    assert len(owner_client.get(handoffs).json()) == 31
    with CaptureQueriesContext(connection) as populated_detail_queries:
        assert len(owner_client.get(detail).json()["handoffs"]) == 31
    assert len(populated_detail_queries) <= len(empty_detail_queries) + 2
    with CaptureQueriesContext(connection) as queries:
        selected = owner_client.get(detail, {"include_handoffs": "false"}).json()
    assert "handoffs" not in selected and "lifecycle_events" in selected
    assert not any('FROM "core_networkcircuithandoff"' in query["sql"] for query in queries)
    page = owner_client.get(handoffs, {"paginated": "true", "page_size": 25, "page": 2}).json()
    assert page["count"] == 31 and len(page["results"]) == 6
    found = owner_client.get(handoffs, {"paginated": "true", "q": "DEMARC-30"}).json()
    assert [row["id"] for row in found["results"]] == [last_id]
    assert owner_client.get(handoffs, {"paginated": "true", "side": "z"}).json()["count"] == 0
    assert owner_client.get(handoffs, {"paginated": "true", "ordering": "invalid"}).status_code == 400
    child_detail = reverse(
        "organization-network-circuit-handoff-detail",
        kwargs={
            "organization_entity_id": client.entity_id,
            "circuit_entity_id": circuit_id,
            "handoff_entity_id": last_id,
        },
    )
    assert owner_client.get(child_detail).json()["circuit_id"] == circuit_id
    for organization_id, parent_id in [(sibling.entity_id, circuit_id), (client.entity_id, records[1]["id"])]:
        hidden = reverse(
            "organization-network-circuit-handoff-detail",
            kwargs={
                "organization_entity_id": organization_id,
                "circuit_entity_id": parent_id,
                "handoff_entity_id": last_id,
            },
        )
        assert owner_client.get(hidden).status_code == 403
    saved = owner_client.patch(detail, {"description": "Changed service notes"}, content_type="application/json")
    assert saved.status_code == 200
    assert saved.json()["provider_id"] == records[0]["provider_id"]
    assert saved.json()["status"] == "active"
    assert len(saved.json()["handoffs"]) == 31


@pytest.mark.django_db
def test_paginated_circuit_choices_search_retention_and_boundaries(owner_client, installation, monkeypatch):
    client = _organization(installation, "Choice client", "client")
    sibling = _organization(installation, "Choice sibling", "client")
    providers = [_organization(installation, f"Carrier {index:03}", "vendor") for index in range(101)]
    url = reverse("organization-network-circuit-choices", kwargs={"organization_entity_id": client.entity_id})
    legacy = owner_client.get(url)
    assert legacy.status_code == 200
    assert len(legacy.json()["providers"]) == 100
    first = owner_client.get(url, {"choice": "providers"}).json()
    assert (first["count"], first["page_size"], len(first["results"]), first["has_more"]) == (101, 25, 25, True)
    last = owner_client.get(url, {"choice": "providers", "page": 5}).json()
    assert [item["id"] for item in last["results"]] == [str(providers[-1].entity_id)]
    assert last["has_more"] is False
    searched = owner_client.get(
        url,
        {
            "choice": "providers",
            "q": "Carrier 100",
            "selected_id": str(providers[0].entity_id),
        },
    ).json()
    assert searched["results"] == last["results"]
    assert searched["selected"]["id"] == str(providers[0].entity_id)
    assert searched["count"] == 1
    assert owner_client.get(url, {"choice": "providers", "q": "missing"}).json()["results"] == []
    assert (
        owner_client.get(url, {"choice": "providers", "selected_id": str(client.entity_id)}).json()["selected"] is None
    )
    for invalid in (
        {"page": 2},
        {"choice": "sites"},
        {"choice": "providers", "page_size": 101},
        {"choice": "providers", "provider_id": str(providers[0].entity_id)},
        {"choice": "contracts", "unknown": "x"},
    ):
        assert owner_client.get(url, invalid).status_code == 400

    contract = _contract(owner_client, client, providers[0]).json()
    foreign = _contract(owner_client, sibling, providers[0]).json()
    other = _contract(owner_client, client, providers[1]).json()
    scoped = owner_client.get(url, {"choice": "contracts", "provider_id": str(providers[0].entity_id)}).json()
    assert [item["id"] for item in scoped["results"]] == [contract["id"]]
    assert scoped["results"][0]["provider_id"] == str(providers[0].entity_id)
    for unavailable in (foreign["id"], other["id"]):
        response = owner_client.get(
            url,
            {
                "choice": "contracts",
                "provider_id": str(providers[0].entity_id),
                "selected_id": unavailable,
            },
        ).json()
        assert response["selected"] is None
    retained = owner_client.get(url, {"choice": "contracts", "q": "missing", "selected_id": contract["id"]}).json()
    assert retained["results"] == []
    assert retained["selected"]["id"] == contract["id"]
    # Equal names still have deterministic paging; contracts beyond page one remain searchable/selectable.
    from apps.core.commercial import create_contract

    for _index in range(26):
        create_contract(
            tenant=installation.tenant,
            organization=client,
            actor_id=installation.owner.id,
            values={"name": "Repeated agreement", "provider_id": providers[0].entity_id, "kind": "service"},
        )
    tied = owner_client.get(url, {"choice": "contracts", "q": "Repeated", "page_size": 25}).json()
    final = owner_client.get(url, {"choice": "contracts", "q": "Repeated", "page": 2, "page_size": 25}).json()
    ids = [item["id"] for item in tied["results"] + final["results"]]
    assert len(ids) == 26 and ids == sorted(ids) and len(set(ids)) == 26
    assert tied["count"] == 26 and final["has_more"] is False
    foreign_tenant = Tenant.objects.create(name="Foreign choice MSP", slug="foreign-choice-msp")
    foreign_anchor = Entity.objects.create_owned(
        tenant=foreign_tenant,
        entity_type="organization",
        display_name="Foreign carrier",
    )
    foreign_provider = Organization.objects.create(tenant=foreign_tenant, entity=foreign_anchor)
    OrganizationClassification.objects.create(tenant=foreign_tenant, organization=foreign_provider, kind="vendor")
    hidden_provider = owner_client.get(
        url,
        {
            "choice": "providers",
            "q": "Foreign carrier",
            "selected_id": str(foreign_provider.entity_id),
        },
    ).json()
    assert hidden_provider["results"] == [] and hidden_provider["selected"] is None
    # Policy projection must apply to counts and retained selections as well as rows.
    monkeypatch.setattr("apps.core.network_circuit_views._can_view_contracts", lambda workspace: False)
    assert owner_client.get(url, {"choice": "contracts", "selected_id": contract["id"]}).status_code == 403
    assert owner_client.get(url, {"choice": "providers"}).json()["can_view_contracts"] is False
    assert owner_client.get(url).json()["contracts"] == []
    assert Client().get(url, {"choice": "providers"}).status_code == 403


@pytest.mark.django_db
def test_handoff_history_is_bounded_parent_scoped_and_authorized(owner_client, installation, monkeypatch):
    organization = _organization(installation, "History client", "client")
    sibling = _organization(installation, "History sibling", "client")
    provider = _organization(installation, "History carrier", "vendor")
    circuit = create_circuit(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="History circuit",
        provider_entity_id=provider.entity_id,
        contract_entity_id=None,
        service_identifier="HISTORY",
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

    def handoff(name):
        return create_handoff(
            circuit=circuit,
            actor_id=installation.owner.id,
            name=name,
            side="a",
            media="fiber",
            connector="",
            provider_reference="",
            site_entity_id=None,
            location_entity_id=None,
            device_entity_id=None,
            interface_entity_id=None,
            description="",
        )

    selected, other = handoff("Selected"), handoff("Other")
    for _ in range(30):
        AuditEvent.objects.create(
            tenant=installation.tenant,
            actor=installation.owner,
            entity_id=circuit.entity_id,
            action="network_circuit.handoff_updated",
            metadata={"handoff_id": str(selected.entity_id)},
        )
    url = reverse("organization-activity-list", kwargs={"organization_entity_id": organization.entity_id})
    query = {"entity_id": str(circuit.entity_id), "handoff_id": str(selected.entity_id), "page_size": 25}
    first = owner_client.get(url, query).json()
    second = owner_client.get(url, {**query, "page": 2}).json()
    assert first["count"] == 31 and first["has_more"] and len(first["results"]) == 25
    assert len(second["results"]) == 6 and not second["has_more"]
    assert {row["id"] for row in first["results"]}.isdisjoint(row["id"] for row in second["results"])
    assert first == owner_client.get(url, query).json()
    assert all("metadata" not in row for row in first["results"])
    assert owner_client.get(url, {**query, "handoff_id": str(other.entity_id)}).json()["count"] == 1
    assert owner_client.get(url, {"handoff_id": str(selected.entity_id)}).status_code == 400
    assert owner_client.get(url, {**query, "handoff_id": ""}).status_code == 400
    assert owner_client.get(url, {**query, "entity_id": str(provider.entity_id)}).status_code == 403
    sibling_url = reverse("organization-activity-list", kwargs={"organization_entity_id": sibling.entity_id})
    assert owner_client.get(sibling_url, query).status_code == 403
    foreign_tenant = Tenant.objects.create(name="Foreign handoff MSP", slug="foreign-handoff")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant, entity_type="organization", display_name="Foreign client"
    )
    Organization.objects.create(tenant=foreign_tenant, entity=foreign_entity, legal_name="Foreign client")
    foreign_url = reverse("organization-activity-list", kwargs={"organization_entity_id": foreign_entity.id})
    assert owner_client.get(foreign_url, query).status_code == 404
    reader = User.objects.create_user(email="handoff-reader@example.invalid", password=secrets.token_urlsafe(24))
    membership = TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant, organization=organization, membership=membership, created_by=installation.owner
    )
    browser = Client()
    browser.force_login(reader)
    assert browser.get(url, query).status_code == 403

    from rest_framework.exceptions import PermissionDenied

    from apps.accounts.policy import PermissionKey
    from apps.core import activity_views

    original = activity_views.require_permission

    def without_networks(user, permission, **kwargs):
        if permission == PermissionKey.NETWORKS_VIEW:
            raise PermissionDenied("Network access denied.")
        return original(user, permission, **kwargs)

    monkeypatch.setattr(activity_views, "require_permission", without_networks)
    assert owner_client.get(url, query).status_code == 403
