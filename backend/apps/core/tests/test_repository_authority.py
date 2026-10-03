import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.core.models import (
    RepositoryCommit,
    RepositoryObjectFormat,
    Tenant,
    Workspace,
    WorkspaceKind,
    WorkspaceRepository,
    repository_storage_relative_path,
)
from apps.core.serializers import WorkspaceContextSerializer


def _repository(workspace: Workspace) -> WorkspaceRepository:
    repository_id = uuid.uuid4()
    return WorkspaceRepository.objects.create(
        id=repository_id,
        tenant=workspace.tenant,
        workspace=workspace,
        storage_relative_path=repository_storage_relative_path(repository_id=repository_id),
    )


@pytest.mark.django_db
def test_repository_has_one_exact_workspace_and_safe_stable_path():
    tenant = Tenant.objects.create(name="Repository MSP", slug="repository-msp")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    _repository(workspace)

    duplicate_id = uuid.uuid4()
    duplicate = WorkspaceRepository(
        id=duplicate_id,
        tenant=tenant,
        workspace=workspace,
        storage_relative_path=repository_storage_relative_path(repository_id=duplicate_id),
    )
    with pytest.raises(ValidationError, match="already exists"):
        duplicate.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceRepository.objects.bulk_create([duplicate])

    other_tenant = Tenant.objects.create(name="Other Repository MSP", slug="other-repository-msp")
    mismatched_id = uuid.uuid4()
    mismatched = WorkspaceRepository(
        id=mismatched_id,
        tenant=other_tenant,
        workspace=workspace,
        storage_relative_path=repository_storage_relative_path(repository_id=mismatched_id),
    )
    with pytest.raises(ValidationError, match="workspace"):
        mismatched.full_clean()

    unsafe_id = uuid.uuid4()
    unsafe = WorkspaceRepository(
        id=unsafe_id,
        tenant=other_tenant,
        workspace=Workspace.objects.get(tenant=other_tenant, kind=WorkspaceKind.MSP),
        storage_relative_path="/srv/tekdocs/repositories/escape.git",
    )
    with pytest.raises(ValidationError, match="stable identity"):
        unsafe.full_clean()


@pytest.mark.django_db
def test_accepted_and_indexed_heads_require_verified_objects_from_the_same_repository():
    tenant = Tenant.objects.create(name="Head Authority MSP", slug="head-authority")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    repository = _repository(workspace)
    verified = RepositoryCommit.objects.create(
        tenant=tenant,
        repository=repository,
        object_format=RepositoryObjectFormat.SHA1,
        object_id="a" * 40,
    )
    repository.accepted_commit = verified
    repository.indexed_commit = verified
    repository.save(update_fields=("accepted_commit", "indexed_commit", "updated_at"))

    assert repository.accepted_commit_id == verified.id
    assert repository.indexed_commit_id == verified.id

    second_tenant = Tenant.objects.create(name="Other Head MSP", slug="other-head")
    second_workspace = Workspace.objects.get(tenant=second_tenant, kind=WorkspaceKind.MSP)
    second_repository = _repository(second_workspace)
    foreign_commit = RepositoryCommit.objects.create(
        tenant=second_tenant,
        repository=second_repository,
        object_format=RepositoryObjectFormat.SHA256,
        object_id="b" * 64,
    )
    repository.accepted_commit = foreign_commit
    with pytest.raises(ValidationError, match="verified object"):
        repository.save()


@pytest.mark.django_db(transaction=True)
def test_database_guards_reject_cross_tenant_repository_and_foreign_head():
    if connection.vendor != "postgresql":
        pytest.skip("Repository authority guards require PostgreSQL")

    first = Tenant.objects.create(name="First Repository MSP", slug=f"first-repository-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second Repository MSP", slug=f"second-repository-{uuid.uuid4()}")
    first_workspace = Workspace.objects.get(tenant=first, kind=WorkspaceKind.MSP)
    second_workspace = Workspace.objects.get(tenant=second, kind=WorkspaceKind.MSP)
    first_repository = _repository(first_workspace)
    second_repository = _repository(second_workspace)
    second_commit = RepositoryCommit.objects.create(
        tenant=second,
        repository=second_repository,
        object_id="c" * 40,
    )

    cross_tenant_id = uuid.uuid4()
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceRepository.objects.bulk_create(
            [
                WorkspaceRepository(
                    id=cross_tenant_id,
                    tenant=second,
                    workspace=first_workspace,
                    storage_relative_path=repository_storage_relative_path(repository_id=cross_tenant_id),
                )
            ]
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceRepository.objects.filter(pk=first_repository.pk).update(accepted_commit=second_commit)


@pytest.mark.django_db
def test_workspace_api_contract_does_not_expose_repository_paths_or_credentials():
    tenant = Tenant.objects.create(name="Private Repository MSP", slug="private-repository")
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    repository = _repository(workspace)

    # Repository authority is intentionally absent from public serializers in this slice.
    serialized_fields = set(WorkspaceContextSerializer().fields)
    assert "storage_relative_path" not in serialized_fields
    assert not any("credential" in field for field in serialized_fields)
    assert repository.storage_relative_path.startswith("repositories/")
