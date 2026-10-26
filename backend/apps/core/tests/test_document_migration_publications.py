from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_storage
from apps.core.content_index import index_repository_content
from apps.core.document_migration_import import DocumentMigrationBlocked, prepare_document_import
from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import create_document, update_document
from apps.core.models import (
    DocumentAuthority,
    DocumentPublication,
    DocumentPublicationControlEvent,
    InstallationState,
    Tenant,
    Workspace,
    WorkspaceKind,
)
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, withdraw_publication
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def published_context(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"), MEDIA_ROOT=str(tmp_path / "media")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Publication parity fixture",
            owner_email=f"parity-{uuid.uuid4()}@example.invalid",
            owner_display_name="Fixture owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Retained guide",
            markdown="Historical instructions.\n",
        )
        publication = publish_document(
            workspace=resolve_msp_workspace(installation.owner),
            document=document,
            actor_id=installation.owner.id,
            reason="Retain internal instructions",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        yield installation, workspace, document, publication


def test_history_assessment_is_read_only_and_does_not_enable_import(published_context, django_runtime_role):
    installation, workspace, document, publication = published_context
    before = publication.manifest.copy()
    with django_runtime_role(), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.SYSTEM,
            actor_user_id=None,
        )
        first = assess_retained_publications(workspace=workspace, document=document)
        assert first["state"] == "verified"
        assert first["publication_count"] == first["artifact_count"] == 1
        assert first["reasons"] == []
        assert len(first["evidence_sha256"]) == 64
        assert assess_retained_publications(workspace=workspace, document=document) == first
        with pytest.raises(DocumentMigrationBlocked, match="publication_parity_required"):
            prepare_document_import(workspace=workspace, document_id=document.id)
    publication.refresh_from_db()
    assert publication.manifest == before
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"
    browser = Client()
    browser.force_login(installation.owner)
    result = browser.get(reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id}))
    assert result.status_code == 200
    assert result.json()["publication_history"] == first
    assert "legacy_publication_history_present" in result.json()["handoff_blockers"]
    assert result.json()["cutover_ready"] is False


@pytest.mark.parametrize("mode", ["missing", "corrupt"])
def test_history_assessment_rejects_bad_retained_bytes(published_context, mode):
    _installation, workspace, document, publication = published_context
    artifact = publication.artifacts.get()
    storage, name = artifact.file.storage, artifact.file.name
    with storage.open(name, "rb") as stream:
        original = stream.read()
    try:
        if mode == "missing":
            storage.delete(name)
        else:
            with storage.open(name, "wb") as stream:
                stream.write(b"Damaged synthetic PDF")
        result = assess_retained_publications(workspace=workspace, document=document)
        assert result["state"] == "blocked"
        assert "publication_custody_invalid" in result["reasons"]
        assert result["evidence_sha256"] is None
    finally:
        with storage.open(name, "wb") as stream:
            stream.write(original)
    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"


def test_history_assessment_rejects_untrusted_signature(published_context):
    _installation, workspace, document, _publication = published_context
    with patch("apps.core.publications.publication_trusted_key_fingerprints", return_value=("", frozenset())):
        result = assess_retained_publications(workspace=workspace, document=document)
    assert "publication_signature_invalid" in result["reasons"]
    assert result["evidence_sha256"] is None


def test_history_assessment_checks_exact_workspace(published_context):
    installation, _workspace, document, _publication = published_context
    other = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Other fixture client",
        legal_name="",
        website="",
        classifications=[],
    )
    other_workspace = Workspace.objects.get(organization=other)
    with pytest.raises(ValueError, match="selected workspace"):
        assess_retained_publications(workspace=other_workspace, document=document)
    browser = Client()
    browser.force_login(installation.owner)
    result = browser.get(
        reverse(
            "organization-document-migration-status",
            kwargs={
                "organization_entity_id": other.entity_id,
                "document_entity_id": document.entity_id,
            },
        )
    )
    assert result.status_code == 404


def test_historical_snapshot_need_not_match_current_draft(published_context):
    installation, workspace, document, _publication = published_context
    before = assess_retained_publications(workspace=workspace, document=document)
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title="Edited guide",
        markdown="New draft instructions.\n",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    document.refresh_from_db()
    assert assess_retained_publications(workspace=workspace, document=document) == before


def test_supersession_and_control_history_change_evidence(published_context):
    installation, workspace, document, publication = published_context
    before = assess_retained_publications(workspace=workspace, document=document)
    newer = publish_document(
        workspace=resolve_msp_workspace(installation.owner),
        document=document,
        actor_id=installation.owner.id,
        reason="Append replacement instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=publication.entity_id,
    )
    after = assess_retained_publications(workspace=workspace, document=document)
    assert after["state"] == "verified"
    assert after["publication_count"] == 2
    assert after["evidence_sha256"] != before["evidence_sha256"]
    withdraw_publication(publication=newer, actor_id=installation.owner.id, reason="Stop distribution")
    withdrawn = assess_retained_publications(workspace=workspace, document=document)
    assert withdrawn["state"] == "verified"
    assert withdrawn["evidence_sha256"] != after["evidence_sha256"]


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("metadata", "publication_metadata_mismatch"),
        ("supersession", "publication_supersession_invalid"),
        ("audience", "publication_shape_unsupported"),
    ],
)
def test_corrupt_loaded_history_is_rejected_without_bypassing_append_only_guards(published_context, damage, reason):
    _installation, workspace, document, _publication = published_context
    original_loader = DocumentPublication.from_db

    def load(*args):
        record = original_loader(*args)
        # Inject a damaged loaded record, keeping database history untouched.
        if damage == "metadata":
            record.manifest = {**record.manifest, "retention": "damaged"}
        elif damage == "supersession":
            record.supersedes_id = record.id
        else:
            record.audience = "client_visible"
        return record

    with patch.object(DocumentPublication, "from_db", side_effect=load):
        result = assess_retained_publications(workspace=workspace, document=document)
    assert reason in result["reasons"]
    assert result["evidence_sha256"] is None
    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"


def test_absence_and_foreign_tenant_are_distinct(published_context, django_runtime_role):
    installation, workspace, document, _publication = published_context
    fresh = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title="Unpublished fixture",
        markdown="Unpublished body.\n",
    )
    assert assess_retained_publications(workspace=workspace, document=fresh) == {
        "state": "absent",
        "publication_count": 0,
        "artifact_count": 0,
        "reasons": [],
        "evidence_sha256": None,
    }
    foreign = Tenant.objects.create(name="Foreign fixture", slug=f"parity-{uuid.uuid4()}")
    foreign_workspace = Workspace.objects.get(tenant=foreign, kind=WorkspaceKind.MSP)
    with pytest.raises(ValueError, match="selected workspace"):
        assess_retained_publications(workspace=foreign_workspace, document=document)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(foreign),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.SYSTEM,
            actor_user_id=None,
        )
        with pytest.raises(ValueError, match="selected workspace"):
            assess_retained_publications(workspace=workspace, document=document)


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("action", "publication_controls_invalid"),
        ("owner", "publication_owner_mismatch"),
    ],
)
def test_loaded_control_corruption_fails_closed(published_context, damage, reason):
    _installation, workspace, document, _publication = published_context
    original_loader = DocumentPublicationControlEvent.from_db

    def load(*args):
        record = original_loader(*args)
        if damage == "action":
            record.action = "unknown"
        else:
            record.tenant_id = uuid.uuid4()
        return record

    with patch.object(DocumentPublicationControlEvent, "from_db", side_effect=load):
        result = assess_retained_publications(workspace=workspace, document=document)
    assert result["state"] == "blocked"
    assert reason in result["reasons"]
    assert result["evidence_sha256"] is None
