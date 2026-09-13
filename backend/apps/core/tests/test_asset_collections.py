# ruff: noqa: F811
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.inventory import create_client_asset
from apps.core.models import ClientHardwareAsset
from apps.core.tests.test_inventory import _organization, installation, owner_client  # noqa: F401
from apps.core.tests.test_inventory_stabilization import _model


@pytest.mark.django_db
def test_summary_collection_searches_all_records_and_preserves_legacy(owner_client, installation):
    supplier = _organization(installation, "Supplier", "vendor")
    client = _organization(installation, "Client", "client")
    sibling = _organization(installation, "Sibling", "client")
    model = _model(result=installation, supplier=supplier, kind="hardware")
    assets = [
        create_client_asset(
            tenant=installation.tenant,
            organization=client,
            actor_id=installation.owner.pk,
            model_entity_id=model.entity_id,
            name=f"Asset {index:03}",
        )
        for index in range(31)
    ]
    create_client_asset(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.pk,
        model_entity_id=model.entity_id,
        name="Asset outside scope",
    )
    ClientHardwareAsset.objects.filter(asset=assets[-1]).update(
        serial_number="OFFPAGE-IDENTIFIER",
        warranty_ends_on=timezone.localdate() - timedelta(days=1),
    )
    url = reverse("organization-asset-collection", kwargs={"organization_entity_id": client.entity_id})
    with CaptureQueriesContext(connection) as queries:
        response = owner_client.get(url)
    assert response.status_code == 200, response.content
    page = response.json()
    assert (page["count"], page["page_size"], len(page["results"]), page["has_more"]) == (31, 25, 25, True)
    assert not {"specifications", "documents", "hardware", "provenance_checksum"} & page["results"][0].keys()
    assert not any('FROM "core_clientassetlifecycleevent"' in query["sql"] for query in queries)
    assert not any('FROM "core_clientassetdocumentprovenance"' in query["sql"] for query in queries)
    assert sum('FROM "core_clientasset"' in query["sql"] for query in queries) == 2
    assert not any('"core_clientasset"."specifications"' in query["sql"] for query in queries)
    for size in (50, 100):
        larger = owner_client.get(url, {"page_size": size}).json()
        assert larger["page_size"] == size and len(larger["results"]) == 31
    empty_page = owner_client.get(url, {"page": 100}).json()
    assert empty_page["results"] == [] and empty_page["count"] == 31 and not empty_page["has_more"]
    second = owner_client.get(url, {"page": 2}).json()
    assert len(second["results"]) == 6
    assert not second["has_more"]
    assert not {row["id"] for row in page["results"]} & {row["id"] for row in second["results"]}
    for params in ({"search": "OFFPAGE-IDENTIFIER"}, {"warranty": "expired"}):
        found = owner_client.get(url, params).json()
        assert found["count"] == 1
        assert found["results"][0]["id"] == str(assets[-1].entity_id)
    descending = owner_client.get(url, {"ordering": "-name"}).json()
    assert descending["results"][0]["id"] == str(assets[-1].entity_id)
    for params in ({"page_size": 10}, {"ordering": "specifications"}, {"arbitrary": "ignored"}, {"status": "invalid"}):
        assert owner_client.get(url, params).status_code == 400
    legacy = owner_client.get(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id})
    ).json()
    assert legacy["page_size"] == 50
    assert "specifications" in legacy["results"][0]
    assert owner_client.get(reverse("msp-asset-collection")).json()["count"] == 0
    assert (
        owner_client.get(
            reverse("organization-asset-collection", kwargs={"organization_entity_id": supplier.entity_id})
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_software_summaries_and_stable_ties(owner_client, installation):
    supplier = _organization(installation, "Supplier", "vendor")
    model = _model(result=installation, supplier=supplier, kind="software")
    assets = [
        create_client_asset(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.pk,
            model_entity_id=model.entity_id,
            name="Same name",
        )
        for _ in range(3)
    ]
    url = reverse("msp-asset-collection")
    result = owner_client.get(url, {"kind": "software", "ordering": "-name"}).json()
    assert [row["id"] for row in result["results"]] == sorted(str(asset.entity_id) for asset in assets)
    assert all(
        row["status"] == "planned" and row["assignment"] is None and row["warranty_ends_on"] is None
        for row in result["results"]
    )
    assert owner_client.get(url, {"kind": "hardware"}).json()["count"] == 0


@pytest.mark.django_db(transaction=True)
def test_collection_does_not_grant_workspace_access(installation, django_runtime_role):
    from django.test import Client

    from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User

    allowed = _organization(installation, "Allowed", "client")
    denied = _organization(installation, "Denied", "client")
    reader = User.objects.create_user(email="layout-reader@example.invalid", display_name="Layout reader")
    member = TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=allowed,
        membership=member,
        created_by=installation.owner,
    )
    supplier = _organization(installation, "Retained Supplier", "vendor")
    model = _model(result=installation, supplier=supplier, kind="hardware")
    asset = create_client_asset(
        tenant=installation.tenant,
        organization=allowed,
        actor_id=installation.owner.pk,
        model_entity_id=model.entity_id,
        name="Authorized asset",
    )
    browser = Client()
    browser.force_login(reader)
    with django_runtime_role():
        result = browser.get(
            reverse("organization-asset-collection", kwargs={"organization_entity_id": allowed.entity_id})
        )
        assert result.status_code == 200, result.content
        assert result.json()["can_manage"] is False
        assert [row["id"] for row in result.json()["results"]] == [str(asset.entity_id)]
        result = browser.get(
            reverse("organization-asset-collection", kwargs={"organization_entity_id": denied.entity_id})
        )
        assert result.status_code in {403, 404}
        assert (
            browser.get(
                reverse("organization-asset-site-choices", kwargs={"organization_entity_id": allowed.entity_id})
            ).status_code
            == 200
        )
        assert browser.get(
            reverse("organization-asset-site-choices", kwargs={"organization_entity_id": denied.entity_id})
        ).status_code in {403, 404}


@pytest.mark.django_db(transaction=True)
def test_site_choices_are_bounded_searchable_and_scope_limited(owner_client, installation, django_runtime_role):
    from apps.core.models import Entity, Site

    supplier = _organization(installation, "Supplier", "vendor")
    client = _organization(installation, "Client", "client")
    model = _model(result=installation, supplier=supplier, kind="hardware")
    sites = []
    for index in range(31):
        entity = Entity.objects.create_owned(
            tenant=installation.tenant, organization=client, entity_type="site", display_name=f"Site {index:03}"
        )
        site = Site.objects.create(tenant=installation.tenant, organization=client, entity=entity)
        asset = create_client_asset(
            tenant=installation.tenant,
            organization=client,
            actor_id=installation.owner.pk,
            model_entity_id=model.entity_id,
            name=f"Asset {index}",
        )
        ClientHardwareAsset.objects.filter(asset=asset).update(assigned_site=site)
        sites.append(site)
    from apps.core.people import create_person

    person = create_person(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.pk,
        full_name="Assigned technician",
        preferred_name="",
        kind="employee",
        role="",
        responsibility="",
        location="",
        office="",
        site=None,
        structured_location=None,
        phone="",
        email="",
    )
    ClientHardwareAsset.objects.filter(asset=asset).update(assigned_person=person)
    url = reverse("organization-asset-site-choices", kwargs={"organization_entity_id": client.entity_id})
    with CaptureQueriesContext(connection) as queries:
        response = owner_client.get(url)
    assert response.status_code == 200, response.content
    first = response.json()
    assert (first["count"], len(first["results"]), first["page_size"], first["has_more"]) == (31, 25, 25, True)
    assert set(first["results"][0]) == {"id", "name"}
    assert not any('FROM "core_location"' in query["sql"] for query in queries)
    filtered_url = reverse("organization-asset-collection", kwargs={"organization_entity_id": client.entity_id})
    with django_runtime_role():
        filtered = owner_client.get(filtered_url, {"site": str(sites[-1].entity_id)}).json()
    assert filtered["count"] == 1, filtered
    assert len(filtered["results"]) == 1, filtered
    assert filtered["results"][0]["assignment"] == "Assigned technician"
    with django_runtime_role():
        assert (
            owner_client.get(filtered_url, {"site": str(sites[-1].entity_id), "assigned": "true"}).json()["count"] == 1
        )
        assert (
            owner_client.get(filtered_url, {"site": str(sites[-1].entity_id), "assigned": "false"}).json()["count"] == 0
        )
    second = owner_client.get(url, {"page": 2}).json()
    assert len(second["results"]) == 6
    assert not {r["id"] for r in first["results"]} & {r["id"] for r in second["results"]}
    found = owner_client.get(url, {"search": "030", "selected": str(sites[0].entity_id)}).json()
    assert found["results"] == [{"id": str(sites[-1].entity_id), "name": "Site 030"}]
    assert found["selected"] == {"id": str(sites[0].entity_id), "name": "Site 000"}
    assert (
        owner_client.get(reverse("msp-asset-site-choices"), {"selected": str(sites[0].entity_id)}).json()["selected"]
        is None
    )
    assert owner_client.get(reverse("msp-asset-site-choices")).json()["count"] == 0
    sites[0].archived_at = timezone.now()
    sites[0].save(update_fields=["archived_at"])
    assert owner_client.get(url, {"selected": str(sites[0].entity_id)}).json()["selected"] is None
    for query in ({"selected": "bad"}, {"page": 0}, {"page_size": 1000}, {"unknown": "value"}):
        assert owner_client.get(url, query).status_code == 400


@pytest.mark.django_db
def test_site_choices_include_software_and_exclude_unused_sites(owner_client, installation):
    from apps.core.models import Entity, Site

    supplier = _organization(installation, "Supplier", "vendor")
    model = _model(result=installation, supplier=supplier, kind="software")
    asset = create_client_asset(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.pk,
        model_entity_id=model.entity_id,
        name="Software",
    )
    sites = []
    for name in ("Used", "Unused"):
        entity = Entity.objects.create_owned(tenant=installation.tenant, entity_type="site", display_name=name)
        sites.append(Site.objects.create(tenant=installation.tenant, entity=entity))
    software = asset.software_installation
    software.site = sites[0]
    software.save(update_fields=["site"])
    result = owner_client.get(reverse("msp-asset-site-choices")).json()
    assert result["results"] == [{"id": str(sites[0].entity_id), "name": "Used"}]
    filtered = owner_client.get(reverse("msp-asset-collection"), {"site": str(sites[0].entity_id)}).json()
    assert filtered["count"] == 1
    assert filtered["results"][0]["id"] == str(asset.entity_id)


@pytest.mark.parametrize("query, expected", [("", None), ("assigned=true", True), ("assigned=false", False)])
def test_optional_assignment_query_is_not_an_html_checkbox(query, expected):
    from django.http import QueryDict

    from apps.core.asset_collection_views import AssetCollectionQuerySerializer

    serializer = AssetCollectionQuerySerializer(data=QueryDict(query))
    assert serializer.is_valid(), serializer.errors
    if expected is None:
        assert "assigned" not in serializer.validated_data
    else:
        assert serializer.validated_data["assigned"] is expected
