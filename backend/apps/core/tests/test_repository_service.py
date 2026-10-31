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


def test_request_database_rollback_also_restores_git_head(managed_repository):
    from types import SimpleNamespace

    from django.http import HttpResponse

    from apps.core.middleware import RLSRequestScopeMiddleware

    repository, _root, _path = managed_repository
    initial = repository_service.reconcile_workspace_repository(repository_id=repository.id).state

    def response(_request):
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/rollback.md": b"Uncommitted request content"}, message="Exercise request rollback",
        )
        transaction.set_rollback(True)
        return HttpResponse(status=500)

    request = SimpleNamespace(COOKIES={}, api_token=object(), user=SimpleNamespace(is_authenticated=False))
    result = RLSRequestScopeMiddleware(response)(request)
    assert result.status_code == 500
    repository.refresh_from_db()
    assert repository.accepted_commit_id is None
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == initial


def test_coordinated_write_restores_refs_after_late_failure(managed_repository):
    repository, _root, _path = managed_repository
    initial = repository_service.reconcile_workspace_repository(repository_id=repository.id).state
    with pytest.raises(ValueError, match="late validation"), repository_service.coordinated_repository_transaction():
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/rollback.md": b"Rollback coordinated content"}, message="Exercise late failure",
        )
        assert repository_service.read_accepted_repository_file(
            repository_id=repository.id, path="docs/rollback.md",
        ) == b"Rollback coordinated content"
        raise ValueError("late validation")
    repository.refresh_from_db()
    assert repository.accepted_commit_id is None
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == initial


def test_nested_coordinated_failure_preserves_earlier_success(managed_repository):
    repository, _root, _path = managed_repository
    with repository_service.coordinated_repository_transaction():
        first = repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/guide.md": b"Earlier successful operation"}, message="Accept earlier operation",
        )
        with pytest.raises(ValueError), repository_service.coordinated_repository_transaction():
            repository_service.commit_repository_files(
                repository_id=repository.id, expected_base=first.object_id,
                changes={"docs/guide.md": b"Failed nested operation"}, message="Attempt nested operation",
            )
            raise ValueError("nested validation")
        assert repository_service.read_accepted_repository_file(
            repository_id=repository.id, path="docs/guide.md",
        ) == b"Earlier successful operation"
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == first.object_id
    assert RepositoryCommit.objects.filter(repository=repository).count() == 1
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == "matched"


def test_post_commit_callback_failure_does_not_revert_committed_git(managed_repository):
    repository, _root, _path = managed_repository

    def fail_after_commit():
        raise ValueError("post-commit callback")

    with (
        pytest.raises(ValueError, match="post-commit callback"),
        repository_service.coordinated_repository_transaction(),
    ):
        committed = repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/guide.md": b"Committed content"}, message="Accept durable operation",
        )
        transaction.on_commit(fail_after_commit)
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == committed.object_id
    assert repository_service.read_accepted_repository_file(
        repository_id=repository.id, path="docs/guide.md",
    ) == b"Committed content"
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == "matched"


def test_nested_explicit_rollback_restores_its_git_checkpoint(managed_repository):
    repository, _root, _path = managed_repository
    with repository_service.coordinated_repository_transaction():
        first = repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/guide.md": b"Earlier successful operation"}, message="Accept earlier operation",
        )
        with repository_service.coordinated_repository_transaction():
            repository_service.commit_repository_files(
                repository_id=repository.id, expected_base=first.object_id,
                changes={"docs/guide.md": b"Explicitly rolled back operation"}, message="Attempt nested operation",
            )
            transaction.set_rollback(True)
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == first.object_id
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == "matched"


def test_post_commit_manifest_synchronization_remains_supported(managed_repository):
    from apps.core.repository_manifests import (
        WORKSPACE_MANIFEST_PATH,
        schedule_tenant_manifest_synchronization,
    )

    repository, _root, _path = managed_repository
    tenant = repository.tenant
    with repository_service.coordinated_repository_transaction():
        tenant.name = "Renamed coordinated fixture"
        tenant.save(update_fields=("name", "updated_at"))
        schedule_tenant_manifest_synchronization(tenant.id)
    import yaml

    manifest = yaml.safe_load(repository_service.read_accepted_repository_file(
        repository_id=repository.id, path=WORKSPACE_MANIFEST_PATH,
    ))
    assert manifest["workspace"]["display_name"] == "Renamed coordinated fixture"


def test_copied_context_cannot_reuse_an_expired_filesystem_lock(managed_repository, monkeypatch):
    from contextvars import copy_context
    from threading import Event

    repository, root, _path = managed_repository
    with repository_service.coordinated_repository_transaction():
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/guide.md": b"Committed context fixture"}, message="Accept context fixture",
        )
        copied = copy_context()
    held, release = Event(), Event()

    def hold_writer():
        with repository_service._repository_lock(root, repository.id, exclusive=True):
            held.set()
            assert release.wait(10)

    monkeypatch.setattr(repository_service, "LOCK_TIMEOUT_SECONDS", 0.05)
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(hold_writer)
        assert held.wait(5)
        try:
            with pytest.raises(repository_service.RepositoryConflictError, match="busy"):
                copied.run(
                    repository_service.read_accepted_repository_file,
                    repository_id=repository.id, path="docs/guide.md",
                )
        finally:
            release.set()
        writer.result(timeout=5)


def test_caught_plain_savepoint_failure_cannot_leave_git_ahead_of_sql(managed_repository):
    repository, _root, _path = managed_repository
    with repository_service.coordinated_repository_transaction():
        first = repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=None,
            changes={"docs/guide.md": b"Committed earlier operation"}, message="Accept earlier operation",
        )
        try:
            with transaction.atomic():
                repository_service.commit_repository_files(
                    repository_id=repository.id, expected_base=first.object_id,
                    changes={"docs/guide.md": b"Rolled-back plain savepoint"}, message="Exercise plain savepoint",
                )
                raise ValueError("caught savepoint failure")
        except ValueError:
            pass
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == first.object_id
    assert repository_service.reconcile_workspace_repository(repository_id=repository.id).state == "matched"


@pytest.mark.parametrize("operation", ["read", "rejected_write"])
def test_coordinated_scope_does_not_repair_preexisting_git_drift(managed_repository, tmp_path, operation):
    repository, _root, path = managed_repository
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id, expected_base=None,
        changes={"docs/guide.md": b"Accepted bytes"}, message="Accept drift fixture",
    )
    git = repository_service._GitRepository(repository.id, path, accepted.object_format)
    stage = tmp_path / "unaccepted-stage"
    stage.mkdir(mode=0o700)
    advanced, _created = git.write_commit(
        base=accepted.object_id, changes={"docs/guide.md": b"Unaccepted bytes"},
        message="Exercise preexisting drift", stage_directory=stage,
    )
    with repository_service.coordinated_repository_transaction():
        if operation == "read":
            assert repository_service.read_accepted_repository_file(
                repository_id=repository.id, path="docs/guide.md",
            ) == b"Accepted bytes"
        else:
            with pytest.raises(repository_service.RepositoryReconciliationError):
                repository_service.commit_repository_files(
                    repository_id=repository.id, expected_base=accepted.object_id,
                    changes={"docs/guide.md": b"Rejected bytes"}, message="Reject drifted write",
                )
    assert git.raw_current_ref() == advanced
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == accepted.object_id


def test_coordinated_artifact_cleanup_attempts_every_file_and_preserves_primary_error():
    from apps.core.repository_service import _active_repository_transaction, coordinated_repository_transaction

    discarded = []

    def unavailable_storage():
        discarded.append("unavailable")
        raise OSError("synthetic storage failure")

    with pytest.raises(RuntimeError, match="original request failed"):
        with coordinated_repository_transaction():
            active = _active_repository_transaction()
            active.register_created_artifact(lambda: False, unavailable_storage)
            active.register_created_artifact(lambda: False, lambda: discarded.append("second"))
            raise RuntimeError("original request failed")
    assert discarded == ["unavailable", "second"]
