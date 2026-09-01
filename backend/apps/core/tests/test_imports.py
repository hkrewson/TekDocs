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

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.imports import create_preview, template_csv
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
