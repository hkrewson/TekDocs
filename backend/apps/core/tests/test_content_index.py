from __future__ import annotations

import uuid

import pytest
from django.db import transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_service, repository_storage
from apps.core.content_index import (
    ContentIndexValidationError,
    content_graph_projection,
    index_repository_content,
)
from apps.core.models import (
    ContentIndexAttempt,
    ContentNode,
    InstallationState,
    Tenant,
    Workspace,
    WorkspaceKind,
)
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope

pytestmark = pytest.mark.django_db(transaction=True)


def _content(*, content_id: uuid.UUID, title: str, body: str, kind: str = "document") -> bytes:
    return (
        "---\n"
        "schema: tekdocs.content/v1\n"
        f"id: {content_id}\n"
        f"kind: {kind}\n"
        f"title: {title}\n"
        "properties:\n"
        "  audience: technicians\n"
        "---\n"
        f"{body}"
    ).encode()


@pytest.fixture
def indexed_repository(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Content Index MSP",
            owner_email="content-index-owner@example.invalid",
            owner_display_name="Content Index Owner",
            password="ContentIndexPassword-2026!",
        )
        tenant = installation.tenant
        workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        expected_base = repository.accepted_commit.object_id if repository.accepted_commit_id else None
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        commit = repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=expected_base,
            changes={
                "docs/guide.md": _content(
                    content_id=first_id,
                    title="Recovery guide",
                    body=f"Read [[{second_id}|shared recovery steps]].\n",
                ),
                "fragments/recovery.md": _content(
                    content_id=second_id,
                    title="Recovery steps",
                    kind="fragment",
                    body="Restart the service.\n",
                ),
            },
            message="Add canonical content",
        )
        yield installation, workspace, repository, commit, first_id, second_id


def test_rebuild_is_deterministic_and_restores_links_backlinks_and_properties(indexed_repository):
    _installation, _workspace, repository, commit, first_id, second_id = indexed_repository
    first = index_repository_content(repository_id=repository.id)
    repository.refresh_from_db()
    before = content_graph_projection(repository=repository)

    assert first.object_id == commit.object_id
    assert first.node_count == 2
    assert first.link_count == 1
    guide = next(node for node in before["nodes"] if node["id"] == str(first_id))
    fragment = next(node for node in before["nodes"] if node["id"] == str(second_id))
    assert guide["properties"] == {"audience": "technicians"}
    assert guide["outgoing_links"] == [
        {"target_id": str(second_id), "fragment": None, "label": "shared recovery steps", "resolved": True}
    ]
    assert fragment["backlinks"] == [str(first_id)]

    ContentNode.objects.filter(repository=repository).delete()
    type(repository).objects.filter(pk=repository.pk).update(indexed_commit=None)
    rebuilt = index_repository_content(repository_id=repository.id, force=True)
    repository.refresh_from_db()
    after = content_graph_projection(repository=repository)

    assert rebuilt.projection_digest == first.projection_digest
    assert after == before


def test_invalid_commit_retains_last_known_good_projection_and_sanitizes_diagnostics(indexed_repository):
    _installation, _workspace, repository, first_commit, first_id, _second_id = indexed_repository
    index_repository_content(repository_id=repository.id)
    repository.refresh_from_db()
    before = content_graph_projection(repository=repository)
    invalid = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first_commit.object_id,
        changes={"docs/guide.md": b"# frontmatter is required\n"},
        message="Introduce invalid content",
    )

    with pytest.raises(ContentIndexValidationError):
        index_repository_content(repository_id=repository.id)

    repository.refresh_from_db()
    assert repository.indexed_commit.object_id == first_commit.object_id
    assert ContentNode.objects.get(repository=repository, content_id=first_id).title == "Recovery guide"
    attempt = ContentIndexAttempt.objects.get(repository=repository, commit__object_id=invalid.object_id)
    assert attempt.status == "rejected"
    assert attempt.diagnostics == [
        {
            "code": "frontmatter.missing",
            "message": "Content must begin with versioned frontmatter",
            "path": "docs/guide.md",
        }
    ]
    assert content_graph_projection(repository=repository)["nodes"] == before["nodes"]


def test_links_never_resolve_across_workspace_repositories(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        first_tenant = Tenant.objects.create(name="First MSP", slug=f"first-{uuid.uuid4()}")
        second_tenant = Tenant.objects.create(name="Second MSP", slug=f"second-{uuid.uuid4()}")
        target_id = uuid.uuid4()
        source_id = uuid.uuid4()
        repositories = []
        for tenant, content in (
            (first_tenant, _content(content_id=source_id, title="Source", body=f"[[{target_id}]]\n")),
            (second_tenant, _content(content_id=target_id, title="Private target", body="private\n")),
        ):
            workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
            repository = repository_storage.ensure_workspace_repository(workspace).repository
            repository_service.commit_repository_files(
                repository_id=repository.id,
                expected_base=None,
                changes={"docs/content.md": content},
                message="Add content",
            )
            index_repository_content(repository_id=repository.id)
            repository.refresh_from_db()
            repositories.append(repository)

        projection = content_graph_projection(repository=repositories[0])
        assert projection["nodes"][0]["outgoing_links"][0]["resolved"] is False
        assert "Private target" not in str(projection)


def test_authorized_api_returns_only_the_selected_repository_projection(indexed_repository):
    installation, _workspace, repository, _commit, first_id, _second_id = indexed_repository
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)

    response = browser.get(reverse("msp-content-graph"))

    assert response.status_code == 200
    assert any(node["id"] == str(first_id) for node in response.json()["nodes"])
    assert Client().get(reverse("msp-content-graph")).status_code in {401, 403}


def test_runtime_role_cannot_read_a_different_workspace_projection(indexed_repository, django_runtime_role):
    installation, _workspace, repository, _commit, _first_id, _second_id = indexed_repository
    index_repository_content(repository_id=repository.id)
    foreign = Tenant.objects.create(name="Foreign content MSP", slug=f"foreign-content-{uuid.uuid4()}")

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
        )
        assert ContentNode.objects.count() == 2
        bind_local_rls_scope(DataScope.tenant(foreign), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert ContentNode.objects.count() == 0
