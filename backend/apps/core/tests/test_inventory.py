import csv
import io
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.asset_csv import FIELDS, SCHEMA_VERSION
from apps.core.models import (
    ClientAsset,
    ClientAssetDocumentProvenance,
    ClientAssetLifecycleEvent,
    ClientHardwareAsset,
    ClientSoftwareInstallation,
    InstallationState,
    SoftwareLicenseEvent,
)
from apps.core.organizations import create_organization
from apps.core.rls_contract import RUNTIME_ROLE
from apps.core.software_inventory import SoftwareInventoryError, assign_seat

HARDWARE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {"ports": {"type": "integer", "minimum": 1}},
    "required": ["ports"],
}

SOFTWARE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {"platform": {"type": "string"}},
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
    approver = User.objects.create_user(
        email=f"catalog-approver-{uuid.uuid4()}@example.invalid",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
        display_name="Catalog Approver",
    )
    membership = TenantMembership.objects.create(
        tenant=supplier.tenant,
        user=approver,
        role=BuiltInRole.ADMINISTRATOR,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=supplier.tenant,
        organization=supplier,
        membership=membership,
        created_by=supplier.tenant.installation_state.owner,
    )
    TOTP.activate(approver, generate_totp_secret())
    approver_client = Client(enforce_csrf_checks=False)
    approver_client.force_login(approver)
    approval = approver_client.post(
        reverse(
            "organization-document-publication-approve",
            kwargs={**base, "document_entity_id": document["id"], "publication_entity_id": publication["id"]},
        ),
        {"reason": "Independent catalog publication approval"},
        content_type="application/json",
    )
    assert approval.status_code == 200
    publication = approval.json()
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


def _software_asset(owner_client, installation, supplier, client, name="Endpoint agent"):  # type: ignore[no-untyped-def]
    base = {"organization_entity_id": supplier.entity_id}
    definition = owner_client.post(
        reverse("organization-catalog-specification-definition-list-create", kwargs=base),
        {"name": "Software deployment", "product_kind": "software", "schema": SOFTWARE_SCHEMA},
        content_type="application/json",
    ).json()
    product = owner_client.post(
        reverse("organization-catalog-product-list-create", kwargs=base),
        {"name": "Secure Agent", "kind": "software", "description": "Managed endpoint agent"},
        content_type="application/json",
    ).json()
    model = owner_client.post(
        reverse("organization-catalog-model-list-create", kwargs={**base, "product_entity_id": product["id"]}),
        {
            "name": "Secure Agent Desktop", "model_number": "SA-DESKTOP",
            "specification_version_id": definition["versions"][0]["id"], "lifecycle": "active",
            "specifications": {"platform": "desktop"}, "notes": "",
        },
        content_type="application/json",
    ).json()
    return owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"model_id": model["id"], "name": name}, content_type="application/json",
    ).json()


def _asset_csv(*rows):  # type: ignore[no-untyped-def]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for values in rows:
        writer.writerow({field: values.get(field, "") for field in FIELDS})
    return output.getvalue().encode()


def _csv_upload(content):  # type: ignore[no-untyped-def]
    return SimpleUploadedFile("assets.csv", content, content_type="text/csv")


@pytest.mark.django_db
def test_asset_csv_preview_apply_retry_export_and_workspace_isolation(owner_client, installation):
    supplier = _organization(installation, "CSV Hardware", "manufacturer")
    client = _organization(installation, "CSV Client", "client")
    other_client = _organization(installation, "Other CSV Client", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)
    content = _asset_csv(
        {
            "schema_version": SCHEMA_VERSION,
            "import_key": "switch-001",
            "name": "=Core switch",
            "kind": "hardware",
            "model_id": model["id"],
            "serial_number": "csv-001",
            "asset_tag": "edge-001",
            "lifecycle_state": "in_service",
            "acquired_on": "2026-08-10",
            "acquisition_method": "purchase",
        }
    )
    base = {"organization_entity_id": client.entity_id}
    preview = owner_client.post(
        reverse("organization-asset-csv-preview", kwargs=base),
        {"file": _csv_upload(content)},
    )
    assert preview.status_code == 200
    assert preview.json()["summary"] == {"total": 1, "create": 1, "update": 0, "skip": 0, "errors": 0}
    token = preview.json()["preview_token"]

    applied = owner_client.post(
        reverse("organization-asset-csv-apply", kwargs=base),
        {"file": _csv_upload(content), "preview_token": token},
    )
    assert applied.status_code == 200
    assert applied.json() == {"created": 1, "updated": 0, "skipped": 0}
    asset = ClientAsset.objects.select_related("entity", "hardware").get(organization=client)
    assert asset.entity.display_name == "=Core switch"
    assert asset.hardware.serial_number == "CSV-001"

    retry_preview = owner_client.post(
        reverse("organization-asset-csv-preview", kwargs=base),
        {"file": _csv_upload(content)},
    ).json()
    assert retry_preview["summary"]["skip"] == 1
    retry = owner_client.post(
        reverse("organization-asset-csv-apply", kwargs=base),
        {"file": _csv_upload(content), "preview_token": retry_preview["preview_token"]},
    )
    assert retry.json() == {"created": 0, "updated": 0, "skipped": 1}
    assert ClientAsset.objects.filter(organization=client).count() == 1

    exported = owner_client.get(reverse("organization-asset-csv-export", kwargs=base))
    assert exported.status_code == 200
    assert b"'=Core switch" in exported.content
    assert b"credential" not in exported.content.lower()
    assert owner_client.get(reverse("organization-asset-csv-template", kwargs=base)).content == _asset_csv()

    cross_scope = _asset_csv(
        {
            "schema_version": SCHEMA_VERSION,
            "asset_id": str(asset.entity_id),
            "name": "Cross-scope update",
            "kind": "hardware",
            "model_id": model["id"],
        }
    )
    rejected = owner_client.post(
        reverse(
            "organization-asset-csv-preview",
            kwargs={"organization_entity_id": other_client.entity_id},
        ),
        {"file": _csv_upload(cross_scope)},
    )
    assert rejected.status_code == 200
    assert rejected.json()["summary"]["errors"] == 1
    assert rejected.json()["preview_token"] is None


@pytest.mark.django_db
def test_asset_csv_rejects_hostile_files_and_duplicate_identifiers_before_apply(owner_client, installation):
    supplier = _organization(installation, "CSV Rollback Hardware", "manufacturer")
    client = _organization(installation, "CSV Rollback Client", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)
    base = {"organization_entity_id": client.entity_id}
    hostile = owner_client.post(
        reverse("organization-asset-csv-preview", kwargs=base),
        {"file": _csv_upload(b"schema_version\x00,asset_id\n")},
    )
    assert hostile.status_code == 400
    assert "null bytes" in str(hostile.json())

    common = {
        "schema_version": SCHEMA_VERSION,
        "kind": "hardware",
        "model_id": model["id"],
        "serial_number": "DUPLICATE-001",
    }
    content = _asset_csv(
        {**common, "import_key": "first", "name": "First switch"},
        {**common, "import_key": "second", "name": "Second switch"},
    )
    preview = owner_client.post(
        reverse("organization-asset-csv-preview", kwargs=base),
        {"file": _csv_upload(content)},
    ).json()
    assert preview["summary"]["errors"] == 1
    assert preview["preview_token"] is None
    assert ClientAsset.objects.filter(organization=client).count() == 0


@pytest.mark.django_db
def test_msp_assets_are_owned_not_aggregated_and_cannot_cross_workspace(owner_client, installation):
    supplier = _organization(installation, "Parity Hardware", "manufacturer")
    client = _organization(installation, "Parity Client", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)

    client_asset = owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"model_id": model["id"], "name": "Client switch"},
        content_type="application/json",
    )
    msp_asset = owner_client.post(
        reverse("msp-asset-list-create"),
        {"model_id": model["id"], "name": "MSP switch"},
        content_type="application/json",
    )
    assert client_asset.status_code == 201
    assert msp_asset.status_code == 201

    msp_list = owner_client.get(reverse("msp-asset-list-create"))
    client_list = owner_client.get(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id})
    )
    assert [record["name"] for record in msp_list.json()["results"]] == ["MSP switch"]
    assert [record["name"] for record in client_list.json()["results"]] == ["Client switch"]
    assert (
        owner_client.get(reverse("msp-asset-detail", kwargs={"asset_entity_id": client_asset.json()["id"]})).status_code
        == 404
    )
    assert (
        owner_client.get(
            reverse(
                "organization-client-asset-detail",
                kwargs={"organization_entity_id": client.entity_id, "asset_entity_id": msp_asset.json()["id"]},
            )
        ).status_code
        == 404
    )

    msp_hardware = ClientAsset.objects.select_related("hardware").get(entity_id=msp_asset.json()["id"])
    assert msp_hardware.organization_id is None
    assert msp_hardware.hardware.organization_id is None
    assert ClientAssetLifecycleEvent.objects.get(asset=msp_hardware).organization_id is None


@pytest.mark.django_db
def test_asset_relationships_and_atomic_bulk_actions_remain_exact_workspace(owner_client, installation):
    supplier = _organization(installation, "Bulk Supplier", "manufacturer")
    client = _organization(installation, "Bulk Client", "client")
    sibling = _organization(installation, "Bulk Sibling", "client")
    _definition, _product, model, _document, _publication = _catalog(owner_client, supplier)
    collection = reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id})
    first = owner_client.post(
        collection,
        {"model_id": model["id"], "name": "Core switch"},
        content_type="application/json",
    ).json()
    second = owner_client.post(
        collection,
        {"model_id": model["id"], "name": "Access switch"},
        content_type="application/json",
    ).json()
    sibling_asset = owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": sibling.entity_id}),
        {"model_id": model["id"], "name": "Sibling switch"},
        content_type="application/json",
    ).json()

    listed = owner_client.get(collection).json()
    assert listed["can_view_relationships"] is True
    search = owner_client.get(
        reverse("organization-entity-search", kwargs={"organization_entity_id": client.entity_id}),
        {"entity_type": "client_asset", "q": "switch"},
    ).json()
    assert {item["display_name"] for item in search["results"]} == {"Core switch", "Access switch"}
    relationship_url = reverse(
        "organization-entity-relationship-list-create",
        kwargs={"organization_entity_id": client.entity_id, "entity_id": first["id"]},
    )
    linked = owner_client.post(
        relationship_url,
        {"target_id": second["id"], "link_type": "depends_on"},
        content_type="application/json",
    )
    assert linked.status_code == 201
    assert linked.json()["related_entity"]["id"] == second["id"]

    bulk_url = reverse("organization-client-asset-bulk", kwargs={"organization_entity_id": client.entity_id})
    changed = owner_client.post(
        bulk_url,
        {"asset_ids": [first["id"], second["id"]], "action": "set_hardware_state", "lifecycle_state": "repair"},
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert changed.json() == {"action": "set_hardware_state", "processed": 2}
    assert set(
        ClientHardwareAsset.objects.filter(asset__entity_id__in=(first["id"], second["id"])).values_list(
            "lifecycle_state", flat=True
        )
    ) == {"repair"}

    software = _software_asset(owner_client, installation, supplier, client, name="Managed agent")
    mixed = owner_client.post(
        bulk_url,
        {
            "asset_ids": [first["id"], software["id"]],
            "action": "set_hardware_state",
            "lifecycle_state": "in_service",
        },
        content_type="application/json",
    )
    assert mixed.status_code == 400
    assert ClientHardwareAsset.objects.get(asset__entity_id=first["id"]).lifecycle_state == "repair"

    cross_scope = owner_client.post(
        bulk_url,
        {"asset_ids": [first["id"], sibling_asset["id"]], "action": "archive"},
        content_type="application/json",
    )
    assert cross_scope.status_code == 400
    assert ClientAsset.objects.get(entity_id=first["id"]).archived_at is None

    retained_before = ClientAsset.objects.select_related("entity", "hardware").get(entity_id=first["id"])
    retained_identity = {
        "entity_id": retained_before.entity_id,
        "workspace_id": retained_before.entity.workspace_id,
        "supplier_id": retained_before.supplier_id,
        "product_id": retained_before.product_id,
        "model_id": retained_before.model_id,
        "model_revision_id": retained_before.model_revision_id,
        "specification_version_id": retained_before.specification_version_id,
        "provenance_checksum": retained_before.provenance_checksum,
        "lifecycle_state": retained_before.hardware.lifecycle_state,
    }

    archived = owner_client.post(
        bulk_url,
        {"asset_ids": [first["id"], second["id"]], "action": "archive"},
        content_type="application/json",
    )
    assert archived.status_code == 200
    assert [item["name"] for item in owner_client.get(collection).json()["results"]] == ["Managed agent"]
    recycle = owner_client.get(
        reverse("organization-recycle-bin", kwargs={"organization_entity_id": client.entity_id})
    ).json()
    assert {item["record_type"] for item in recycle["results"]} == {"client_asset"}
    restored = owner_client.post(
        reverse(
            "organization-recycle-bin-restore",
            kwargs={
                "organization_entity_id": client.entity_id,
                "record_type": "client_asset",
                "record_id": first["id"],
            },
        ),
        content_type="application/json",
    )
    assert restored.status_code == 204
    assert owner_client.get(collection).json()["count"] == 2
    retained_after = ClientAsset.objects.select_related("entity", "hardware").get(entity_id=first["id"])
    assert {
        "entity_id": retained_after.entity_id,
        "workspace_id": retained_after.entity.workspace_id,
        "supplier_id": retained_after.supplier_id,
        "product_id": retained_after.product_id,
        "model_id": retained_after.model_id,
        "model_revision_id": retained_after.model_revision_id,
        "specification_version_id": retained_after.specification_version_id,
        "provenance_checksum": retained_after.provenance_checksum,
        "lifecycle_state": retained_after.hardware.lifecycle_state,
    } == retained_identity


@pytest.mark.django_db
def test_msp_software_license_retains_exact_null_owner_scope(owner_client, installation):
    supplier = _organization(installation, "Parity Software", "vendor")
    base = {"organization_entity_id": supplier.entity_id}
    definition = owner_client.post(
        reverse("organization-catalog-specification-definition-list-create", kwargs=base),
        {"name": "MSP software", "product_kind": "software", "schema": SOFTWARE_SCHEMA},
        content_type="application/json",
    ).json()
    product = owner_client.post(
        reverse("organization-catalog-product-list-create", kwargs=base),
        {"name": "MSP Agent", "kind": "software", "description": "Internal endpoint agent"},
        content_type="application/json",
    ).json()
    model = owner_client.post(
        reverse("organization-catalog-model-list-create", kwargs={**base, "product_entity_id": product["id"]}),
        {
            "name": "MSP Agent Desktop",
            "model_number": "MSP-AGENT",
            "specification_version_id": definition["versions"][0]["id"],
            "lifecycle": "active",
            "specifications": {"platform": "desktop"},
            "notes": "",
        },
        content_type="application/json",
    ).json()
    asset = owner_client.post(
        reverse("msp-asset-list-create"),
        {"model_id": model["id"], "name": "MSP managed agent"},
        content_type="application/json",
    )
    assert asset.status_code == 201
    license_response = owner_client.post(
        reverse("msp-software-license-list-create"),
        {
            "name": "MSP Agent entitlement",
            "asset_id": asset.json()["id"],
            "kind": "subscription",
            "status": "active",
            "seat_limit": 5,
            "renewal_interval": "annual",
            "auto_renew": True,
        },
        content_type="application/json",
    )
    assert license_response.status_code == 201
    stored = ClientSoftwareInstallation.objects.get(asset__entity_id=asset.json()["id"])
    assert stored.organization_id is None
    assert SoftwareLicenseEvent.objects.get(license__entity_id=license_response.json()["id"]).organization_id is None


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
    person_response = owner_client.post(
        reverse("organization-people-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"full_name": "Morgan Ellis", "kind": "contact", "email": "morgan@example.invalid", "site_id": site["id"]},
        content_type="application/json",
    )
    assert person_response.status_code == 201
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
        "created",
        "state_changed",
        "assigned",
        "unassigned",
        "disposed",
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


@pytest.mark.django_db
def test_software_installation_license_seats_renewal_and_isolation(owner_client, installation):
    supplier = _organization(installation, "License Supplier", "vendor")
    client = _organization(installation, "Licensed Client", "client")
    sibling = _organization(installation, "Sibling License Client", "client")
    asset = _software_asset(owner_client, installation, supplier, client)
    assert asset["software_installation"]["status"] == "planned"
    assert asset["hardware"] is None
    asset_base = {"organization_entity_id": client.entity_id, "asset_entity_id": asset["id"]}
    updated = owner_client.patch(
        reverse("organization-client-software-detail", kwargs=asset_base),
        {"status": "installed", "installed_version": "7.4.1", "installed_on": "2026-08-10"},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["installed_version"] == "7.4.1"

    person_response = owner_client.post(
        reverse("organization-people-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"full_name": "Avery Chen", "kind": "contact", "email": "avery@example.invalid"},
        content_type="application/json",
    )
    assert person_response.status_code == 201
    license_record = owner_client.post(
        reverse("organization-software-license-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {
            "name": "Secure Agent annual entitlement",
            "asset_id": asset["id"],
            "kind": "subscription",
            "seat_limit": 1,
            "starts_on": "2026-08-01",
            "renews_on": "2027-08-01",
            "ends_on": "2027-08-31",
            "renewal_interval": "annual",
            "auto_renew": True,
            "reference": "CONTRACT-REFERENCE",
        },
        content_type="application/json",
    )
    assert license_record.status_code == 201
    payload = license_record.json()
    assert payload["product_name"] == "Secure Agent"
    assert payload["renewal_interval"] == "annual"
    assert payload["reference"] == "CONTRACT-REFERENCE"
    installation_id = payload["installations"][0]["id"]
    second_asset = owner_client.post(
        reverse("organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"model_id": asset["model_id"], "name": "Second secured endpoint"},
        content_type="application/json",
    ).json()
    second_installation_id = second_asset["software_installation"]["id"]
    asset_collection = reverse(
        "organization-client-asset-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    first_asset_page = owner_client.get(asset_collection, {"page": 1, "page_size": 1})
    assert first_asset_page.status_code == 200
    assert first_asset_page.json()["count"] == 2
    assert first_asset_page.json()["has_more"] is True
    assert len(first_asset_page.json()["results"]) == 1
    assert owner_client.get(asset_collection, {"page": 2, "page_size": 1}).json()["has_more"] is False
    assert owner_client.get(asset_collection, {"page_size": 101}).status_code == 400

    license_collection = reverse(
        "organization-software-license-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    license_page = owner_client.get(license_collection, {"page": 1, "page_size": 1})
    assert license_page.status_code == 200
    assert license_page.json()["page"] == 1
    assert license_page.json()["page_size"] == 1
    assert license_page.json()["count"] == 1
    assert license_page.json()["has_more"] is False
    assert owner_client.get(license_collection, {"page_size": 101}).status_code == 400
    linked = owner_client.post(
        reverse(
            "organization-software-license-installation",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"installation_id": second_installation_id},
        content_type="application/json",
    )
    assert linked.status_code == 200
    assert {item["id"] for item in linked.json()["installations"]} == {installation_id, second_installation_id}
    choices = owner_client.get(
        reverse("organization-software-license-choices", kwargs={"organization_entity_id": client.entity_id})
    ).json()
    person_id = choices["people"][0]["id"]
    sibling_person = owner_client.post(
        reverse("organization-people-list-create", kwargs={"organization_entity_id": sibling.entity_id}),
        {"full_name": "Hidden License User", "kind": "contact", "email": "hidden-license@example.invalid"},
        content_type="application/json",
    ).json()
    foreign_target = owner_client.post(
        reverse(
            "organization-software-license-seat",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"person_id": sibling_person["id"]},
        content_type="application/json",
    )
    assert foreign_target.status_code == 400
    assert b"Hidden License User" not in foreign_target.content

    seat = owner_client.post(
        reverse(
            "organization-software-license-seat",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"person_id": person_id, "installation_id": installation_id},
        content_type="application/json",
    )
    assert seat.status_code == 200
    assert seat.json()["active_seats"] == 1
    assert seat.json()["seats"][0]["person_name"] == "Avery Chen"
    exhausted = owner_client.post(
        reverse(
            "organization-software-license-seat",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"installation_id": installation_id},
        content_type="application/json",
    )
    assert exhausted.status_code == 400
    assert b"No seats" in exhausted.content
    lower_limit = owner_client.patch(
        reverse(
            "organization-software-license-detail",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"seat_limit": 0},
        content_type="application/json",
    )
    assert lower_limit.status_code == 400
    seat_id = seat.json()["seats"][0]["id"]
    revoked = owner_client.delete(
        reverse(
            "organization-software-license-seat-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "license_entity_id": payload["id"],
                "seat_id": seat_id,
            },
        )
    )
    assert revoked.status_code == 200
    assert revoked.json()["active_seats"] == 0
    changed = owner_client.patch(
        reverse(
            "organization-software-license-detail",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"name": "Secure Agent renewed entitlement", "renews_on": "2027-09-01", "status": "suspended"},
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert changed.json()["name"] == "Secure Agent renewed entitlement"
    assert changed.json()["renews_on"] == "2027-09-01"
    inactive_assignment = owner_client.post(
        reverse(
            "organization-software-license-seat",
            kwargs={"organization_entity_id": client.entity_id, "license_entity_id": payload["id"]},
        ),
        {"installation_id": second_installation_id},
        content_type="application/json",
    )
    assert inactive_assignment.status_code == 400
    assert b"active license" in inactive_assignment.content
    sibling_read = owner_client.get(
        reverse(
            "organization-software-license-detail",
            kwargs={"organization_entity_id": sibling.entity_id, "license_entity_id": payload["id"]},
        )
    )
    assert sibling_read.status_code == 404
    event_types = SoftwareLicenseEvent.objects.filter(license__entity_id=payload["id"]).values_list(
        "event_type", flat=True
    )
    assert set(event_types) == {"created", "installation_linked", "seat_assigned", "seat_revoked", "details_updated"}


@pytest.mark.django_db(transaction=True)
def test_concurrent_license_seat_allocation_never_exceeds_limit(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Seat-allocation concurrency certification requires PostgreSQL")
    supplier = _organization(installation, "Concurrent License Supplier", "vendor")
    client = _organization(installation, "Concurrent License Client", "client")
    asset = _software_asset(owner_client, installation, supplier, client, name="Concurrent endpoint agent")
    people = []
    for index in range(2):
        response = owner_client.post(
            reverse("organization-people-list-create", kwargs={"organization_entity_id": client.entity_id}),
            {
                "full_name": f"Concurrent User {index}",
                "kind": "contact",
                "email": f"concurrent-{index}@example.invalid",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        people.append(uuid.UUID(response.json()["association_id"]))
    created = owner_client.post(
        reverse("organization-software-license-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"name": "One-seat entitlement", "asset_id": asset["id"], "kind": "subscription", "seat_limit": 1},
        content_type="application/json",
    )
    assert created.status_code == 201
    license_id = uuid.UUID(created.json()["id"])
    barrier = threading.Barrier(2)

    def allocate(person_id):  # type: ignore[no-untyped-def]
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            record = installation.tenant.software_licenses.get(entity_id=license_id)
            assign_seat(license_record=record, actor_id=installation.owner.id, person_id=person_id)
            return "assigned"
        except SoftwareInventoryError:
            return "full"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(allocate, people))
    assert outcomes == ["assigned", "full"]
    license_record = installation.tenant.software_licenses.get(entity_id=license_id)
    assert license_record.seats.filter(revoked_at__isnull=True).count() == 1
    assert SoftwareLicenseEvent.objects.filter(license=license_record, event_type="seat_assigned").count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_software_license_history_mutation(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Software licensing database guards require PostgreSQL")
    supplier = _organization(installation, "Software Guard Supplier", "manufacturer")
    client = _organization(installation, "Software Guard Client", "client")
    asset = _software_asset(owner_client, installation, supplier, client, "Guarded agent")
    created = owner_client.post(
        reverse("organization-software-license-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"name": "Guarded license", "asset_id": asset["id"], "kind": "perpetual", "seat_limit": 1},
        content_type="application/json",
    ).json()
    event = SoftwareLicenseEvent.objects.get(license__entity_id=created["id"])
    with pytest.raises(DatabaseError), transaction.atomic():
        SoftwareLicenseEvent.objects.filter(pk=event.pk).update(event_type="details_updated")


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
        cursor.execute("SELECT set_config('tekdocs.user_id', %s, true)", [str(installation.owner.id)])
        cursor.execute("SELECT set_config('tekdocs.principal_mode', 'user', true)")
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
        cursor.execute("SELECT set_config('tekdocs.organization_id', '', true)")
        cursor.execute("SELECT set_config('tekdocs.organization_mode', 'msp', true)")
        cursor.execute("SELECT id FROM core_entity WHERE id = %s", [supplier.entity_id])
        assert cursor.fetchone() == (supplier.entity_id,)
        cursor.execute("SELECT id FROM core_documentpublication WHERE id = %s", [provenance.publication_id])
        assert cursor.fetchone() == (provenance.publication_id,)
        cursor.execute("SELECT id FROM core_entity WHERE display_name = 'Supplier internal notes'")
        assert cursor.fetchall() == []
        cursor.execute(
            "SELECT tekdocs_msp_catalog_publication_visible(%s, %s)",
            [provenance.publication_id, installation.tenant.id],
        )
        assert cursor.fetchone() == (True,)
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(uuid.uuid4())])
        cursor.execute(
            "SELECT tekdocs_client_catalog_publication_visible(%s, %s)",
            [provenance.publication_id, installation.tenant.id],
        )
        assert cursor.fetchone() == (False,)
        cursor.execute(
            "SELECT tekdocs_msp_catalog_publication_visible(%s, %s)",
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
