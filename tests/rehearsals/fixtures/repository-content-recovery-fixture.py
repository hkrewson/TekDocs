"""Retain and verify real Markdown, composition, and Git history across recovery."""

import hashlib
import os
import uuid

import yaml
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.accounts.models import User
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_read import document_detail
from apps.core.document_attachments import (
    append_repository_primary_document_file,
    copy_attachment_content,
    create_document_attachment,
    create_repository_document_attachment,
    replace_primary_document_file,
)
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import create_document, resolve_document, update_document
from apps.core.publications import publish_document, verify_retained_publication_custody
from apps.core.models import (
    ContentNode,
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    DocumentAuthority,
    DocumentAuthorityMode,
    Organization,
    WorkspaceKind,
    WorkspaceRepository,
)
from apps.core.repository_editable_bundle_validation import verify_repository_editable_bundle
from apps.core.repository_editable_bundles import export_repository_editable_bundle
from apps.core.repository_manifests import ORGANIZATION_DIRECTORY_PATH
from apps.core.repository_service import (
    RepositoryFileNotFoundError,
    RepositoryInputError,
    read_accepted_repository_file,
    read_repository_markdown_files_at_commit,
)
from apps.core.repository_source_exports import export_repository_sources
from apps.core.repository_source_git_validation import verify_repository_source_against_git
from apps.core.repository_source_validation import verify_repository_source_snapshot
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace

OWNER_EMAIL = "validation-recovery@example.invalid"
ORGANIZATION_NAME = "Validation Recovery Client"
FRAGMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.fragment")
DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.document")
ORGANIZATION_DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.organization.document")
NATIVE_PRIMARY_DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.native.primary.document")
INITIAL_FRAGMENT = "Confirm the device serial number.\n"
UPDATED_FRAGMENT = "Confirm the device serial number and enrollment status.\n"
DOCUMENT_MARKDOWN = "# Laptop setup\n\nFollow the retained prerequisite.\n"
ORGANIZATION_MARKDOWN = "# Client enrollment\n\nUse this client's device policy.\n"
PUBLICATION_DOCUMENT_TITLE = "Client setup guide"
PUBLICATION_ATTACHMENT_NAME = "recovery-guide.txt"
PUBLICATION_ATTACHMENT_BYTES = b"Client setup instructions retained for recovery.\n"
PUBLICATION_ATTACHMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.guide.attachment")
PUBLICATION_MARKDOWN = f"# {PUBLICATION_DOCUMENT_TITLE}\n\n[Guide](tekdocs://attachment/{PUBLICATION_ATTACHMENT_ID})\n"
NATIVE_ATTACHMENT_NAME = "client-enrollment.txt"
NATIVE_ATTACHMENT_BYTES = b"Client enrollment instructions retained for recovery.\n"
LEGACY_PRIMARY_V1_BYTES = b"Client setup primary file, original version.\n"
LEGACY_PRIMARY_V2_BYTES = b"Client setup primary file, revised version.\n"
NATIVE_PRIMARY_V1_BYTES = b"Native primary file, original version.\n"
NATIVE_PRIMARY_V2_BYTES = b"Native primary file, revised version.\n"
AUTHORITY_EDITED_MARKDOWN = (
    "# Git-authoritative recovery guide\n\n"
    "Retain the edited revision through rollback and recovery.\n"
)


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


def _editable_bundle_digest(repository, attachment, native_attachment, primary_versions, native_primary_versions):
    bundle = export_repository_editable_bundle(repository)
    manifest = verify_repository_editable_bundle(bundle.content)
    assert manifest["workspace_id"] == str(repository.workspace_id)
    assert manifest["accepted_commit"] == repository.accepted_commit.object_id
    descriptors = {descriptor["id"]: descriptor for descriptor in manifest["attachments"]}
    assert set(descriptors) == {str(attachment.entity_id), str(native_attachment.entity_id)}
    legacy_descriptor = descriptors[str(attachment.entity_id)]
    assert legacy_descriptor["owner"] == {"type": "legacy_document", "id": str(attachment.document_id)}
    assert legacy_descriptor["sha256"] == hashlib.sha256(PUBLICATION_ATTACHMENT_BYTES).hexdigest()
    native_descriptor = descriptors[str(native_attachment.entity_id)]
    assert native_descriptor["owner"] == {"type": "repository_document", "id": str(ORGANIZATION_DOCUMENT_ID)}
    assert native_descriptor["sha256"] == hashlib.sha256(NATIVE_ATTACHMENT_BYTES).hexdigest()
    assert copy_attachment_content(attachment) == PUBLICATION_ATTACHMENT_BYTES
    assert copy_attachment_content(native_attachment) == NATIVE_ATTACHMENT_BYTES
    primary_descriptors = manifest["primary_files"]
    assert len(primary_descriptors) == len(primary_versions) + len(native_primary_versions) == 4
    descriptors_by_id = {item["id"]: item for item in primary_descriptors}
    for versions, owner, expected_contents in (
        (primary_versions, {"type": "legacy_document", "id": str(attachment.document_id)},
         (LEGACY_PRIMARY_V1_BYTES, LEGACY_PRIMARY_V2_BYTES)),
        (native_primary_versions, {"type": "repository_document", "id": str(NATIVE_PRIMARY_DOCUMENT_ID)},
         (NATIVE_PRIMARY_V1_BYTES, NATIVE_PRIMARY_V2_BYTES)),
    ):
        for index, (record, expected_bytes) in enumerate(zip(versions, expected_contents, strict=True)):
            descriptor = descriptors_by_id.pop(str(record.entity_id))
            assert descriptor["owner"] == owner
            assert descriptor["version_number"] == index + 1
            assert descriptor["replaces_id"] == (str(versions[index - 1].entity_id) if index else None)
            assert descriptor["sha256"] == hashlib.sha256(expected_bytes).hexdigest()
            assert descriptor["size"] == len(expected_bytes)
            assert copy_attachment_content(record) == expected_bytes
    assert not descriptors_by_id
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
    native_attachment = create_repository_document_attachment(
        repository=repository,
        content_id=ORGANIZATION_DOCUMENT_ID,
        actor_id=owner.id,
        upload=SimpleUploadedFile(NATIVE_ATTACHMENT_NAME, NATIVE_ATTACHMENT_BYTES),
    )
    native_source = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=ORGANIZATION_DOCUMENT_ID,
        base_commit=document.accepted_commit,
        base_blob=document.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=f"{ORGANIZATION_MARKDOWN}\n[Enrollment](tekdocs://attachment/{native_attachment.entity_id})\n",
        metadata_patch={},
    )
    assert native_source.accepted_commit == native_source.indexed_commit
    native_primary_document = author_content(
        repository=repository,
        actor_id=owner.id,
        request_id=None,
        operation="create",
        content_id=NATIVE_PRIMARY_DOCUMENT_ID,
        base_commit=native_source.accepted_commit,
        base_blob=None,
        kind="document",
        path=None,
        title="Native primary recovery guide",
        markdown="# Native primary recovery guide\n\nRetained version history.\n",
        metadata_patch={},
    )
    assert native_primary_document.accepted_commit == native_primary_document.indexed_commit
    native_primary_v1 = append_repository_primary_document_file(
        repository=repository, content_id=NATIVE_PRIMARY_DOCUMENT_ID, actor_id=owner.id,
        upload=SimpleUploadedFile("native-primary-v1.txt", NATIVE_PRIMARY_V1_BYTES),
        expected_current_entity_id=None,
    )
    native_primary_v2 = append_repository_primary_document_file(
        repository=repository, content_id=NATIVE_PRIMARY_DOCUMENT_ID, actor_id=owner.id,
        upload=SimpleUploadedFile("native-primary-v2.txt", NATIVE_PRIMARY_V2_BYTES),
        expected_current_entity_id=native_primary_v1.entity_id,
    )
    legacy_document = create_document(
        tenant=repository.tenant,
        organization=organization,
        actor_id=owner.id,
        title=PUBLICATION_DOCUMENT_TITLE,
        markdown=PUBLICATION_MARKDOWN,
    )
    attachment = create_document_attachment(
        document=legacy_document,
        actor_id=owner.id,
        upload=SimpleUploadedFile(PUBLICATION_ATTACHMENT_NAME, PUBLICATION_ATTACHMENT_BYTES),
        entity_id=PUBLICATION_ATTACHMENT_ID,
    )
    primary_v1 = create_document_attachment(
        document=legacy_document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("client-setup-v1.txt", LEGACY_PRIMARY_V1_BYTES),
        purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
        version_number=1,
    )
    primary_v2 = replace_primary_document_file(
        document=legacy_document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("client-setup-v2.txt", LEGACY_PRIMARY_V2_BYTES),
    )
    preview = prepare_document_import(workspace=repository.workspace, document_id=legacy_document.id)
    publication_import = apply_document_import(
        workspace=repository.workspace,
        document_id=legacy_document.id,
        expected_base=preview.base_commit,
        plan_sha256=preview.plan_sha256,
        actor_id=owner.id,
    )
    assert publication_import.status == "imported" and publication_import.indexed
    authority_document = create_document(
        tenant=repository.tenant,
        organization=organization,
        actor_id=owner.id,
        title="Git-authoritative recovery guide",
        markdown="# Git-authoritative recovery guide\n\nRestore the canonical revision.\n",
    )
    authority_preview = prepare_document_import(workspace=repository.workspace, document_id=authority_document.id)
    authority_import = apply_document_import(
        workspace=repository.workspace,
        document_id=authority_document.id,
        expected_base=authority_preview.base_commit,
        plan_sha256=authority_preview.plan_sha256,
        actor_id=owner.id,
    )
    assert authority_import.status == "imported" and authority_import.indexed
    reader_workspace = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    assert transition_document_authority(
        workspace=repository.workspace,
        document_id=authority_document.id,
        actor_id=owner.id,
        target=DocumentAuthorityMode.REPOSITORY,
        reader_workspace=reader_workspace,
    ) == "transitioned"
    assert (
        DocumentAuthority.objects.get(workspace=repository.workspace, content_id=authority_document.id).authority
        == DocumentAuthorityMode.REPOSITORY
    )
    block = authority_document.placements.get(parent__isnull=True, position=0).block
    original_revision = block.current_revision_id
    source = read_authored_content(repository=repository, content_id=block.id)
    edited = author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=block.id, base_commit=source.accepted_commit, base_blob=source.source_blob,
        kind=None, path=None, title=None, markdown=AUTHORITY_EDITED_MARKDOWN, metadata_patch={},
    )
    root = read_authored_content(repository=repository, content_id=authority_document.id)
    try:
        author_content(
            repository=repository, actor_id=owner.id, request_id=None, operation="update",
            content_id=authority_document.id, base_commit=root.accepted_commit, base_blob=root.source_blob,
            kind=None, path=None, title="Would break rollback", markdown=None, metadata_patch={},
        )
    except RepositoryInputError as exc:
        assert "reversible" in str(exc)
    else:
        raise AssertionError("Migrated root metadata edit was accepted")
    repository.refresh_from_db()
    assert repository.accepted_commit.object_id == edited.accepted_commit
    assert transition_document_authority(
        workspace=repository.workspace, document_id=authority_document.id, actor_id=owner.id,
        target=DocumentAuthorityMode.LEGACY, reader_workspace=reader_workspace,
    ) == "transitioned"
    block.refresh_from_db()
    assert block.current_revision.parent_id == original_revision
    assert resolve_document(authority_document).markdown == AUTHORITY_EDITED_MARKDOWN
    assert transition_document_authority(
        workspace=repository.workspace, document_id=authority_document.id, actor_id=owner.id,
        target=DocumentAuthorityMode.REPOSITORY, reader_workspace=reader_workspace,
    ) == "transitioned"
    # Retain both a legacy snapshot and its Git-authored successor across backup.
    published_guide = create_document(
        tenant=repository.tenant, organization=repository.workspace.organization, actor_id=owner.id,
        title="Published Git recovery guide", markdown="Retained legacy recovery instructions.\n",
    )
    legacy_snapshot = publish_document(
        workspace=reader_workspace, document=published_guide, actor_id=owner.id,
        reason="Recovery fixture legacy snapshot", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    update_document(
        document=published_guide, actor_id=owner.id, title="Published Git recovery guide",
        markdown="Pre-promotion recovery draft.\n",
        base_revision_id=published_guide.placements.get().block.current_revision_id,
    )
    plan = prepare_document_import(workspace=repository.workspace, document_id=published_guide.id)
    apply_document_import(
        workspace=repository.workspace, document_id=published_guide.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=owner.id,
    )
    transition_document_authority(
        workspace=repository.workspace, document_id=published_guide.id, actor_id=owner.id,
        target=DocumentAuthorityMode.REPOSITORY, reader_workspace=reader_workspace,
    )
    fragment = read_authored_content(repository=repository, content_id=published_guide.placements.get().block_id)
    author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None, markdown="Recovered Git publication body.\n", metadata_patch={},
    )
    retained = publish_internal_git_document(
        workspace=reader_workspace, document=published_guide, actor=owner, reason="Recovery fixture Git snapshot",
        supersedes_entity_id=legacy_snapshot.entity_id,
    )
    assert verify_internal_git_publication(retained)
    return attachment, native_attachment, (primary_v1, primary_v2), (native_primary_v1, native_primary_v2)


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
    native_attachment = DocumentAttachment.objects.get(
        tenant=repository.tenant,
        organization=organization,
        document__isnull=True,
        owner_workspace=repository.workspace,
        owner_content_id=ORGANIZATION_DOCUMENT_ID,
        original_filename=NATIVE_ATTACHMENT_NAME,
    )
    expected_markdown = f"{ORGANIZATION_MARKDOWN}\n[Enrollment](tekdocs://attachment/{native_attachment.entity_id})\n"
    assert document.markdown == expected_markdown
    assert document.accepted_commit == document.indexed_commit
    assert ContentNode.objects.get(repository=repository, content_id=ORGANIZATION_DOCUMENT_ID).markdown == (
        expected_markdown
    )
    native_primary_document = read_authored_content(repository=repository, content_id=NATIVE_PRIMARY_DOCUMENT_ID)
    assert native_primary_document.markdown == "# Native primary recovery guide\n\nRetained version history.\n"
    assert not Document.objects.filter(id=NATIVE_PRIMARY_DOCUMENT_ID).exists()
    legacy_document = Document.objects.get(
        tenant=repository.tenant,
        organization=organization,
        entity__display_name=PUBLICATION_DOCUMENT_TITLE,
    )
    authority_document = Document.objects.get(
        tenant=repository.tenant,
        organization=organization,
        entity__display_name="Git-authoritative recovery guide",
    )
    assert (
        DocumentAuthority.objects.get(workspace=repository.workspace, content_id=authority_document.id).authority
        == DocumentAuthorityMode.REPOSITORY
    )
    reader_workspace = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    authority_read = document_detail(
        workspace=reader_workspace, content_id=authority_document.id, audience="msp_internal"
    )
    assert authority_read["markdown"] == AUTHORITY_EDITED_MARKDOWN
    # Verify reverse projection from the recovered repository, then restore the
    # fixture's authority state without rewriting or resetting its Git history.
    assert transition_document_authority(
        workspace=repository.workspace, document_id=authority_document.id, actor_id=owner.id,
        target=DocumentAuthorityMode.LEGACY, reader_workspace=reader_workspace,
    ) == "transitioned"
    assert resolve_document(authority_document).markdown == AUTHORITY_EDITED_MARKDOWN
    assert transition_document_authority(
        workspace=repository.workspace, document_id=authority_document.id, actor_id=owner.id,
        target=DocumentAuthorityMode.REPOSITORY, reader_workspace=reader_workspace,
    ) == "transitioned"
    published_guide = Document.objects.get(
        tenant=repository.tenant, organization=organization, entity__display_name="Published Git recovery guide",
    )
    legacy_snapshot, retained = published_guide.publications.order_by("published_at", "id")
    assert legacy_snapshot.canonical_markdown == "Retained legacy recovery instructions.\n"
    assert retained.supersedes_id == legacy_snapshot.id
    assert legacy_snapshot.lifecycle_state == "superseded"
    assert verify_retained_publication_custody(legacy_snapshot)
    assert retained.canonical_markdown == "Recovered Git publication body.\n"
    assert verify_internal_git_publication(retained)
    history = assess_retained_publications(workspace=repository.workspace, document=published_guide)
    assert history["state"] == "verified"
    assert history["evidence_sha256"] == os.environ["TEKDOCS_RECOVERY_HISTORY_SHA256"]
    retained_digest = retained.content_digest
    state = DocumentAuthority.objects.get(workspace=repository.workspace, content_id=published_guide.id)
    if state.authority == DocumentAuthorityMode.LEGACY:
        assert transition_document_authority(
            workspace=repository.workspace, document_id=published_guide.id, actor_id=owner.id,
            target=DocumentAuthorityMode.REPOSITORY, reader_workspace=reader_workspace,
        ) == "transitioned"
    assert transition_document_authority(
        workspace=repository.workspace, document_id=published_guide.id, actor_id=owner.id,
        target=DocumentAuthorityMode.LEGACY, reader_workspace=reader_workspace,
    ) == "transitioned"
    published_guide.refresh_from_db()
    assert resolve_document(published_guide).markdown == retained.canonical_markdown
    retained.refresh_from_db()
    assert retained.content_digest == retained_digest
    assert verify_internal_git_publication(retained)
    assert assess_retained_publications(workspace=repository.workspace, document=published_guide) == history
    attachment = legacy_document.attachments.get(original_filename=PUBLICATION_ATTACHMENT_NAME)
    publication_source = read_authored_content(repository=repository, content_id=legacy_document.id)
    assert publication_source.markdown == ""
    assert ContentNode.objects.get(repository=repository, content_id=legacy_document.id).composition_variants[
        "all"
    ]["markdown"] == PUBLICATION_MARKDOWN
    assert directory_entry["repository_id"] == str(repository.id)
    assert directory_entry["workspace_id"] == str(repository.workspace_id)
    _assert_absent(repository=repository, content_id=DOCUMENT_ID)
    primary_versions = tuple(
        legacy_document.attachments.filter(
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
        ).order_by("version_number")
    )
    assert len(primary_versions) == 2
    assert primary_versions[0].version_number == 1
    assert primary_versions[0].replaces_id is None
    assert primary_versions[1].version_number == 2
    assert primary_versions[1].replaces_id == primary_versions[0].id
    native_primary_versions = tuple(DocumentAttachment.objects.filter(
        tenant=repository.tenant, organization=organization, document__isnull=True,
        owner_workspace=repository.workspace, owner_content_id=NATIVE_PRIMARY_DOCUMENT_ID,
        purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
    ).order_by("version_number"))
    assert len(native_primary_versions) == 2
    return attachment, native_attachment, primary_versions, native_primary_versions


owner = User.objects.get(email=OWNER_EMAIL)
tenant = owner.tenant_memberships.get(organization__isnull=True).tenant
mode = os.environ.get("TEKDOCS_RECOVERY_CONTENT_MODE")
if mode == "create" and not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
    TOTP.activate(owner, generate_totp_secret())
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
    elif mode in {
        "break_managed_file",
        "repair_managed_file",
        "break_historical_primary",
        "repair_historical_primary",
    }:
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
        attachment, native_attachment, primary_versions, native_primary_versions = create_organization_fixture(
            owner, organization
        )
        organization_repository = _organization_repository(owner, organization)
        organization_snapshot_digest = _source_snapshot_digest(organization_repository)
        organization_editable_digest = _editable_bundle_digest(
            organization_repository, attachment, native_attachment, primary_versions, native_primary_versions
        )
        print(f"MSP_SOURCE_SHA256={msp_snapshot_digest}")
        print(f"ORGANIZATION_SOURCE_SHA256={organization_snapshot_digest}")
        print(f"ORGANIZATION_EDITABLE_SHA256={organization_editable_digest}")
        published_guide = Document.objects.get(
            tenant=tenant, organization=organization, entity__display_name="Published Git recovery guide",
        )
        history = assess_retained_publications(workspace=organization_repository.workspace, document=published_guide)
        assert history["state"] == "verified"
        print(f"PUBLICATION_HISTORY_SHA256={history['evidence_sha256']}")
        print("MSP and client repository Markdown and managed-file recovery fixtures created")
    else:
        legacy_document = Document.objects.get(
            tenant=tenant, organization=organization, entity__display_name=PUBLICATION_DOCUMENT_TITLE
        )
        attachment = legacy_document.attachments.get(original_filename=PUBLICATION_ATTACHMENT_NAME)
        historical_primary = legacy_document.attachments.get(
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
            version_number=1,
        )
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
        elif mode == "break_historical_primary":
            historical_primary.file.storage.delete(historical_primary.file.name)
            assert not historical_primary.file.storage.exists(historical_primary.file.name)
            print("Disposable historical primary-file custody removed for recovery fault injection")
        elif mode == "repair_historical_primary":
            assert not historical_primary.file.storage.exists(historical_primary.file.name)
            assert historical_primary.file.storage.save(
                historical_primary.file.name, ContentFile(LEGACY_PRIMARY_V1_BYTES)
            ) == historical_primary.file.name
            assert copy_attachment_content(historical_primary) == LEGACY_PRIMARY_V1_BYTES
            print("Disposable historical primary-file custody repaired")
        else:
            attachment, native_attachment, primary_versions, native_primary_versions = verify_organization_fixture(
                owner, organization, directory_entry
            )
            organization_repository = _organization_repository(owner, organization)
            organization_snapshot_digest = _source_snapshot_digest(organization_repository)
            organization_editable_digest = _editable_bundle_digest(
                organization_repository, attachment, native_attachment, primary_versions, native_primary_versions
            )
            assert msp_snapshot_digest == os.environ["TEKDOCS_RECOVERY_MSP_SOURCE_SHA256"]
            assert organization_snapshot_digest == os.environ["TEKDOCS_RECOVERY_ORG_SOURCE_SHA256"]
            assert organization_editable_digest == os.environ["TEKDOCS_RECOVERY_ORG_EDITABLE_SHA256"]
            print(
                "MSP directory, client isolation, Markdown, Git history, managed-file bundle, and "
                "Git-authoritative document read restored"
            )
