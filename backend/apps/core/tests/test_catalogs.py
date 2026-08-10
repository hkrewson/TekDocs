import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.catalogs import CatalogError, validate_specification_schema
from apps.core.models import (
    CatalogModelRevision,
    CatalogSpecificationDefinitionVersion,
    InstallationState,
)
from apps.core.organizations import create_organization, update_organization

HARDWARE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ports": {"type": "integer", "minimum": 1},
        "managed": {"type": "boolean"},
    },
    "required": ["ports"],
}


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Catalog MSP",
        owner_email="catalog-owner@example.invalid",
        owner_display_name="Catalog Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def supplier(installation):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Catalog Manufacturer",
        legal_name="Catalog Manufacturer, Inc.",
        website="https://catalog.example.invalid",
        classifications=["manufacturer"],
    )


@pytest.fixture
def client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def test_schema_contract_rejects_remote_and_open_ended_shapes():
    assert validate_specification_schema(HARDWARE_SCHEMA) == HARDWARE_SCHEMA
    with pytest.raises(CatalogError, match="closed object"):
        validate_specification_schema({"type": "object", "properties": {}})
    with pytest.raises(CatalogError, match="unsupported schema keyword"):
        validate_specification_schema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"remote": {"$ref": "https://example.invalid/schema"}},
            }
        )
    with pytest.raises(CatalogError, match="unsupported schema keyword"):
        validate_specification_schema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"host": {"type": "string", "pattern": "(a+)+$"}},
            }
        )


@pytest.mark.django_db
def test_supplier_catalog_versions_specs_and_rejects_stale_model_write(client, installation, supplier):
    base = {"organization_entity_id": supplier.entity_id}
    definition_response = client.post(
        reverse("organization-catalog-specification-definition-list-create", kwargs=base),
        data={"name": "Managed switch", "product_kind": "hardware", "schema": HARDWARE_SCHEMA},
        content_type="application/json",
    )
    assert definition_response.status_code == 201
    definition = definition_response.json()
    version_id = definition["versions"][0]["id"]
    assert len(definition["versions"][0]["checksum"]) == 64

    product_response = client.post(
        reverse("organization-catalog-product-list-create", kwargs=base),
        data={"name": "EdgeSwitch", "kind": "hardware", "description": "Managed edge switching"},
        content_type="application/json",
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]
    model_collection = reverse(
        "organization-catalog-model-list-create", kwargs={**base, "product_entity_id": product_id}
    )
    invalid = client.post(
        model_collection,
        data={
            "name": "EdgeSwitch 24",
            "model_number": "ES-24",
            "specification_version_id": version_id,
            "lifecycle": "active",
            "specifications": {"ports": 0},
            "notes": "",
        },
        content_type="application/json",
    )
    assert invalid.status_code == 400
    created = client.post(
        model_collection,
        data={
            "name": "EdgeSwitch 24",
            "model_number": "ES-24",
            "specification_version_id": version_id,
            "lifecycle": "active",
            "specifications": {"ports": 24, "managed": True},
            "notes": "Initial specification",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    model = created.json()
    base_revision = model["current_revision"]["id"]
    detail = reverse(
        "organization-catalog-model-detail",
        kwargs={**base, "product_entity_id": product_id, "model_entity_id": model["id"]},
    )
    revision_payload = {
        "base_revision_id": base_revision,
        "name": "EdgeSwitch 24 PoE",
        "model_number": "ES-24-POE",
        "specification_version_id": version_id,
        "lifecycle": "active",
        "specifications": {"ports": 24, "managed": True},
        "notes": "PoE-capable revision",
    }
    revised = client.patch(detail, data=revision_payload, content_type="application/json")
    assert revised.status_code == 200
    assert revised.json()["current_revision"]["revision"] == 2
    assert len(revised.json()["revisions"]) == 2
    stale = client.patch(detail, data=revision_payload, content_type="application/json")
    assert stale.status_code == 409
    assert stale.json()["current_revision"]["revision"] == 2


@pytest.mark.django_db
def test_catalog_requires_supplier_classification_and_exact_workspace(client, installation, supplier):
    client_org = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Client Only",
        legal_name="",
        website="",
        classifications=["client"],
    )
    denied = client.get(
        reverse(
            "organization-catalog-product-list-create",
            kwargs={"organization_entity_id": client_org.entity_id},
        )
    )
    assert denied.status_code == 403

    created = client.post(
        reverse(
            "organization-catalog-product-list-create",
            kwargs={"organization_entity_id": supplier.entity_id},
        ),
        data={"name": "Scoped product", "kind": "software", "description": ""},
        content_type="application/json",
    )
    product_id = created.json()["id"]
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Vendor",
        legal_name="",
        website="",
        classifications=["vendor"],
    )
    hidden = client.get(
        reverse(
            "organization-catalog-product-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "product_entity_id": product_id},
        )
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_supplier_with_catalog_must_retain_supplier_classification(client, installation, supplier):
    response = client.post(
        reverse(
            "organization-catalog-product-list-create",
            kwargs={"organization_entity_id": supplier.entity_id},
        ),
        data={"name": "Classification guard", "kind": "hardware", "description": ""},
        content_type="application/json",
    )
    assert response.status_code == 201

    with pytest.raises(ValidationError, match="must remain classified"):
        update_organization(
            organization=supplier,
            actor_id=installation.owner.id,
            name=supplier.entity.display_name,
            legal_name=supplier.legal_name,
            website=supplier.website,
            classifications=["client"],
        )

    update_organization(
        organization=supplier,
        actor_id=installation.owner.id,
        name=supplier.entity.display_name,
        legal_name=supplier.legal_name,
        website=supplier.website,
        classifications=["vendor"],
    )
    assert list(supplier.classifications.values_list("kind", flat=True)) == ["vendor"]


@pytest.mark.django_db(transaction=True)
def test_postgres_catalog_history_is_append_only(client, installation, supplier):
    if connection.vendor != "postgresql":
        pytest.skip("Catalog database guards require PostgreSQL")
    response = client.post(
        reverse(
            "organization-catalog-specification-definition-list-create",
            kwargs={"organization_entity_id": supplier.entity_id},
        ),
        data={"name": "Immutable", "product_kind": "hardware", "schema": HARDWARE_SCHEMA},
        content_type="application/json",
    )
    version = CatalogSpecificationDefinitionVersion.objects.get(id=response.json()["versions"][0]["id"])
    with pytest.raises(ValidationError, match="immutable"):
        version.save()
    with pytest.raises(DatabaseError), transaction.atomic():
        CatalogSpecificationDefinitionVersion.objects.filter(pk=version.pk).update(checksum="0" * 64)
    assert CatalogModelRevision.objects.count() == 0
