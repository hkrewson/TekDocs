from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest
from django.test import override_settings

from apps.core import repository_storage
from apps.core.models import RepositoryCommit, RepositoryObjectFormat, Tenant, Workspace, WorkspaceKind
from apps.core.repository_recovery import (
    RepositoryRecoveryError,
    create_repository_recovery_archive,
    restore_repository_recovery_archive,
    validate_repository_recovery_archive,
    verify_repository_recovery_database,
)
from apps.core.repository_service import CANONICAL_REF, commit_repository_files

pytestmark = pytest.mark.django_db(transaction=True)


def _git(repository: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "Recovery Test",
            "GIT_AUTHOR_EMAIL": "recovery-test@tekdocs.invalid",
            "GIT_AUTHOR_DATE": "1700000000 +0000",
            "GIT_COMMITTER_NAME": "Recovery Test",
            "GIT_COMMITTER_EMAIL": "recovery-test@tekdocs.invalid",
            "GIT_COMMITTER_DATE": "1700000000 +0000",
        }
    )
    return subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/git", f"--git-dir={repository}", *arguments],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    ).stdout.strip()


@pytest.fixture
def recovery_repository(tmp_path):
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        tenant = Tenant.objects.create(name="Recovery MSP", slug="recovery-msp")
        workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        initialized = repository_storage.ensure_workspace_repository(workspace)
        assert initialized is not None
        _, path = repository_storage.resolve_managed_repository_path(initialized.repository)
        commit_repository_files(
            repository_id=initialized.repository.id,
            expected_base=None,
            changes={"docs/recovery.md": b"# Recovery\n"},
            message="Add recovery evidence",
        )
        initialized.repository.refresh_from_db()
        yield initialized.repository, path, root


def test_repository_archive_restores_exact_database_authority_and_unreachable_evidence(
    recovery_repository, tmp_path
):
    repository, path, _ = recovery_repository
    tree = _git(path, "rev-parse", f"{CANONICAL_REF}^{{tree}}")
    unreachable = _git(path, "commit-tree", tree, "-m", "Retained evidence")
    RepositoryCommit.objects.create(
        tenant=repository.tenant,
        repository=repository,
        object_format=repository.accepted_commit.object_format,
        object_id=unreachable,
    )
    archive = tmp_path / "repositories.tar"

    manifest = create_repository_recovery_archive(archive)
    assert manifest["repositories"][0]["accepted_commit"] == repository.accepted_commit.object_id
    assert unreachable in manifest["repositories"][0]["verified_commits"]
    assert validate_repository_recovery_archive(archive) == manifest
    assert verify_repository_recovery_database(archive) == manifest

    restored_root = tmp_path / "restored"
    restore_repository_recovery_archive(archive, restored_root)
    restored = restored_root / f"{repository.id}.git"
    assert _git(restored, "rev-parse", CANONICAL_REF) == repository.accepted_commit.object_id
    assert _git(restored, "cat-file", "-t", unreachable) == "commit"
    assert not _git(restored, "for-each-ref", "--format=%(refname)", "refs/tekdocs/recovery")


def test_repository_archive_refuses_advanced_repository(recovery_repository, tmp_path):
    repository, path, _ = recovery_repository
    tree = _git(path, "rev-parse", f"{CANONICAL_REF}^{{tree}}")
    advanced = _git(path, "commit-tree", tree, "-p", repository.accepted_commit.object_id, "-m", "Unaccepted")
    _git(path, "update-ref", CANONICAL_REF, advanced)

    with pytest.raises(RepositoryRecoveryError, match="match its accepted head"):
        create_repository_recovery_archive(tmp_path / "advanced.tar")


def test_repository_archive_refuses_mixed_verified_object_formats(recovery_repository, tmp_path):
    repository, _, _ = recovery_repository
    RepositoryCommit.objects.create(
        tenant=repository.tenant,
        repository=repository,
        object_format=RepositoryObjectFormat.SHA256,
        object_id="a" * 64,
    )
    with pytest.raises(RepositoryRecoveryError, match="different format"):
        create_repository_recovery_archive(tmp_path / "mixed.tar")


def test_repository_verification_rejects_missing_retained_commit(recovery_repository, tmp_path):
    repository, path, _ = recovery_repository
    tree = _git(path, "rev-parse", f"{CANONICAL_REF}^{{tree}}")
    retained = _git(path, "commit-tree", tree, "-m", "Retained but unreachable")
    RepositoryCommit.objects.create(
        tenant=repository.tenant,
        repository=repository,
        object_format=repository.accepted_commit.object_format,
        object_id=retained,
    )
    archive = tmp_path / "repositories.tar"
    create_repository_recovery_archive(archive)
    assert verify_repository_recovery_database(archive)
    retained_object = path / "objects" / retained[:2] / retained[2:]
    assert retained_object.is_file()
    retained_object.unlink()
    with pytest.raises(RepositoryRecoveryError, match="verified Git commit is unavailable"):
        verify_repository_recovery_database(archive)


def test_repository_archive_rejects_truncation_and_swapped_bundle(recovery_repository, tmp_path):
    _, _, _ = recovery_repository
    archive = tmp_path / "repositories.tar"
    create_repository_recovery_archive(archive)
    truncated = tmp_path / "truncated.tar"
    truncated.write_bytes(archive.read_bytes()[:512])
    with pytest.raises(RepositoryRecoveryError, match="invalid or truncated"):
        validate_repository_recovery_archive(truncated)

    with tarfile.open(archive, "r:") as source:
        manifest = json.loads(source.extractfile("manifest.json").read())
        bundle_name = manifest["repositories"][0]["bundle"]
        bundle = source.extractfile(bundle_name).read()
    swapped = tmp_path / "swapped.tar"
    replacement = b"not a git bundle"
    manifest["repositories"][0]["sha256"] = hashlib.sha256(replacement).hexdigest()
    with tarfile.open(swapped, "w") as destination:
        manifest_bytes = (json.dumps(manifest, sort_keys=True) + "\n").encode()
        manifest_info = tarfile.TarInfo("manifest.json")
        manifest_info.size = len(manifest_bytes)
        destination.addfile(manifest_info, io.BytesIO(manifest_bytes))
        bundle_info = tarfile.TarInfo(bundle_name)
        bundle_info.size = len(replacement)
        destination.addfile(bundle_info, io.BytesIO(replacement))
    assert bundle
    with pytest.raises(RepositoryRecoveryError, match="archived or verified"):
        validate_repository_recovery_archive(swapped)


def test_repository_archive_restore_requires_empty_destination(recovery_repository, tmp_path):
    archive = tmp_path / "repositories.tar"
    create_repository_recovery_archive(archive)
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "retained").write_text("do not replace")

    with pytest.raises(RepositoryRecoveryError, match="must be empty"):
        restore_repository_recovery_archive(archive, destination)
    assert (destination / "retained").read_text() == "do not replace"
