from __future__ import annotations

import uuid

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
from apps.core.models import ContentNode, InstallationState, Workspace, WorkspaceKind
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
