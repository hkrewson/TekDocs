import secrets
import uuid

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    ClientAsset,
    ClientAssetDocumentProvenance,
    ClientAssetLifecycleEvent,
    ClientHardwareAsset,
    InstallationState,
)
from apps.core.organizations import create_organization
from apps.core.rls_contract import RUNTIME_ROLE

HARDWARE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {"ports": {"type": "integer", "minimum": 1}},
    "required": ["ports"],
}


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Inventory MSP",
        owner_email="inventory-owner@example.invalid",
        owner_display_name="Inventory Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name, classification):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=[classification],
    )


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def _catalog(owner_client, supplier):  # type: ignore[no-untyped-def]
    base = {"organization_entity_id": supplier.entity_id}
    definition = owner_client.post(
        reverse("organization-catalog-specification-definition-list-create", kwargs=base),
        {"name": "Managed switch", "product_kind": "hardware", "schema": HARDWARE_SCHEMA},
        content_type="application/json",
    ).json()
    product = owner_client.post(
        reverse("organization-catalog-product-list-create", kwargs=base),
        {"name": "EdgeSwitch", "kind": "hardware", "description": "Managed switching"},
        content_type="application/json",
    ).json()
    model = owner_client.post(
        reverse(
            "organization-catalog-model-list-create",
            kwargs={**base, "product_entity_id": product["id"]},
        ),
        {
            "name": "EdgeSwitch 24",
            "model_number": "ES-24",
            "specification_version_id": definition["versions"][0]["id"],
            "lifecycle": "active",
            "specifications": {"ports": 24},
            "notes": "Initial",
        },
        content_type="application/json",
    ).json()
    document = owner_client.post(
        reverse("organization-document-list-create", kwargs=base),
        {"title": "EdgeSwitch installation guide", "markdown": "# Install\n\nRetained instructions."},
        content_type="application/json",
    ).json()
    publication = owner_client.post(
        reverse(
            "organization-document-publication-list-create",
            kwargs={**base, "document_entity_id": document["id"]},
        ),
        {"reason": "Approved product guide", "audience": "client_visible", "retention": "permanent"},
        content_type="application/json",
    ).json()
    association = owner_client.post(
        reverse(
            "organization-catalog-product-document-list-create",
            kwargs={**base, "product_entity_id": product["id"]},
        ),
        {"publication_id": publication["id"], "model_id": model["id"]},
        content_type="application/json",
    )
    assert association.status_code == 201
    return definition, product, model, document, publication


@pytest.mark.django_db
def test_client_asset_retains_catalog_and_static_document_provenance(owner_client, installation):
    supplier = _organization(installation, "Northwind Networks", "manufacturer")
    client = _organization(installation, "Contoso Clinic", "client")
    sibling = _organization(installation, "Sibling Clinic", "client")
    definition, product, model, _document, publication = _catalog(owner_client, supplier)

    choice_response = owner_client.get(
        reverse(
            "organization-client-asset-model-choices",
            kwargs={"organization_entity_id": client.entity_id},
        ),
        {"q": "ES-24"},
    )
    assert choice_response.status_code == 200
    assert choice_response.json()["results"][0]["supplier_name"] == "Northwind Networks"

    created = owner_client.post(
        reverse(
            "organization-client-asset-list-create",
            kwargs={"organization_entity_id": client.entity_id},
        ),
        {"model_id": model["id"], "name": "Core switch"},
        content_type="application/json",
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Core switch"
    assert payload["supplier_id"] == str(supplier.entity_id)
    assert payload["product_id"] == product["id"]
    assert payload["model_id"] == model["id"]
    assert payload["model_revision"] == 1
    assert payload["specifications"] == {"ports": 24}
    assert len(payload["provenance_checksum"]) == 64
    assert payload["documents"][0]["publication_id"] == publication["id"]
    assert payload["documents"][0]["verification"]["valid"] is True
    assert payload["hardware"]["lifecycle_state"] == "in_stock"

    document_projection = owner_client.get(
        reverse(
            "organization-client-asset-document-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "asset_entity_id": payload["id"],
                "publication_entity_id": publication["id"],
            },
        )
    )
    assert document_projection.status_code == 200
    assert "Retained instructions" in document_projection.json()["sanitized_html"]

    vendors = owner_client.get(
        reverse("organization-client-vendor-list", kwargs={"organization_entity_id": client.entity_id})
    ).json()
    assert [(item["name"], item["asset_count"]) for item in vendors["results"]] == [("Northwind Networks", 1)]

    hidden = owner_client.get(
        reverse(
            "organization-client-asset-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "asset_entity_id": payload["id"]},
        )
    )
    assert hidden.status_code == 404

    revised = owner_client.patch(
        reverse(
            "organization-catalog-model-detail",
            kwargs={
                "organization_entity_id": supplier.entity_id,
                "product_entity_id": product["id"],
                "model_entity_id": model["id"],
            },
        ),
        {
            "base_revision_id": model["current_revision"]["id"],
            "name": "EdgeSwitch 48",
            "model_number": "ES-48",
            "specification_version_id": definition["versions"][0]["id"],
            "lifecycle": "active",
            "specifications": {"ports": 48},
            "notes": "New catalog revision",
        },
        content_type="application/json",
    )
    assert revised.status_code == 200
    retained = owner_client.get(
        reverse(
            "organization-client-asset-detail",
            kwargs={"organization_entity_id": client.entity_id, "asset_entity_id": payload["id"]},
        )
    ).json()
    assert retained["model_revision"] == 1
    assert retained["specifications"] == {"ports": 24}


@pytest.mark.django_db
def test_hardware_identity_assignment_disposal_and_history_are_scoped(owner_client, installation):
    supplier = _organization(installation, "Lifecycle Supplier", "vendor")
    client = _organization(installation, "Lifecycle Client", "client")
    sibling = _organization(installation, "Other Client", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)
    asset = owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"model_id": model["id"], "name": "Lobby switch"},
        content_type="application/json",
    ).json()
    base = {"organization_entity_id": client.entity_id, "asset_entity_id": asset["id"]}
    hardware_url = reverse("organization-client-hardware-detail", kwargs=base)
    updated = owner_client.patch(
        hardware_url,
        {
            "serial_number": " sn-100 ",
            "asset_tag": " sw-100 ",
            "lifecycle_state": "in_service",
            "acquired_on": "2026-08-01",
            "acquisition_method": "purchase",
            "acquisition_reference": "PO-100",
            "warranty_provider": "Lifecycle Supplier",
            "warranty_starts_on": "2026-08-01",
            "warranty_ends_on": "2029-08-01",
            "warranty_reference": "W-100",
        },
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["serial_number"] == "SN-100"

    site = owner_client.post(
        reverse("organization-site-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"name": "Main office", "code": "MAIN", "country_code": "US"},
        content_type="application/json",
    ).json()
    person = owner_client.post(
        reverse("organization-people-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"full_name": "Morgan Ellis", "kind": "contact", "email": "morgan@example.invalid", "site_id": site["id"]},
        content_type="application/json",
    )
    assert person.status_code == 201
    sibling_site = owner_client.post(
        reverse("organization-site-list-create", kwargs={"organization_entity_id": sibling.entity_id}),
        {"name": "Sibling office", "code": "SIBLING", "country_code": "US"},
        content_type="application/json",
    ).json()
    sibling_person = owner_client.post(
        reverse("organization-people-list-create", kwargs={"organization_entity_id": sibling.entity_id}),
        {
            "full_name": "Hidden sibling contact",
            "kind": "contact",
            "email": "hidden-sibling@example.invalid",
            "site_id": sibling_site["id"],
        },
        content_type="application/json",
    ).json()
    foreign_assignment = owner_client.post(
        reverse("organization-client-hardware-assignment", kwargs=base),
        {"person_id": sibling_person["id"], "site_id": sibling_site["id"]},
        content_type="application/json",
    )
    assert foreign_assignment.status_code == 400
    assert "Hidden sibling contact" not in foreign_assignment.content.decode()
    choices = owner_client.get(reverse("organization-client-hardware-assignment-choices", kwargs=base)).json()
    assigned = owner_client.post(
        reverse("organization-client-hardware-assignment", kwargs=base),
        {"person_id": choices["people"][0]["id"], "site_id": choices["sites"][0]["id"]},
        content_type="application/json",
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignment"]["person_name"] == "Morgan Ellis"

    sibling_choices = owner_client.get(
        reverse(
            "organization-client-hardware-assignment-choices",
            kwargs={"organization_entity_id": sibling.entity_id, "asset_entity_id": asset["id"]},
        )
    )
    assert sibling_choices.status_code == 404

    disposed = owner_client.post(
        reverse("organization-client-hardware-disposal", kwargs=base),
        {"disposed_on": "2026-08-10", "method": "recycled", "reason": "Replaced"},
        content_type="application/json",
    )
    assert disposed.status_code == 200
    assert disposed.json()["lifecycle_state"] == "disposed"
    assert disposed.json()["assignment"]["assigned_at"] is None
    assert owner_client.patch(hardware_url, {"asset_tag": "LATE"}, content_type="application/json").status_code == 400
    history = owner_client.get(reverse("organization-client-hardware-lifecycle", kwargs=base)).json()
    assert [event["event_type"] for event in reversed(history)] == [
        "created", "state_changed", "assigned", "unassigned", "disposed"
    ]
    assert ClientHardwareAsset.objects.get(asset__entity_id=asset["id"]).disposal_reason == "Replaced"
    assert ClientAssetLifecycleEvent.objects.filter(asset__entity_id=asset["id"]).exists()


@pytest.mark.django_db
def test_software_asset_rejects_hardware_lifecycle(owner_client, installation):
    supplier = _organization(installation, "Software Supplier", "vendor")
    client = _organization(installation, "Software Client", "client")
    base = {"organization_entity_id": supplier.entity_id}
    definition = owner_client.post(
        reverse("organization-catalog-specification-definition-list-create", kwargs=base),
        {
            "name": "Software",
            "product_kind": "software",
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
        content_type="application/json",
    ).json()
    product = owner_client.post(
        reverse("organization-catalog-product-list-create", kwargs=base),
        {"name": "Agent", "kind": "software", "description": ""},
        content_type="application/json",
    ).json()
    model = owner_client.post(
        reverse("organization-catalog-model-list-create", kwargs={**base, "product_entity_id": product["id"]}),
        {
            "name": "Agent 1",
            "model_number": "A1",
            "specification_version_id": definition["versions"][0]["id"],
            "lifecycle": "active",
            "specifications": {},
            "notes": "",
        },
        content_type="application/json",
    ).json()
    asset = owner_client.post(
        reverse(
            "organization-client-asset-list-create",
            kwargs={"organization_entity_id": client.entity_id},
        ),
        {"model_id": model["id"], "name": "Endpoint agent"},
        content_type="application/json",
    ).json()
    response = owner_client.get(
        reverse(
            "organization-client-hardware-detail",
            kwargs={"organization_entity_id": client.entity_id, "asset_entity_id": asset["id"]},
        )
    )
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_client_asset_provenance_mutation(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Client asset database guards require PostgreSQL")
    supplier = _organization(installation, "Guarded Supplier", "vendor")
    client = _organization(installation, "Guarded Client", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)
    hidden_document = owner_client.post(
        reverse(
            "organization-document-list-create",
            kwargs={"organization_entity_id": supplier.entity_id},
        ),
        {"title": "Supplier internal notes", "markdown": "Never projected."},
        content_type="application/json",
    )
    assert hidden_document.status_code == 201
    created = owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"model_id": model["id"], "name": "Guarded asset"},
        content_type="application/json",
    ).json()
    asset = ClientAsset.objects.get(entity_id=created["id"])
    provenance = ClientAssetDocumentProvenance.objects.get(asset=asset)
    profile = ClientHardwareAsset.objects.get(asset=asset)
    lifecycle_event = ClientAssetLifecycleEvent.objects.get(asset=asset)

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(installation.tenant.id)])
        cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(client.id)])
        cursor.execute("SELECT set_config('tekdocs.organization_mode', 'organization', true)")
        cursor.execute("SELECT id FROM core_catalogmodel WHERE id = %s", [asset.model_id])
        assert cursor.fetchone() == (asset.model_id,)
        cursor.execute("SELECT id FROM core_catalogproductdocument WHERE id = %s", [provenance.catalog_document_id])
        assert cursor.fetchone() == (provenance.catalog_document_id,)
        cursor.execute("SELECT id FROM core_documentpublication WHERE id = %s", [provenance.publication_id])
        assert cursor.fetchone() == (provenance.publication_id,)
        cursor.execute("SELECT id FROM core_entity WHERE display_name = 'Supplier internal notes'")
        assert cursor.fetchall() == []
        cursor.execute(
            "SELECT tekdocs_client_catalog_publication_visible(%s, %s)",
            [provenance.publication_id, installation.tenant.id],
        )
        assert cursor.fetchone() == (True,)
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(uuid.uuid4())])
        cursor.execute(
            "SELECT tekdocs_client_catalog_publication_visible(%s, %s)",
            [provenance.publication_id, installation.tenant.id],
        )
        assert cursor.fetchone() == (False,)

    with pytest.raises(DatabaseError), transaction.atomic():
        ClientAsset.objects.filter(pk=asset.pk).update(specifications={"ports": 999})
    with pytest.raises(DatabaseError), transaction.atomic():
        ClientAssetDocumentProvenance.objects.filter(pk=provenance.pk).update(content_digest="0" * 64)
    with pytest.raises(DatabaseError), transaction.atomic():
        ClientAssetLifecycleEvent.objects.filter(pk=lifecycle_event.pk).update(to_state="repair")
    with pytest.raises(DatabaseError), transaction.atomic():
        ClientHardwareAsset.objects.filter(pk=profile.pk).update(serial_number="not-normalized")
