from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404
import tarfile
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from .models import RepositoryCommit, RepositoryObjectFormat, WorkspaceRepository
from .repository_service import CANONICAL_REF, _repository_lock
from .repository_storage import GIT_EXECUTABLE, resolve_managed_repository_path

FORMAT = "tekdocs-repositories-v1"
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_REPOSITORIES = 100_000
GIT_TIMEOUT_SECONDS = 120
RECOVERY_REF_PREFIX = "refs/tekdocs/recovery/"


class RepositoryRecoveryError(RuntimeError):
    pass


def _git(*arguments: str, git_dir: Path | None = None, timeout: int = GIT_TIMEOUT_SECONDS) -> bytes:
    command = [GIT_EXECUTABLE]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
    command.extend(arguments)
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603
            command,
            check=True,
            capture_output=True,
            env=environment,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepositoryRecoveryError("A managed repository could not be archived or verified.") from exc
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _object_length(object_format: str) -> int:
    return 40 if object_format == RepositoryObjectFormat.SHA1 else 64


def _valid_object_id(value: object, object_format: str) -> bool:
    length = _object_length(object_format)
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validated_manifest(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise RepositoryRecoveryError("The repository recovery manifest is too large.")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryRecoveryError("The repository recovery manifest is invalid.") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise RepositoryRecoveryError("The repository recovery format is unsupported.")
    repositories = manifest.get("repositories")
    if not isinstance(repositories, list) or len(repositories) > MAX_REPOSITORIES:
        raise RepositoryRecoveryError("The repository recovery inventory is invalid.")
    seen_ids: set[str] = set()
    seen_bundles: set[str] = set()
    for entry in repositories:
        if not isinstance(entry, dict):
            raise RepositoryRecoveryError("The repository recovery inventory is invalid.")
        repository_id = entry.get("repository_id")
        workspace_id = entry.get("workspace_id")
        tenant_id = entry.get("tenant_id")
        bundle = entry.get("bundle")
        checksum = entry.get("sha256")
        object_format = entry.get("object_format")
        commits = entry.get("verified_commits")
        if object_format not in RepositoryObjectFormat.values:
            raise RepositoryRecoveryError("The repository recovery object format is invalid.")
        try:
            uuid.UUID(str(repository_id))
            uuid.UUID(str(workspace_id))
            uuid.UUID(str(tenant_id))
        except (TypeError, ValueError) as exc:
            raise RepositoryRecoveryError("The repository recovery identity is invalid.") from exc
        expected_bundle = f"repositories/{repository_id}.bundle"
        if (
            repository_id in seen_ids
            or bundle in seen_bundles
            or bundle != expected_bundle
            or not isinstance(checksum, str)
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            or not isinstance(commits, list)
            or not commits
            or len(commits) != len(set(commits))
            or any(not _valid_object_id(value, object_format) for value in commits)
            or not _valid_object_id(entry.get("accepted_commit"), object_format)
            or (
                entry.get("indexed_commit") is not None
                and not _valid_object_id(entry.get("indexed_commit"), object_format)
            )
            or entry.get("accepted_commit") not in commits
            or (entry.get("indexed_commit") is not None and entry.get("indexed_commit") not in commits)
        ):
            raise RepositoryRecoveryError("The repository recovery inventory is invalid.")
        seen_ids.add(str(repository_id))
        seen_bundles.add(str(bundle))
    return manifest


def _tar_info(path: Path, arcname: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(arcname)
    info.size = path.stat().st_size
    info.mode = 0o600
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _write_archive(staging: Path, destination: Path, bundle_names: list[str]) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with tarfile.open(temporary, "w", format=tarfile.PAX_FORMAT) as archive:
            for name in [MANIFEST_NAME, *bundle_names]:
                source = staging / name
                with source.open("rb") as stream:
                    archive.addfile(_tar_info(source, name), stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_repository_recovery_archive(destination: Path) -> dict[str, Any]:
    if destination.exists() or destination.is_symlink():
        raise RepositoryRecoveryError("Refusing to overwrite a repository recovery archive.")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    repositories = tuple(
        WorkspaceRepository.objects.select_related("workspace", "accepted_commit", "indexed_commit")
        .order_by("id")
    )
    with tempfile.TemporaryDirectory(prefix="tekdocs-repository-backup-") as temporary_name:
        staging = Path(temporary_name)
        (staging / "repositories").mkdir(mode=0o700)
        entries: list[dict[str, Any]] = []
        bundle_names: list[str] = []
        for repository in repositories:
            if repository.accepted_commit is None:
                raise RepositoryRecoveryError("Every managed repository must have an accepted commit before backup.")
            root, path = resolve_managed_repository_path(repository)
            object_format = repository.accepted_commit.object_format
            commits = tuple(
                RepositoryCommit.objects.filter(repository=repository, object_format=object_format)
                .order_by("object_id")
                .values_list("object_id", flat=True)
            )
            accepted = repository.accepted_commit.object_id
            bundle_name = f"repositories/{repository.id}.bundle"
            bundle_path = staging / bundle_name
            recovery_refs: list[str] = []
            with _repository_lock(root, repository.id, exclusive=True):
                try:
                    current = _git("rev-parse", "--verify", CANONICAL_REF, git_dir=path).decode().strip()
                    if current != accepted:
                        raise RepositoryRecoveryError(
                            "Every managed repository must match its accepted head before backup."
                        )
                    for object_id in commits:
                        _git("cat-file", "-e", f"{object_id}^{{commit}}", git_dir=path)
                        reference = f"{RECOVERY_REF_PREFIX}{object_id}"
                        _git("update-ref", reference, object_id, git_dir=path)
                        recovery_refs.append(reference)
                    _git("bundle", "create", str(bundle_path), "--all", git_dir=path)
                finally:
                    for reference in recovery_refs:
                        _git("update-ref", "-d", reference, git_dir=path)
            bundle_names.append(bundle_name)
            entries.append(
                {
                    "repository_id": str(repository.id),
                    "tenant_id": str(repository.tenant_id),
                    "workspace_id": str(repository.workspace_id),
                    "object_format": object_format,
                    "accepted_commit": accepted,
                    "indexed_commit": (
                        repository.indexed_commit.object_id if repository.indexed_commit is not None else None
                    ),
                    "verified_commits": list(commits),
                    "bundle": bundle_name,
                    "sha256": _sha256(bundle_path),
                }
            )
        manifest: dict[str, Any] = {"format": FORMAT, "repositories": entries}
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_archive(staging, destination, bundle_names)
    return manifest


@contextmanager
def _validated_archive(archive_path: Path) -> Iterator[tuple[dict[str, Any], Path]]:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise RepositoryRecoveryError("The repository recovery archive is unavailable.")
    with tempfile.TemporaryDirectory(prefix="tekdocs-repository-verify-") as temporary_name:
        staging = Path(temporary_name)
        try:
            with tarfile.open(archive_path, "r:") as archive:
                members = archive.getmembers()
                names = [member.name for member in members]
                if len(names) != len(set(names)) or MANIFEST_NAME not in names:
                    raise RepositoryRecoveryError("The repository recovery archive inventory is invalid.")
                for member in members:
                    path = PurePosixPath(member.name)
                    if (
                        not member.isfile()
                        or path.is_absolute()
                        or ".." in path.parts
                        or len(path.parts) > 2
                    ):
                        raise RepositoryRecoveryError("The repository recovery archive contains an unsafe member.")
                manifest_member = archive.getmember(MANIFEST_NAME)
                manifest_stream = archive.extractfile(manifest_member)
                if manifest_stream is None:
                    raise RepositoryRecoveryError("The repository recovery manifest is unavailable.")
                manifest = _validated_manifest(manifest_stream.read(MAX_MANIFEST_BYTES + 1))
                expected = {MANIFEST_NAME, *(entry["bundle"] for entry in manifest["repositories"])}
                if set(names) != expected:
                    raise RepositoryRecoveryError("The repository recovery archive inventory is incomplete.")
                for entry in manifest["repositories"]:
                    bundle_path = staging / entry["bundle"]
                    bundle_path.parent.mkdir(mode=0o700, exist_ok=True)
                    source = archive.extractfile(archive.getmember(entry["bundle"]))
                    if source is None:
                        raise RepositoryRecoveryError("A repository recovery bundle is unavailable.")
                    with bundle_path.open("wb") as destination:
                        shutil.copyfileobj(source, destination, length=1024 * 1024)
                    bundle_path.chmod(0o600)
                    if _sha256(bundle_path) != entry["sha256"]:
                        raise RepositoryRecoveryError("A repository recovery bundle checksum is invalid.")
        except (KeyError, OSError, tarfile.TarError) as exc:
            raise RepositoryRecoveryError("The repository recovery archive is invalid or truncated.") from exc
        for entry in manifest["repositories"]:
            bundle_path = staging / entry["bundle"]
            verification_repository = staging / f"verify-{entry['repository_id']}.git"
            init_arguments = ["init", "--bare"]
            if entry["object_format"] == RepositoryObjectFormat.SHA256:
                init_arguments.append("--object-format=sha256")
            init_arguments.append(str(verification_repository))
            _git(*init_arguments)
            _git("fetch", str(bundle_path), "+refs/*:refs/*", git_dir=verification_repository)
            for object_id in entry["verified_commits"]:
                _git("cat-file", "-e", f"{object_id}^{{commit}}", git_dir=verification_repository)
        yield manifest, staging


def validate_repository_recovery_archive(archive_path: Path) -> dict[str, Any]:
    with _validated_archive(archive_path) as (manifest, _):
        return manifest


def restore_repository_recovery_archive(archive_path: Path, destination_root: Path) -> dict[str, Any]:
    if destination_root.is_symlink():
        raise RepositoryRecoveryError("The repository recovery destination is unsafe.")
    destination_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(destination_root.iterdir()):
        raise RepositoryRecoveryError("The repository recovery destination must be empty.")
    with _validated_archive(archive_path) as (manifest, staging):
        created: list[Path] = []
        try:
            for entry in manifest["repositories"]:
                repository_path = destination_root / f"{entry['repository_id']}.git"
                init_arguments = ["init", "--bare"]
                if entry["object_format"] == RepositoryObjectFormat.SHA256:
                    init_arguments.append("--object-format=sha256")
                init_arguments.append(str(repository_path))
                _git(*init_arguments)
                created.append(repository_path)
                _git(
                    "fetch",
                    str(staging / entry["bundle"]),
                    "+refs/*:refs/*",
                    git_dir=repository_path,
                )
                _git("update-ref", CANONICAL_REF, entry["accepted_commit"], git_dir=repository_path)
                for object_id in entry["verified_commits"]:
                    _git("update-ref", "-d", f"{RECOVERY_REF_PREFIX}{object_id}", git_dir=repository_path)
                _git("symbolic-ref", "HEAD", CANONICAL_REF, git_dir=repository_path)
                for path in repository_path.rglob("*"):
                    if path.is_symlink():
                        raise RepositoryRecoveryError("The restored repository contains an unsafe link.")
                    path.chmod(0o700 if path.is_dir() else 0o600)
                repository_path.chmod(0o700)
        except Exception:
            for path in reversed(created):
                shutil.rmtree(path, ignore_errors=True)
            raise
    return manifest


def verify_repository_recovery_database(archive_path: Path) -> dict[str, Any]:
    manifest = validate_repository_recovery_archive(archive_path)
    expected = {entry["repository_id"]: entry for entry in manifest["repositories"]}
    repositories = tuple(
        WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").order_by("id")
    )
    if {str(repository.id) for repository in repositories} != set(expected):
        raise RepositoryRecoveryError("The restored database and repository inventory do not match.")
    for repository in repositories:
        entry = expected[str(repository.id)]
        if (
            str(repository.tenant_id) != entry["tenant_id"]
            or str(repository.workspace_id) != entry["workspace_id"]
            or repository.accepted_commit is None
            or repository.accepted_commit.object_id != entry["accepted_commit"]
            or (
                repository.indexed_commit.object_id if repository.indexed_commit is not None else None
            )
            != entry["indexed_commit"]
        ):
            raise RepositoryRecoveryError("The restored database and repository authority do not match.")
        commits = set(
            RepositoryCommit.objects.filter(repository=repository).values_list("object_id", flat=True)
        )
        if commits != set(entry["verified_commits"]):
            raise RepositoryRecoveryError("The restored verified repository objects do not match.")
    return manifest
