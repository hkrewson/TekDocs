import csv
import io
import os
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.asset_csv import FIELDS, SCHEMA_VERSION, apply_assets_csv, preview_assets_csv
from apps.core.catalogs import create_definition, create_model, create_product
from apps.core.commercial import create_contract, create_cost
from apps.core.credential_references import create_credential_reference, normalize_credential_reference
from apps.core.document_attachments import create_document_attachment
from apps.core.documents import create_document
from apps.core.inventory import create_client_asset, update_hardware_details
from apps.core.models import (
    AuditEvent,
    ClientAsset,
    CommercialContract,
    CredentialReference,
    DocumentAttachment,
    InstallationState,
    SoftwareLicense,
    SoftwareLicenseSeat,
)
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, rls_scope
from apps.core.scoping import DataScope
from apps.core.software_inventory import assign_seat, create_license, link_installation

PRIVATE_LINK = (
    "https://start.1password.com/open/i?"
    "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
    "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
)


def model(result, supplier, kind):
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
        name=f"Recovery {kind} schema",
        product_kind=kind,
        schema=schema,
    )
    product = create_product(
        tenant=result.tenant,
        organization=supplier,
        actor_id=result.owner.id,
        name=f"Recovery {kind} product",
        kind=kind,
        description="Retained inventory recovery fixture",
    )
    return create_model(
        product=product,
        actor_id=result.owner.id,
        name=f"Recovery {kind} model",
        model_number=f"REC-{kind.upper()}",
        specification_version=definition.versions.get(version=1),
        lifecycle="active",
        specifications={},
        notes="",
    )


def csv_bytes(model_id):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            **{field: "" for field in FIELDS},
            "schema_version": SCHEMA_VERSION,
            "import_key": "recovery-import-001",
            "name": "Recovery imported switch",
            "kind": "hardware",
            "model_id": str(model_id),
            "serial_number": "RECOVERY-CSV-001",
            "lifecycle_state": "in_stock",
        }
    )
    return output.getvalue().encode("utf-8")


def create_fixture():
    result = bootstrap_owner(
        tenant_name="Inventory Recovery MSP",
        owner_email="inventory-recovery@example.invalid",
        owner_display_name="Inventory Recovery Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        supplier = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Recovery Supplier",
            legal_name="Recovery Supplier, Inc.",
            website="",
            classifications=["vendor"],
        )
        client = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Recovery Client",
            legal_name="Recovery Client, LLC",
            website="",
            classifications=["client"],
        )
        bind_local_rls_scope(
            DataScope.organization(result.tenant, supplier),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        hardware_model = model(result, supplier, "hardware")
        software_model = model(result, supplier, "software")
        bind_local_rls_scope(
            DataScope.organization(result.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        hardware = create_client_asset(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            model_entity_id=hardware_model.entity_id,
            name="Recovery core switch",
        )
        update_hardware_details(
            asset=hardware,
            actor_id=result.owner.id,
            values={"serial_number": "RECOVERY-SERIAL-001", "asset_tag": "RECOVERY-TAG-001", "lifecycle_state": "in_service"},
        )
        software = create_client_asset(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            model_entity_id=software_model.entity_id,
            name="Recovery endpoint agent",
        )
        license_record = create_license(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            asset=software,
            values={
                "name": "Recovery endpoint entitlement",
                "kind": "subscription",
                "status": "active",
                "seat_limit": 5,
                "renewal_interval": "annual",
                "auto_renew": True,
                "reference": "RECOVERY-LICENSE",
            },
        )
        link_installation(
            license_record=license_record,
            actor_id=result.owner.id,
            installation_id=software.software_installation.id,
        )
        assign_seat(
            license_record=license_record,
            actor_id=result.owner.id,
            installation_id=software.software_installation.id,
        )
        contract = create_contract(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            values={
                "name": "Recovery support agreement",
                "provider_id": supplier.entity_id,
                "kind": "support",
                "status": "active",
                "description": "Recovery fixture",
                "reference": "RECOVERY-CONTRACT",
                "auto_renew": False,
                "renewal_notice_days": 30,
            },
        )
        create_cost(
            contract=contract,
            actor_id=result.owner.id,
            values={"label": "Recovery service", "amount": "42.00", "currency": "USD", "billing_interval": "monthly", "quantity": "1"},
        )
        create_credential_reference(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Recovery firewall credential",
            provider="onepassword",
            reference_url=PRIVATE_LINK,
        )
        content = csv_bytes(hardware_model.entity_id)
        scope = DataScope.organization(result.tenant, client)
        preview = preview_assets_csv(scope=scope, content=content)
        applied = apply_assets_csv(
            scope=scope,
            content=content,
            preview_token=preview["preview_token"],
            actor_id=result.owner.id,
            tenant=result.tenant,
            organization=client,
        )
        imported = ClientAsset.objects.get(entity__display_name="Recovery imported switch")
        assert imported.entity_id == uuid.uuid5(imported.entity.workspace_id, "recovery-import-001")
        assert applied == {"created": 1, "updated": 0, "skipped": 0}
        document = create_document(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Recovery inventory attachment",
            markdown="# Recovery inventory\n",
        )
        create_document_attachment(
            document=document,
            actor_id=result.owner.id,
            upload=SimpleUploadedFile("inventory-recovery.txt", b"inventory recovery bytes\n", content_type="text/plain"),
        )
    print("Inventory certification fixture created")


def verify_fixture():
    tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED):
        client = tenant.organizations.get(entity__display_name="Recovery Client")
        bind_local_rls_scope(
            DataScope.organization(tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        assets = ClientAsset.objects.filter(organization=client).select_related(
            "entity", "hardware", "model_revision", "specification_version"
        )
        assert assets.count() == 3
        hardware = assets.get(entity__display_name="Recovery core switch")
        assert hardware.entity.workspace.organization_id == client.id
        assert hardware.hardware.serial_number == "RECOVERY-SERIAL-001"
        assert hardware.hardware.lifecycle_state == "in_service"
        assert len(hardware.provenance_checksum) == 64
        imported = assets.get(entity__display_name="Recovery imported switch")
        assert imported.entity_id == uuid.uuid5(imported.entity.workspace_id, "recovery-import-001")
        assert imported.hardware.serial_number == "RECOVERY-CSV-001"
        assert imported.entity.workspace_id == hardware.entity.workspace_id
        license_record = SoftwareLicense.objects.get(entity__display_name="Recovery endpoint entitlement")
        seat = SoftwareLicenseSeat.objects.get(license=license_record, revoked_at__isnull=True)
        assert seat.installation.asset.entity.display_name == "Recovery endpoint agent"
        contract = CommercialContract.objects.get(entity__display_name="Recovery support agreement")
        assert contract.costs.get().amount == 42
        reference = CredentialReference.objects.get(entity__display_name="Recovery firewall credential")
        assert normalize_credential_reference(reference.provider, reference.reference_url) == PRIVATE_LINK
        assert not AuditEvent.objects.filter(entity_id=reference.entity_id).exclude(metadata={}).exists()
        attachment = DocumentAttachment.objects.get(original_filename="inventory-recovery.txt")
        with attachment.file.storage.open(attachment.file.name, "rb") as stored:
            assert stored.read() == b"inventory recovery bytes\n"
    print("Inventory, credential reference, and managed bytes verified")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
