from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.core import repository_manifests, repository_storage
from apps.core.models import (
    Entity,
    Organization,
    OrganizationClassification,
    OrganizationKind,
    RepositoryCommit,
    Tenant,
    Workspace,
    WorkspaceKind,
    WorkspaceRepository,
)
from apps.core.organizations import create_organization, update_organization
from apps.core.repository_service import (
    RepositoryFileNotFoundError,
    commit_repository_files,
    read_accepted_repository_file,
)

pytestmark = pytest.mark.django_db(transaction=True)
FIXTURES = Path(__file__).parent / "fixtures" / "repository_manifests"


def _organization(
    tenant: Tenant,
    name: str,
    classifications: tuple[str, ...],
    *,
    marker: str = "",
) -> Organization:
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP),
        entity_type="organization",
        display_name=name,
    )
    organization = Organization.objects.create(
        tenant=tenant,
        entity=entity,
        legal_name=marker,
        billing_contact_name=marker,
        billing_address_line_1=marker,
    )
    OrganizationClassification.objects.bulk_create(
        [
            OrganizationClassification(tenant=tenant, organization=organization, kind=kind)
            for kind in classifications
        ]
    )
    return organization


def _initialize_tenant_repositories(tenant: Tenant) -> None:
    for workspace in Workspace.objects.filter(tenant=tenant).order_by("id"):
        result = repository_storage.ensure_workspace_repository(workspace)
        assert result is not None


@pytest.fixture
def manifest_tenant(tmp_path):
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        tenant = Tenant.objects.create(name="Manifest MSP", slug="manifest-msp")
        first = _organization(tenant, "Zeta Supplier", (OrganizationKind.VENDOR, OrganizationKind.MANUFACTURER))
        second = _organization(tenant, "Alpha Client", (OrganizationKind.CLIENT,))
        _initialize_tenant_repositories(tenant)
        yield tenant, first, second, root


def _content(repository: WorkspaceRepository, path: str) -> bytes:
    return read_accepted_repository_file(repository_id=repository.id, path=path)


def test_rendered_manifests_match_versioned_schema_fixtures():
    repository = repository_manifests.render_repository_manifest(
        repository_manifests.RepositoryManifestProjection(
            repository_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
            workspace_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        )
    )
    workspace = repository_manifests.render_workspace_manifest(
        repository_manifests.WorkspaceManifestProjection(
            workspace_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
            kind=WorkspaceKind.ORGANIZATION,
            display_name="Acme Support",
            organization_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
            classifications=(OrganizationKind.PARTNER, OrganizationKind.CLIENT),
        )
    )
    directory = repository_manifests.render_organization_directory(
        (
            repository_manifests.OrganizationDirectoryEntry(
                organization_id=uuid.UUID("77777777-7777-4777-8777-777777777777"),
                workspace_id=uuid.UUID("88888888-8888-4888-8888-888888888888"),
                repository_id=uuid.UUID("99999999-9999-4999-8999-999999999999"),
                display_name="Zeta Supplier",
                classifications=(OrganizationKind.VENDOR, OrganizationKind.MANUFACTURER),
            ),
            repository_manifests.OrganizationDirectoryEntry(
                organization_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
                workspace_id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
                repository_id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
                display_name="Alpha Client",
                classifications=(OrganizationKind.CLIENT,),
            ),
        )
    )

    assert repository == (FIXTURES / "repository.yml").read_bytes()
    assert workspace == (FIXTURES / "workspace.yml").read_bytes()
    assert directory == (FIXTURES / "organizations.yml").read_bytes()


def test_sync_is_deterministic_and_organization_repositories_are_isolated(manifest_tenant):
    tenant, first, second, _ = manifest_tenant
    first_sync = repository_manifests.synchronize_tenant_manifests(tenant.id)
    assert first_sync == repository_manifests.ManifestSyncSummary(created=3, unchanged=0)

    repositories = {
        repository.workspace_id: repository
        for repository in WorkspaceRepository.objects.filter(tenant=tenant).select_related("workspace")
    }
    before = {}
    for repository in repositories.values():
        before[repository.id] = (
            _content(repository, repository_manifests.REPOSITORY_MANIFEST_PATH),
            _content(repository, repository_manifests.WORKSPACE_MANIFEST_PATH),
        )

    first_repository = repositories[first.ownership_workspace.id]
    first_workspace = yaml.safe_load(before[first_repository.id][1])
    assert first_workspace["workspace"] == {
        "classifications": ["manufacturer", "vendor"],
        "display_name": "Zeta Supplier",
        "id": str(first.ownership_workspace.id),
        "kind": "organization",
        "organization_id": str(first.id),
    }
    assert "Alpha Client" not in before[first_repository.id][1].decode()
    with pytest.raises(RepositoryFileNotFoundError):
        _content(first_repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH)

    second_repository = repositories[second.ownership_workspace.id]
    assert "Zeta Supplier" not in before[second_repository.id][1].decode()
    msp_repository = repositories[Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP).id]
    directory = yaml.safe_load(_content(msp_repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH))
    assert [entry["organization_id"] for entry in directory["organizations"]] == sorted(
        (str(first.id), str(second.id))
    )

    second_sync = repository_manifests.synchronize_tenant_manifests(tenant.id)
    assert second_sync == repository_manifests.ManifestSyncSummary(created=0, unchanged=3)
    assert RepositoryCommit.objects.filter(tenant=tenant).count() == 3
    for repository in repositories.values():
        assert before[repository.id] == (
            _content(repository, repository_manifests.REPOSITORY_MANIFEST_PATH),
            _content(repository, repository_manifests.WORKSPACE_MANIFEST_PATH),
        )


def test_operational_and_secret_shaped_database_values_are_not_projected(tmp_path):
    marker = "private-operational-marker-47d9"
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        tenant = Tenant.objects.create(name="Redaction MSP", slug="redaction-msp")
        organization = _organization(tenant, "Visible Client", (OrganizationKind.CLIENT,), marker=marker)
        user = User.objects.create_user(
            email=f"{marker}@example.invalid",
            password="Manifest-test-only-Aa7-password",
            display_name=marker,
        )
        assert user.email.startswith(marker)
        _initialize_tenant_repositories(tenant)
        repository_manifests.synchronize_tenant_manifests(tenant.id)

        for repository in WorkspaceRepository.objects.filter(tenant=tenant):
            for path in (
                repository_manifests.REPOSITORY_MANIFEST_PATH,
                repository_manifests.WORKSPACE_MANIFEST_PATH,
            ):
                assert marker.encode() not in _content(repository, path)
        msp_repository = WorkspaceRepository.objects.get(
            tenant=tenant,
            workspace__kind=WorkspaceKind.MSP,
        )
        directory = _content(msp_repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH)
        assert marker.encode() not in directory
        assert str(organization.id).encode() in directory


def test_yaml_values_cannot_inject_manifest_structure(manifest_tenant):
    tenant, organization, _, _ = manifest_tenant
    hostile_name = "Client\nschema: hostile\n- sibling: injected 🧪"
    organization.entity.display_name = hostile_name
    organization.entity.save(update_fields=("display_name", "updated_at"))

    repository_manifests.synchronize_tenant_manifests(tenant.id)

    repository = WorkspaceRepository.objects.get(workspace=organization.ownership_workspace)
    parsed = yaml.safe_load(_content(repository, repository_manifests.WORKSPACE_MANIFEST_PATH))
    assert parsed["schema"] == repository_manifests.WORKSPACE_SCHEMA
    assert parsed["workspace"]["display_name"] == hostile_name
    assert set(parsed) == {"schema", "workspace"}


@pytest.mark.parametrize(
    "hostile",
    (
        b"schema: tekdocs.repository/v1\nfuture: &shared value\ncopy: *shared\n",
        b"schema: tekdocs.repository/v1\nschema: tekdocs.repository/v1\n",
        b"schema: tekdocs.repository/v1\nfuture: !!python/object:builtins.object {}\n",
        b"schema: tekdocs.repository/v1\napi_token: forbidden\n",
        b"schema: tekdocs.repository/v1\nbase: &base {future: true}\nmerged: {<<: *base}\n",
    ),
)
def test_hostile_existing_yaml_fails_closed(hostile):
    projection = repository_manifests.RepositoryManifestProjection(uuid.uuid4(), uuid.uuid4())

    with pytest.raises(repository_manifests.RepositoryManifestError):
        repository_manifests.render_repository_manifest(projection, existing=hostile)


def test_existing_yaml_depth_is_bounded_before_construction():
    projection = repository_manifests.RepositoryManifestProjection(uuid.uuid4(), uuid.uuid4())
    nested = "value"
    for index in range(repository_manifests.MAX_MANIFEST_DEPTH + 1):
        nested = f"level_{index}:\n" + "  ".join(("", nested.replace("\n", "\n  ")))
    hostile = f"schema: tekdocs.repository/v1\n{nested}\n".encode()

    with pytest.raises(repository_manifests.RepositoryManifestError, match="structure exceeds"):
        repository_manifests.render_repository_manifest(projection, existing=hostile)


def test_unknown_safe_fields_are_preserved_and_foreign_directory_entries_are_removed():
    repository_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    existing_repository = (
        b"schema: tekdocs.repository/v1\n"
        b"future:\n  feature_flag: true\n"
        b"repository:\n  future_label: retained\n  id: 00000000-0000-4000-8000-000000000000\n"
    )
    rendered_repository = yaml.safe_load(
        repository_manifests.render_repository_manifest(
            repository_manifests.RepositoryManifestProjection(repository_id, workspace_id),
            existing=existing_repository,
        )
    )
    assert rendered_repository["future"] == {"feature_flag": True}
    assert rendered_repository["repository"]["future_label"] == "retained"
    assert rendered_repository["repository"]["id"] == str(repository_id)

    existing_directory = (
        "schema: tekdocs.organization-directory/v1\n"
        "future_label: retained\n"
        "organizations:\n"
        f"- organization_id: {organization_id}\n  future_label: retained-entry\n"
        f"- organization_id: {uuid.uuid4()}\n  future_label: remove-foreign-entry\n"
    ).encode()
    directory = yaml.safe_load(
        repository_manifests.render_organization_directory(
            (
                repository_manifests.OrganizationDirectoryEntry(
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                    display_name="Known Client",
                    classifications=(OrganizationKind.CLIENT,),
                ),
            ),
            existing=existing_directory,
        )
    )
    assert directory["future_label"] == "retained"
    assert len(directory["organizations"]) == 1
    assert directory["organizations"][0]["future_label"] == "retained-entry"


def test_rename_updates_names_without_changing_stable_identities(manifest_tenant):
    tenant, organization, _, _ = manifest_tenant
    repository_manifests.synchronize_tenant_manifests(tenant.id)
    original = (organization.id, organization.ownership_workspace.id, organization.ownership_workspace.repository.id)

    organization.entity.display_name = "Renamed Client"
    organization.entity.save(update_fields=("display_name", "updated_at"))
    OrganizationClassification.objects.filter(organization=organization).delete()
    OrganizationClassification.objects.create(
        tenant=tenant,
        organization=organization,
        kind=OrganizationKind.PARTNER,
    )
    repository_manifests.synchronize_tenant_manifests(tenant.id)

    organization.refresh_from_db()
    current = (organization.id, organization.ownership_workspace.id, organization.ownership_workspace.repository.id)
    assert current == original
    repository = WorkspaceRepository.objects.get(pk=current[2])
    workspace = yaml.safe_load(_content(repository, repository_manifests.WORKSPACE_MANIFEST_PATH))
    assert workspace["workspace"]["display_name"] == "Renamed Client"
    assert workspace["workspace"]["classifications"] == ["partner"]
    msp_repository = WorkspaceRepository.objects.get(tenant=tenant, workspace__kind=WorkspaceKind.MSP)
    directory = yaml.safe_load(_content(msp_repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH))
    renamed = next(entry for entry in directory["organizations"] if entry["organization_id"] == str(organization.id))
    assert renamed["display_name"] == "Renamed Client"
    assert renamed["classifications"] == ["partner"]


def test_cross_tenant_directories_never_include_foreign_organizations(tmp_path):
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        first_tenant = Tenant.objects.create(name="First MSP", slug="manifest-first-msp")
        second_tenant = Tenant.objects.create(name="Second MSP", slug="manifest-second-msp")
        first = _organization(first_tenant, "First Client", (OrganizationKind.CLIENT,))
        second = _organization(second_tenant, "Second Client", (OrganizationKind.CLIENT,))
        _initialize_tenant_repositories(first_tenant)
        _initialize_tenant_repositories(second_tenant)
        repository_manifests.synchronize_tenant_manifests(first_tenant.id)
        repository_manifests.synchronize_tenant_manifests(second_tenant.id)

        first_repository = WorkspaceRepository.objects.get(
            tenant=first_tenant,
            workspace__kind=WorkspaceKind.MSP,
        )
        first_directory = _content(first_repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH)
        assert str(first.id).encode() in first_directory
        assert str(second.id).encode() not in first_directory
        assert b"Second Client" not in first_directory


def test_initializer_backfills_manifests_and_is_retry_safe(manifest_tenant):
    tenant, _, _, _ = manifest_tenant
    first_output = io.StringIO()
    call_command("initialize_workspace_repositories", stdout=first_output)
    assert "0 initialized, 3 retained" in first_output.getvalue()
    assert "3 updated, 0 unchanged" in first_output.getvalue()

    second_output = io.StringIO()
    call_command("initialize_workspace_repositories", stdout=second_output)
    assert "0 initialized, 3 retained" in second_output.getvalue()
    assert "0 updated, 3 unchanged" in second_output.getvalue()
    assert RepositoryCommit.objects.filter(tenant=tenant).count() == 3


def test_supported_create_and_update_paths_refresh_manifests(
    tmp_path,
    django_capture_on_commit_callbacks,
):
    root = tmp_path / "repositories"
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(root)):
        tenant = Tenant.objects.create(name="Lifecycle MSP", slug="manifest-lifecycle-msp")
        actor = User.objects.create_user(
            email="manifest-lifecycle@example.invalid",
            password="Manifest-lifecycle-only-Aa7-password",
            display_name="Manifest Operator",
        )
        msp_workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        assert repository_storage.ensure_workspace_repository(msp_workspace) is not None
        repository_manifests.synchronize_tenant_manifests(tenant.id)

        with django_capture_on_commit_callbacks(execute=True):
            organization = create_organization(
                tenant=tenant,
                actor_id=actor.id,
                name="Lifecycle Client",
                legal_name="",
                website="",
                classifications=(OrganizationKind.CLIENT,),
            )
        organization_repository = WorkspaceRepository.objects.get(workspace=organization.ownership_workspace)
        created = yaml.safe_load(
            _content(organization_repository, repository_manifests.WORKSPACE_MANIFEST_PATH)
        )
        assert created["workspace"]["display_name"] == "Lifecycle Client"

        with django_capture_on_commit_callbacks(execute=True):
            update_organization(
                organization=organization,
                actor_id=actor.id,
                name="Lifecycle Client Renamed",
                legal_name="",
                website="",
                classifications=(OrganizationKind.CLIENT, OrganizationKind.PARTNER),
            )
        updated = yaml.safe_load(
            _content(organization_repository, repository_manifests.WORKSPACE_MANIFEST_PATH)
        )
        assert updated["workspace"]["display_name"] == "Lifecycle Client Renamed"
        assert updated["workspace"]["classifications"] == ["client", "partner"]


def test_organization_sync_removes_msp_directory_from_its_repository(manifest_tenant):
    tenant, organization, _, _ = manifest_tenant
    repository_manifests.synchronize_tenant_manifests(tenant.id)
    repository = WorkspaceRepository.objects.get(workspace=organization.ownership_workspace)
    repository.refresh_from_db()
    accepted = repository.accepted_commit.object_id
    injected = commit_repository_files(
        repository_id=repository.id,
        expected_base=accepted,
        changes={
            repository_manifests.ORGANIZATION_DIRECTORY_PATH: (
                b"schema: tekdocs.organization-directory/v1\norganizations: []\n"
            )
        },
        message="Inject forbidden organization directory",
    )
    assert injected.created is True

    repository_manifests.synchronize_workspace_manifests(repository.id)

    with pytest.raises(RepositoryFileNotFoundError):
        _content(repository, repository_manifests.ORGANIZATION_DIRECTORY_PATH)
