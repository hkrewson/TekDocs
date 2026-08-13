import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.catalogs import create_definition, create_model, create_product
from apps.core.documents import markdown_checksum
from apps.core.inventory import _checksum
from apps.core.models import (
    BlockRevision,
    CatalogModelLifecycle,
    CatalogModelRevision,
    ClientAsset,
    Entity,
    EntityVisibility,
    Organization,
    OrganizationClassification,
    Workspace,
)
from apps.core.organizations import create_organization
from apps.core.tests.test_stabilization_performance import (
    P95_TARGET_SECONDS,
    _create_reference_fixture,
    _p95,
    _timed_requests,
)

REFERENCE_ENTITIES = 100_000
REFERENCE_REVISIONS = 250_000
REFERENCE_ASSETS = 25_000
BATCH_SIZE = 5_000


def _hardware_model(result):  # type: ignore[no-untyped-def]
    supplier = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Capacity Reference Supplier",
        legal_name="Capacity Reference Supplier, Inc.",
        website="",
        classifications=["vendor"],
    )
    definition = create_definition(
        tenant=result.tenant,
        organization=supplier,
        actor_id=result.owner.id,
        name="Capacity hardware schema",
        product_kind="hardware",
        schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )
    product = create_product(
        tenant=result.tenant,
        organization=supplier,
        actor_id=result.owner.id,
        name="Capacity hardware product",
        kind="hardware",
        description="Public-beta capacity fixture",
    )
    model = create_model(
        product=product,
        actor_id=result.owner.id,
        name="Capacity hardware model",
        model_number="CAP-HW-1",
        specification_version=definition.versions.get(version=1),
        lifecycle=CatalogModelLifecycle.ACTIVE,
        specifications={},
        notes="",
    )
    return supplier, product, model, CatalogModelRevision.objects.get(model=model, revision=1)


def _grow_revision_chain(result, document) -> None:  # type: ignore[no-untyped-def]
    block = document.placements.select_related("block__current_revision").get(
        parent__isnull=True,
        position=0,
    ).block
    parent_id = block.current_revision_id
    existing = BlockRevision.objects.filter(block=block).count()
    for start in range(existing + 1, REFERENCE_REVISIONS + 1, BATCH_SIZE):
        batch = []
        for revision_number in range(start, min(start + BATCH_SIZE, REFERENCE_REVISIONS + 1)):
            markdown = f"Capacity revision {revision_number}"
            revision = BlockRevision(
                tenant=result.tenant,
                organization=None,
                block=block,
                parent_id=parent_id,
                revision_number=revision_number,
                markdown=markdown,
                checksum=markdown_checksum(markdown),
                created_by=result.owner,
            )
            parent_id = revision.id
            batch.append(revision)
        BlockRevision.objects.bulk_create(batch, batch_size=BATCH_SIZE)
    block.current_revision_id = parent_id
    block.save(update_fields=("current_revision", "updated_at"))


def _grow_assets(result, selected: Organization) -> None:  # type: ignore[no-untyped-def]
    supplier, product, model, revision = _hardware_model(result)
    workspace = Workspace.objects.get(tenant=result.tenant, organization=selected)
    provenance_checksum = _checksum(
        {
            "supplier_id": str(supplier.entity_id),
            "product_id": str(product.entity_id),
            "model_id": str(model.entity_id),
            "model_revision_id": str(revision.id),
            "specification_version_id": str(revision.specification_version_id),
            "specifications": revision.specifications,
        }
    )
    for start in range(0, REFERENCE_ASSETS, BATCH_SIZE):
        entities = [
            Entity(
                tenant=result.tenant,
                organization=selected,
                workspace=workspace,
                entity_type="client_asset",
                display_name=f"Capacity asset {index:05d}",
                visibility=EntityVisibility.MSP_PRIVATE,
            )
            for index in range(start, min(start + BATCH_SIZE, REFERENCE_ASSETS))
        ]
        Entity.objects.bulk_create(entities, batch_size=BATCH_SIZE)
        ClientAsset.objects.bulk_create(
            [
                ClientAsset(
                    tenant=result.tenant,
                    organization=selected,
                    entity=entity,
                    supplier=supplier,
                    product=product,
                    model=model,
                    model_revision=revision,
                    specification_version=revision.specification_version,
                    specifications={},
                    provenance_checksum=provenance_checksum,
                    created_by=result.owner,
                )
                for entity in entities
            ],
            batch_size=BATCH_SIZE,
        )


def _grow_entities(result) -> None:  # type: ignore[no-untyped-def]
    organizations = list(
        Organization.objects.filter(
            tenant=result.tenant,
            classifications__kind="client",
        ).order_by("id")
    )
    workspaces = {
        workspace.organization_id: workspace
        for workspace in Workspace.objects.filter(tenant=result.tenant, organization__in=organizations)
    }
    current = Entity.objects.filter(tenant=result.tenant).count()
    for start in range(current, REFERENCE_ENTITIES, BATCH_SIZE):
        entities = []
        for index in range(start, min(start + BATCH_SIZE, REFERENCE_ENTITIES)):
            organization = organizations[index % len(organizations)]
            entities.append(
                Entity(
                    tenant=result.tenant,
                    organization=organization,
                    workspace=workspaces[organization.id],
                    entity_type="capacity_record",
                    display_name=f"Capacity record {index:06d}",
                    visibility=EntityVisibility.MSP_PRIVATE,
                )
            )
        Entity.objects.bulk_create(entities, batch_size=BATCH_SIZE)


def _concurrent_get(cookies, url: str, params: dict[str, object]) -> tuple[int, float]:  # type: ignore[no-untyped-def]
    close_old_connections()
    browser = Client()
    browser.cookies = cookies.copy()
    started = time.perf_counter()
    try:
        response = browser.get(url, params)
        return response.status_code, time.perf_counter() - started
    finally:
        close_old_connections()


@pytest.mark.django_db(transaction=True)
def test_public_beta_reference_capacity_is_bounded_scoped_and_responsive():
    if connection.vendor != "postgresql":
        pytest.skip("Public-beta capacity certification requires PostgreSQL")

    result, selected, _linked_entity, document = _create_reference_fixture()
    _grow_assets(result, selected)
    _grow_entities(result)
    _grow_revision_chain(result, document)

    assert OrganizationClassification.objects.filter(tenant=result.tenant, kind="client").count() == 100
    assert Entity.objects.filter(tenant=result.tenant).count() >= REFERENCE_ENTITIES
    assert ClientAsset.objects.filter(tenant=result.tenant).count() == REFERENCE_ASSETS
    assert BlockRevision.objects.filter(block__placements__document=document).distinct().count() >= REFERENCE_REVISIONS

    browser = Client()
    browser.force_login(result.owner)
    base = {"organization_entity_id": selected.entity_id}
    asset_url = reverse("organization-client-asset-list-create", kwargs=base)
    history_url = reverse("msp-document-revision-list", kwargs={"document_entity_id": document.entity_id})
    search_url = reverse("organization-entity-search", kwargs=base)
    paths = (
        (asset_url, {"page": 1, "page_size": 25}),
        (asset_url, {"page": 500, "page_size": 25}),
        (asset_url, {"page": 1_000, "page_size": 25}),
        (history_url, {"page": 5_000, "page_size": 50}),
        (search_url, {"q": "Capacity record", "page": 1, "page_size": 25}),
    )
    for url, params in paths:
        p95 = _timed_requests(browser, url, params)
        print(f"capacity {url}: p95_ms={p95 * 1_000:.1f}")
        assert p95 < P95_TARGET_SECONDS, f"{url} p95 was {p95:.3f}s"

    for url, params, budget in (
        (asset_url, {"page": 1_000, "page_size": 25}, 32),
        (history_url, {"page": 5_000, "page_size": 50}, 28),
        (search_url, {"q": "Capacity record", "page": 1, "page_size": 25}, 32),
    ):
        with CaptureQueriesContext(connection) as queries:
            response = browser.get(url, params)
        assert response.status_code == 200
        assert len(queries) <= budget, f"{url} used {len(queries)} queries"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: _concurrent_get(browser.cookies, asset_url, {"page": 1_000, "page_size": 25}),
                range(8),
            )
        )
    assert {status for status, _elapsed in results} == {200}
    concurrent_p95 = _p95([elapsed for _status, elapsed in results])
    print(f"capacity concurrent asset page: p95_ms={concurrent_p95 * 1_000:.1f}")
    assert concurrent_p95 < 2.0
