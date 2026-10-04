import hashlib
import json
import os

import yaml
from django.db import transaction

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core import repository_service
from apps.core.models import (
    OrganizationKind,
    WorkspaceKind,
    WorkspaceRepository,
    repository_identity_uuid,
    repository_storage_relative_path,
)
from apps.core.organizations import create_organization
from apps.core.repository_manifests import (
    ORGANIZATION_DIRECTORY_PATH,
    REPOSITORY_MANIFEST_PATH,
    WORKSPACE_MANIFEST_PATH,
    synchronize_workspace_manifests,
)
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.repository_service import (
    RepositoryAuditAttribution,
    RepositoryFileNotFoundError,
    commit_repository_files,
    read_accepted_repository_file,
)
from apps.core.repository_storage import resolve_managed_repository_path


OWNER_EMAIL = "repository-foundation@example.invalid"
CLIENT_NAME = "Repository Foundation Client"
VENDOR_NAME = "Repository Foundation Vendor"
CONTENT_PREFIX = "foundation"


def _repositories():
    return tuple(
        WorkspaceRepository.objects.select_related(
            "tenant",
            "workspace",
            "accepted_commit",
            "indexed_commit",
        ).order_by("workspace__kind", "workspace_id")
    )


def _content_path(repository):
    return f"{CONTENT_PREFIX}/{repository.workspace_id}.md"


def _content(repository):
    return (
        "# Repository foundation acceptance\n\n"
        f"Workspace: {repository.workspace_id}\n"
        f"Kind: {repository.workspace.kind}\n"
    ).encode()


def _assert_no_remote_authority(repository, path):
    assert not any(name.startswith(("GITHUB_", "GH_")) for name in os.environ)
    config = (path / "config").read_text(encoding="utf-8").casefold()
    assert "[remote " not in config
    assert "[include" not in config
    assert not (path / "objects" / "info" / "alternates").exists()
    assert read_accepted_repository_file(
        repository_id=repository.id,
        path=REPOSITORY_MANIFEST_PATH,
    )


def _workspace_manifest(repository):
    return yaml.safe_load(
        read_accepted_repository_file(
            repository_id=repository.id,
            path=WORKSPACE_MANIFEST_PATH,
        )
    )["workspace"]


def _assert_foundation(*, require_content):
    repositories = _repositories()
    assert len(repositories) == 3
    assert [repository.workspace.kind for repository in repositories].count(WorkspaceKind.MSP) == 1
    organizations = [
        repository for repository in repositories if repository.workspace.kind == WorkspaceKind.ORGANIZATION
    ]
    assert len(organizations) == 2
    classifications = {
        tuple(_workspace_manifest(repository)["classifications"])
        for repository in organizations
    }
    assert classifications == {(OrganizationKind.CLIENT,), (OrganizationKind.VENDOR,)}

    repository_ids = {repository.id for repository in repositories}
    workspace_ids = {repository.workspace_id for repository in repositories}
    assert len(repository_ids) == len(workspace_ids) == 3
    for repository in repositories:
        assert repository.id == repository_identity_uuid(workspace_id=repository.workspace_id)
        assert repository.storage_relative_path == repository_storage_relative_path(
            repository_id=repository.id
        )
        assert repository.tenant_id == repository.workspace.tenant_id
        assert repository.accepted_commit is not None
        assert repository.indexed_commit is None
        _, path = resolve_managed_repository_path(repository)
        assert path.stat().st_uid == os.geteuid()
        assert path.stat().st_gid == os.getegid()
        assert path.stat().st_mode & 0o777 == 0o700
        _assert_no_remote_authority(repository, path)
        manifest = _workspace_manifest(repository)
        assert manifest["id"] == str(repository.workspace_id)
        assert manifest["kind"] == repository.workspace.kind
        if require_content:
            assert read_accepted_repository_file(
                repository_id=repository.id,
                path=_content_path(repository),
            ) == _content(repository)

    msp = next(repository for repository in repositories if repository.workspace.kind == WorkspaceKind.MSP)
    assert read_accepted_repository_file(
        repository_id=msp.id,
        path=ORGANIZATION_DIRECTORY_PATH,
    )
    for repository in organizations:
        try:
            read_accepted_repository_file(
                repository_id=repository.id,
                path=ORGANIZATION_DIRECTORY_PATH,
            )
        except RepositoryFileNotFoundError:
            pass
        else:
            raise AssertionError("organization repository contains the MSP organization directory")

    if require_content:
        for repository in repositories:
            for other in repositories:
                if other.id == repository.id:
                    continue
                try:
                    read_accepted_repository_file(
                        repository_id=repository.id,
                        path=_content_path(other),
                    )
                except RepositoryFileNotFoundError:
                    pass
                else:
                    raise AssertionError("one workspace repository exposed another workspace's content")
    return repositories


def create_fixture():
    result = bootstrap_owner(
        tenant_name="Repository Foundation MSP",
        owner_email=OWNER_EMAIL,
        owner_display_name="Repository Foundation Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name=CLIENT_NAME,
        legal_name="",
        website="",
        classifications=(OrganizationKind.CLIENT,),
    )
    create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name=VENDOR_NAME,
        legal_name="",
        website="",
        classifications=(OrganizationKind.VENDOR,),
    )


def exercise_fixture():
    owner = User.objects.get(email=OWNER_EMAIL)
    tenant = owner.tenant_memberships.get(organization__isnull=True).tenant
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(tenant),
            organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
            actor_user_id=owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        _exercise_fixture(owner)


def _exercise_fixture(owner):
    repositories = _assert_foundation(require_content=False)
    for repository in repositories:
        result = commit_repository_files(
            repository_id=repository.id,
            expected_base=repository.accepted_commit.object_id,
            changes={_content_path(repository): _content(repository)},
            message="Add repository foundation acceptance marker",
            attribution=RepositoryAuditAttribution(
                actor_id=owner.id,
                action="repository.foundation.acceptance",
            ),
        )
        assert result.created is True

    interrupted = next(
        repository
        for repository in _repositories()
        if repository.workspace.kind == WorkspaceKind.ORGANIZATION
        and OrganizationKind.CLIENT in _workspace_manifest(repository)["classifications"]
    )
    accepted_before = interrupted.accepted_commit.object_id
    root, path = resolve_managed_repository_path(interrupted)
    original_accept = repository_service._accept_commit
    repository_service._accept_commit = lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt())
    try:
        try:
            commit_repository_files(
                repository_id=interrupted.id,
                expected_base=accepted_before,
                changes={f"{CONTENT_PREFIX}/interrupted.md": b"interrupted\n"},
                message="Interrupt repository foundation write",
            )
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("the injected interruption did not interrupt the commit")
    finally:
        repository_service._accept_commit = original_accept
    interrupted.refresh_from_db()
    assert interrupted.accepted_commit.object_id == accepted_before
    git = repository_service._GitRepository(interrupted.id, path, interrupted.accepted_commit.object_format)
    assert git.raw_current_ref() == accepted_before
    assert not tuple(root.glob(f".{interrupted.id}.stage-*"))

    abandoned = root / f".{interrupted.id}.stage-abandoned"
    abandoned.mkdir(mode=0o700)
    (abandoned / "index.lock").write_bytes(b"abandoned")
    (abandoned / "index.lock").chmod(0o600)
    recovered = commit_repository_files(
        repository_id=interrupted.id,
        expected_base=accepted_before,
        changes={f"{CONTENT_PREFIX}/interrupted.md": b"recovered\n"},
        message="Recover repository foundation write",
        attribution=RepositoryAuditAttribution(
            actor_id=owner.id,
            action="repository.foundation.recovered",
        ),
    )
    assert recovered.created is True
    assert not abandoned.exists()
    assert read_accepted_repository_file(
        repository_id=interrupted.id,
        path=f"{CONTENT_PREFIX}/interrupted.md",
    ) == b"recovered\n"

    repositories = _assert_foundation(require_content=True)
    for repository in repositories:
        before = repository.accepted_commit.object_id
        result = synchronize_workspace_manifests(repository.id)
        assert result.created is False
        assert result.object_id == before


def inventory_fixture():
    repositories = _assert_foundation(require_content=True)
    inventory = []
    for repository in repositories:
        content = read_accepted_repository_file(
            repository_id=repository.id,
            path=_content_path(repository),
        )
        inventory.append(
            {
                "accepted_commit": repository.accepted_commit.object_id,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "indexed_commit": None,
                "kind": repository.workspace.kind,
                "repository_id": str(repository.id),
                "tenant_id": str(repository.tenant_id),
                "workspace_id": str(repository.workspace_id),
            }
        )
    print(json.dumps(inventory, separators=(",", ":"), sort_keys=True))


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "exercise":
    exercise_fixture()
elif mode == "verify":
    _assert_foundation(require_content=True)
elif mode == "inventory":
    inventory_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create, exercise, verify, or inventory")
