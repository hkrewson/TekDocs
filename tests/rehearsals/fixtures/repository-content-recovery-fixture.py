"""Retain and verify real Markdown, composition, and Git history across recovery."""

import os
import uuid

from django.db import transaction

from apps.accounts.models import User
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.models import ContentNode, WorkspaceKind, WorkspaceRepository
from apps.core.repository_service import read_repository_markdown_files_at_commit
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


OWNER_EMAIL = "validation-recovery@example.invalid"
FRAGMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.fragment")
DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.document")
INITIAL_FRAGMENT = "Confirm the device serial number.\n"
UPDATED_FRAGMENT = "Confirm the device serial number and enrollment status.\n"
DOCUMENT_MARKDOWN = "# Laptop setup\n\nFollow the retained prerequisite.\n"


def _repository(owner):
    return WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").get(
        tenant=owner.tenant_memberships.get(organization__isnull=True).tenant,
        workspace__kind=WorkspaceKind.MSP,
    )


def create_fixture(owner):
    repository = _repository(owner)
    fragment = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="create",
        content_id=FRAGMENT_ID,
        base_commit=repository.accepted_commit.object_id,
        base_blob=None,
        kind="fragment",
        path=None,
        title="Laptop prerequisite",
        markdown=INITIAL_FRAGMENT,
        metadata_patch={},
    )
    document = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="create",
        content_id=DOCUMENT_ID,
        base_commit=fragment.accepted_commit,
        base_blob=None,
        kind="document",
        path=None,
        title="Laptop setup",
        markdown=DOCUMENT_MARKDOWN,
        metadata_patch={
            "includes": [
                {
                    "id": str(FRAGMENT_ID),
                    "mode": "pinned",
                    "audience": "shared",
                    "commit": fragment.accepted_commit,
                }
            ]
        },
    )
    updated = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=FRAGMENT_ID,
        base_commit=document.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=UPDATED_FRAGMENT,
        metadata_patch={},
    )
    assert updated.accepted_commit == updated.indexed_commit
    print("repository Markdown recovery fixture created")


def verify_fixture(owner):
    repository = _repository(owner)
    fragment = read_authored_content(repository=repository, content_id=FRAGMENT_ID)
    document = read_authored_content(repository=repository, content_id=DOCUMENT_ID)
    assert fragment.markdown == UPDATED_FRAGMENT
    assert document.markdown == DOCUMENT_MARKDOWN
    assert fragment.accepted_commit == document.accepted_commit == fragment.indexed_commit
    node = ContentNode.objects.get(repository=repository, content_id=DOCUMENT_ID)
    assert node.composition_variants["all"]["markdown"] == (
        DOCUMENT_MARKDOWN.strip() + "\n\n" + INITIAL_FRAGMENT.strip() + "\n"
    )
    include = node.includes.get()
    assert include.target_content_id == FRAGMENT_ID
    assert include.resolution_mode == "pinned"
    assert include.resolved_object_id != fragment.accepted_commit
    _, historical_files = read_repository_markdown_files_at_commit(
        repository_id=repository.id, object_id=include.resolved_object_id
    )
    assert dict(historical_files)[fragment.path].decode() != fragment.source
    assert dict(historical_files)[fragment.path].endswith(INITIAL_FRAGMENT.encode())
    print("repository Markdown, pinned composition, and Git history restored")


owner = User.objects.get(email=OWNER_EMAIL)
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.tenant(owner.tenant_memberships.get(organization__isnull=True).tenant),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )
    mode = os.environ.get("TEKDOCS_RECOVERY_CONTENT_MODE")
    if mode == "create":
        create_fixture(owner)
    elif mode == "verify":
        verify_fixture(owner)
    else:
        raise RuntimeError("TEKDOCS_RECOVERY_CONTENT_MODE must be create or verify")
