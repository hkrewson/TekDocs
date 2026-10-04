from __future__ import annotations

import fcntl
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, transaction
from django.test import override_settings

from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import repository_service, repository_storage
from apps.core.models import (
    AuditEvent,
    RepositoryCommit,
    RepositoryCommitAudit,
    RepositoryHealthState,
    RepositoryReconciliationState,
    Tenant,
    Workspace,
    WorkspaceKind,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def managed_repository(tmp_path):
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        tenant = Tenant.objects.create(name="Repository Service MSP", slug="repository-service-msp")
        workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        initialized = repository_storage.ensure_workspace_repository(workspace)
        assert initialized is not None
        yield initialized.repository, root, root / f"{initialized.repository.id}.git"


def test_commit_read_delete_and_deterministic_identity(managed_repository):
    repository, _, path = managed_repository
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"# Setup\n"},
        message="Create setup guide",
    )

    assert first.created is True
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id,
        path="docs/guide.md",
    ) == b"# Setup\n"
    # The executable and operation are fixed; the path and object came from the
    # custody service exercised by this test.
    commit_text = subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/git", f"--git-dir={path}", "cat-file", "commit", first.object_id],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    identity = (
        f"{repository_service.SERVICE_NAME} "
        f"<{repository_service.SERVICE_EMAIL}>"
    )
    assert f"author {identity} " in commit_text
    assert f"committer {identity} " in commit_text

    unchanged = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={"docs/guide.md": b"# Setup\n"},
        message="Retain setup guide",
    )
    assert unchanged == repository_service.RepositoryCommitResult(
        repository.id,
        first.object_id,
        first.object_format,
        False,
    )

    deleted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={"docs/guide.md": None},
        message="Remove setup guide",
    )
    assert deleted.created is True
    with pytest.raises(repository_service.RepositoryInputError, match="does not exist"):
        repository_service.read_accepted_repository_file(
            repository_id=repository.id,
            path="docs/guide.md",
        )


def test_expected_base_prevents_silent_overwrite(managed_repository):
    repository, _, _ = managed_repository
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"accepted"},
        message="Accept first writer",
    )

    with pytest.raises(repository_service.RepositoryConflictError, match="base changed"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/guide.md": b"stale overwrite"},
            message="Reject stale writer",
        )

    assert RepositoryCommit.objects.filter(repository=repository).count() == 1
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id,
        path="docs/guide.md",
    ) == b"accepted"
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == accepted.object_id


def test_concurrent_writers_cannot_silently_overwrite(managed_repository):
    repository, _, _ = managed_repository

    def write(content: bytes):
        close_old_connections()
        try:
            return repository_service.commit_repository_files(
                repository_id=repository.id,
                expected_base=None,
                changes={"docs/concurrent.md": content},
                message="Competing writer",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write, content) for content in (b"first", b"second")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except repository_service.RepositoryConflictError:
                outcomes.append("conflict")

    assert sum(value == "conflict" for value in outcomes) == 1
    assert sum(isinstance(value, repository_service.RepositoryCommitResult) for value in outcomes) == 1
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id,
        path="docs/concurrent.md",
    ) in {b"first", b"second"}


@pytest.mark.parametrize(
    "path",
    (
        "/absolute.md",
        "../escape.md",
        "docs/../escape.md",
        "./guide.md",
        "-option.md",
        "docs:guide.md",
        "docs\\guide.md",
        ".git/config",
        "docs/\x01secret.md",
    ),
)
def test_hostile_paths_fail_closed(managed_repository, path):
    repository, _, _ = managed_repository

    with pytest.raises(repository_service.RepositoryInputError, match="path is invalid"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={path: b"content"},
            message="Rejected path",
        )


@pytest.mark.parametrize("expected_base", ("HEAD", "--help", "A" * 40, "0" * 39, b"0" * 40))
def test_hostile_refs_fail_closed(managed_repository, expected_base):
    repository, _, _ = managed_repository

    with pytest.raises(repository_service.RepositoryInputError, match="object identity"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=expected_base,
            changes={"docs/guide.md": b"content"},
            message="Rejected base",
        )


def test_empty_initial_commit_is_rejected(managed_repository):
    repository, _, path = managed_repository

    with pytest.raises(repository_service.RepositoryInputError, match="cannot be empty"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/missing.md": None},
            message="Reject empty initial state",
        )

    assert not (path / "refs" / "heads" / "main").exists()


def test_change_and_command_output_limits_are_enforced(managed_repository, monkeypatch):
    repository, _, path = managed_repository
    monkeypatch.setattr(repository_service, "MAX_FILE_BYTES", 4)
    with pytest.raises(repository_service.RepositoryResourceLimitError, match="size limit"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/guide.md": b"oversized"},
            message="Reject oversized file",
        )

    git = repository_service._GitRepository(repository.id, path, "sha1")
    with pytest.raises(repository_service.RepositoryResourceLimitError, match="output limit"):
        git._run("bounded_output_probe", ("version",), output_limit=1)


def test_git_command_timeout_terminates_the_process_group(managed_repository, monkeypatch, tmp_path):
    repository, _, path = managed_repository
    executable = tmp_path / "slow-git"
    executable.write_text("#!/bin/sh\nsleep 30\n")
    executable.chmod(0o700)
    monkeypatch.setattr(repository_service, "GIT_EXECUTABLE", str(executable))
    monkeypatch.setattr(repository_service, "GIT_TIMEOUT_SECONDS", 0.01)
    git = repository_service._GitRepository(repository.id, path, "sha1")

    with pytest.raises(repository_service.RepositoryCommandError, match="timed out"):
        git._run("timeout_probe", ())


@pytest.mark.parametrize("tamper", ("config", "alternate", "head"))
def test_malicious_repository_configuration_fails_closed(managed_repository, tamper):
    repository, _, path = managed_repository
    outside = path.parent / "untrusted-object-store"
    if tamper == "config":
        with (path / "config").open("a", encoding="utf-8") as config:
            config.write(f"[include]\n\tpath = {outside}\n")
    elif tamper == "alternate":
        (path / "objects" / "info" / "alternates").write_text(f"{outside}\n")
    else:
        (path / "HEAD").write_text("ref: refs/heads/-hostile\n")

    with pytest.raises(repository_service.RepositoryServiceError):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/guide.md": b"content"},
            message="Reject repository tampering",
        )


def test_interruption_rolls_back_and_next_write_recovers(managed_repository, monkeypatch):
    repository, root, path = managed_repository
    original = repository_service._accept_commit
    monkeypatch.setattr(
        repository_service,
        "_accept_commit",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/guide.md": b"interrupted"},
            message="Interrupted write",
        )

    assert not (path / "refs" / "heads" / "main").exists()
    assert RepositoryCommit.objects.filter(repository=repository).count() == 0
    assert not tuple(root.glob(f".{repository.id}.stage-*"))

    stale = root / f".{repository.id}.stage-abandoned"
    stale.mkdir(mode=0o700)
    (stale / "index.lock").write_bytes(b"abandoned")
    os.chmod(stale / "index.lock", 0o600)
    monkeypatch.setattr(repository_service, "_accept_commit", original)
    recovered = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"recovered"},
        message="Recover interrupted write",
    )

    assert recovered.created is True
    assert not stale.exists()


def test_repository_lock_timeout_is_bounded(managed_repository, monkeypatch):
    repository, root, _ = managed_repository
    lock_directory = root / ".locks"
    lock_directory.mkdir(mode=0o700)
    lock_path = lock_directory / f"{repository.id}.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    monkeypatch.setattr(repository_service, "LOCK_TIMEOUT_SECONDS", 0.01)
    try:
        with pytest.raises(repository_service.RepositoryConflictError, match="busy"):
            repository_service.commit_repository_files(
                repository_id=repository.id,
                expected_base=None,
                changes={"docs/guide.md": b"blocked"},
                message="Bounded lock wait",
            )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def test_command_failures_do_not_log_repository_content(managed_repository, monkeypatch, caplog):
    repository, _, _ = managed_repository
    sensitive_marker = "never-log-this-value"
    monkeypatch.setattr(repository_service, "GIT_EXECUTABLE", "/bin/false")

    with caplog.at_level(logging.WARNING), pytest.raises(
        repository_service.RepositoryCommandError,
        match="command failed",
    ):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={f"docs/{sensitive_marker}.md": sensitive_marker.encode()},
            message=f"Commit {sensitive_marker}",
        )

    assert sensitive_marker not in caplog.text


def test_authenticated_audit_attribution_is_separate_from_git_identity(managed_repository):
    repository, _, path = managed_repository
    actor = User.objects.create_user(email="repository-actor@example.invalid", display_name="Repository Actor")
    TenantMembership.objects.create(tenant=repository.tenant, user=actor, role=BuiltInRole.ADMINISTRATOR)
    request_id = repository.id

    result = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"accepted"},
        message="Accept attributed content",
        attribution=repository_service.RepositoryAuditAttribution(
            actor_id=actor.id,
            action="repository.content.accepted",
            request_id=request_id,
        ),
    )

    attribution = RepositoryCommitAudit.objects.select_related("audit_event", "commit").get(
        repository=repository
    )
    assert attribution.commit.object_id == result.object_id
    assert attribution.audit_event.actor_id == actor.id
    assert attribution.audit_event.action == "repository.content.accepted"
    assert attribution.audit_event.request_id == request_id
    commit_text = subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/git", f"--git-dir={path}", "cat-file", "commit", result.object_id],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert actor.display_name not in commit_text
    with pytest.raises(ValidationError, match="immutable"):
        attribution.save()
    with pytest.raises(ValidationError, match="append-only"):
        attribution.audit_event.save()
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        RepositoryCommitAudit.objects.filter(pk=attribution.pk).update(created_at=attribution.created_at)


def test_unaccepted_advanced_head_blocks_writes_but_keeps_last_known_good_readable(
    managed_repository, tmp_path
):
    repository, root, path = managed_repository
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"accepted"},
        message="Accept content",
    )
    git = repository_service._GitRepository(repository.id, path, accepted.object_format)
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700)
    advanced, created = git.write_commit(
        base=accepted.object_id,
        changes={"docs/guide.md": b"unaccepted"},
        message="Unaccepted crash-window commit",
        stage_directory=stage,
    )
    assert created is True

    diagnosis = repository_service.reconcile_workspace_repository(repository_id=repository.id)
    assert diagnosis.state == RepositoryReconciliationState.ADVANCED
    assert diagnosis.health == RepositoryHealthState.DEGRADED
    assert diagnosis.repaired is False
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == accepted.object_id
    assert git.raw_current_ref() == advanced
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id, path="docs/guide.md"
    ) == b"accepted"
    with pytest.raises(repository_service.RepositoryReconciliationError, match="requires reconciliation"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=accepted.object_id,
            changes={"docs/guide.md": b"new write"},
            message="Blocked until repaired",
        )

    repaired = repository_service.reconcile_workspace_repository(
        repository_id=repository.id, repair_to_accepted=True
    )
    assert repaired.state == RepositoryReconciliationState.MATCHED
    assert repaired.repaired is True
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == accepted.object_id
    assert git.raw_current_ref() == accepted.object_id
    assert not tuple(root.glob(f".{repository.id}.stage-*"))


def test_missing_accepted_object_disables_reads_and_writes(managed_repository):
    repository, _, path = managed_repository
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"accepted"},
        message="Accept content",
    )
    subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/git", f"--git-dir={path}", "update-ref", "-d", repository_service.CANONICAL_REF],
        check=True,
    )
    object_path = path / "objects" / accepted.object_id[:2] / accepted.object_id[2:]
    object_path.unlink()

    diagnosis = repository_service.reconcile_workspace_repository(repository_id=repository.id)
    assert diagnosis.state == RepositoryReconciliationState.MISSING
    with pytest.raises(repository_service.RepositoryReconciliationError, match="unavailable"):
        repository_service.read_accepted_repository_file(repository_id=repository.id, path="docs/guide.md")
    repaired = repository_service.reconcile_workspace_repository(
        repository_id=repository.id, repair_to_accepted=True
    )
    assert repaired.repaired is False
    assert repaired.state == RepositoryReconciliationState.MISSING


def test_audit_attribution_rejects_actor_outside_tenant(managed_repository):
    repository, _, _ = managed_repository
    actor = User.objects.create_user(email="outsider@example.invalid", display_name="Outsider")

    with pytest.raises(repository_service.RepositoryInputError, match="not authorized"):
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=None,
            changes={"docs/guide.md": b"rejected"},
            message="Reject outsider",
            attribution=repository_service.RepositoryAuditAttribution(
                actor_id=actor.id,
                action="repository.content.accepted",
            ),
        )

    assert not RepositoryCommit.objects.filter(repository=repository).exists()
    assert not AuditEvent.objects.filter(actor=actor).exists()


def test_non_commit_head_is_corrupt_and_explicit_repair_restores_accepted_head(managed_repository):
    repository, _, path = managed_repository
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=None,
        changes={"docs/guide.md": b"accepted"},
        message="Accept content",
    )
    blob_id = subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/git", f"--git-dir={path}", "hash-object", "-w", "--stdin"],
        input=b"not a commit",
        check=True,
        capture_output=True,
    ).stdout.decode().strip()
    (path / "refs" / "heads" / "main").write_text(f"{blob_id}\n", encoding="ascii")

    diagnosis = repository_service.reconcile_workspace_repository(repository_id=repository.id)
    assert diagnosis.state == RepositoryReconciliationState.CORRUPT
    assert diagnosis.health == RepositoryHealthState.BLOCKED
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id, path="docs/guide.md"
    ) == b"accepted"
    repaired = repository_service.reconcile_workspace_repository(
        repository_id=repository.id, repair_to_accepted=True
    )
    assert repaired.repaired is True
    assert repaired.state == RepositoryReconciliationState.MATCHED


def test_unavailable_repository_records_bounded_health(managed_repository, monkeypatch, caplog):
    repository, _, _ = managed_repository
    sensitive_marker = "private-repository-path"
    monkeypatch.setattr(
        repository_service,
        "_load_repository",
        lambda repository_id: (_ for _ in ()).throw(
            repository_service.RepositoryServiceError(sensitive_marker)
        ),
    )

    with caplog.at_level(logging.WARNING):
        diagnosis = repository_service.reconcile_workspace_repository(repository_id=repository.id)

    assert diagnosis.state == RepositoryReconciliationState.UNAVAILABLE
    assert diagnosis.health == RepositoryHealthState.BLOCKED
    assert sensitive_marker not in caplog.text
    repository.refresh_from_db()
    assert repository.last_reconciliation_state == RepositoryReconciliationState.UNAVAILABLE
