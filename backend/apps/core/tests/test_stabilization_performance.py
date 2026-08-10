import secrets
import time

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.policy import PermissionKey, require_permission
from apps.core.documents import create_document, markdown_checksum, revisions_for_document
from apps.core.models import (
    BlockRevision,
    Entity,
    EntityLink,
    InstallationState,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    PersonAssociation,
    Site,
    Workspace,
    WorkspaceKind,
    workspace_for_owner,
    workspace_identity_uuid,
)
from apps.core.organization_views import _organizations_for_context
from apps.core.people import query_people
from apps.core.relationships import relationships_for_entity, search_entities
from apps.core.sites import query_sites
from apps.core.workspaces import resolve_organization_workspace, search_organization_workspaces

REFERENCE_ORGANIZATIONS = 100
REFERENCE_ENTITIES = 10_000
REFERENCE_PEOPLE = 250
REFERENCE_SITES = 50
REFERENCE_LOCATIONS_PER_SITE = 5
REFERENCE_DOCUMENT_REVISIONS = 2_500
P95_TARGET_SECONDS = 0.5


def _p95(samples: list[float]) -> float:
    return sorted(samples)[max(0, round(0.95 * len(samples) + 0.5) - 1)]


def _timed_requests(client: Client, url: str, params: dict[str, object] | None = None) -> float:
    response = client.get(url, params or {})
    assert response.status_code == 200

    samples = []
    for _ in range(8):
        started = time.perf_counter()
        response = client.get(url, params or {})
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
    return _p95(samples)


def _query_count(operation):  # type: ignore[no-untyped-def]
    with CaptureQueriesContext(connection) as queries:
        operation()
    return len(queries)


def _create_reference_fixture():  # type: ignore[no-untyped-def]
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Stabilization Reference MSP",
        owner_email="stabilization-owner@example.invalid",
        owner_display_name="Stabilization Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    msp_workspace = workspace_for_owner(tenant=result.tenant, organization=None)
    anchors = [
        Entity(
            tenant=result.tenant,
            workspace=msp_workspace,
            entity_type="organization",
            display_name=f"Reference Client {index:03d}",
        )
        for index in range(REFERENCE_ORGANIZATIONS)
    ]
    Entity.objects.bulk_create(anchors)
    organizations = [
        Organization(
            tenant=result.tenant,
            entity=anchor,
            legal_name=f"{anchor.display_name}, LLC",
        )
        for anchor in anchors
    ]
    Organization.objects.bulk_create(organizations)
    Workspace.objects.bulk_create(
        [
            Workspace(
                id=workspace_identity_uuid(tenant_id=result.tenant.id, organization_id=organization.id),
                tenant=result.tenant,
                kind=WorkspaceKind.ORGANIZATION,
                organization=organization,
            )
            for organization in organizations
        ]
    )
    organization_workspaces = {
        workspace.organization_id: workspace
        for workspace in Workspace.objects.filter(tenant=result.tenant, kind=WorkspaceKind.ORGANIZATION)
    }
    OrganizationClassification.objects.bulk_create(
        [
            OrganizationClassification(tenant=result.tenant, organization=organization, kind="client")
            for organization in organizations
        ]
    )

    distributed_entities = [
        Entity(
            tenant=result.tenant,
            organization=organizations[index % REFERENCE_ORGANIZATIONS],
            workspace=organization_workspaces[organizations[index % REFERENCE_ORGANIZATIONS].id],
            entity_type="reference_record",
            display_name=f"Reference Record {index:05d}",
        )
        for index in range(REFERENCE_ENTITIES)
    ]
    Entity.objects.bulk_create(distributed_entities, batch_size=1_000)

    selected = organizations[0]
    person_entities = [
        Entity(
            tenant=result.tenant,
            workspace=msp_workspace,
            entity_type="person",
            display_name=f"Reference Person {index:03d}",
        )
        for index in range(REFERENCE_PEOPLE)
    ]
    Entity.objects.bulk_create(person_entities)
    people = [
        Person(
            tenant=result.tenant,
            entity=entity,
            preferred_name=f"Person {index:03d}",
            email=f"person-{index:03d}@example.invalid",
        )
        for index, entity in enumerate(person_entities)
    ]
    Person.objects.bulk_create(people)
    PersonAssociation.objects.bulk_create(
        [
            PersonAssociation(
                tenant=result.tenant,
                organization=selected,
                person=person,
                kind="contact",
                role="Technical contact" if index % 2 == 0 else "Office contact",
            )
            for index, person in enumerate(people)
        ]
    )

    site_entities = [
        Entity(
            tenant=result.tenant,
            organization=selected,
            workspace=organization_workspaces[selected.id],
            entity_type="site",
            display_name=f"Reference Site {index:03d}",
        )
        for index in range(REFERENCE_SITES)
    ]
    Entity.objects.bulk_create(site_entities)
    sites = [
        Site(
            tenant=result.tenant,
            organization=selected,
            entity=entity,
            code=f"SITE-{index:03d}",
            city="Madison",
        )
        for index, entity in enumerate(site_entities)
    ]
    Site.objects.bulk_create(sites)
    location_entities = [
        Entity(
            tenant=result.tenant,
            organization=selected,
            workspace=organization_workspaces[selected.id],
            entity_type="location",
            display_name=f"Site {site_index:03d} Room {location_index:02d}",
        )
        for site_index in range(REFERENCE_SITES)
        for location_index in range(REFERENCE_LOCATIONS_PER_SITE)
    ]
    Entity.objects.bulk_create(location_entities)
    Location.objects.bulk_create(
        [
            Location(
                tenant=result.tenant,
                organization=selected,
                entity=entity,
                site=sites[index // REFERENCE_LOCATIONS_PER_SITE],
                kind="room",
                code=f"R-{index % REFERENCE_LOCATIONS_PER_SITE:02d}",
            )
            for index, entity in enumerate(location_entities)
        ]
    )
    links = []
    for index in range(25):
        endpoints = sorted(
            (distributed_entities[index], distributed_entities[index + REFERENCE_ORGANIZATIONS]),
            key=lambda entity: entity.id.int,
        )
        links.append(
            EntityLink(
                tenant=result.tenant,
                source=endpoints[0],
                target=endpoints[1],
                link_type="related_to",
            )
        )
    EntityLink.objects.bulk_create(links)
    document = create_document(
        tenant=result.tenant,
        organization=None,
        actor_id=result.owner.id,
        title="Long-history reference runbook",
        markdown="Revision 1",
    )
    block = document.placements.select_related("block__current_revision").get(parent__isnull=True, position=0).block
    parent = block.current_revision
    revisions = []
    for revision_number in range(2, REFERENCE_DOCUMENT_REVISIONS + 1):
        markdown = f"Revision {revision_number}"
        parent = BlockRevision(
            tenant=result.tenant,
            organization=None,
            block=block,
            parent=parent,
            revision_number=revision_number,
            markdown=markdown,
            checksum=markdown_checksum(markdown),
            created_by=result.owner,
        )
        revisions.append(parent)
    BlockRevision.objects.bulk_create(revisions, batch_size=100)
    block.current_revision = parent
    block.save(update_fields=("current_revision", "updated_at"))
    return result, selected, distributed_entities[0], document


@pytest.mark.django_db(transaction=True)
def test_reference_dataset_read_paths_meet_query_and_latency_budgets():
    if connection.vendor != "postgresql":
        pytest.skip("Reference performance certification requires PostgreSQL")

    result, selected, linked_entity, document = _create_reference_fixture()
    assert Entity.objects.filter(tenant=result.tenant).count() >= REFERENCE_ENTITIES

    client = Client()
    client.force_login(result.owner)
    paths = (
        (reverse("workspace-organization-search"), {"q": "Reference", "page_size": 25}),
        (reverse("organization-list-create"), {}),
        (
            reverse("organization-people-list-create", kwargs={"organization_entity_id": selected.entity_id}),
            {"q": "Reference", "page_size": 25},
        ),
        (
            reverse("organization-site-list-create", kwargs={"organization_entity_id": selected.entity_id}),
            {"q": "Reference"},
        ),
        (
            reverse("organization-entity-search", kwargs={"organization_entity_id": selected.entity_id}),
            {"q": "Reference", "page_size": 25},
        ),
        (
            reverse(
                "organization-entity-relationship-list-create",
                kwargs={"organization_entity_id": selected.entity_id, "entity_id": linked_entity.id},
            ),
            {},
        ),
        (
            reverse("msp-document-revision-list", kwargs={"document_entity_id": document.entity_id}),
            {"page": 25, "page_size": 50},
        ),
    )

    for url, params in paths:
        p95 = _timed_requests(client, url, params)
        print(f"performance {url}: p95_ms={p95 * 1_000:.1f}")
        assert p95 < P95_TARGET_SECONDS, f"{url} p95 was {p95:.3f}s (target {P95_TARGET_SECONDS:.3f}s)"

    workspace = resolve_organization_workspace(result.owner, entity_id=selected.entity_id)
    operations = (
        (
            "workspace discovery",
            lambda: search_organization_workspaces(
                result.owner,
                query="Reference",
                classification="client",
                page=1,
                page_size=25,
            ),
            12,
        ),
        (
            "organization list",
            lambda: list(
                _organizations_for_context(
                    require_permission(result.owner, PermissionKey.ORGANIZATIONS_VIEW),
                    PermissionKey.ORGANIZATIONS_VIEW,
                )
            ),
            12,
        ),
        (
            "People list",
            lambda: query_people(
                scope=workspace.data_scope,
                q="Reference",
                filter_field="",
                filter_value="",
                ordering="full_name",
                page=1,
                page_size=25,
            ),
            4,
        ),
        ("Sites list", lambda: query_sites(scope=workspace.data_scope, q="Reference"), 3),
        (
            "entity discovery",
            lambda: search_entities(
                workspace=workspace,
                query="Reference",
                entity_type="",
                page=1,
                page_size=25,
            ),
            5,
        ),
        (
            "relationship discovery",
            lambda: relationships_for_entity(workspace=workspace, entity_id=linked_entity.id),
            6,
        ),
        (
            "document revision history",
            lambda: list(revisions_for_document(document)[1_200:1_250]),
            3,
        ),
    )
    for label, operation, budget in operations:
        count = _query_count(operation)
        print(f"performance {label}: queries={count}")
        assert count <= budget, f"{label} used {count} queries (budget {budget})"
