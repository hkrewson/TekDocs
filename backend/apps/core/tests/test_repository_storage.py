import io
import os
import stat
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_storage
from apps.core.models import (
    InstallationState,
    Tenant,
    Workspace,
    WorkspaceKind,
    WorkspaceRepository,
    repository_identity_uuid,
    repository_storage_relative_path,
)
from apps.core.organizations import create_organization


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


@pytest.mark.parametrize(
    "relative_path",
    [
        "/repositories/repository.git",
        "../repository.git",
        "repositories/../repository.git",
        "other/repository.git",
        "repositories/repository.git/child",
    ],
)
def test_repository_path_rejects_noncanonical_paths(tmp_path, relative_path):
    repository_id = uuid.uuid4()

    with pytest.raises(repository_storage.RepositoryStorageError):
        repository_storage.repository_path(
            root=tmp_path,
            repository_id=repository_id,
            storage_relative_path=relative_path,
        )


@pytest.mark.django_db
def test_repository_initialization_is_private_deterministic_and_idempotent(tmp_path):
    root = tmp_path / "repositories"
    tenant = Tenant.objects.create(name="Custody MSP", slug="custody-msp")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)

    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        first = repository_storage.ensure_workspace_repository(workspace)
        assert first is not None
        expected_id = repository_identity_uuid(workspace_id=workspace.id)
        destination = root / f"{expected_id}.git"
        assert first.repository.id == expected_id
        assert first.repository.storage_relative_path == repository_storage_relative_path(
            repository_id=expected_id
        )
        assert first.binding_created is True
        assert first.storage_created is True
        assert (destination / "HEAD").read_text().strip() == "ref: refs/heads/main"
        assert _mode(root) == 0o700
        assert all(_mode(path) == 0o700 for path in (destination, destination / "objects", destination / "refs"))
        assert all(_mode(path) == 0o600 for path in (destination / "HEAD", destination / "config"))

        destination.chmod(0o755)
        (destination / "HEAD").chmod(0o644)
        second = repository_storage.ensure_workspace_repository(workspace)

    assert second is not None
    assert second.repository.id == expected_id
    assert second.binding_created is False
    assert second.storage_created is False
    assert _mode(destination) == 0o700
    assert _mode(destination / "HEAD") == 0o600
    assert WorkspaceRepository.objects.filter(workspace=workspace).count() == 1


@pytest.mark.django_db
def test_repository_initialization_rejects_symlinks_and_unexpected_ownership(tmp_path, monkeypatch):
    root = tmp_path / "repositories"
    tenant = Tenant.objects.create(name="Boundary MSP", slug="boundary-msp")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)

    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        result = repository_storage.ensure_workspace_repository(workspace)
        assert result is not None
        destination = root / f"{result.repository.id}.git"
        head = destination / "HEAD"
        head.unlink()
        head.symlink_to(tmp_path / "outside")
        with pytest.raises(repository_storage.RepositoryStorageError, match="symbolic links"):
            repository_storage.ensure_workspace_repository(workspace)

    safe_root = tmp_path / "wrong-owner"
    safe_root.mkdir(mode=0o700)
    monkeypatch.setattr(repository_storage, "_runtime_identity", lambda: (os.geteuid() + 1, os.getegid()))
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(safe_root)):
        with pytest.raises(repository_storage.RepositoryStorageError, match="ownership"):
            repository_storage.ensure_workspace_repository(workspace)


@pytest.mark.django_db
def test_failed_git_initialization_leaves_no_partial_repository(tmp_path, monkeypatch):
    root = tmp_path / "repositories"
    tenant = Tenant.objects.create(name="Atomic MSP", slug="atomic-msp")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    repository_id = repository_identity_uuid(workspace_id=workspace.id)
    monkeypatch.setattr(
        repository_storage.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        with pytest.raises(repository_storage.RepositoryStorageError, match="initialization failed"):
            repository_storage.ensure_workspace_repository(workspace)

    assert not (root / f"{repository_id}.git").exists()
    assert list(root.iterdir()) == []


@pytest.mark.django_db
def test_repository_initializer_backfills_all_workspaces_and_is_retry_safe(tmp_path):
    root = tmp_path / "repositories"
    first_tenant = Tenant.objects.create(name="First MSP", slug="first-custody-msp")
    second_tenant = Tenant.objects.create(name="Second MSP", slug="second-custody-msp")
    output = io.StringIO()

    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        call_command("initialize_workspace_repositories", stdout=output)
        assert "2 initialized, 0 retained" in output.getvalue()
        output = io.StringIO()
        call_command("initialize_workspace_repositories", stdout=output)

    assert "0 initialized, 2 retained" in output.getvalue()
    assert WorkspaceRepository.objects.count() == 2
    first = WorkspaceRepository.objects.get(workspace__tenant=first_tenant)
    second = WorkspaceRepository.objects.get(workspace__tenant=second_tenant)
    assert first.id != second.id
    assert (root / f"{first.id}.git").is_dir()
    assert (root / f"{second.id}.git").is_dir()


@pytest.mark.django_db
def test_supported_workspace_creation_paths_initialize_storage(
    tmp_path,
    django_capture_on_commit_callbacks,
):
    root = tmp_path / "repositories"
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)

    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        installation = bootstrap_owner(
            tenant_name="Lifecycle MSP",
            owner_email="repository-owner@example.com",
            owner_display_name="Repository Owner",
            password="Repository-only-Aa7-password",
        )
        msp_workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        assert WorkspaceRepository.objects.filter(workspace=msp_workspace).exists()

        with django_capture_on_commit_callbacks(execute=True):
            organization = create_organization(
                tenant=installation.tenant,
                actor_id=installation.owner.id,
                name="Lifecycle Client",
                legal_name="",
                website="",
                classifications=(),
            )
            sibling = create_organization(
                tenant=installation.tenant,
                actor_id=installation.owner.id,
                name="Lifecycle Sibling",
                legal_name="",
                website="",
                classifications=(),
            )

    client_repository = WorkspaceRepository.objects.get(workspace=organization.ownership_workspace)
    sibling_repository = WorkspaceRepository.objects.get(workspace=sibling.ownership_workspace)
    assert client_repository.id != sibling_repository.id
    assert (root / f"{client_repository.id}.git").is_dir()
    assert (root / f"{sibling_repository.id}.git").is_dir()


def test_repository_root_rejects_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repositories"
    root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(repository_storage.RepositoryStorageError, match="symbolic links"):
        repository_storage.ensure_repository_root(root)


def test_repository_root_rejects_symlinked_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(repository_storage.RepositoryStorageError, match="symbolic links"):
        repository_storage.ensure_repository_root(linked_parent / "repositories")


def test_initializer_is_a_noop_when_repository_custody_is_disabled():
    output = io.StringIO()

    with override_settings(TEKDOCS_REPOSITORY_ROOT=""):
        call_command("initialize_workspace_repositories", stdout=output)

    assert output.getvalue().strip() == "Workspace repository custody is disabled."
