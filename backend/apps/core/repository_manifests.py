from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml
from django.db import transaction

from .models import Tenant, WorkspaceKind, WorkspaceRepository
from .repository_service import (
    RepositoryCommitResult,
    RepositoryConflictError,
    RepositoryFileNotFoundError,
    commit_repository_files,
    read_accepted_repository_file,
)
from .repository_storage import configured_repository_root
from .rls import OrganizationRLSMode, system_rls_scope_if_postgresql
from .scoping import DataScope

REPOSITORY_MANIFEST_PATH = ".tekdocs/repository.yml"
WORKSPACE_MANIFEST_PATH = ".tekdocs/workspace.yml"
ORGANIZATION_DIRECTORY_PATH = ".tekdocs/organizations.yml"
REPOSITORY_SCHEMA = "tekdocs.repository/v1"
WORKSPACE_SCHEMA = "tekdocs.workspace/v1"
ORGANIZATION_DIRECTORY_SCHEMA = "tekdocs.organization-directory/v1"
MANIFEST_COMMIT_MESSAGE = "Synchronize portable workspace manifests"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_DEPTH = 8
MAX_MANIFEST_NODES = 50_000
MAX_KEY_BYTES = 80
MAX_STRING_BYTES = 4096
MAX_SYNC_ATTEMPTS = 3
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,79}")
SENSITIVE_KEY_PARTS = (
    "asset",
    "audit",
    "authorization",
    "contract",
    "cookie",
    "credential",
    "integration",
    "password",
    "permission",
    "private_key",
    "secret",
    "serial",
    "session",
    "token",
    "user",
)


class RepositoryManifestError(RuntimeError):
    pass


class _StrictManifestLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):  # type: ignore[no-untyped-call]
            raise RepositoryManifestError("Repository manifest aliases are not allowed")
        node = super().compose_node(parent, index)
        if node is None:
            raise RepositoryManifestError("Repository manifest structure is invalid")
        return node

    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise RepositoryManifestError("Repository manifest mappings are invalid")
        keys: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge" or key_node.value == "<<":
                raise RepositoryManifestError("Repository manifest merge keys are not allowed")
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
            except TypeError as exc:
                raise RepositoryManifestError("Repository manifest keys must be scalar") from exc
            if duplicate:
                raise RepositoryManifestError("Repository manifest keys must be unique")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


@dataclass(frozen=True, slots=True)
class RepositoryManifestProjection:
    repository_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class WorkspaceManifestProjection:
    workspace_id: uuid.UUID
    kind: str
    display_name: str
    organization_id: uuid.UUID | None = None
    classifications: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrganizationDirectoryEntry:
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    repository_id: uuid.UUID
    display_name: str
    classifications: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManifestSyncSummary:
    created: int
    unchanged: int


def _safe_key(value: Any) -> str:
    if not isinstance(value, str):
        raise RepositoryManifestError("Repository manifest keys must be strings")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RepositoryManifestError("Repository manifest keys must be valid UTF-8") from exc
    normalized = value.casefold().replace("-", "_")
    if (
        len(encoded) > MAX_KEY_BYTES
        or not KEY_PATTERN.fullmatch(value)
        or any(part in normalized for part in SENSITIVE_KEY_PARTS)
    ):
        raise RepositoryManifestError("Repository manifest contains a prohibited field")
    return value


def _validate_portable_value(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_MANIFEST_NODES or depth > MAX_MANIFEST_DEPTH:
        raise RepositoryManifestError("Repository manifest structure exceeds its limit")
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RepositoryManifestError("Repository manifest numbers must be finite")
        return
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise RepositoryManifestError("Repository manifest text must be valid UTF-8") from exc
        if len(encoded) > MAX_STRING_BYTES or any(
            (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
            for character in value
        ):
            raise RepositoryManifestError("Repository manifest text is invalid")
        return
    if isinstance(value, list):
        for item in value:
            _validate_portable_value(item, depth=depth + 1, counter=counter)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _safe_key(key)
            _validate_portable_value(item, depth=depth + 1, counter=counter)
        return
    raise RepositoryManifestError("Repository manifest contains an unsupported value")


def _preflight_yaml(text: str) -> None:
    depth = 0
    nodes = 0
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent):
                raise RepositoryManifestError("Repository manifest aliases are not allowed")
            if isinstance(event, yaml.CollectionStartEvent):
                depth += 1
                nodes += 1
                if depth > MAX_MANIFEST_DEPTH or nodes > MAX_MANIFEST_NODES:
                    raise RepositoryManifestError("Repository manifest structure exceeds its limit")
            elif isinstance(event, yaml.CollectionEndEvent):
                depth -= 1
            elif isinstance(event, yaml.ScalarEvent):
                nodes += 1
                if nodes > MAX_MANIFEST_NODES:
                    raise RepositoryManifestError("Repository manifest structure exceeds its limit")
    except yaml.YAMLError as exc:
        raise RepositoryManifestError("Repository manifest YAML is invalid") from exc


def _load_existing(content: bytes | None, *, schema: str) -> dict[str, Any]:
    if content is None:
        return {}
    if len(content) > MAX_MANIFEST_BYTES:
        raise RepositoryManifestError("Repository manifest exceeds its size limit")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryManifestError("Repository manifest must be UTF-8") from exc
    _preflight_yaml(text)
    try:
        value = yaml.load(text, Loader=_StrictManifestLoader)  # noqa: S506  # nosec B506
    except yaml.YAMLError as exc:
        raise RepositoryManifestError("Repository manifest YAML is invalid") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise RepositoryManifestError("Repository manifest schema is unsupported")
    _validate_portable_value(value)
    return value


def _merge_mapping(existing: Mapping[str, Any], generated: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in generated.items():
        previous = merged.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            merged[key] = _merge_mapping(previous, value)
        else:
            merged[key] = value
    return merged


def _dump_manifest(value: Mapping[str, Any]) -> bytes:
    _validate_portable_value(dict(value))
    rendered = yaml.safe_dump(
        dict(value),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=120,
    ).encode("utf-8")
    if len(rendered) > MAX_MANIFEST_BYTES:
        raise RepositoryManifestError("Repository manifest exceeds its size limit")
    return rendered


def _portable_text(value: str) -> str:
    _validate_portable_value(value)
    return value


def render_repository_manifest(
    projection: RepositoryManifestProjection,
    *,
    existing: bytes | None = None,
) -> bytes:
    previous = _load_existing(existing, schema=REPOSITORY_SCHEMA)
    generated = {
        "schema": REPOSITORY_SCHEMA,
        "repository": {
            "id": str(projection.repository_id),
            "workspace_id": str(projection.workspace_id),
        },
    }
    return _dump_manifest(_merge_mapping(previous, generated))


def render_workspace_manifest(
    projection: WorkspaceManifestProjection,
    *,
    existing: bytes | None = None,
) -> bytes:
    kind = str(projection.kind)
    if kind not in WorkspaceKind.values:
        raise RepositoryManifestError("Repository workspace kind is invalid")
    workspace: dict[str, Any] = {
        "classifications": sorted({str(value) for value in projection.classifications}),
        "display_name": _portable_text(projection.display_name),
        "id": str(projection.workspace_id),
        "kind": kind,
    }
    if kind == WorkspaceKind.ORGANIZATION:
        if projection.organization_id is None:
            raise RepositoryManifestError("Organization workspace identity is incomplete")
        workspace["organization_id"] = str(projection.organization_id)
    elif projection.organization_id is not None or projection.classifications:
        raise RepositoryManifestError("MSP workspace identity contains organization data")
    previous = _load_existing(existing, schema=WORKSPACE_SCHEMA)
    generated = {"schema": WORKSPACE_SCHEMA, "workspace": workspace}
    return _dump_manifest(_merge_mapping(previous, generated))


def render_organization_directory(
    entries: tuple[OrganizationDirectoryEntry, ...],
    *,
    existing: bytes | None = None,
) -> bytes:
    previous = _load_existing(existing, schema=ORGANIZATION_DIRECTORY_SCHEMA)
    old_entries = previous.get("organizations", [])
    if not isinstance(old_entries, list):
        raise RepositoryManifestError("Organization directory entries are invalid")
    existing_by_id: dict[str, dict[str, Any]] = {}
    for value in old_entries:
        if not isinstance(value, dict) or not isinstance(value.get("organization_id"), str):
            raise RepositoryManifestError("Organization directory entry is invalid")
        try:
            identity = str(uuid.UUID(value["organization_id"]))
        except ValueError as exc:
            raise RepositoryManifestError("Organization directory identity is invalid") from exc
        if identity in existing_by_id:
            raise RepositoryManifestError("Organization directory identities must be unique")
        existing_by_id[identity] = value

    organizations: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: str(item.organization_id)):
        identity = str(entry.organization_id)
        generated = {
            "classifications": sorted({str(value) for value in entry.classifications}),
            "display_name": _portable_text(entry.display_name),
            "organization_id": identity,
            "repository_id": str(entry.repository_id),
            "workspace_id": str(entry.workspace_id),
        }
        organizations.append(_merge_mapping(existing_by_id.get(identity, {}), generated))
    merged = dict(previous)
    merged.update({"organizations": organizations, "schema": ORGANIZATION_DIRECTORY_SCHEMA})
    return _dump_manifest(merged)


def _read_optional_manifest(repository: WorkspaceRepository, path: str) -> bytes | None:
    if repository.accepted_commit_id is None:
        return None
    try:
        return read_accepted_repository_file(repository_id=repository.id, path=path)
    except RepositoryFileNotFoundError:
        return None


def _repository_projections(
    repository: WorkspaceRepository,
) -> tuple[RepositoryManifestProjection, WorkspaceManifestProjection]:
    workspace = repository.workspace
    if workspace.kind == WorkspaceKind.MSP:
        workspace_projection = WorkspaceManifestProjection(
            workspace_id=workspace.id,
            kind=workspace.kind,
            display_name=repository.tenant.name,
        )
    else:
        organization = workspace.organization
        if organization is None or organization.tenant_id != repository.tenant_id:
            raise RepositoryManifestError("Organization workspace identity is invalid")
        workspace_projection = WorkspaceManifestProjection(
            workspace_id=workspace.id,
            kind=workspace.kind,
            display_name=organization.entity.display_name,
            organization_id=organization.id,
            classifications=tuple(
                organization.classifications.order_by("kind").values_list("kind", flat=True)
            ),
        )
    return RepositoryManifestProjection(repository.id, workspace.id), workspace_projection


def _organization_directory_entries(tenant_id: uuid.UUID) -> tuple[OrganizationDirectoryEntry, ...]:
    repositories = (
        WorkspaceRepository.objects.filter(
            tenant_id=tenant_id,
            workspace__kind=WorkspaceKind.ORGANIZATION,
        )
        .select_related("workspace__organization__entity")
        .order_by("workspace__organization_id")
    )
    entries = []
    for repository in repositories:
        organization = repository.workspace.organization
        if organization is None or organization.tenant_id != tenant_id:
            raise RepositoryManifestError("Organization directory scope is invalid")
        entries.append(
            OrganizationDirectoryEntry(
                organization_id=organization.id,
                workspace_id=repository.workspace_id,
                repository_id=repository.id,
                display_name=organization.entity.display_name,
                classifications=tuple(
                    organization.classifications.order_by("kind").values_list("kind", flat=True)
                ),
            )
        )
    return tuple(entries)


def synchronize_workspace_manifests(repository_id: uuid.UUID) -> RepositoryCommitResult:
    conflict: RepositoryConflictError | None = None
    for _ in range(MAX_SYNC_ATTEMPTS):
        control_plane_repository = WorkspaceRepository.objects.select_related("tenant").get(pk=repository_id)
        scope = DataScope.tenant(control_plane_repository.tenant)
        with system_rls_scope_if_postgresql(scope, organization_mode=OrganizationRLSMode.MSP_ONLY):
            repository = (
                WorkspaceRepository.objects.select_related(
                    "tenant",
                    "workspace__organization__entity",
                    "accepted_commit",
                )
                .get(pk=repository_id)
            )
            repository_projection, workspace_projection = _repository_projections(repository)
            changes: dict[str, bytes | None] = {
                REPOSITORY_MANIFEST_PATH: render_repository_manifest(
                    repository_projection,
                    existing=_read_optional_manifest(repository, REPOSITORY_MANIFEST_PATH),
                ),
                WORKSPACE_MANIFEST_PATH: render_workspace_manifest(
                    workspace_projection,
                    existing=_read_optional_manifest(repository, WORKSPACE_MANIFEST_PATH),
                ),
            }
            if repository.workspace.kind == WorkspaceKind.MSP:
                changes[ORGANIZATION_DIRECTORY_PATH] = render_organization_directory(
                    _organization_directory_entries(repository.tenant_id),
                    existing=_read_optional_manifest(repository, ORGANIZATION_DIRECTORY_PATH),
                )
            else:
                changes[ORGANIZATION_DIRECTORY_PATH] = None
            accepted_commit = repository.accepted_commit
            expected_base = accepted_commit.object_id if accepted_commit is not None else None
            try:
                return commit_repository_files(
                    repository_id=repository.id,
                    expected_base=expected_base,
                    changes=changes,
                    message=MANIFEST_COMMIT_MESSAGE,
                )
            except RepositoryConflictError as exc:
                conflict = exc
    raise RepositoryConflictError("Repository manifests changed concurrently") from conflict


def synchronize_tenant_manifests(tenant_id: uuid.UUID) -> ManifestSyncSummary:
    if configured_repository_root() is None:
        return ManifestSyncSummary(0, 0)
    repository_ids = tuple(
        WorkspaceRepository.objects.filter(tenant_id=tenant_id)
        .order_by("workspace__kind", "workspace_id")
        .values_list("id", flat=True)
    )
    created = 0
    unchanged = 0
    for repository_id in repository_ids:
        result = synchronize_workspace_manifests(repository_id)
        if result.created:
            created += 1
        else:
            unchanged += 1
    return ManifestSyncSummary(created, unchanged)


def synchronize_all_workspace_manifests() -> ManifestSyncSummary:
    created = 0
    unchanged = 0
    for tenant_id in Tenant.objects.order_by("id").values_list("id", flat=True):
        summary = synchronize_tenant_manifests(tenant_id)
        created += summary.created
        unchanged += summary.unchanged
    return ManifestSyncSummary(created, unchanged)


def schedule_tenant_manifest_synchronization(tenant_id: uuid.UUID) -> None:
    if configured_repository_root() is None:
        return
    transaction.on_commit(lambda: synchronize_tenant_manifests(tenant_id))
