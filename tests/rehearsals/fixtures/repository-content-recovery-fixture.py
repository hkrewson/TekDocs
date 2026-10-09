"""Retain and verify real Markdown, composition, and Git history across recovery."""

import hashlib
import os
import uuid

import yaml
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.accounts.models import User
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.document_attachments import copy_attachment_content, create_document_attachment
from apps.core.documents import create_document
from apps.core.models import ContentNode, Document, Organization, WorkspaceKind, WorkspaceRepository
from apps.core.repository_editable_bundle_validation import verify_repository_editable_bundle
from apps.core.repository_editable_bundles import export_repository_editable_bundle
from apps.core.repository_manifests import ORGANIZATION_DIRECTORY_PATH
from apps.core.repository_service import (
    RepositoryFileNotFoundError,
    read_accepted_repository_file,
    read_repository_markdown_files_at_commit,
)
from apps.core.repository_source_exports import export_repository_sources
from apps.core.repository_source_git_validation import verify_repository_source_against_git
from apps.core.repository_source_validation import verify_repository_source_snapshot
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


OWNER_EMAIL = "validation-recovery@example.invalid"
ORGANIZATION_NAME = "Validation Recovery Client"
FRAGMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.fragment")
DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.document")
ORGANIZATION_DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.organization.document")
INITIAL_FRAGMENT = "Confirm the device serial number.\n"
UPDATED_FRAGMENT = "Confirm the device serial number and enrollment status.\n"
DOCUMENT_MARKDOWN = "# Laptop setup\n\nFollow the retained prerequisite.\n"
ORGANIZATION_MARKDOWN = "# Client enrollment\n\nUse this client's device policy.\n"
PUBLICATION_DOCUMENT_TITLE = "Client setup guide"
PUBLICATION_ATTACHMENT_NAME = "recovery-guide.txt"
PUBLICATION_ATTACHMENT_BYTES = b"Client setup instructions retained for recovery.\n"


def _repository(owner):
    return WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").get(
        tenant=owner.tenant_memberships.get(organization__isnull=True).tenant,
        workspace__kind=WorkspaceKind.MSP,
    )


def _organization_repository(owner, organization):
    return WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").get(
        tenant=owner.tenant_memberships.get(organization__isnull=True).tenant,
        workspace__organization=organization,
    )


def _assert_absent(*, repository, content_id):
    try:
        read_authored_content(repository=repository, content_id=content_id)
    except RepositoryFileNotFoundError:
        return
    raise AssertionError("content from another Workspace appeared in this repository")


def _source_snapshot_digest(repository):
    snapshot = export_repository_sources(repository)
    manifest = verify_repository_source_snapshot(snapshot.content)
    verify_repository_source_against_git(manifest, repository_id=repository.id)
    return hashlib.sha256(snapshot.content).hexdigest()


def _editable_bundle_digest(repository, attachment):
    bundle = export_repository_editable_bundle(repository)
    manifest = verify_repository_editable_bundle(bundle.content)
    assert manifest["workspace_id"] == str(repository.workspace_id)
    assert manifest["accepted_commit"] == repository.accepted_commit.object_id
    assert len(manifest["attachments"]) == 1
    descriptor = manifest["attachments"][0]
    assert descriptor["id"] == str(attachment.entity_id)
    assert descriptor["document_id"] == str(attachment.document_id)
    assert descriptor["sha256"] == hashlib.sha256(PUBLICATION_ATTACHMENT_BYTES).hexdigest()
    assert copy_attachment_content(attachment) == PUBLICATION_ATTACHMENT_BYTES
    return hashlib.sha256(bundle.content).hexdigest()


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


def create_organization_fixture(owner, organization):
    repository = _organization_repository(owner, organization)
    document = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="create",
        content_id=ORGANIZATION_DOCUMENT_ID,
        base_commit=repository.accepted_commit.object_id,
        base_blob=None,
        kind="document",
        path=None,
        title="Client enrollment",
        markdown=ORGANIZATION_MARKDOWN,
        metadata_patch={},
    )
    assert document.accepted_commit == document.indexed_commit
    legacy_document = create_document(
        tenant=repository.tenant,
        organization=organization,
        actor_id=owner.id,
        title=PUBLICATION_DOCUMENT_TITLE,
        markdown="Legacy attachment owner.\n",
    )
    attachment = create_document_attachment(
        document=legacy_document,
        actor_id=owner.id,
        upload=SimpleUploadedFile(PUBLICATION_ATTACHMENT_NAME, PUBLICATION_ATTACHMENT_BYTES),
    )
    publication_source = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="create",
        content_id=legacy_document.id,
        base_commit=document.accepted_commit,
        base_blob=None,
        kind="document",
        path=None,
        title=PUBLICATION_DOCUMENT_TITLE,
        markdown=f"# {PUBLICATION_DOCUMENT_TITLE}\n\n[Guide](tekdocs://attachment/{attachment.entity_id})\n",
        metadata_patch={},
    )
    assert publication_source.accepted_commit == publication_source.indexed_commit
    return attachment


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
    _assert_absent(repository=repository, content_id=ORGANIZATION_DOCUMENT_ID)
    directory = yaml.safe_load(
        read_accepted_repository_file(repository_id=repository.id, path=ORGANIZATION_DIRECTORY_PATH)
    )
    organization = Organization.objects.get(tenant=repository.tenant, entity__display_name=ORGANIZATION_NAME)
    matching = [
        entry for entry in directory["organizations"] if entry["organization_id"] == str(organization.id)
    ]
    assert len(matching) == 1
    assert matching[0]["display_name"] == ORGANIZATION_NAME
    assert matching[0]["classifications"] == ["client"]
    return matching[0]


def verify_organization_fixture(owner, organization, directory_entry):
    repository = _organization_repository(owner, organization)
    document = read_authored_content(repository=repository, content_id=ORGANIZATION_DOCUMENT_ID)
    assert document.markdown == ORGANIZATION_MARKDOWN
    assert document.accepted_commit == document.indexed_commit
    assert ContentNode.objects.get(repository=repository, content_id=ORGANIZATION_DOCUMENT_ID).markdown == (
        ORGANIZATION_MARKDOWN
    )
    legacy_document = Document.objects.get(
        tenant=repository.tenant,
        organization=organization,
        entity__display_name=PUBLICATION_DOCUMENT_TITLE,
    )
    attachment = legacy_document.attachments.get(original_filename=PUBLICATION_ATTACHMENT_NAME)
    publication_source = read_authored_content(repository=repository, content_id=legacy_document.id)
    assert publication_source.markdown == (
        f"# {PUBLICATION_DOCUMENT_TITLE}\n\n[Guide](tekdocs://attachment/{attachment.entity_id})\n"
    )
    assert directory_entry["repository_id"] == str(repository.id)
    assert directory_entry["workspace_id"] == str(repository.workspace_id)
    _assert_absent(repository=repository, content_id=DOCUMENT_ID)
    return attachment


owner = User.objects.get(email=OWNER_EMAIL)
tenant = owner.tenant_memberships.get(organization__isnull=True).tenant
mode = os.environ.get("TEKDOCS_RECOVERY_CONTENT_MODE")
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.tenant(tenant),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )
    organization = Organization.objects.get(tenant=tenant, entity__display_name=ORGANIZATION_NAME)
    if mode == "create":
        create_fixture(owner)
        msp_snapshot_digest = _source_snapshot_digest(_repository(owner))
    elif mode == "verify":
        directory_entry = verify_fixture(owner)
        msp_snapshot_digest = _source_snapshot_digest(_repository(owner))
    elif mode in {"break_managed_file", "repair_managed_file"}:
        pass
    else:
        raise RuntimeError("Unsupported TEKDOCS_RECOVERY_CONTENT_MODE")
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.organization(tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )
    if mode == "create":
        attachment = create_organization_fixture(owner, organization)
        organization_repository = _organization_repository(owner, organization)
        organization_snapshot_digest = _source_snapshot_digest(organization_repository)
        organization_editable_digest = _editable_bundle_digest(organization_repository, attachment)
        print(f"MSP_SOURCE_SHA256={msp_snapshot_digest}")
        print(f"ORGANIZATION_SOURCE_SHA256={organization_snapshot_digest}")
        print(f"ORGANIZATION_EDITABLE_SHA256={organization_editable_digest}")
        print("MSP and client repository Markdown and managed-file recovery fixtures created")
    else:
        legacy_document = Document.objects.get(
            tenant=tenant, organization=organization, entity__display_name=PUBLICATION_DOCUMENT_TITLE
        )
        attachment = legacy_document.attachments.get(original_filename=PUBLICATION_ATTACHMENT_NAME)
        if mode == "break_managed_file":
            attachment.file.storage.delete(attachment.file.name)
            assert not attachment.file.storage.exists(attachment.file.name)
            print("Disposable managed-file custody removed for recovery fault injection")
        elif mode == "repair_managed_file":
            assert not attachment.file.storage.exists(attachment.file.name)
            assert attachment.file.storage.save(
                attachment.file.name, ContentFile(PUBLICATION_ATTACHMENT_BYTES)
            ) == attachment.file.name
            assert copy_attachment_content(attachment) == PUBLICATION_ATTACHMENT_BYTES
            print("Disposable managed-file custody repaired")
        else:
            attachment = verify_organization_fixture(owner, organization, directory_entry)
            organization_repository = _organization_repository(owner, organization)
            organization_snapshot_digest = _source_snapshot_digest(organization_repository)
            organization_editable_digest = _editable_bundle_digest(organization_repository, attachment)
            assert msp_snapshot_digest == os.environ["TEKDOCS_RECOVERY_MSP_SOURCE_SHA256"]
            assert organization_snapshot_digest == os.environ["TEKDOCS_RECOVERY_ORG_SOURCE_SHA256"]
            assert organization_editable_digest == os.environ["TEKDOCS_RECOVERY_ORG_EDITABLE_SHA256"]
            print("MSP directory, client isolation, Markdown, Git history, and managed-file bundle restored")
