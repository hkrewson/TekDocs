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
from apps.core.models import ClientAsset, ClientAssetDocumentProvenance, InstallationState
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
