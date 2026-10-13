import csv
import io
import json
import secrets
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.imports import _decode_bundle, _decode_csv, create_preview, template_csv
from apps.core.models import ImportBatch, ImportExternalKey, ImportRow, InstallationState, Organization, Site, Workspace
from apps.core.workspaces import resolve_msp_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Import MSP",
        owner_email="import-owner@example.invalid",
        owner_display_name="Import Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def _csv(record_type: str, *rows: str) -> SimpleUploadedFile:
    header = template_csv(record_type).decode().strip()
    return SimpleUploadedFile(f"{record_type}.csv", ("\n".join((header, *rows)) + "\n").encode(), "text/csv")


def _damaged_bundle(kind):
    output = io.BytesIO()
    manifest = json.dumps({"format": "tekdocs-import", "version": 1})
    records = '{"record_type":"sites","external_key":"site-1","name":"Example"}'
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr("records.jsonl", records)
        if kind == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("records.jsonl", records)
    payload = output.getvalue()
    if kind == "manifest_crc":
        payload = payload.replace(manifest.encode(), b"x" + manifest.encode()[1:], 1)
    elif kind == "records_crc":
        payload = payload.replace(records.encode(), b"x" + records.encode()[1:], 1)
    return payload


@pytest.mark.parametrize("kind", ["manifest_crc", "records_crc", "duplicate"])
def test_bundle_decoder_rejects_corrupt_and_ambiguous_members(kind):
    with pytest.raises(ValidationError):
        _decode_bundle(_damaged_bundle(kind))


def test_csv_decoder_reports_parser_limits_as_validation_errors():
    payload = b"external_key,name\nsite-1," + b"x" * (csv.field_size_limit() + 1)
    with pytest.raises(ValidationError):
        _decode_csv(payload, record_type="sites")


@pytest.mark.parametrize("extra", ("private-unmapped-value", ""))
def test_csv_decoder_rejects_extra_cells_instead_of_discarding_them(extra):
    payload = f"external_key,name\nsite-1,Example,{extra}\n".encode()
    with pytest.raises(ValidationError) as caught:
        _decode_csv(payload, record_type="sites")
    assert str(caught.value.detail["file"]) == "CSV row 2 has more values than header columns."
    assert "private-unmapped-value" not in str(caught.value.detail)


def test_csv_decoder_preserves_quoted_commas_and_blank_optional_fields():
    rows = _decode_csv(b'external_key,name,code\nsite-1,"Office, West",\n', record_type="sites")
    assert rows[0]["name"] == "Office, West"
    assert rows[0]["code"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["manifest_crc", "records_crc", "duplicate", "csv_limit", "csv_extra"])
def test_invalid_import_container_returns_400_without_staging(installation, kind):
    browser = Client()
    browser.force_login(installation.owner)
    is_csv = kind.startswith("csv_")
    if kind == "csv_extra":
        payload = b"external_key,name\nsite-1,Example,private-unmapped-value\n"
    elif kind == "csv_limit":
        payload = b"external_key,name\nsite-1," + b"x" * (csv.field_size_limit() + 1)
    else:
        payload = _damaged_bundle(kind)
    response = browser.post(
        reverse("msp-import-list-create"),
        data={
            "source_format": "tekdocs_csv" if is_csv else "tekdocs_bundle",
            "record_type": "sites",
            "file": SimpleUploadedFile("invalid.csv" if is_csv else "invalid.zip", payload),
        },
    )
    assert response.status_code == 400
    assert not ImportBatch.objects.exists()
    assert not ImportRow.objects.exists()
    assert not Site.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["record_type", "external_key"])
@pytest.mark.parametrize(
    "bad_value,reason",
    [
        ({"nested": "invalid"}, "field_type_invalid"),
        ("=HYPERLINK(1)", "spreadsheet_formula_rejected"),
        ("x" * 500, "field_length_invalid"),
    ],
)
def test_invalid_import_identity_is_rejected_without_crashing_or_retaining_content(
    installation, field, bad_value, reason
):
    invalid = {
        "record_type": "sites",
        "external_key": "invalid-row",
        "name": "Do not retain this row",
        field: bad_value,
    }
    valid = {"record_type": "sites", "external_key": "valid-row", "name": "Valid site"}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "tekdocs-import", "version": 1}))
        archive.writestr("records.jsonl", "\n".join(json.dumps(row) for row in (invalid, valid)))
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.post(
        reverse("msp-import-list-create"),
        data={
            "source_format": "tekdocs_bundle",
            "file": SimpleUploadedFile("identities.zip", output.getvalue()),
        },
    )
    assert response.status_code == 201
    batch = ImportBatch.objects.get(pk=response.json()["id"])
    rejected, accepted = list(batch.rows.order_by("row_number"))
    assert (rejected.action, rejected.reason_code, rejected.normalized_data) == ("rejected", reason, {})
    assert rejected.record_type == ("unknown" if field == "record_type" else "sites")
    assert rejected.external_key == ("row-1" if field == "external_key" else "invalid-row")
    assert accepted.action == "create"
    assert accepted.external_key == "valid-row"
    assert (
        browser.post(
            reverse("msp-import-apply", kwargs={"batch_id": batch.id}), data="{}", content_type="application/json"
        ).status_code
        == 400
    )
    assert not Site.objects.exists()


@pytest.mark.django_db
def test_preview_is_side_effect_free_and_repeated_apply_is_idempotent(installation):
    workspace = resolve_msp_workspace(installation.owner)
    upload = _csv("organizations", "acme,Acme,Acme Inc.,https://acme.example,client")

    preview = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=upload,
        source_format="tekdocs_csv",
        record_type="organizations",
    )
    assert preview.result_counts == {"create": 1, "update": 0, "unchanged": 0, "conflict": 0, "rejected": 0}
    assert Organization.objects.count() == 0

    browser = Client()
    browser.force_login(installation.owner)
    response = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": preview.id}), data="{}", content_type="application/json"
    )
    assert response.status_code == 200
    assert Organization.objects.get().entity.display_name == "Acme"
    assert ImportExternalKey.objects.get(external_key="acme").local_entity.display_name == "Acme"
    assert ImportRow.objects.get(batch=preview).normalized_data == {}

    repeated = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=_csv("organizations", "acme,Acme,Acme Inc.,https://acme.example,client"),
        source_format="tekdocs_csv",
        record_type="organizations",
    )
    assert repeated.result_counts["unchanged"] == 1
    second = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": repeated.id}), data="{}", content_type="application/json"
    )
    assert second.status_code == 200
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_client_import_is_exact_workspace_and_cancel_erases_staging(installation):
    browser = Client()
    browser.force_login(installation.owner)
    organization_preview = create_preview(
        workspace=resolve_msp_workspace(installation.owner),
        actor_id=installation.owner.id,
        upload=_csv("organizations", "first,First client,,,client", "second,Second client,,,client"),
        source_format="tekdocs_csv",
        record_type="organizations",
    )
    assert (
        browser.post(
            reverse("msp-import-apply", kwargs={"batch_id": organization_preview.id}),
            data="{}",
            content_type="application/json",
        ).status_code
        == 200
    )
    first, second = list(Organization.objects.select_related("entity").order_by("entity__display_name"))

    preview_path = reverse("organization-import-list-create", kwargs={"organization_entity_id": first.entity_id})
    response = browser.post(
        preview_path,
        data={
            "source_format": "tekdocs_csv",
            "record_type": "sites",
            "file": _csv("sites", "hq,HQ,HQ,1 Main,,Town,IA,50000,US,America/Chicago,555-0100"),
        },
    )
    assert response.status_code == 201
    batch_id = response.json()["id"]
    sibling_rows = reverse(
        "organization-import-row-list",
        kwargs={"organization_entity_id": second.entity_id, "batch_id": batch_id},
    )
    assert browser.get(sibling_rows).status_code == 404

    sibling_workspace = Workspace.objects.get(organization=second)
    with pytest.raises(DatabaseError, match="import row batch scope mismatch"), transaction.atomic():
        ImportRow.objects.filter(batch_id=batch_id).update(workspace=sibling_workspace, organization=second)

    cancel_path = reverse(
        "organization-import-cancel",
        kwargs={"organization_entity_id": first.entity_id, "batch_id": batch_id},
    )
    assert browser.post(cancel_path, data="{}", content_type="application/json").status_code == 200
    assert ImportBatch.objects.get(pk=batch_id).state == "cancelled"
    assert ImportRow.objects.get(batch_id=batch_id).normalized_data == {}


@pytest.mark.django_db
def test_bundle_and_csv_reject_unsafe_or_secret_bearing_input(installation):
    workspace = resolve_msp_workspace(installation.owner)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "tekdocs-import", "version": 1}))
        archive.writestr(
            "records.jsonl",
            json.dumps(
                {
                    "record_type": "credential_references",
                    "external_key": "vault-1",
                    "title": "Firewall",
                    "provider": "onepassword",
                    "reference_url": "https://start.1password.com/open/i?a=abc&v=def&i=ghi&h=example.1password.com",
                    "password": "must-not-stage",
                }
            ),
        )
    batch = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("bundle.zip", output.getvalue(), "application/zip"),
        source_format="tekdocs_bundle",
    )
    row = ImportRow.objects.get(batch=batch)
    assert (row.action, row.reason_code, row.normalized_data) == ("rejected", "secret_field_rejected", {})

    browser = Client()
    browser.force_login(installation.owner)
    rejected_apply = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": batch.id}), data="{}", content_type="application/json"
    )
    assert rejected_apply.status_code == 400
    assert ImportBatch.objects.get(pk=batch.id).state == "preview_ready"

    formula = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=_csv("sites", 'formula,=HYPERLINK("https://example.invalid"),,,,,,,,,'),
        source_format="tekdocs_csv",
        record_type="sites",
    )
    assert ImportRow.objects.get(batch=formula).reason_code == "spreadsheet_formula_rejected"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "tekdocs-import", "version": 1}))
        archive.writestr("records.jsonl", "")
        archive.writestr("attachment.bin", b"unsupported")
    response = browser.post(
        reverse("msp-import-list-create"),
        data={
            "source_format": "tekdocs_bundle",
            "file": SimpleUploadedFile("unsafe.zip", output.getvalue(), "application/zip"),
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_possible_exact_name_match_requires_operator_confirmation(installation):
    workspace = resolve_msp_workspace(installation.owner)
    first = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=_csv("organizations", "first,Acme,,,client"),
        source_format="tekdocs_csv",
        record_type="organizations",
    )
    browser = Client()
    browser.force_login(installation.owner)
    assert (
        browser.post(
            reverse("msp-import-apply", kwargs={"batch_id": first.id}), data="{}", content_type="application/json"
        ).status_code
        == 200
    )

    conflict = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=_csv("organizations", "different-source-id,Acme,,,client"),
        source_format="tekdocs_csv",
        record_type="organizations",
    )
    row = ImportRow.objects.get(batch=conflict)
    assert (row.action, row.reason_code) == ("conflict", "possible_match_requires_confirmation")
    denied = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": conflict.id}), data="{}", content_type="application/json"
    )
    assert denied.status_code == 400
    entity_id = str(Organization.objects.get().entity_id)
    confirmed = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": conflict.id}),
        data=json.dumps({"matches": {str(row.id): entity_id}}),
        content_type="application/json",
    )
    assert confirmed.status_code == 200
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_apply_rolls_back_every_domain_write_when_a_later_row_fails(installation):
    workspace = resolve_msp_workspace(installation.owner)
    preview = create_preview(
        workspace=workspace,
        actor_id=installation.owner.id,
        upload=_csv(
            "sites",
            "good,Good site,,,,,,,,America/Chicago,",
            "bad,Bad site,,,,,,,,Not/A_Timezone,",
        ),
        source_format="tekdocs_csv",
        record_type="sites",
    )
    assert preview.result_counts["create"] == 2
    browser = Client()
    browser.force_login(installation.owner)

    response = browser.post(
        reverse("msp-import-apply", kwargs={"batch_id": preview.id}), data="{}", content_type="application/json"
    )

    assert response.status_code == 400
    assert Site.objects.count() == 0
    assert ImportExternalKey.objects.filter(workspace=workspace.data_scope.workspace_id).count() == 0
    assert ImportBatch.objects.get(pk=preview.id).state == "preview_ready"
