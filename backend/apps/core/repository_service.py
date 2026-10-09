from __future__ import annotations

import configparser
import fcntl
import logging
import os
import re
import shutil
import signal
import stat
import subprocess  # nosec B404
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.db import transaction
from django.utils import timezone

from .models import (
    AuditEvent,
    InstallationState,
    RepositoryCommit,
    RepositoryCommitAudit,
    RepositoryHealthState,
    RepositoryLifecycleState,
    RepositoryObjectFormat,
    RepositoryReconciliationState,
    WorkspaceRepository,
)
from .repository_storage import (
    DIRECTORY_MODE,
    FILE_MODE,
    GIT_EXECUTABLE,
    RepositoryStorageError,
    _enforce_private_tree,
    _require_owned_path,
    resolve_managed_repository_path,
)

logger = logging.getLogger(__name__)

CANONICAL_REF = "refs/heads/main"
SERVICE_NAME = "TekDocs Repository Service"
SERVICE_EMAIL = "repository-service@tekdocs.invalid"
GIT_TIMEOUT_SECONDS = 10
LOCK_TIMEOUT_SECONDS = 5
LOCK_POLL_SECONDS = 0.025
MAX_GIT_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_GIT_ERROR_BYTES = 32 * 1024
MAX_CONFIG_BYTES = 8 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_COMMIT_BYTES = 4 * 1024 * 1024
MAX_COMMIT_PATHS = 128
MAX_INDEX_PATHS = 2048
MAX_PINNED_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_PATH_BYTES = 512
MAX_MESSAGE_BYTES = 240
REGULAR_FILE_MODE = "100644"


class RepositoryServiceError(RuntimeError):
    pass


class RepositoryConflictError(RepositoryServiceError):
    pass


class RepositoryInputError(RepositoryServiceError):
    pass


class RepositoryFileNotFoundError(RepositoryInputError):
    pass


class RepositoryCommandError(RepositoryServiceError):
    pass


class RepositoryResourceLimitError(RepositoryServiceError):
    pass


class RepositoryReconciliationError(RepositoryServiceError):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryCommitResult:
    repository_id: uuid.UUID
    object_id: str
    object_format: str
    created: bool


@dataclass(frozen=True, slots=True)
class RepositoryAuditAttribution:
    actor_id: uuid.UUID
    action: str
    request_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RepositoryReconciliationResult:
    repository_id: uuid.UUID
    state: str
    health: str
    repaired: bool


def _validate_path(value: str) -> str:
    if not isinstance(value, str):
        raise RepositoryInputError("Repository path is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RepositoryInputError("Repository path is invalid") from exc
    candidate = PurePosixPath(value)
    if (
        not value
        or len(encoded) > MAX_PATH_BYTES
        or value.startswith("-")
        or value.endswith("/")
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or candidate.is_absolute()
        or str(candidate) != value
        or any(part in {"", ".", ".."} or part.casefold() == ".git" for part in candidate.parts)
    ):
        raise RepositoryInputError("Repository path is invalid")
    return value


def _validate_message(value: str) -> str:
    if not isinstance(value, str):
        raise RepositoryInputError("Repository commit message is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RepositoryInputError("Repository commit message is invalid") from exc
    if (
        not value
        or value.strip() != value
        or len(encoded) > MAX_MESSAGE_BYTES
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryInputError("Repository commit message is invalid")
    return value


def _validate_attribution(value: RepositoryAuditAttribution | None) -> RepositoryAuditAttribution | None:
    if value is None:
        return None
    if (
        not isinstance(value.actor_id, uuid.UUID)
        or not isinstance(value.action, str)
        or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,119}", value.action)
        or (value.request_id is not None and not isinstance(value.request_id, uuid.UUID))
    ):
        raise RepositoryInputError("Repository audit attribution is invalid")
    return value


def _object_pattern(object_format: str) -> re.Pattern[str]:
    length = 40 if object_format == RepositoryObjectFormat.SHA1 else 64
    return re.compile(rf"[0-9a-f]{{{length}}}")


def _validate_object_id(value: str, object_format: str) -> str:
    if not isinstance(value, str) or not _object_pattern(object_format).fullmatch(value):
        raise RepositoryInputError("Repository object identity is invalid")
    return value


def _zero_object_id(object_format: str) -> str:
    return "0" * (40 if object_format == RepositoryObjectFormat.SHA1 else 64)


def _ensure_private_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _require_owned_path(path, directory=True)
    else:
        try:
            path.mkdir(mode=DIRECTORY_MODE)
        except FileExistsError:
            pass
        _require_owned_path(path, directory=True)
    path.chmod(DIRECTORY_MODE)


def _cleanup_staging_directories(root: Path, repository_id: uuid.UUID) -> None:
    prefix = f".{repository_id}.stage-"
    try:
        candidates = tuple(root.iterdir())
    except OSError as exc:
        raise RepositoryServiceError("Repository staging area is unavailable") from exc
    for candidate in candidates:
        if not candidate.name.startswith(prefix):
            continue
        try:
            _enforce_private_tree(candidate)
            shutil.rmtree(candidate)
        except (OSError, RepositoryStorageError) as exc:
            raise RepositoryServiceError("Repository staging cleanup failed") from exc


@contextmanager
def _repository_lock(root: Path, repository_id: uuid.UUID, *, exclusive: bool) -> Iterator[None]:
    lock_directory = root / ".locks"
    _ensure_private_directory(lock_directory)
    lock_path = lock_directory / f"{repository_id}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, FILE_MODE)
    except OSError as exc:
        raise RepositoryServiceError("Repository lock is unavailable") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or (details.st_uid, details.st_gid) != (
            os.geteuid(),
            os.getegid(),
        ):
            raise RepositoryServiceError("Repository lock is invalid")
        os.fchmod(descriptor, FILE_MODE)
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise RepositoryConflictError("Repository is busy") from exc
                time.sleep(LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


class _GitRepository:
    def __init__(self, repository_id: uuid.UUID, path: Path, object_format: str) -> None:
        self.repository_id = repository_id
        self.path = path
        self.object_format = object_format

    def _environment(self, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        environment = {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_DIR": str(self.path),
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "XDG_CONFIG_HOME": "/nonexistent",
        }
        if overrides:
            environment.update(overrides)
        return environment

    def _run(
        self,
        operation: str,
        arguments: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
        allowed_returncodes: frozenset[int] = frozenset({0}),
        output_limit: int = MAX_GIT_OUTPUT_BYTES,
    ) -> tuple[int, bytes]:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(  # noqa: S603  # nosec B603
                    [GIT_EXECUTABLE, *arguments],
                    stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    cwd=self.path.parent,
                    env=self._environment(environment),
                    start_new_session=True,
                )
                try:
                    process.communicate(input=input_bytes, timeout=GIT_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    logger.warning(
                        "repository_git_failed repository=%s operation=%s code=timeout",
                        self.repository_id,
                        operation,
                    )
                    raise RepositoryCommandError("Managed repository command timed out") from exc
            except OSError as exc:
                raise RepositoryCommandError("Managed repository command is unavailable") from exc
            if stdout_file.tell() > output_limit or stderr_file.tell() > MAX_GIT_ERROR_BYTES:
                logger.warning(
                    "repository_git_failed repository=%s operation=%s code=output_limit",
                    self.repository_id,
                    operation,
                )
                raise RepositoryResourceLimitError("Managed repository command exceeded its output limit")
            if process.returncode not in allowed_returncodes:
                logger.warning(
                    "repository_git_failed repository=%s operation=%s code=command_failed",
                    self.repository_id,
                    operation,
                )
                raise RepositoryCommandError("Managed repository command failed")
            stdout_file.seek(0)
            return process.returncode, stdout_file.read()

    def _parse_object(self, output: bytes) -> str:
        try:
            value = output.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise RepositoryCommandError("Managed repository returned an invalid object identity") from exc
        try:
            return _validate_object_id(value, self.object_format)
        except RepositoryInputError as exc:
            raise RepositoryCommandError("Managed repository returned an invalid object identity") from exc

    def current_ref(self) -> str | None:
        returncode, output = self._run(
            "read_head",
            ("rev-parse", "--verify", "--quiet", f"{CANONICAL_REF}^{{commit}}"),
            allowed_returncodes=frozenset({0, 1}),
            output_limit=128,
        )
        return None if returncode == 1 else self._parse_object(output)

    def raw_current_ref(self) -> str | None:
        returncode, output = self._run(
            "read_raw_head",
            ("rev-parse", "--verify", "--quiet", CANONICAL_REF),
            allowed_returncodes=frozenset({0, 1}),
            output_limit=128,
        )
        return None if returncode == 1 else self._parse_object(output)

    def commit_present(self, object_id: str) -> bool:
        _, output = self._run(
            "inspect_commit",
            ("cat-file", "--batch-check=%(objectname) %(objecttype)"),
            input_bytes=f"{object_id}\n".encode("ascii"),
            output_limit=160,
        )
        try:
            value = output.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise RepositoryCommandError("Managed repository returned invalid object metadata") from exc
        if value == f"{object_id} missing":
            return False
        if value == f"{object_id} commit":
            return True
        raise RepositoryCommandError("Managed repository returned invalid object metadata")

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        returncode, _ = self._run(
            "compare_commits",
            ("merge-base", "--is-ancestor", ancestor, descendant),
            allowed_returncodes=frozenset({0, 1}),
            output_limit=0,
        )
        return returncode == 0

    def first_parent_history(self, object_id: str, *, limit: int) -> tuple[str, ...]:
        _, output = self._run(
            "read_accepted_history",
            ("rev-list", "--first-parent", f"--max-count={limit}", object_id),
            output_limit=limit * (64 + 1),
        )
        try:
            identities = tuple(line for line in output.decode("ascii").splitlines() if line)
        except UnicodeDecodeError as exc:
            raise RepositoryCommandError("Managed repository returned invalid commit history") from exc
        if not identities or identities[0] != object_id or len(identities) > limit:
            raise RepositoryCommandError("Managed repository returned invalid commit history")
        try:
            return tuple(_validate_object_id(identity, self.object_format) for identity in identities)
        except RepositoryInputError as exc:
            raise RepositoryCommandError("Managed repository returned invalid commit history") from exc

    def verify_commit(self, object_id: str) -> None:
        self._run("verify_commit", ("cat-file", "-e", f"{object_id}^{{commit}}"), output_limit=0)

    def recover_ref(self, accepted: str | None, current: str | None) -> None:
        if accepted == current:
            return
        if accepted is None:
            if current is not None:
                self._run("recover_head", ("update-ref", "-d", CANONICAL_REF, current), output_limit=0)
        else:
            self.verify_commit(accepted)
            self._run(
                "recover_head",
                ("update-ref", CANONICAL_REF, accepted, current or _zero_object_id(self.object_format)),
                output_limit=0,
            )
        logger.warning("repository_ref_recovered repository=%s", self.repository_id)

    def read_file(self, commit_id: str, path: str) -> bytes:
        self.verify_commit(commit_id)
        _, listing = self._run(
            "locate_file",
            ("ls-tree", "-z", commit_id, "--", path),
            output_limit=MAX_PATH_BYTES + 128,
        )
        expected_suffix = b"\t" + path.encode("utf-8") + b"\0"
        if not listing.endswith(expected_suffix) or listing.count(b"\0") != 1:
            raise RepositoryFileNotFoundError("Repository file does not exist")
        metadata = listing[: -len(expected_suffix)]
        fields = metadata.split(b" ")
        if len(fields) != 3 or fields[0] != REGULAR_FILE_MODE.encode() or fields[1] != b"blob":
            raise RepositoryInputError("Repository file type is not supported")
        try:
            blob_id = self._parse_object(fields[2])
        except RepositoryCommandError as exc:
            raise RepositoryInputError("Repository file is invalid") from exc
        _, size_output = self._run("read_file_size", ("cat-file", "-s", blob_id), output_limit=32)
        try:
            size = int(size_output.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCommandError("Managed repository returned an invalid file size") from exc
        if size < 0 or size > MAX_FILE_BYTES:
            raise RepositoryResourceLimitError("Repository file exceeds its size limit")
        _, content = self._run("read_file", ("cat-file", "blob", blob_id), output_limit=MAX_FILE_BYTES)
        if len(content) != size:
            raise RepositoryCommandError("Managed repository returned an incomplete file")
        return content

    def markdown_paths(self, commit_id: str) -> tuple[str, ...]:
        self.verify_commit(commit_id)
        _, listing = self._run(
            "list_markdown_files",
            ("ls-tree", "-r", "-z", "--full-tree", commit_id),
            output_limit=MAX_GIT_OUTPUT_BYTES,
        )
        paths: list[str] = []
        for record in listing.split(b"\0"):
            if not record:
                continue
            try:
                metadata, encoded_path = record.split(b"\t", 1)
                mode, object_type, _object_id = metadata.split(b" ", 2)
                path = encoded_path.decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise RepositoryCommandError("Managed repository returned an invalid tree") from exc
            if mode != REGULAR_FILE_MODE.encode() or object_type != b"blob":
                raise RepositoryInputError("Repository file type is not supported")
            _validate_path(path)
            if path.casefold().endswith(".md"):
                paths.append(path)
                if len(paths) > MAX_INDEX_PATHS:
                    raise RepositoryResourceLimitError("Repository exceeds its Markdown file limit")
        return tuple(sorted(paths))

    def write_commit(
        self,
        *,
        base: str | None,
        changes: Mapping[str, bytes | None],
        message: str,
        stage_directory: Path,
    ) -> tuple[str, bool]:
        index_path = stage_directory / "index"
        index_environment = {"GIT_INDEX_FILE": str(index_path)}
        if base is None:
            self._run("prepare_index", ("read-tree", "--empty"), environment=index_environment, output_limit=0)
            base_tree = None
        else:
            self.verify_commit(base)
            self._run("prepare_index", ("read-tree", base), environment=index_environment, output_limit=0)
            _, base_tree_output = self._run(
                "read_base_tree", ("rev-parse", f"{base}^{{tree}}"), output_limit=128
            )
            base_tree = self._parse_object(base_tree_output)

        index_records = bytearray()
        for path, content in sorted(changes.items()):
            encoded_path = path.encode("utf-8")
            if content is None:
                index_records.extend(f"0 {_zero_object_id(self.object_format)}\t".encode("ascii"))
                index_records.extend(encoded_path + b"\0")
                continue
            _, blob_output = self._run(
                "write_blob",
                ("hash-object", "-w", "--stdin"),
                input_bytes=content,
                output_limit=128,
            )
            blob_id = self._parse_object(blob_output)
            index_records.extend(f"{REGULAR_FILE_MODE} {blob_id}\t".encode("ascii"))
            index_records.extend(encoded_path + b"\0")
        self._run(
            "stage_changes",
            ("update-index", "-z", "--index-info"),
            input_bytes=bytes(index_records),
            environment=index_environment,
            output_limit=0,
        )
        _, tree_output = self._run(
            "write_tree", ("write-tree",), environment=index_environment, output_limit=128
        )
        tree_id = self._parse_object(tree_output)
        if tree_id == base_tree and base is not None:
            return base, False
        if base is None and not changes:
            raise RepositoryInputError("Initial repository commit cannot be empty")

        commit_arguments = ["commit-tree", tree_id]
        if base is not None:
            commit_arguments.extend(("-p", base))
        identity_environment = {
            "GIT_AUTHOR_EMAIL": SERVICE_EMAIL,
            "GIT_AUTHOR_NAME": SERVICE_NAME,
            "GIT_COMMITTER_EMAIL": SERVICE_EMAIL,
            "GIT_COMMITTER_NAME": SERVICE_NAME,
        }
        _, commit_output = self._run(
            "write_commit",
            tuple(commit_arguments),
            input_bytes=f"{message}\n".encode(),
            environment=identity_environment,
            output_limit=128,
        )
        commit_id = self._parse_object(commit_output)
        self.verify_commit(commit_id)
        self._run(
            "advance_head",
            ("update-ref", CANONICAL_REF, commit_id, base or _zero_object_id(self.object_format)),
            output_limit=0,
        )
        return commit_id, True

    def rollback_ref(self, *, current: str, previous: str | None) -> None:
        if previous is None:
            self._run("rollback_head", ("update-ref", "-d", CANONICAL_REF, current), output_limit=0)
        else:
            self._run("rollback_head", ("update-ref", CANONICAL_REF, previous, current), output_limit=0)


def _repository_object_format(path: Path) -> str:
    config_path = path / "config"
    try:
        config_size = config_path.stat().st_size
    except OSError as exc:
        raise RepositoryServiceError("Repository configuration is invalid") from exc
    if config_size > MAX_CONFIG_BYTES:
        raise RepositoryResourceLimitError("Repository configuration exceeds its size limit")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise RepositoryServiceError("Repository configuration is invalid") from exc
    allowed: dict[str, frozenset[str]] = {
        "core": frozenset({"repositoryformatversion", "filemode", "bare"}),
        "extensions": frozenset({"objectformat"}),
    }
    for section in parser.sections():
        normalized = section.casefold()
        if normalized not in allowed or not set(parser.options(section)) <= allowed[normalized]:
            raise RepositoryServiceError("Repository configuration is not allowed")
    if not parser.has_section("core") or parser.get("core", "bare", fallback="").casefold() != "true":
        raise RepositoryServiceError("Repository configuration is not bare")
    object_format = parser.get("extensions", "objectformat", fallback="sha1").casefold()
    if object_format not in {RepositoryObjectFormat.SHA1, RepositoryObjectFormat.SHA256}:
        raise RepositoryServiceError("Repository object format is not supported")
    expected_version = "0" if object_format == RepositoryObjectFormat.SHA1 else "1"
    if parser.get("core", "repositoryformatversion", fallback="") != expected_version:
        raise RepositoryServiceError("Repository format version is not supported")
    for forbidden in (path / "objects" / "info" / "alternates", path / "objects" / "info" / "http-alternates"):
        if forbidden.exists() or forbidden.is_symlink():
            raise RepositoryServiceError("Repository alternate object storage is not allowed")
    try:
        head = (path / "HEAD").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RepositoryServiceError("Repository default branch is invalid") from exc
    if head != f"ref: {CANONICAL_REF}\n":
        raise RepositoryServiceError("Repository default branch is invalid")
    return object_format


def _load_repository(repository_id: uuid.UUID) -> tuple[WorkspaceRepository, Path, Path, str]:
    try:
        repository = WorkspaceRepository.objects.select_related("workspace", "accepted_commit").get(
            pk=repository_id
        )
        root, path = resolve_managed_repository_path(repository)
    except (WorkspaceRepository.DoesNotExist, RepositoryStorageError) as exc:
        raise RepositoryServiceError("Managed repository is unavailable") from exc
    object_format = _repository_object_format(path)
    return repository, root, path, object_format


def _validate_changes(changes: Mapping[str, bytes | None]) -> dict[str, bytes | None]:
    if not isinstance(changes, Mapping) or len(changes) > MAX_COMMIT_PATHS:
        raise RepositoryResourceLimitError("Repository change set exceeds its path limit")
    validated: dict[str, bytes | None] = {}
    total = 0
    for raw_path, content in changes.items():
        path = _validate_path(raw_path)
        if content is not None and not isinstance(content, bytes):
            raise RepositoryInputError("Repository file content must be bytes")
        if content is not None:
            if len(content) > MAX_FILE_BYTES:
                raise RepositoryResourceLimitError("Repository file exceeds its size limit")
            total += len(content)
        validated[path] = content
    if total > MAX_COMMIT_BYTES:
        raise RepositoryResourceLimitError("Repository change set exceeds its size limit")
    return validated


def _accept_commit(
    *,
    repository: WorkspaceRepository,
    object_format: str,
    commit_id: str,
) -> RepositoryCommit:
    commit, _ = RepositoryCommit.objects.get_or_create(
        tenant=repository.tenant,
        repository=repository,
        object_format=object_format,
        object_id=commit_id,
    )
    repository.accepted_commit = commit
    repository.save(update_fields=("accepted_commit", "updated_at"))
    return commit


def _health_for_reconciliation(state: str) -> str:
    if state == RepositoryReconciliationState.MATCHED:
        return RepositoryHealthState.HEALTHY
    if state in {RepositoryReconciliationState.MISSING, RepositoryReconciliationState.ADVANCED}:
        return RepositoryHealthState.DEGRADED
    if state == RepositoryReconciliationState.NEVER:
        return RepositoryHealthState.UNKNOWN
    return RepositoryHealthState.BLOCKED


def _record_reconciliation(repository: WorkspaceRepository, state: str) -> None:
    repository.health_state = _health_for_reconciliation(state)
    repository.last_reconciliation_state = state
    repository.last_reconciled_at = timezone.now()
    repository.save(
        update_fields=("health_state", "last_reconciliation_state", "last_reconciled_at", "updated_at")
    )


def _classify_reconciliation(git: _GitRepository, accepted: str | None) -> tuple[str, bool]:
    try:
        current = git.raw_current_ref()
        if accepted is None:
            if current is None:
                return RepositoryReconciliationState.MATCHED, True
            if not git.commit_present(current):
                return RepositoryReconciliationState.CORRUPT, False
            return RepositoryReconciliationState.ADVANCED, False
        if not git.commit_present(accepted):
            return RepositoryReconciliationState.MISSING, False
        if current is None:
            return RepositoryReconciliationState.MISSING, True
        if current == accepted:
            return RepositoryReconciliationState.MATCHED, True
        if not git.commit_present(current):
            return RepositoryReconciliationState.CORRUPT, True
        if git.is_ancestor(accepted, current):
            return RepositoryReconciliationState.ADVANCED, True
        return RepositoryReconciliationState.MISMATCHED, True
    except RepositoryCommandError:
        return RepositoryReconciliationState.CORRUPT, accepted is not None


def _accepted_object(repository: WorkspaceRepository, object_format: str) -> str | None:
    if repository.accepted_commit_id is None:
        return None
    commit = RepositoryCommit.objects.get(pk=repository.accepted_commit_id)
    if commit.repository_id != repository.id or commit.object_format != object_format:
        raise RepositoryServiceError("Accepted repository object is invalid")
    return commit.object_id


def _record_commit_attribution(
    *,
    repository: WorkspaceRepository,
    commit: RepositoryCommit,
    attribution: RepositoryAuditAttribution,
) -> None:
    from apps.accounts.models import TenantMembership

    is_owner = InstallationState.objects.filter(
        pk=InstallationState.SINGLETON_ID,
        tenant_id=repository.tenant_id,
        owner_id=attribution.actor_id,
    ).exists()
    is_member = TenantMembership.objects.filter(
        tenant_id=repository.tenant_id,
        user_id=attribution.actor_id,
    ).exists()
    if not (is_owner or is_member):
        raise RepositoryInputError("Repository audit actor is not authorized for this tenant")
    event = AuditEvent.objects.create(
        tenant_id=repository.tenant_id,
        actor_id=attribution.actor_id,
        action=attribution.action,
        entity_id=repository.workspace_id,
        request_id=attribution.request_id,
        metadata={},
    )
    RepositoryCommitAudit.objects.create(
        tenant_id=repository.tenant_id,
        repository=repository,
        commit=commit,
        audit_event=event,
    )


def commit_repository_files(
    *,
    repository_id: uuid.UUID,
    expected_base: str | None,
    changes: Mapping[str, bytes | None],
    message: str,
    attribution: RepositoryAuditAttribution | None = None,
) -> RepositoryCommitResult:
    validated_changes = _validate_changes(changes)
    validated_message = _validate_message(message)
    validated_attribution = _validate_attribution(attribution)
    repository, root, path, object_format = _load_repository(repository_id)
    if expected_base is not None:
        _validate_object_id(expected_base, object_format)

    with _repository_lock(root, repository.id, exclusive=True):
        _cleanup_staging_directories(root, repository.id)
        reconciliation_error = False
        with transaction.atomic():
            locked = WorkspaceRepository.objects.select_for_update().get(pk=repository.id)
            if locked.lifecycle_state != RepositoryLifecycleState.ACTIVE:
                raise RepositoryServiceError("Managed repository does not accept writes")
            accepted = _accepted_object(locked, object_format)
            git = _GitRepository(locked.id, path, object_format)
            reconciliation, _ = _classify_reconciliation(git, accepted)
            _record_reconciliation(locked, reconciliation)
            if reconciliation != RepositoryReconciliationState.MATCHED:
                reconciliation_error = True
            elif expected_base != accepted:
                raise RepositoryConflictError("Repository base changed")
            elif accepted is None and not any(content is not None for content in validated_changes.values()):
                raise RepositoryInputError("Initial repository commit cannot be empty")
            if not reconciliation_error:
                stage_directory = Path(tempfile.mkdtemp(prefix=f".{locked.id}.stage-", dir=root))
                stage_directory.chmod(DIRECTORY_MODE)
                advanced = False
                commit_id = accepted
                try:
                    commit_id, created = git.write_commit(
                        base=accepted,
                        changes=validated_changes,
                        message=validated_message,
                        stage_directory=stage_directory,
                    )
                    advanced = created
                    if created:
                        commit = _accept_commit(
                            repository=locked,
                            object_format=object_format,
                            commit_id=commit_id,
                        )
                        if validated_attribution is not None:
                            _record_commit_attribution(
                                repository=locked,
                                commit=commit,
                                attribution=validated_attribution,
                            )
                    _record_reconciliation(locked, RepositoryReconciliationState.MATCHED)
                except BaseException:
                    if advanced and commit_id is not None:
                        try:
                            git.rollback_ref(current=commit_id, previous=accepted)
                        except RepositoryServiceError:
                            logger.critical("repository_ref_rollback_failed repository=%s", locked.id)
                    raise
                finally:
                    try:
                        _cleanup_staging_directories(root, locked.id)
                    except RepositoryServiceError as exc:
                        logger.error("repository_stage_cleanup_failed repository=%s", locked.id)
                        raise RepositoryServiceError("Repository staging cleanup failed") from exc

        if reconciliation_error:
            raise RepositoryReconciliationError("Managed repository requires reconciliation")

    if commit_id is None:  # pragma: no cover - an initial empty commit is rejected above
        raise RepositoryServiceError("Managed repository did not produce a commit")
    logger.info(
        "repository_commit_completed repository=%s outcome=%s",
        repository.id,
        "created" if created else "unchanged",
    )
    return RepositoryCommitResult(repository.id, commit_id, object_format, created)


def read_accepted_repository_file(*, repository_id: uuid.UUID, path: str) -> bytes:
    validated_path = _validate_path(path)
    repository, root, repository_path, object_format = _load_repository(repository_id)
    with _repository_lock(root, repository.id, exclusive=False):
        repository.refresh_from_db(fields=("accepted_commit",))
        if repository.accepted_commit_id is None:
            raise RepositoryInputError("Repository has no accepted content")
        accepted = _accepted_object(repository, object_format)
        if accepted is None:  # pragma: no cover - guarded above
            raise RepositoryInputError("Repository has no accepted content")
        git = _GitRepository(repository.id, repository_path, object_format)
        reconciliation, accepted_usable = _classify_reconciliation(git, accepted)
        _record_reconciliation(repository, reconciliation)
        if not accepted_usable:
            raise RepositoryReconciliationError("Accepted repository content is unavailable")
        return git.read_file(accepted, validated_path)


def read_accepted_repository_markdown_files(
    *,
    repository_id: uuid.UUID,
    max_files: int | None = None,
    max_bytes: int | None = None,
    record_reconciliation: bool = True,
) -> tuple[RepositoryCommit, tuple[tuple[str, bytes], ...]]:
    """Read a bounded, stable Markdown snapshot from exactly one accepted commit."""

    repository, root, repository_path, object_format = _load_repository(repository_id)
    with _repository_lock(root, repository.id, exclusive=False):
        repository.refresh_from_db(fields=("accepted_commit",))
        if repository.accepted_commit_id is None:
            raise RepositoryInputError("Repository has no accepted content")
        commit = RepositoryCommit.objects.get(pk=repository.accepted_commit_id)
        accepted = _accepted_object(repository, object_format)
        if accepted is None:  # pragma: no cover - guarded above
            raise RepositoryInputError("Repository has no accepted content")
        git = _GitRepository(repository.id, repository_path, object_format)
        reconciliation, accepted_usable = _classify_reconciliation(git, accepted)
        if record_reconciliation:
            _record_reconciliation(repository, reconciliation)
        if not accepted_usable:
            raise RepositoryReconciliationError("Accepted repository content is unavailable")
        paths = git.markdown_paths(accepted)
        if max_files is not None and len(paths) > max_files:
            raise RepositoryResourceLimitError("Accepted repository exceeds the file limit")
        files: list[tuple[str, bytes]] = []
        total_bytes = 0
        for path in paths:
            source = git.read_file(accepted, path)
            total_bytes += len(source)
            if max_bytes is not None and total_bytes > max_bytes:
                raise RepositoryResourceLimitError("Accepted repository exceeds the byte limit")
            files.append((path, source))
        return commit, tuple(files)


def list_accepted_repository_history(*, repository_id: uuid.UUID, limit: int = 32) -> tuple[str, ...]:
    """Return a bounded first-parent chain from the exact accepted Git head."""

    if limit < 1 or limit > 32:
        raise RepositoryInputError("History limit is outside the migration safety bound")
    repository, root, repository_path, object_format = _load_repository(repository_id)
    with _repository_lock(root, repository.id, exclusive=False):
        repository.refresh_from_db(fields=("accepted_commit",))
        accepted = _accepted_object(repository, object_format)
        if accepted is None:
            raise RepositoryInputError("Repository has no accepted content")
        git = _GitRepository(repository.id, repository_path, object_format)
        reconciliation, accepted_usable = _classify_reconciliation(git, accepted)
        _record_reconciliation(repository, reconciliation)
        if not accepted_usable:
            raise RepositoryReconciliationError("Accepted repository content is unavailable")
        return git.first_parent_history(accepted, limit=limit)


def read_repository_markdown_files_at_commit(
    *, repository_id: uuid.UUID, object_id: str, record_reconciliation: bool = True
) -> tuple[RepositoryCommit, tuple[tuple[str, bytes], ...]]:
    """Read one retained commit from the selected repository without widening its scope."""

    repository, root, repository_path, object_format = _load_repository(repository_id)
    validated_object_id = _validate_object_id(object_id, object_format)
    with _repository_lock(root, repository.id, exclusive=False):
        repository.refresh_from_db(fields=("accepted_commit",))
        accepted = _accepted_object(repository, object_format)
        if accepted is None:
            raise RepositoryInputError("Repository has no accepted content")
        git = _GitRepository(repository.id, repository_path, object_format)
        reconciliation, accepted_usable = _classify_reconciliation(git, accepted)
        if record_reconciliation:
            _record_reconciliation(repository, reconciliation)
        if not accepted_usable:
            raise RepositoryReconciliationError("Accepted repository content is unavailable")
        try:
            commit = RepositoryCommit.objects.get(repository=repository, object_id=validated_object_id)
        except RepositoryCommit.DoesNotExist as exc:
            raise RepositoryFileNotFoundError("Repository commit is unavailable") from exc
        git.verify_commit(validated_object_id)
        files: list[tuple[str, bytes]] = []
        total_bytes = 0
        for path in git.markdown_paths(validated_object_id):
            content = git.read_file(validated_object_id, path)
            total_bytes += len(content)
            if total_bytes > MAX_PINNED_SNAPSHOT_BYTES:
                raise RepositoryResourceLimitError("Pinned repository snapshot exceeds its size limit")
            files.append((path, content))
        return commit, tuple(files)


@contextmanager
def pin_accepted_repository_for_publication(repository_id: uuid.UUID) -> Iterator[WorkspaceRepository]:
    """Hold the Git and database head stable through one publication insert.

    A publisher must do its append-only insert inside this context. The lock
    order matches repository writes (filesystem first, database second), so a
    writer cannot advance the accepted ref between proof and retention.
    """

    repository, root, path, object_format = _load_repository(repository_id)
    with _repository_lock(root, repository.id, exclusive=False):
        with transaction.atomic():
            locked = WorkspaceRepository.objects.select_for_update().get(pk=repository.id)
            if locked.lifecycle_state != RepositoryLifecycleState.ACTIVE:
                raise RepositoryServiceError("Managed repository does not accept publication")
            accepted = _accepted_object(locked, object_format)
            if accepted is None or locked.indexed_commit_id != locked.accepted_commit_id:
                raise RepositoryServiceError("Repository accepted content is not indexed")
            git = _GitRepository(locked.id, path, object_format)
            reconciliation, _ = _classify_reconciliation(git, accepted)
            if reconciliation != RepositoryReconciliationState.MATCHED:
                raise RepositoryReconciliationError("Managed repository requires reconciliation")
            pinned_commit_id = locked.accepted_commit_id
            yield locked
            locked.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
            if locked.accepted_commit_id != pinned_commit_id or locked.indexed_commit_id != pinned_commit_id:
                raise RepositoryConflictError("Repository accepted head changed during publication")
            reconciliation, _ = _classify_reconciliation(git, accepted)
            if reconciliation != RepositoryReconciliationState.MATCHED:
                raise RepositoryReconciliationError("Managed repository changed during publication")


def reconcile_workspace_repository(
    *, repository_id: uuid.UUID, repair_to_accepted: bool = False
) -> RepositoryReconciliationResult:
    try:
        repository, root, path, object_format = _load_repository(repository_id)
    except RepositoryServiceError:
        WorkspaceRepository.objects.filter(pk=repository_id).update(
            health_state=RepositoryHealthState.BLOCKED,
            last_reconciliation_state=RepositoryReconciliationState.UNAVAILABLE,
            last_reconciled_at=timezone.now(),
        )
        logger.warning("repository_reconciliation repository=%s state=unavailable", repository_id)
        return RepositoryReconciliationResult(
            repository_id,
            RepositoryReconciliationState.UNAVAILABLE,
            RepositoryHealthState.BLOCKED,
            False,
        )

    repaired = False
    with _repository_lock(root, repository.id, exclusive=repair_to_accepted):
        with transaction.atomic():
            locked = WorkspaceRepository.objects.select_for_update().get(pk=repository.id)
            accepted = _accepted_object(locked, object_format)
            git = _GitRepository(locked.id, path, object_format)
            state, accepted_usable = _classify_reconciliation(git, accepted)
            if repair_to_accepted and state != RepositoryReconciliationState.MATCHED:
                can_repair = accepted is None or accepted_usable
                if can_repair:
                    current = git.raw_current_ref()
                    git.recover_ref(accepted, current)
                    state, _ = _classify_reconciliation(git, accepted)
                    repaired = state == RepositoryReconciliationState.MATCHED
            _record_reconciliation(locked, state)
            health = locked.health_state
    logger.info(
        "repository_reconciliation repository=%s state=%s repaired=%s",
        repository.id,
        state,
        repaired,
    )
    return RepositoryReconciliationResult(repository.id, state, health, repaired)


def reconcile_all_workspace_repositories(
    *, repair_to_accepted: bool = False
) -> tuple[RepositoryReconciliationResult, ...]:
    return tuple(
        reconcile_workspace_repository(repository_id=repository_id, repair_to_accepted=repair_to_accepted)
        for repository_id in WorkspaceRepository.objects.order_by("id").values_list("id", flat=True)
    )


def repository_health_diagnostics() -> dict[str, object]:
    from django.conf import settings
    from django.db.models import Count, Max

    if not settings.TEKDOCS_REPOSITORY_ROOT:
        return {
            "status": "not_configured",
            "total": 0,
            "healthy": 0,
            "degraded": 0,
            "blocked": 0,
            "unknown": 0,
            "states": {state: 0 for state in RepositoryReconciliationState.values},
            "last_checked_at": None,
            "repair": None,
        }
    health_counts = {
        row["health_state"]: row["count"]
        for row in WorkspaceRepository.objects.values("health_state").annotate(count=Count("id"))
    }
    state_counts = {
        row["last_reconciliation_state"]: row["count"]
        for row in WorkspaceRepository.objects.values("last_reconciliation_state").annotate(count=Count("id"))
    }
    total = sum(health_counts.values())
    blocked = health_counts.get(RepositoryHealthState.BLOCKED, 0)
    degraded = health_counts.get(RepositoryHealthState.DEGRADED, 0)
    unknown = health_counts.get(RepositoryHealthState.UNKNOWN, 0)
    status = "unavailable" if blocked else "degraded" if degraded or unknown else "ready"
    return {
        "status": status,
        "total": total,
        "healthy": health_counts.get(RepositoryHealthState.HEALTHY, 0),
        "degraded": degraded,
        "blocked": blocked,
        "unknown": unknown,
        "states": {state: state_counts.get(state, 0) for state in RepositoryReconciliationState.values},
        "last_checked_at": WorkspaceRepository.objects.aggregate(value=Max("last_reconciled_at"))["value"],
        "repair": "reconcile_to_accepted" if status != "ready" else None,
    }
