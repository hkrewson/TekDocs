import json
import secrets
from io import BytesIO
from zipfile import ZipFile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    DocumentationMapBaseline,
    DocumentationMapEntry,
    DocumentationMapRevision,
    InstallationState,
)


@pytest.fixture
def map_owner(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Map MSP",
        owner_email="map-owner@example.invalid",
        owner_display_name="Map Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    client = Client()
    client.force_login(result.owner)
    return result, client


@pytest.mark.django_db
def test_map_revisions_are_append_only_and_reject_stale_editor(map_owner):  # type: ignore[no-untyped-def]
    _result, client = map_owner
    document = client.post(
        reverse("msp-document-list-create"),
        {"title": "Recovery procedure", "markdown": "# Recover\n\nRestore from backup."},
        content_type="application/json",
    ).json()
    created = client.post(
        reverse("msp-documentation-map-list-create"),
        {
            "title": "Operations manual",
            "purpose": "Daily operations and recovery",
            "map_type": "operating_manual",
            "audience": "msp_internal",
            "owner_id": None,
            "entries": [
                {
                    "parent_index": None,
                    "position": 0,
                    "kind": "document_revision",
                    "label": "Known-good recovery",
                    "document_id": document["id"],
                    "document_revision_id": document["current_revision_id"],
                }
            ],
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    first = created.json()
    detail = reverse("msp-documentation-map-detail", kwargs={"map_entity_id": first["id"]})
    update_payload = {
        "title": "Operations and recovery manual",
        "purpose": first["purpose"],
        "map_type": first["map_type"],
        "audience": first["audience"],
        "owner_id": None,
        "entries": [
            {
                "parent_index": None,
                "position": 0,
                "kind": "document",
                "label": "Live recovery procedure",
                "document_id": document["id"],
            }
        ],
        "expected_revision_id": first["current_revision"]["id"],
    }
    updated = client.put(detail, update_payload, content_type="application/json")
    assert updated.status_code == 200
    assert updated.json()["current_revision"]["revision_number"] == 2
    assert DocumentationMapRevision.objects.count() == 2
    assert DocumentationMapEntry.objects.count() == 2

    stale = client.put(detail, update_payload, content_type="application/json")
    assert stale.status_code == 409


@pytest.mark.django_db
def test_map_baseline_retains_portable_manifest_and_exact_files(map_owner, tmp_path):  # type: ignore[no-untyped-def]
    _result, client = map_owner
    with override_settings(MEDIA_ROOT=tmp_path):
        document = client.post(
            reverse("msp-document-list-create"),
            {"title": "Handoff checklist", "markdown": "# Handoff\n\n- Verify access"},
            content_type="application/json",
        ).json()
        created = client.post(
            reverse("msp-documentation-map-list-create"),
            {
                "title": "Handoff package",
                "purpose": "Portable handoff evidence",
                "map_type": "handoff",
                "audience": "msp_internal",
                "owner_id": None,
                "entries": [
                    {
                        "parent_index": None,
                        "position": 0,
                        "kind": "document_revision",
                        "label": "Checklist",
                        "document_id": document["id"],
                        "document_revision_id": document["current_revision_id"],
                    }
                ],
            },
            content_type="application/json",
        ).json()
        baseline = client.post(
            reverse("msp-documentation-map-baselines", kwargs={"map_entity_id": created["id"]}),
            {"expected_revision_id": created["current_revision"]["id"], "formats": ["docx"]},
            content_type="application/json",
        )
        assert baseline.status_code == 201
        download = client.get(
            reverse(
                "msp-documentation-map-baseline-download",
                kwargs={"map_entity_id": created["id"], "baseline_id": baseline.json()["id"]},
            )
        )
        assert download.status_code == 200
        retained = DocumentationMapBaseline.objects.get(id=baseline.json()["id"])
        assert bytes(download.content) == retained.artifact.read()
        with ZipFile(BytesIO(download.content)) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
            assert names == sorted(names)
            assert {"manifest.json", "index.md", "index.html"}.issubset(names)
            assert any(name.endswith("document.md") for name in names)
            assert any(name.endswith("document.html") for name in names)
            assert any(name.endswith("document.docx") for name in names)
            assert manifest["format"] == "tekdocs-documentation-map-baseline/v1"
            assert manifest["map_revision_id"] == created["current_revision"]["id"]
