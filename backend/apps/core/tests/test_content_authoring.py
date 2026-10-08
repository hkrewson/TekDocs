from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
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
from apps.core.models import AuditEvent, ContentNode, InstallationState, Workspace, WorkspaceKind
from apps.core.organizations import create_organization
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
    assert browser.get(url).content == response.content
    events = AuditEvent.objects.filter(action="repository_source_export.downloaded", entity_id=repository.id)
    assert events.count() == 2
    assert events.first().metadata == {"accepted_commit": second.accepted_commit, "file_count": 2}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        assert manifest["format"] == "tekdocs-repository-source-snapshot/v2"
        assert manifest["workspace_id"] == str(repository.workspace_id)
        assert manifest["accepted_commit"] == second.accepted_commit
        assert manifest["scope"] == "current-files-and-reachable-pinned-includes"
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


def test_repository_source_snapshot_retains_only_reachable_pinned_fragments(authoring_context, monkeypatch):
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
    assert browser.get(url).content == response.content
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("tekdocs-source.json"))
        historical = manifest["historical_files"]
        assert {item["content_id"] for item in historical} == {str(parent_id), str(nested_id)}
        assert {item["commit"] for item in historical} == {first.object_id}
        assert {item["source_path"] for item in historical} == {"fragments/parent.md", "fragments/nested.md"}
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
