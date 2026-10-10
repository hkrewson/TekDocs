from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import repository_service, repository_storage
from apps.core.content_authoring import (
    ContentAuthoringConflict,
    ContentAuthoringError,
    _validate_patch,
    author_content,
    read_authored_content,
    resolve_authored_path,
)
from apps.core.content_index import ContentIndexValidationError, index_repository_content
from apps.core.document_attachments import create_document_attachment
from apps.core.documents import create_document
from apps.core.models import (
    AuditEvent,
    ContentNode,
    DocumentAttachment,
    InstallationState,
    Tenant,
    Workspace,
    WorkspaceKind,
)
from apps.core.organizations import create_organization
from apps.core.repository_editable_bundle_validation import (
    RepositoryEditableBundleValidationError,
    verify_repository_editable_bundle,
)
from apps.core.repository_editable_bundles import _archive
from apps.core.repository_source_exports import export_repository_sources
from apps.core.repository_source_validation import verify_repository_source_snapshot
from apps.core.tasks import reconcile_content_indexes

pytestmark = pytest.mark.django_db(transaction=True)


def test_managed_authoring_does_not_change_legacy_key_bindings():
    with pytest.raises(ContentAuthoringError, match="unsupported fields"):
        _validate_patch({"key_bindings": {"subject": str(uuid.uuid4())}})


@pytest.fixture
def authoring_context(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Authoring MSP",
            owner_email=f"authoring-{uuid.uuid4()}@example.invalid",
            owner_display_name="Authoring Owner",
            password="AuthoringPassword-2026!",
        )
        TOTP.activate(installation.owner, generate_totp_secret())
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        yield installation, repository


def _create(installation, repository, *, content_id=None, title="Runbook"):
    content_id = content_id or uuid.uuid4()
    repository.refresh_from_db()
    authored = author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="create",
        content_id=content_id,
        base_commit=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
        base_blob=None,
        kind="document",
        path=None,
        title=title,
        markdown="Initial instructions.\n",
        metadata_patch={"properties": {"lifecycle": "active"}},
    )
    return authored


def test_authoring_preserves_unedited_frontmatter_and_reindexes(authoring_context):
    installation, repository = authoring_context
    first = _create(installation, repository)
    assert first.accepted_commit == first.indexed_commit
    assert ContentNode.objects.get(content_id=first.content_id).title == "Runbook"

    source_with_comment = first.source.replace('title: "Runbook"', 'title: "Runbook" # Keep this note')
    source_with_comment = source_with_comment.replace("properties:\n", "# Operator-owned note\nproperties:\n")
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.accepted_commit,
        changes={first.path: source_with_comment.encode()},
        message="Add hand-authored comment",
    )
    index_repository_content(repository_id=repository.id)
    exact = read_authored_content(repository=repository, content_id=first.content_id)
    changed = author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=first.content_id,
        base_commit=exact.accepted_commit,
        base_blob=exact.source_blob,
        kind=None,
        path=None,
        title="Updated runbook",
        markdown="Updated instructions.\n",
        metadata_patch={"entity_links": [{"id": str(uuid.uuid4()), "relationship": "maintenance"}]},
    )
    assert "# Operator-owned note" in changed.source
    assert 'title: "Updated runbook" # Keep this note' in changed.source
    assert "lifecycle: active" in changed.source
    assert 'title: "Updated runbook"' in changed.source
    assert changed.accepted_commit == changed.indexed_commit
    assert ContentNode.objects.get(content_id=first.content_id).markdown == "Updated instructions.\n"


def test_stale_blob_conflicts_but_unrelated_head_change_merges_safely(authoring_context):
    installation, repository = authoring_context
    first = _create(installation, repository)
    _create(installation, repository, title="Other runbook")
    merged = author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=first.content_id,
        base_commit=first.accepted_commit,
        base_blob=first.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Edited after unrelated commit.\n",
        metadata_patch={},
    )
    assert merged.source.endswith("Edited after unrelated commit.\n")
    before_conflict = merged.accepted_commit
    with pytest.raises(ContentAuthoringConflict) as captured:
        author_content(
            repository=repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="update",
            content_id=first.content_id,
            base_commit=first.accepted_commit,
            base_blob=first.source_blob,
            kind=None,
            path=None,
            title=None,
            markdown="Stale browser text.\n",
            metadata_patch={},
        )
    assert captured.value.payload["reason"] == "changed"
    assert captured.value.payload["base"].endswith("Initial instructions.\n")
    assert captured.value.payload["current"].endswith("Edited after unrelated commit.\n")
    assert captured.value.payload["proposed"].endswith("Stale browser text.\n")
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == before_conflict


def test_invalid_composition_never_advances_accepted_head_and_move_retains_alias(authoring_context):
    installation, repository = authoring_context
    first = _create(installation, repository)
    with pytest.raises(ContentIndexValidationError):
        author_content(
            repository=repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="update",
            content_id=first.content_id,
            base_commit=first.accepted_commit,
            base_blob=first.source_blob,
            kind=None,
            path=None,
            title=None,
            markdown=None,
            metadata_patch={"includes": [{"id": str(uuid.uuid4()), "mode": "live", "audience": "shared"}]},
        )
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == first.accepted_commit
    with pytest.raises(ContentIndexValidationError):
        author_content(
            repository=repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="move",
            content_id=first.content_id,
            base_commit=first.accepted_commit,
            base_blob=first.source_blob,
            kind=None,
            path="docs/invalid-move.md",
            title=None,
            markdown=None,
            metadata_patch={"includes": [{"id": "not-a-uuid", "mode": "live", "audience": "shared"}]},
        )
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == first.accepted_commit
    moved = author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="move",
        content_id=first.content_id,
        base_commit=first.accepted_commit,
        base_blob=first.source_blob,
        kind=None,
        path="docs/renamed-runbook.md",
        title="Renamed runbook",
        markdown=None,
        metadata_patch={},
    )
    assert moved.path == "docs/renamed-runbook.md"
    assert first.path in moved.source
    assert ContentNode.objects.get(content_id=first.content_id).source_path == moved.path
    assert resolve_authored_path(repository=repository, path=first.path).content_id == first.content_id
    browser = Client()
    browser.force_login(installation.owner)
    resolved = browser.get(reverse("msp-content-resolve-path"), {"path": first.path})
    assert resolved.status_code == 200
    assert resolved.json()["path"] == moved.path


def test_authoring_api_checks_permissions_and_returns_conflicts(authoring_context):
    installation, repository = authoring_context
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-content-authoring")
    document_id = uuid.uuid4()
    repository.refresh_from_db()
    create = browser.post(
        url,
        data={
            "operation": "create",
            "content_id": str(document_id),
            "base_commit": repository.accepted_commit.object_id if repository.accepted_commit_id else None,
            "kind": "document",
            "title": "API guide",
            "markdown": "First revision.\n",
        },
        content_type="application/json",
    )
    assert create.status_code == 200, create.content
    created = create.json()
    assert (
        browser.get(reverse("msp-content-authoring-source", args=[document_id])).json()["source_blob"]
        == created["source_blob"]
    )
    update = browser.post(
        url,
        data={
            "operation": "update",
            "content_id": str(document_id),
            "base_commit": created["accepted_commit"],
            "base_blob": created["source_blob"],
            "markdown": "Second revision.\n",
        },
        content_type="application/json",
    )
    assert update.status_code == 200, update.content
    stale = browser.post(
        url,
        data={
            "operation": "update",
            "content_id": str(document_id),
            "base_commit": created["accepted_commit"],
            "base_blob": created["source_blob"],
            "markdown": "Stale revision.\n",
        },
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["reason"] == "changed"
    assert Client().post(url, data={}, content_type="application/json").status_code in {401, 403}

    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Separate client",
        legal_name="Separate client",
        website="https://example.invalid",
        classifications=["client"],
    )
    foreign_source = reverse(
        "organization-content-authoring-source",
        kwargs={"organization_entity_id": organization.entity_id, "content_id": document_id},
    )
    assert browser.get(foreign_source).status_code == 404


def test_native_attachment_upload_scans_and_requires_exact_indexed_document(authoring_context, tmp_path):
    installation, repository = authoring_context
    document = _create(installation, repository)
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-content-authoring-attachment-create", args=[document.content_id])
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        response = browser.post(url, {"file": SimpleUploadedFile("instructions.txt", b"Safe instructions\n")})
        assert response.status_code == 201, response.content
        attachment = DocumentAttachment.objects.get(entity_id=response.json()["id"])
        assert attachment.document_id is None
        assert attachment.owner_workspace_id == repository.workspace_id
        assert attachment.owner_content_id == document.content_id
        assert attachment.organization_id is None
        assert attachment.scan_status == "clean"
        assert attachment.file.name.startswith(f"document-attachments/{installation.tenant.id}/{document.content_id}/")
        call_command("verify_recovery_managed_files", verbosity=0)
        assert AuditEvent.objects.filter(action="document.attachment.created", entity_id=attachment.entity_id).exists()

        count = DocumentAttachment.objects.count()
        missing_url = reverse("msp-content-authoring-attachment-create", args=[uuid.uuid4()])
        assert browser.post(missing_url, {"file": SimpleUploadedFile("missing.txt", b"No target\n")}).status_code == 400
        fragment_id = uuid.uuid4()
        repository.refresh_from_db()
        author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="create", content_id=fragment_id,
            base_commit=repository.accepted_commit.object_id, base_blob=None,
            kind="fragment", path=None, title="Reusable fragment", markdown="Shared text.\n", metadata_patch={},
        )
        fragment_url = reverse("msp-content-authoring-attachment-create", args=[fragment_id])
        assert browser.post(
            fragment_url, {"file": SimpleUploadedFile("fragment.txt", b"No fragment\n")}
        ).status_code == 400
        assert browser.post(
            url, {"file": SimpleUploadedFile("unsafe.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE")}
        ).status_code == 400

        repository.refresh_from_db()
        repository.indexed_commit = None
        repository.save(update_fields=["indexed_commit", "updated_at"])
        assert browser.post(url, {"file": SimpleUploadedFile("lag.txt", b"Index lag\n")}).status_code == 400
        assert DocumentAttachment.objects.count() == count
        assert Client().post(url, {"file": SimpleUploadedFile("anon.txt", b"No access\n")}).status_code in {401, 403}


def test_native_attachment_upload_rejects_sibling_workspace(authoring_context, tmp_path):
    installation, repository = authoring_context
    document = _create(installation, repository)
    sibling = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name="Sibling attachment workspace",
        legal_name="Sibling attachment workspace", website="", classifications=["client"],
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-content-authoring-attachment-create",
        kwargs={"organization_entity_id": sibling.entity_id, "content_id": document.content_id},
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        assert browser.post(url, {"file": SimpleUploadedFile("foreign.txt", b"Wrong workspace\n")}).status_code == 400
    assert not DocumentAttachment.objects.exists()


def test_native_attachment_upload_accepts_exact_organization_workspace(authoring_context, tmp_path):
    installation, _repository = authoring_context
    organization = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name="File-owning client",
        legal_name="File-owning client", website="", classifications=["client"],
    )
    workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
    repository = repository_storage.ensure_workspace_repository(workspace).repository
    repository.refresh_from_db()
    content_id = uuid.uuid4()
    author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="create", content_id=content_id,
        base_commit=repository.accepted_commit.object_id, base_blob=None,
        kind="document", path=None, title="Client onboarding", markdown="Onboard.\n", metadata_patch={},
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-content-authoring-attachment-create",
        kwargs={"organization_entity_id": organization.entity_id, "content_id": content_id},
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        response = browser.post(url, {"file": SimpleUploadedFile("client.txt", b"Client steps\n")})
        assert response.status_code == 201, response.content
        attachment = DocumentAttachment.objects.get(entity_id=response.json()["id"])
        assert attachment.document_id is None
        assert attachment.owner_workspace_id == workspace.id
        assert attachment.organization_id == organization.id
        call_command("verify_recovery_managed_files", verbosity=0)
        listed = browser.get(url)
        assert listed.status_code == 200, listed.content
        assert listed.json()["results"][0]["can_archive"] is True
        archive_url = reverse(
            "organization-content-authoring-attachment-archive",
            kwargs={"organization_entity_id": organization.entity_id, "content_id": content_id,
                    "attachment_entity_id": attachment.entity_id},
        )
        wrong_content = reverse(
            "organization-content-authoring-attachment-archive",
            kwargs={"organization_entity_id": organization.entity_id, "content_id": uuid.uuid4(),
                    "attachment_entity_id": attachment.entity_id},
        )
        assert browser.delete(wrong_content).status_code == 404
        sibling = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Other file owner",
            legal_name="Other file owner", website="", classifications=["client"],
        )
        sibling_url = reverse(
            "organization-content-authoring-attachment-archive",
            kwargs={"organization_entity_id": sibling.entity_id, "content_id": content_id,
                    "attachment_entity_id": attachment.entity_id},
        )
        assert browser.delete(sibling_url).status_code == 404
        assert Client().get(url).status_code in {401, 403}
        assert Client().delete(archive_url).status_code in {401, 403}
        portal_user = User.objects.create_user(
            email="native-archive-client@example.invalid", display_name="File client"
        )
        TenantMembership.objects.create(
            tenant=installation.tenant, user=portal_user, role=BuiltInRole.CLIENT_USER, organization=organization
        )
        browser.force_login(portal_user)
        assert browser.get(url).status_code == 403
        assert browser.delete(archive_url).status_code == 403
        foreign_tenant = Tenant.objects.create(name="Foreign archive MSP", slug=f"foreign-archive-{uuid.uuid4()}")
        foreign_user = User.objects.create_user(
            email="foreign-archive@example.invalid", display_name="Foreign archive user"
        )
        TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_user, role=BuiltInRole.ADMINISTRATOR)
        browser.force_login(foreign_user)
        assert browser.get(url).status_code in {403, 404}
        assert browser.delete(archive_url).status_code in {403, 404}
        browser.force_login(installation.owner)
        assert browser.delete(archive_url).status_code == 204


def test_native_msp_attachment_download_uses_content_owner(authoring_context, tmp_path):
    installation, repository = authoring_context
    document = _create(installation, repository)
    browser = Client()
    browser.force_login(installation.owner)
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        upload = browser.post(
            reverse("msp-content-authoring-attachment-create", args=[document.content_id]),
            {"file": SimpleUploadedFile("owner.txt", b"MSP only\n")},
        )
        assert upload.status_code == 201, upload.content
        attachment_id = upload.json()["id"]
        download_url = reverse(
            "msp-content-document-attachment-download",
            kwargs={"content_id": document.content_id, "attachment_entity_id": attachment_id},
        )
        download = browser.get(download_url)
        assert download.status_code == 200
        assert b"".join(download.streaming_content) == b"MSP only\n"
        assert Client().get(download_url).status_code in {401, 403}


def test_native_attachment_archive_only_before_any_git_advance(authoring_context, tmp_path):
    installation, repository = authoring_context
    document = _create(installation, repository)
    browser = Client()
    browser.force_login(installation.owner)
    collection = reverse("msp-content-authoring-attachment-create", args=[document.content_id])
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        uploaded = browser.post(collection, {"file": SimpleUploadedFile("unused.txt", b"Unused\n")})
        assert uploaded.status_code == 201, uploaded.content
        attachment_id = uploaded.json()["id"]
        creation = AuditEvent.objects.get(action="document.attachment.created", entity_id=attachment_id)
        assert creation.metadata["upload_commit"] == document.accepted_commit
        listing = browser.get(collection)
        assert listing.status_code == 200, listing.content
        assert listing.json()["results"][0] == {
            "id": attachment_id, "filename": "unused.txt", "size": 7,
            "linked_current": False, "can_archive": True,
        }
        archive_url = reverse(
            "msp-content-authoring-attachment-archive", args=[document.content_id, attachment_id]
        )
        assert Client().delete(archive_url).status_code in {401, 403}
        assert browser.delete(archive_url).status_code == 204
        attachment = DocumentAttachment.objects.get(entity_id=attachment_id)
        assert attachment.archived_at is not None
        assert attachment.file.storage.exists(attachment.file.name)
        assert browser.get(collection).json()["count"] == 0
        assert browser.delete(archive_url).status_code == 404

        linked_upload = browser.post(collection, {"file": SimpleUploadedFile("linked.txt", b"Linked\n")})
        assert linked_upload.status_code == 201, linked_upload.content
        linked_id = linked_upload.json()["id"]
        current = read_authored_content(repository=repository, content_id=document.content_id)
        author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=document.content_id,
            base_commit=current.accepted_commit, base_blob=current.source_blob,
            kind=None, path=None, title=None,
            markdown=f"See [linked](tekdocs://attachment/{linked_id}).\n", metadata_patch={},
        )
        linked_archive = reverse(
            "msp-content-authoring-attachment-archive", args=[document.content_id, linked_id]
        )
        assert browser.delete(linked_archive).status_code == 409
        linked_status = browser.get(collection).json()["results"][0]
        assert linked_status["linked_current"] is True
        assert linked_status["can_archive"] is False

        abandoned_upload = browser.post(collection, {"file": SimpleUploadedFile("later.txt", b"Later\n")})
        assert abandoned_upload.status_code == 201, abandoned_upload.content
        abandoned_id = abandoned_upload.json()["id"]
        repository.refresh_from_db()
        upload_commit_id = repository.accepted_commit_id
        current = read_authored_content(repository=repository, content_id=document.content_id)
        author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=document.content_id,
            base_commit=current.accepted_commit, base_blob=current.source_blob,
            kind=None, path=None, title=None,
            markdown=f"See [linked](tekdocs://attachment/{linked_id}).\nMore text.\n", metadata_patch={},
        )
        abandoned_archive = reverse(
            "msp-content-authoring-attachment-archive", args=[document.content_id, abandoned_id]
        )
        assert browser.delete(abandoned_archive).status_code == 409
        abandoned_status = next(
            item for item in browser.get(collection).json()["results"] if item["id"] == abandoned_id
        )
        assert abandoned_status["linked_current"] is False
        assert abandoned_status["can_archive"] is False
        repository.refresh_from_db()
        repository.accepted_commit_id = upload_commit_id
        repository.indexed_commit_id = upload_commit_id
        repository.save(update_fields=["accepted_commit", "indexed_commit", "updated_at"])
        assert browser.delete(abandoned_archive).status_code == 409


def test_accepted_index_marker_retries_without_rewriting_git(authoring_context):
    installation, repository = authoring_context
    authored = _create(installation, repository)
    repository.indexed_commit = None
    repository.save(update_fields=["indexed_commit", "updated_at"])
    assert reconcile_content_indexes() == 1
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == authored.accepted_commit
    assert repository.indexed_commit.object_id == authored.accepted_commit


def test_repository_source_snapshot_exports_exact_current_files_and_rejects_lag(authoring_context):
    installation, repository = authoring_context
    first = _create(installation, repository)
    second = _create(installation, repository, title="Second guide")
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-content-authoring-export")
    response = browser.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert response["Cache-Control"] == "no-store"
    filename = f'tekdocs-repository-{second.accepted_commit[:12]}.zip'
    assert response["Content-Disposition"] == f'attachment; filename="{filename}"'
    assert verify_repository_source_snapshot(response.content)["accepted_commit"] == second.accepted_commit
    assert browser.get(url).content == response.content
    events = AuditEvent.objects.filter(action="repository_source_export.downloaded", entity_id=repository.id)
    assert events.count() == 2
    assert events.first().metadata == {"accepted_commit": second.accepted_commit, "file_count": 2}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        assert manifest["format"] == "tekdocs-repository-source-snapshot/v3"
        assert manifest["workspace_id"] == str(repository.workspace_id)
        assert manifest["accepted_commit"] == second.accepted_commit
        assert manifest["scope"] == "current-files-and-reachable-markdown-dependencies"
        assert manifest["historical_files"] == []
        assert len(manifest["files"]) == 2
        assert {item["content_id"] for item in manifest["files"]} == {str(first.content_id), str(second.content_id)}
        for item in manifest["files"]:
            source = archive.read(item["path"])
            assert hashlib.sha256(source).hexdigest() == item["sha256"]
            authored = read_authored_content(repository=repository, content_id=uuid.UUID(item["content_id"]))
            assert source == authored.source.encode()
        assert "not a complete dependency bundle or backup" in archive.read("README.md").decode()
    assert Client().get(url).status_code in {401, 403}

    repository.indexed_commit = None
    repository.save(update_fields=["indexed_commit", "updated_at"])
    assert browser.get(url).status_code == 409
    assert events.count() == 2


def test_editable_bundle_includes_exact_referenced_file_and_verifies_offline(authoring_context, tmp_path):
    installation, repository = authoring_context
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        document = create_document(
            tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
            title="Bundle guide", markdown="Legacy source.\n",
        )
        attachment = create_document_attachment(
            document=document, actor_id=installation.owner.id,
            upload=SimpleUploadedFile("guide.txt", b"Exact managed bytes"),
        )
        authored = _create(installation, repository, content_id=document.id, title="Bundle guide")
        source = authored.source.replace(
            "Initial instructions.\n", f"[Guide](tekdocs://attachment/{attachment.entity_id})\n"
        )
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=authored.accepted_commit,
            changes={authored.path: source.encode()}, message="Link managed file",
        )
        index_repository_content(repository_id=repository.id)
        browser = Client()
        browser.force_login(installation.owner)
        url = reverse("msp-content-authoring-export") + "?bundle=editable"
        response = browser.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/zip"
        assert "tekdocs-repository-editable-" in response["Content-Disposition"]
        manifest = verify_repository_editable_bundle(response.content)
        assert manifest["attachments"][0]["id"] == str(attachment.entity_id)
        assert manifest["attachments"][0]["owner"] == {"type": "legacy_document", "id": str(document.id)}
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read(f"attachments/{attachment.entity_id}") == b"Exact managed bytes"
            entries = {name: archive.read(name) for name in archive.namelist()}
        legacy_manifest = {**manifest, "format": "tekdocs-repository-editable-bundle/v1"}
        legacy_manifest["attachments"] = [
            {**{key: value for key, value in item.items() if key != "owner"}, "document_id": item["owner"]["id"]}
            for item in manifest["attachments"]
        ]
        legacy_entries = dict(entries)
        legacy_entries["tekdocs-bundle.json"] = (
            json.dumps(legacy_manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        assert verify_repository_editable_bundle(_archive(legacy_entries))["format"] == legacy_manifest["format"]
        changed = dict(entries)
        changed[f"attachments/{attachment.entity_id}"] = b"Alter managed bytes"
        with pytest.raises(RepositoryEditableBundleValidationError, match="checksum"):
            verify_repository_editable_bundle(_archive(changed))
        omitted = dict(entries)
        omitted.pop(f"attachments/{attachment.entity_id}")
        with pytest.raises(RepositoryEditableBundleValidationError, match="descriptor"):
            verify_repository_editable_bundle(_archive(omitted))
        archive_path = tmp_path / "editable.zip"
        archive_path.write_bytes(response.content)
        call_command("verify_repository_editable_bundle", archive_path)
        assert AuditEvent.objects.filter(action="repository_editable_bundle.downloaded").count() == 1
        assert Client().get(url).status_code in {401, 403}

        attachment.file.storage.delete(attachment.file.name)
        assert browser.get(url).status_code == 409
        assert AuditEvent.objects.filter(action="repository_editable_bundle.downloaded").count() == 1


def test_editable_bundle_includes_native_file_from_current_git_source(authoring_context, tmp_path):
    installation, repository = authoring_context
    document = _create(installation, repository)
    browser = Client()
    browser.force_login(installation.owner)
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        upload = browser.post(
            reverse("msp-content-authoring-attachment-create", args=[document.content_id]),
            {"file": SimpleUploadedFile("native.txt", b"Native file bytes\n")},
        )
        assert upload.status_code == 201, upload.content
        attachment_id = upload.json()["id"]
        current = read_authored_content(repository=repository, content_id=document.content_id)
        author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=document.content_id,
            base_commit=current.accepted_commit, base_blob=current.source_blob,
            kind=None, path=None, title=None,
            markdown=f"[Native](tekdocs://attachment/{attachment_id})\n", metadata_patch={},
        )
        url = reverse("msp-content-authoring-export") + "?bundle=editable"
        response = browser.get(url)
        assert response.status_code == 200, response.content
        manifest = verify_repository_editable_bundle(response.content)
        assert manifest["format"] == "tekdocs-repository-editable-bundle/v2"
        assert manifest["attachments"][0]["owner"] == {
            "type": "repository_document", "id": str(document.content_id),
        }
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read(f"attachments/{attachment_id}") == b"Native file bytes\n"
            entries = {name: archive.read(name) for name in archive.namelist()}
        forged = dict(entries)
        forged_manifest = json.loads(forged["tekdocs-bundle.json"])
        forged_manifest["attachments"][0]["owner"]["id"] = str(uuid.uuid4())
        forged["tekdocs-bundle.json"] = (
            json.dumps(forged_manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        with pytest.raises(RepositoryEditableBundleValidationError, match="unknown repository owner"):
            verify_repository_editable_bundle(_archive(forged))
        attachment = DocumentAttachment.objects.get(entity_id=attachment_id)
        attachment.file.storage.delete(attachment.file.name)
        assert browser.get(url).status_code == 409
        assert AuditEvent.objects.filter(action="repository_editable_bundle.downloaded").count() == 1


def test_editable_bundle_rejects_extra_file_bytes(authoring_context):
    installation, repository = authoring_context
    authored = _create(installation, repository)
    response = Client()
    response.force_login(installation.owner)
    content = response.get(reverse("msp-content-authoring-export") + "?bundle=editable").content
    assert verify_repository_editable_bundle(content)["attachments"] == []
    with zipfile.ZipFile(io.BytesIO(content)) as original:
        entries = {name: original.read(name) for name in original.namelist()}
    entries["attachments/" + str(uuid.uuid4())] = b"unlisted"
    with pytest.raises(RepositoryEditableBundleValidationError, match="unlisted"):
        verify_repository_editable_bundle(_archive(entries))
    assert authored.content_id


def test_editable_bundle_rejects_foreign_workspace_file(authoring_context, tmp_path):
    installation, repository = authoring_context
    organization = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id,
        name="Other client", legal_name="Other client", website="https://example.invalid",
        classifications=["client"],
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        foreign_document = create_document(
            tenant=installation.tenant, organization=organization, actor_id=installation.owner.id,
            title="Foreign file", markdown="Private.\n",
        )
        foreign_attachment = create_document_attachment(
            document=foreign_document, actor_id=installation.owner.id,
            upload=SimpleUploadedFile("private.txt", b"Foreign bytes"),
        )
        authored = _create(installation, repository)
        source = authored.source.replace(
            "Initial instructions.\n", f"[Foreign](tekdocs://attachment/{foreign_attachment.entity_id})\n"
        )
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=authored.accepted_commit,
            changes={authored.path: source.encode()}, message="Reference foreign file",
        )
        index_repository_content(repository_id=repository.id)
        browser = Client()
        browser.force_login(installation.owner)
        assert browser.get(reverse("msp-content-authoring-export") + "?bundle=editable").status_code == 409
        assert AuditEvent.objects.filter(action="repository_editable_bundle.downloaded").count() == 0


def test_editable_bundle_rejects_foreign_native_file(authoring_context, tmp_path):
    installation, repository = authoring_context
    organization = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id,
        name="Native file owner", legal_name="Native file owner", website="", classifications=["client"],
    )
    workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
    foreign_repository = repository_storage.ensure_workspace_repository(workspace).repository
    foreign_repository.refresh_from_db()
    foreign_id = uuid.uuid4()
    author_content(
        repository=foreign_repository, actor_id=installation.owner.id, request_id=None,
        operation="create", content_id=foreign_id,
        base_commit=foreign_repository.accepted_commit.object_id, base_blob=None,
        kind="document", path=None, title="Client-only file", markdown="Private.\n", metadata_patch={},
    )
    browser = Client()
    browser.force_login(installation.owner)
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        upload = browser.post(
            reverse("organization-content-authoring-attachment-create", kwargs={
                "organization_entity_id": organization.entity_id, "content_id": foreign_id,
            }),
            {"file": SimpleUploadedFile("private.txt", b"Client-only bytes\n")},
        )
        assert upload.status_code == 201, upload.content
        authored = _create(installation, repository)
        author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=authored.content_id,
            base_commit=authored.accepted_commit, base_blob=authored.source_blob,
            kind=None, path=None, title=None,
            markdown=f"[Foreign](tekdocs://attachment/{upload.json()['id']})\n", metadata_patch={},
        )
        assert browser.get(reverse("msp-content-authoring-export") + "?bundle=editable").status_code == 409
        assert AuditEvent.objects.filter(action="repository_editable_bundle.downloaded").count() == 0
        current = read_authored_content(repository=foreign_repository, content_id=foreign_id)
        author_content(
            repository=foreign_repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=foreign_id,
            base_commit=current.accepted_commit, base_blob=current.source_blob,
            kind=None, path=None, title=None,
            markdown=f"[Own file](tekdocs://attachment/{upload.json()['id']})\n", metadata_patch={},
        )
        organization_export = reverse(
            "organization-content-authoring-export", kwargs={"organization_entity_id": organization.entity_id}
        ) + "?bundle=editable"
        own_bundle = browser.get(organization_export)
        assert own_bundle.status_code == 200, own_bundle.content
        own_manifest = verify_repository_editable_bundle(own_bundle.content)
        assert own_manifest["workspace_id"] == str(workspace.id)
        assert own_manifest["attachments"][0]["owner"] == {
            "type": "repository_document", "id": str(foreign_id),
        }


def test_editable_bundle_includes_file_referenced_only_by_pinned_fragment(authoring_context, tmp_path):
    installation, repository = authoring_context
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        document = create_document(
            tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
            title="Pinned guide", markdown="Legacy source.\n",
        )
        attachment = create_document_attachment(
            document=document, actor_id=installation.owner.id,
            upload=SimpleUploadedFile("pinned.txt", b"Pinned file bytes"),
        )
        fragment_id = uuid.uuid4()

        def source(content_id, kind, body, includes=""):  # type: ignore[no-untyped-def]
            return (
                f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\n"
                f"title: Pinned guide\n{includes}---\n{body}"
            ).encode()

        first = repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
            changes={"fragments/step.md": source(
                fragment_id, "fragment", f"[File](tekdocs://attachment/{attachment.entity_id})\n"
            )}, message="Add original fragment",
        )
        second = repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=first.object_id,
            changes={"fragments/step.md": source(fragment_id, "fragment", "Revised step.\n")},
            message="Revise fragment",
        )
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=second.object_id,
            changes={"documents/pinned-guide.md": source(
                document.id, "document", "Use the original step.\n",
                f"includes:\n  - id: {fragment_id}\n    mode: pinned\n    audience: shared\n"
                f"    commit: {first.object_id}\n",
            )}, message="Pin original fragment",
        )
        index_repository_content(repository_id=repository.id)
        browser = Client()
        browser.force_login(installation.owner)
        response = browser.get(reverse("msp-content-authoring-export") + "?bundle=editable")
        assert response.status_code == 200
        manifest = verify_repository_editable_bundle(response.content)
        assert [item["id"] for item in manifest["attachments"]] == [str(attachment.entity_id)]
        with zipfile.ZipFile(io.BytesIO(response.content)) as outer:
            with zipfile.ZipFile(io.BytesIO(outer.read("source-snapshot.zip"))) as inner:
                assert f"pinned/{first.object_id}/fragments/step.md" in inner.namelist()


def test_source_snapshot_git_verification_requires_exact_workspace_and_accepted_head(authoring_context, tmp_path):
    installation, repository = authoring_context
    _create(installation, repository)
    snapshot = export_repository_sources(repository)
    archive = tmp_path / "sources.zip"
    archive.write_bytes(snapshot.content)
    repository.refresh_from_db()
    reconciled_at = repository.last_reconciled_at
    call_command("verify_repository_source_snapshot", archive, repository_id=repository.id)
    repository.refresh_from_db()
    assert repository.last_reconciled_at == reconciled_at

    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Verification client",
        legal_name="Verification client",
        website="https://example.invalid",
        classifications=["client"],
    )
    other_workspace = Workspace.objects.get(
        tenant=installation.tenant, kind=WorkspaceKind.ORGANIZATION, organization=organization
    )
    other_repository = repository_storage.ensure_workspace_repository(other_workspace).repository
    with pytest.raises(CommandError, match="different Workspace"):
        call_command("verify_repository_source_snapshot", archive, repository_id=other_repository.id)

    _create(installation, repository, title="New guide")
    with pytest.raises(CommandError, match="accepted Git revision"):
        call_command("verify_repository_source_snapshot", archive, repository_id=repository.id)


def test_source_snapshot_git_verification_rejects_index_lag(authoring_context, tmp_path):
    installation, repository = authoring_context
    _create(installation, repository)
    archive = tmp_path / "sources.zip"
    archive.write_bytes(export_repository_sources(repository).content)
    repository.indexed_commit = None
    repository.save(update_fields=["indexed_commit", "updated_at"])
    with pytest.raises(CommandError, match="unavailable or unready"):
        call_command("verify_repository_source_snapshot", archive, repository_id=repository.id)


def test_source_snapshot_git_verification_rejects_current_git_byte_difference(authoring_context, tmp_path, monkeypatch):
    installation, repository = authoring_context
    _create(installation, repository)
    archive = tmp_path / "sources.zip"
    archive.write_bytes(export_repository_sources(repository).content)
    original_reader = repository_service.read_accepted_repository_markdown_files

    def changed_current(**kwargs):
        commit, files = original_reader(**kwargs)
        return commit, tuple((path, source + b"changed") for path, source in files)

    monkeypatch.setattr(
        "apps.core.repository_source_git_validation.read_accepted_repository_markdown_files",
        changed_current,
    )
    with pytest.raises(CommandError, match="current files differ"):
        call_command("verify_repository_source_snapshot", archive, repository_id=repository.id)


def test_repository_source_snapshot_does_not_cross_workspace(authoring_context):
    installation, repository = authoring_context
    authored = _create(installation, repository)
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Separate source client",
        legal_name="Separate source client",
        website="https://example.invalid",
        classifications=["client"],
    )
    workspace = Workspace.objects.get(
        tenant=installation.tenant, kind=WorkspaceKind.ORGANIZATION, organization=organization
    )
    organization_repository = repository_storage.ensure_workspace_repository(workspace).repository
    own = _create(installation, organization_repository, title="Client guide")
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(
        reverse("organization-content-authoring-export", kwargs={"organization_entity_id": organization.entity_id})
    )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        assert manifest["workspace_id"] == str(workspace.id)
        assert {item["content_id"] for item in manifest["files"]} == {str(own.content_id)}
        assert authored.source.encode() not in [archive.read(item["path"]) for item in manifest["files"]]


def test_repository_source_snapshot_fails_closed_on_file_limit(authoring_context, monkeypatch):
    installation, repository = authoring_context
    _create(installation, repository)
    monkeypatch.setattr("apps.core.repository_source_exports.MAX_SOURCE_FILES", 0)
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(reverse("msp-content-authoring-export"))
    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")


def test_repository_source_snapshot_retains_only_reachable_pinned_fragments(authoring_context, monkeypatch, tmp_path):
    installation, repository = authoring_context
    parent_id, nested_id, unrelated_id, document_id = (uuid.uuid4() for _ in range(4))

    def source(content_id, title, kind, body, includes=""):  # type: ignore[no-untyped-def]
        return (
            f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\n"
            f"title: {title}\n{includes}---\n{body}"
        ).encode()

    first_parent = source(
        parent_id, "Parent", "fragment", "Original parent.\n",
        f"includes:\n  - id: {nested_id}\n    mode: live\n    audience: shared\n",
    )
    first_nested = source(nested_id, "Nested", "fragment", "Original nested.\n")
    repository.refresh_from_db()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
        changes={
            "fragments/parent.md": first_parent,
            "fragments/nested.md": first_nested,
            "fragments/unrelated.md": source(unrelated_id, "Unrelated", "fragment", "Unrelated old text.\n"),
        },
        message="Add original fragments",
    )
    document = source(
        document_id, "Guide", "document", "Guide body.\n",
        f"includes:\n  - id: {parent_id}\n    mode: pinned\n    audience: shared\n    commit: {first.object_id}\n",
    )
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/parent.md": source(parent_id, "Parent", "fragment", "Current parent.\n"),
            "fragments/nested.md": source(nested_id, "Nested", "fragment", "Current nested.\n"),
            "docs/guide.md": document,
        },
        message="Pin original parent",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-content-authoring-export")
    response = browser.get(url)
    assert response.status_code == 200, response.content
    assert len(verify_repository_source_snapshot(response.content)["historical_files"]) == 2
    source_archive = tmp_path / "pinned-sources.zip"
    source_archive.write_bytes(response.content)
    call_command("verify_repository_source_snapshot", source_archive, repository_id=repository.id)
    original_reader = repository_service.read_repository_markdown_files_at_commit

    def changed_history(*, repository_id, object_id, record_reconciliation):
        commit, files = original_reader(
            repository_id=repository_id, object_id=object_id, record_reconciliation=record_reconciliation
        )
        return commit, tuple(
            (path, source + b"changed" if path == "fragments/parent.md" else source)
            for path, source in files
        )

    monkeypatch.setattr(
        "apps.core.repository_source_git_validation.read_repository_markdown_files_at_commit",
        changed_history,
    )
    with pytest.raises(CommandError, match="historical source file differs"):
        call_command("verify_repository_source_snapshot", source_archive, repository_id=repository.id)
    assert browser.get(url).content == response.content
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        historical = manifest["historical_files"]
        assert {item["content_id"] for item in historical} == {str(parent_id), str(nested_id)}
        assert {item["commit"] for item in historical} == {first.object_id}
        assert {item["source_path"] for item in historical} == {"fragments/parent.md", "fragments/nested.md"}
        assert all(item["roles"] == ["include"] for item in historical)
        for item in historical:
            actual = archive.read(item["path"])
            assert hashlib.sha256(actual).hexdigest() == item["sha256"]
        assert archive.read(f"pinned/{first.object_id}/fragments/parent.md") == first_parent
        assert archive.read(f"pinned/{first.object_id}/fragments/nested.md") == first_nested
        assert f"pinned/{first.object_id}/fragments/unrelated.md" not in archive.namelist()
        assert archive.read("repository/fragments/parent.md").endswith(b"Current parent.\n")

    def missing_commit(*, repository_id, object_id):  # type: ignore[no-untyped-def]
        raise repository_service.RepositoryFileNotFoundError("Pinned commit is unavailable")

    monkeypatch.setattr(
        "apps.core.repository_source_exports.read_repository_markdown_files_at_commit", missing_commit
    )
    audits_before = AuditEvent.objects.filter(action="repository_source_export.downloaded").count()
    assert browser.get(url).status_code == 503
    assert AuditEvent.objects.filter(action="repository_source_export.downloaded").count() == audits_before


def test_repository_source_snapshot_follows_template_and_copy_provenance(authoring_context):
    installation, repository = authoring_context
    origin_id, nested_id, unrelated_id, template_id, copy_id, document_id = (uuid.uuid4() for _ in range(6))

    def source(content_id, title, kind, body, metadata=""):  # type: ignore[no-untyped-def]
        return (
            f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\ntitle: {title}\n{metadata}---\n{body}"
        ).encode()

    original_fragment = source(origin_id, "Origin", "fragment", "Original origin.\n")
    original_nested = source(nested_id, "Nested", "fragment", "Original nested.\n")
    original_template = source(
        template_id,
        "Template",
        "document",
        "Original template.\n",
        f"includes:\n  - id: {nested_id}\n    mode: live\n    audience: shared\n",
    )
    repository.refresh_from_db()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
        changes={
            "fragments/origin.md": original_fragment,
            "fragments/nested.md": original_nested,
            "fragments/unrelated.md": source(unrelated_id, "Unrelated", "fragment", "Unrelated old text.\n"),
            "docs/template.md": original_template,
        },
        message="Add original template and fragments",
    )
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/origin.md": source(origin_id, "Origin", "fragment", "Current origin.\n"),
            "fragments/nested.md": source(nested_id, "Nested", "fragment", "Current nested.\n"),
            "docs/template.md": source(template_id, "Template", "document", "Current template.\n"),
            "fragments/copy.md": source(
                copy_id,
                "Copy",
                "fragment",
                "Copied content.\n",
                f"derived_from:\n  id: {origin_id}\n  commit: {first.object_id}\n",
            ),
            "docs/guide.md": source(
                document_id,
                "Guide",
                "document",
                "Guide body.\n",
                f"template_sources:\n  - id: {template_id}\n    commit: {first.object_id}\n"
                f"  - id: {origin_id}\n    commit: {first.object_id}\n",
            ),
        },
        message="Add copied fragment and template-derived document",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(reverse("msp-content-authoring-export"))
    assert response.status_code == 200, response.content
    assert len(verify_repository_source_snapshot(response.content)["historical_files"]) == 3
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        historical = {item["content_id"]: item for item in manifest["historical_files"]}
        assert set(historical) == {str(origin_id), str(nested_id), str(template_id)}
        assert {item["commit"] for item in historical.values()} == {first.object_id}
        assert historical[str(origin_id)]["roles"] == ["derived_from", "template_source"]
        assert historical[str(template_id)]["roles"] == ["template_source"]
        assert historical[str(nested_id)]["roles"] == ["include"]
        assert archive.read(historical[str(origin_id)]["path"]) == original_fragment
        assert archive.read(historical[str(template_id)]["path"]) == original_template
        assert archive.read(historical[str(nested_id)]["path"]) == original_nested
        assert f"pinned/{first.object_id}/fragments/unrelated.md" not in archive.namelist()
