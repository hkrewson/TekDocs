from __future__ import annotations

import errno
import os
import shutil
import stat
import subprocess  # nosec B404
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from .models import (
    Workspace,
    WorkspaceRepository,
    repository_identity_uuid,
    repository_storage_relative_path,
)

# Git is the local managed object-store implementation and is invoked without a shell.
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
GIT_INIT_TIMEOUT_SECONDS = 10
GIT_EXECUTABLE = "/usr/bin/git"


class RepositoryStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryInitialization:
    repository: WorkspaceRepository
    binding_created: bool
    storage_created: bool


def configured_repository_root() -> Path | None:
    configured = str(settings.TEKDOCS_REPOSITORY_ROOT).strip()
    if not configured:
        return None
    root = Path(configured)
    if not root.is_absolute() or os.path.normpath(configured) != configured or ".." in root.parts:
        raise ImproperlyConfigured("TEKDOCS_REPOSITORY_ROOT must be an absolute normalized path")
    return root


def _runtime_identity() -> tuple[int, int]:
    return os.geteuid(), os.getegid()


def _require_owned_path(path: Path, *, directory: bool) -> os.stat_result:
    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise RepositoryStorageError("Managed repository storage is incomplete") from exc
    if stat.S_ISLNK(details.st_mode):
        raise RepositoryStorageError("Managed repository storage cannot contain symbolic links")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(details.st_mode):
        raise RepositoryStorageError("Managed repository storage has an invalid entry type")
    if (details.st_uid, details.st_gid) != _runtime_identity():
        raise RepositoryStorageError("Managed repository storage has unexpected ownership")
    return details


def ensure_repository_root(root: Path) -> None:
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if stat.S_ISLNK(current.lstat().st_mode):
                raise RepositoryStorageError("Managed repository storage cannot contain symbolic links")
    if root.exists() or root.is_symlink():
        _require_owned_path(root, directory=True)
    else:
        try:
            root.mkdir(mode=DIRECTORY_MODE)
        except (FileExistsError, OSError) as exc:
            raise RepositoryStorageError("Managed repository root could not be created safely") from exc
        _require_owned_path(root, directory=True)
    root.chmod(DIRECTORY_MODE)


def repository_path(
    *,
    root: Path,
    repository_id: uuid.UUID,
    storage_relative_path: str,
) -> Path:
    expected = repository_storage_relative_path(repository_id=repository_id)
    if storage_relative_path != expected:
        raise RepositoryStorageError("Repository path does not match its stable identity")
    relative_parts = Path(storage_relative_path).parts
    if len(relative_parts) != 2 or relative_parts[0] != "repositories":
        raise RepositoryStorageError("Repository path escapes managed storage")
    candidate = root / relative_parts[1]
    if candidate.parent != root:
        raise RepositoryStorageError("Repository path escapes managed storage")
    return candidate


def _enforce_private_tree(repository_path_value: Path) -> None:
    _require_owned_path(repository_path_value, directory=True)
    for current_root, directory_names, file_names in os.walk(repository_path_value, followlinks=False):
        current = Path(current_root)
        _require_owned_path(current, directory=True)
        current.chmod(DIRECTORY_MODE)
        for name in directory_names:
            child = current / name
            _require_owned_path(child, directory=True)
            child.chmod(DIRECTORY_MODE)
        for name in file_names:
            child = current / name
            _require_owned_path(child, directory=False)
            child.chmod(FILE_MODE)


def _validate_bare_repository(repository_path_value: Path) -> None:
    _enforce_private_tree(repository_path_value)
    for relative, directory in (("HEAD", False), ("config", False), ("objects", True), ("refs", True)):
        _require_owned_path(repository_path_value / relative, directory=directory)


def _initialize_bare_repository(root: Path, destination: Path) -> bool:
    if destination.exists() or destination.is_symlink():
        _validate_bare_repository(destination)
        return False

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.stem}.init-", dir=root))
    try:
        environment = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(temporary),
            "PATH": os.environ.get("PATH", ""),
            "XDG_CONFIG_HOME": str(temporary),
        }
        # The executable and every option are fixed; only the custody-created
        # private temporary directory is supplied as data.
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [GIT_EXECUTABLE, "init", "--bare", "--initial-branch=main", "--template=", str(temporary)],
            check=False,
            capture_output=True,
            env=environment,
            timeout=GIT_INIT_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            raise RepositoryStorageError("Managed repository initialization failed")
        _validate_bare_repository(temporary)
        created = True
        try:
            temporary.rename(destination)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            _validate_bare_repository(destination)
            created = False
        _validate_bare_repository(destination)
        return created
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryStorageError("Managed repository initialization failed") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def resolve_managed_repository_path(repository: WorkspaceRepository) -> tuple[Path, Path]:
    root = configured_repository_root()
    if root is None:
        raise RepositoryStorageError("Managed repository storage is not configured")
    ensure_repository_root(root)
    if repository.workspace.tenant_id != repository.tenant_id:
        raise RepositoryStorageError("Repository binding does not match its Workspace tenant")
    destination = repository_path(
        root=root,
        repository_id=repository.id,
        storage_relative_path=repository.storage_relative_path,
    )
    _validate_bare_repository(destination)
    return root, destination


def ensure_workspace_repository(workspace: Workspace) -> RepositoryInitialization | None:
    root = configured_repository_root()
    if root is None:
        return None
    ensure_repository_root(root)

    repository_id = repository_identity_uuid(workspace_id=workspace.id)
    relative_path = repository_storage_relative_path(repository_id=repository_id)
    with transaction.atomic():
        repository, binding_created = WorkspaceRepository.objects.get_or_create(
            workspace=workspace,
            defaults={
                "id": repository_id,
                "tenant": workspace.tenant,
                "storage_relative_path": relative_path,
            },
        )
    if repository.tenant_id != workspace.tenant_id:
        raise RepositoryStorageError("Repository binding does not match its Workspace tenant")
    destination = repository_path(
        root=root,
        repository_id=repository.id,
        storage_relative_path=repository.storage_relative_path,
    )
    destination.parent.mkdir(mode=DIRECTORY_MODE, exist_ok=True)
    _require_owned_path(destination.parent, directory=True)
    destination.parent.chmod(DIRECTORY_MODE)
    storage_created = _initialize_bare_repository(root, destination)
    return RepositoryInitialization(repository, binding_created, storage_created)


def initialize_workspace_repository(workspace_id: uuid.UUID) -> None:
    workspace = Workspace.objects.select_related("tenant").get(pk=workspace_id)
    ensure_workspace_repository(workspace)


def schedule_workspace_repository_initialization(workspace_id: uuid.UUID) -> None:
    if configured_repository_root() is None:
        return
    transaction.on_commit(lambda: initialize_workspace_repository(workspace_id))
