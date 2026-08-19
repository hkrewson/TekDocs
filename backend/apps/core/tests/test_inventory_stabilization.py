import time

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.catalogs import create_definition, create_model, create_product
from apps.core.commercial import create_contract
from apps.core.credential_references import create_credential_reference
from apps.core.inventory import create_client_asset
from apps.core.models import CatalogModelLifecycle, SoftwareLicenseKind, SoftwareLicenseStatus, SoftwareRenewalInterval
from apps.core.organizations import create_organization
from apps.core.software_inventory import create_license
from apps.core.tests.test_stabilization_performance import (
    P95_SAMPLES,
    _create_reference_fixture,
    _p95,
    assert_p95_within_budget,
)

PRIVATE_LINK = (
    "https://start.1password.com/open/i?"
    "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
    "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
)
PAGE_SIZE = 25
REFERENCE_ASSETS = 120
REFERENCE_CREDENTIALS = 120
REFERENCE_CONTRACTS = 120


def _model(*, result, supplier, kind: str):  # type: ignore[no-untyped-def]
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }
    definition = create_definition(
        tenant=result.tenant,
        organization=supplier,
        actor_id=result.owner.id,
        name=f"Reference {kind} schema",
        product_kind=kind,
        schema=schema,
    )
    version = definition.versions.get(version=1)
    product = create_product(
        tenant=result.tenant,
        organization=supplier,
        actor_id=result.owner.id,
        name=f"Reference {kind} product",
        kind=kind,
        description="Inventory validation fixture",
    )
    return create_model(
        product=product,
        actor_id=result.owner.id,
        name=f"Reference {kind} model",
        model_number=f"REF-{kind.upper()}",
        specification_version=version,
        lifecycle=CatalogModelLifecycle.ACTIVE,
        specifications={},
        notes="",
    )


def _p95_get(client: Client, url: str, params: dict[str, object]) -> float:
    response = client.get(url, params)
    assert response.status_code == 200
    samples = []
    for _ in range(P95_SAMPLES):
        started = time.perf_counter()
        response = client.get(url, params)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
    return _p95(samples)


@pytest.mark.django_db(transaction=True)
def test_inventory_reference_pages_are_bounded_policy_scoped_and_fast():
    if connection.vendor != "postgresql":
        pytest.skip("Inventory reference performance validation requires PostgreSQL")

    result, selected, _linked_entity, _document = _create_reference_fixture()
    supplier = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Inventory Reference Supplier",
        legal_name="Inventory Reference Supplier, Inc.",
        website="",
        classifications=["vendor"],
    )
    hardware_model = _model(result=result, supplier=supplier, kind="hardware")
    software_model = _model(result=result, supplier=supplier, kind="software")

    software_assets = []
    for index in range(REFERENCE_ASSETS):
        kind = "software" if index % 2 else "hardware"
        asset = create_client_asset(
            tenant=result.tenant,
            organization=selected,
            actor_id=result.owner.id,
            model_entity_id=(software_model if kind == "software" else hardware_model).entity_id,
            name=f"Reference asset {index:03d}",
        )
        if kind == "software":
            software_assets.append(asset)

    for index, asset in enumerate(software_assets):
        create_license(
            tenant=result.tenant,
            organization=selected,
            actor_id=result.owner.id,
            asset=asset,
            values={
                "name": f"Reference license {index:03d}",
                "kind": SoftwareLicenseKind.SUBSCRIPTION,
                "status": SoftwareLicenseStatus.ACTIVE,
                "seat_limit": 25,
                "renewal_interval": SoftwareRenewalInterval.ANNUAL,
                "auto_renew": True,
                "reference": "",
            },
        )

    for index in range(REFERENCE_CONTRACTS):
        create_contract(
            tenant=result.tenant,
            organization=selected,
            actor_id=result.owner.id,
            values={
                "name": f"Reference contract {index:03d}",
                "provider_id": supplier.entity_id,
                "kind": "service",
                "status": "active",
                "description": "Reference operational agreement",
                "reference": "",
                "auto_renew": False,
                "renewal_notice_days": 0,
            },
        )

    for index in range(REFERENCE_CREDENTIALS):
        create_credential_reference(
            tenant=result.tenant,
            organization=selected,
            actor_id=result.owner.id,
            title=f"Reference credential {index:03d}",
            provider="onepassword",
            reference_url=PRIVATE_LINK,
        )

    browser = Client()
    browser.force_login(result.owner)
    base = {"organization_entity_id": selected.entity_id}
    paths = (
        (reverse("organization-client-asset-list-create", kwargs=base), {"page": 1, "page_size": PAGE_SIZE}, 32),
        (reverse("organization-software-license-list-create", kwargs=base), {"page": 2, "page_size": PAGE_SIZE}, 32),
        (reverse("organization-commercial-contract-list-create", kwargs=base), {"page": 3, "page_size": PAGE_SIZE}, 32),
        (
            reverse("organization-credential-reference-list-create", kwargs=base),
            {"page": 5, "page_size": PAGE_SIZE},
            32,
        ),
    )
    for url, params, query_budget in paths:
        assert_p95_within_budget(url, _p95_get(browser, url, params))
        with CaptureQueriesContext(connection) as queries:
            response = browser.get(url, params)
        assert response.status_code == 200
        assert len(response.json()["results"]) <= PAGE_SIZE
        assert len(queries) <= query_budget, f"{url} used {len(queries)} queries"

    asset_page = browser.get(paths[0][0], paths[0][1]).json()
    assert asset_page["count"] == REFERENCE_ASSETS
    assert asset_page["has_more"] is True
    credential_page = browser.get(paths[-1][0], paths[-1][1])
    assert credential_page.json()["count"] == REFERENCE_CREDENTIALS
    assert credential_page.json()["has_more"] is False
    assert PRIVATE_LINK not in credential_page.content.decode()

    msp_assets = browser.get(reverse("msp-asset-list-create"), {"page_size": PAGE_SIZE}).json()
    assert msp_assets["count"] == 0
