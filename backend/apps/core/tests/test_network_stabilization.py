import secrets
import time

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    Entity,
    EntityVisibility,
    InstallationState,
    NetworkIPAddress,
    NetworkSubnet,
    Organization,
    OrganizationClassification,
    Workspace,
    WorkspaceKind,
    workspace_for_owner,
    workspace_identity_uuid,
)

REFERENCE_CLIENTS = 100
REFERENCE_NETWORK_ENTITIES = 10_000
P95_TARGET_SECONDS = 0.5
SEARCH_QUERY_BUDGET = 32


def _p95(samples: list[float]) -> float:
    return sorted(samples)[max(0, round(0.95 * len(samples) + 0.5) - 1)]


def _reference_fixture():  # type: ignore[no-untyped-def]
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Network stabilization MSP",
        owner_email="network-stabilization-owner@example.invalid",
        owner_display_name="Network Stabilization Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    msp_workspace = workspace_for_owner(tenant=result.tenant, organization=None)
    anchors = [
        Entity(
            tenant=result.tenant,
            workspace=msp_workspace,
            entity_type="organization",
            display_name=f"Network Client {index:03d}",
        )
        for index in range(REFERENCE_CLIENTS)
    ]
    Entity.objects.bulk_create(anchors)
    organizations = [
        Organization(tenant=result.tenant, entity=entity, legal_name=f"{entity.display_name}, Inc.")
        for entity in anchors
    ]
    Organization.objects.bulk_create(organizations)
    workspaces = [
        Workspace(
            id=workspace_identity_uuid(tenant_id=result.tenant.id, organization_id=organization.id),
            tenant=result.tenant,
            kind=WorkspaceKind.ORGANIZATION,
            organization=organization,
        )
        for organization in organizations
    ]
    Workspace.objects.bulk_create(workspaces)
    OrganizationClassification.objects.bulk_create(
        [
            OrganizationClassification(tenant=result.tenant, organization=organization, kind="client")
            for organization in organizations
        ]
    )

    subnet_entities = [
        Entity(
            tenant=result.tenant,
            organization=organization,
            workspace=workspaces[index],
            entity_type="network_subnet",
            display_name=f"Client {index:03d} reference subnet",
            visibility=EntityVisibility.MSP_PRIVATE,
        )
        for index, organization in enumerate(organizations)
    ]
    Entity.objects.bulk_create(subnet_entities)
    subnets = [
        NetworkSubnet(
            tenant=result.tenant,
            organization=organization,
            entity=subnet_entities[index],
            cidr=f"10.{index}.0.0/16",
            address_family=4,
            description="Scale reference subnet",
        )
        for index, organization in enumerate(organizations)
    ]
    NetworkSubnet.objects.bulk_create(subnets)

    ip_entities = []
    ip_addresses = []
    addresses_per_client = (REFERENCE_NETWORK_ENTITIES - REFERENCE_CLIENTS) // REFERENCE_CLIENTS
    for organization_index, organization in enumerate(organizations):
        for address_index in range(addresses_per_client):
            address = f"10.{organization_index}.{address_index // 254}.{address_index % 254 + 1}"
            entity = Entity(
                tenant=result.tenant,
                organization=organization,
                workspace=workspaces[organization_index],
                entity_type="network_ip_address",
                display_name=address,
                visibility=EntityVisibility.MSP_PRIVATE,
            )
            ip_entities.append(entity)
            ip_addresses.append(
                NetworkIPAddress(
                    tenant=result.tenant,
                    organization=organization,
                    entity=entity,
                    subnet=subnets[organization_index],
                    address=address,
                    address_family=4,
                    status="active",
                    dns_name=f"host-{address_index:03d}.client-{organization_index:03d}.example.invalid",
                    description="Scale reference address",
                )
            )
    Entity.objects.bulk_create(ip_entities, batch_size=1_000)
    NetworkIPAddress.objects.bulk_create(ip_addresses, batch_size=1_000)
    return result, organizations


@pytest.mark.django_db(transaction=True)
def test_network_search_export_scale_and_isolation_stabilization():
    if connection.vendor != "postgresql":
        pytest.skip("Network scale validation requires PostgreSQL")

    result, organizations = _reference_fixture()
    assert Entity.objects.filter(tenant=result.tenant, entity_type__startswith="network_").count() == 10_000
    client = Client()
    client.force_login(result.owner)
    selected = organizations[42]
    search_url = reverse("organization-network-search", kwargs={"organization_entity_id": selected.entity_id})

    response = client.get(search_url, {"q": "client-042", "page_size": 25})
    assert response.status_code == 200
    assert response.json()["count"] == 99
    assert all(item["name"].startswith("10.42.") for item in response.json()["results"])
    assert "client-041" not in response.content.decode()

    samples = []
    for page in (1, 2, 4, 1, 2, 4, 1, 4):
        started = time.perf_counter()
        response = client.get(search_url, {"page": page, "page_size": 25})
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
        assert response.json()["count"] == 100
    assert _p95(samples) < P95_TARGET_SECONDS

    with CaptureQueriesContext(connection) as queries:
        response = client.get(search_url, {"q": "10.42.0.50", "page_size": 25})
    assert response.status_code == 200
    assert len(queries) <= SEARCH_QUERY_BUDGET

    export_response = client.get(
        reverse("organization-network-export", kwargs={"organization_entity_id": selected.entity_id})
    )
    assert export_response.status_code == 200
    assert export_response.streaming is True
    exported = b"".join(export_response.streaming_content).decode()
    assert exported.count("tekdocs.networks.v1") == 100
    assert "10.42.0.50" in exported
    assert "client-041" not in exported

    msp_search = client.get(reverse("msp-network-search"), {"page_size": 25})
    assert msp_search.status_code == 200
    assert msp_search.json()["count"] == 0
