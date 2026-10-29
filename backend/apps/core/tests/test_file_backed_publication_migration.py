"""File custody through the supported operator and publication boundaries."""

from copy import deepcopy

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.publications import publish_document, read_publication_artifact, verify_retained_publication_custody
from apps.core.workspaces import resolve_msp_workspace

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def file_history(published_context):
    from apps.core.documents import update_document
    from apps.core.rendering import render_pdf

    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    first = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("primary-v1.pdf", render_pdf("Primary document version one.")),
        purpose="primary_file",
        version_number=1,
    )
    second = replace_primary_document_file(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("primary-v2.pdf", render_pdf("Primary document version two.")),
    )
    attachment = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("linked-file.txt", b"Independently retained file bytes.\n"),
    )
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title=document.entity.display_name,
        markdown=f"Historical file instructions.\n\n[Checklist](tekdocs://attachment/{attachment.entity_id})\n",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    historical = publish_document(
        workspace=resolve_msp_workspace(installation.owner),
        document=document,
        actor_id=installation.owner.id,
        reason="Retain linked file before migration",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    return published_context, (first, second, attachment), historical


def test_restricted_role_publishes_and_downloads_all_retained_files(file_history, django_runtime_role):
    context, files, historical = file_history
    installation, workspace, document, original = context
    from apps.core.document_attachments import copy_attachment_content
    from apps.core.document_migration_publications import assess_retained_publications

    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"
    assert historical.artifacts.count() == 2
    original_pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    signed = (deepcopy(historical.manifest), historical.signature, historical.content_digest)
    expected = {str(item.entity_id): copy_attachment_content(item) for item in files}
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=resolve_msp_workspace(installation.owner),
    )
    browser = Client()
    browser.force_login(installation.owner)
    with django_runtime_role():
        response = browser.post(
            reverse("msp-document-publication-list-create", kwargs={"document_entity_id": document.entity_id}),
            {
                "reason": "Restricted role file snapshot",
                "audience": "msp_internal",
                "retention": "permanent",
            },
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
        result = response.json()
        assert result["manifest"]["format"] == "tekdocs-static-publication/v6"
        assert result["verification"]["valid"]
        retained = [item for item in result["artifacts"] if item["kind"] == "attachment"]
        assert len(retained) == 3
        for artifact in retained:
            download = browser.get(
                reverse(
                    "msp-document-publication-artifact-download",
                    kwargs={
                        "document_entity_id": document.entity_id,
                        "publication_entity_id": result["id"],
                        "artifact_entity_id": artifact["id"],
                    },
                )
            )
            assert download.status_code == 200
            assert download.content == expected[artifact["source_attachment_id"]]
    historical.refresh_from_db()
    assert (historical.manifest, historical.signature, historical.content_digest) == signed
    assert read_publication_artifact(original.artifacts.get(kind="pdf")) == original_pdf


def test_file_backed_signed_document_migrates_and_rolls_back_with_all_versions(published_context):
    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    reader = resolve_msp_workspace(installation.owner)
    browser = Client()
    browser.force_login(installation.owner)
    first = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("guide-v1.txt", b"Original primary file.\n"),
        purpose="primary_file",
        version_number=1,
    )
    second = replace_primary_document_file(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("guide-v2.txt", b"Revised primary file.\n"),
    )
    attachment = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("checklist.txt", b"Retained checklist.\n"),
    )
    snapshots = [(item.pk, item.file.name, item.checksum, item.document_id) for item in (first, second, attachment)]
    signed = (deepcopy(original.manifest), original.signature, original.content_digest)
    pdf = read_publication_artifact(original.artifacts.get())
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert (
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        ).status
        == "imported"
    )
    for target in ("repository", "legacy", "repository"):
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target=target,
                reader_workspace=reader,
            )
            == "transitioned"
        )
        for item, content in (
            (first, b"Original primary file.\n"),
            (second, b"Revised primary file.\n"),
            (attachment, b"Retained checklist.\n"),
        ):
            route = (
                "msp-content-document-attachment-download"
                if target == "repository"
                else "msp-document-attachment-download"
            )
            kwargs = (
                {"content_id": document.id} if target == "repository" else {"document_entity_id": document.entity_id}
            )
            response = browser.get(reverse(route, kwargs={**kwargs, "attachment_entity_id": item.entity_id}))
            assert response.status_code == 200
            assert b"".join(response.streaming_content) == content
    newer = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain migrated file versions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    assert newer.manifest["format"] == "tekdocs-static-publication/v6"
    expected_files = {
        first.entity_id: b"Original primary file.\n",
        second.entity_id: b"Revised primary file.\n",
        attachment.entity_id: b"Retained checklist.\n",
    }
    assert {
        item.source_attachment.entity_id: read_publication_artifact(item)
        for item in newer.artifacts.select_related("source_attachment")
        if item.kind == "attachment"
    } == expected_files
    assert verify_retained_publication_custody(newer)
    for target in ("legacy", "repository"):
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target=target,
                reader_workspace=reader,
            )
            == "transitioned"
        )
    for item, expected in zip((first, second, attachment), snapshots, strict=True):
        item.refresh_from_db()
        assert (item.pk, item.file.name, item.checksum, item.document_id) == expected
    original.refresh_from_db()
    assert (original.manifest, original.signature, original.content_digest) == signed
    assert read_publication_artifact(original.artifacts.get()) == pdf
    assert verify_retained_publication_custody(original)


def test_file_created_after_promotion_is_available_after_rollback(published_context):
    from apps.core.document_attachments import create_repository_document_attachment

    installation, workspace, document, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    created = create_repository_document_attachment(
        repository=workspace.repository,
        content_id=document.id,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("new-checklist.txt", b"Checklist added in Git authority.\n"),
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="legacy",
        reader_workspace=reader,
    )
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(
        reverse(
            "msp-document-attachment-download",
            kwargs={
                "document_entity_id": document.entity_id,
                "attachment_entity_id": created.entity_id,
            },
        )
    )
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"Checklist added in Git authority.\n"


def test_database_rejects_file_snapshot_with_omitted_attachment_projection(file_history):
    import uuid

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity

    context, _files, _historical = file_history
    installation, workspace, document, _original = context
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Intact source",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        entity_type="document_publication",
        display_name="Rejected snapshot",
        visibility="msp_private",
    )
    values = {
        f.attname: getattr(publication, f.attname)
        for f in DocumentPublication._meta.concrete_fields
        if f.name not in {"id", "entity", "manifest"}
    }
    publication_id = uuid.uuid4()
    manifest = deepcopy(publication.manifest)
    manifest.update(publication_id=str(publication_id), publication_entity_id=str(entity.id), attachments=[])
    with pytest.raises(DatabaseError, match="internal Git publication files are invalid"), transaction.atomic():
        DocumentPublication.objects.create(id=publication_id, entity=entity, manifest=manifest, **values)
        raise AssertionError("Invalid file projection accepted before deferred artifact checks")


def test_primary_file_without_notes_can_migrate_and_publish(file_history):
    from apps.core.document_git_publications import preflight_internal_git_document
    from apps.core.documents import update_document

    context, _files, _historical = file_history
    installation, workspace, document, _original = context
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title=document.entity.display_name,
        markdown="",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    reader = resolve_msp_workspace(installation.owner)
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    assert preflight_internal_git_document(document=document, audience="msp_internal")["valid"]
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain primary file without notes",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert publication.canonical_markdown == ""
    assert publication.artifacts.filter(kind="attachment").count() == 3
    assert verify_retained_publication_custody(publication)
    assert read_publication_artifact(publication.artifacts.get(kind="pdf")).startswith(b"%PDF-")


@pytest.mark.parametrize("damage", ["missing_primary", "changed_primary", "missing_attachment", "changed_attachment"])
def test_bad_live_file_custody_refuses_migration_without_touching_signed_history(file_history, damage):
    from django.core.files.base import ContentFile

    from apps.core.document_attachments import copy_attachment_content
    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.models import DocumentAuthority

    context, files, historical = file_history
    _installation, workspace, document, original = context
    record = files[2] if damage.endswith("attachment") else files[0]
    content = copy_attachment_content(record)
    pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    signed = deepcopy(historical.manifest), historical.signature
    repository = workspace.repository
    repository.refresh_from_db()
    commit = repository.accepted_commit_id
    try:
        if damage.startswith("changed"):
            with record.file.storage.open(record.file.name, "wb") as stream:
                stream.write(b"Altered historical bytes")
        else:
            record.file.storage.delete(record.file.name)
        with pytest.raises(DocumentMigrationBlocked):
            prepare_document_import(workspace=workspace, document_id=document.id)
        repository.refresh_from_db()
        assert repository.accepted_commit_id == commit
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"
        historical.refresh_from_db()
        assert (historical.manifest, historical.signature) == signed
        assert read_publication_artifact(original.artifacts.get(kind="pdf")) == pdf
    finally:
        if damage.startswith("changed"):
            with record.file.storage.open(record.file.name, "wb") as stream:
                stream.write(content)
        else:
            assert record.file.storage.save(record.file.name, ContentFile(content)) == record.file.name


def test_new_primary_version_invalidates_an_existing_import_plan(file_history):
    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.models import DocumentAuthority

    context, _files, historical = file_history
    installation, workspace, document, _original = context
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    replace_primary_document_file(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("third.txt", b"New primary version after preview.\n"),
    )
    with pytest.raises(DocumentMigrationBlocked):
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        )
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"
    assert verify_retained_publication_custody(historical)


@pytest.mark.parametrize("actor_kind", ["anonymous", "read_only", "missing_mfa", "foreign_tenant", "wrong_client"])
def test_file_snapshot_creation_preserves_existing_permission_boundaries(file_history, actor_kind):
    import uuid

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.models import Tenant
    from apps.core.organizations import create_organization

    context, _files, _historical = file_history
    installation, workspace, document, _original = context
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    browser = Client()
    kwargs = {"document_entity_id": document.entity_id}
    route = "msp-document-publication-list-create"
    if actor_kind == "wrong_client":
        other = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Wrong workspace",
            legal_name="",
            website="",
            classifications=[],
        )
        route = "organization-document-publication-list-create"
        kwargs["organization_entity_id"] = other.entity_id
        browser.force_login(installation.owner)
    elif actor_kind == "missing_mfa":
        installation.owner.authenticator_set.all().delete()
        browser.force_login(installation.owner)
    elif actor_kind != "anonymous":
        actor = User.objects.create_user(
            email=f"file-reader-{uuid.uuid4()}@example.invalid", display_name="File reader"
        )
        tenant = (
            Tenant.objects.create(name="Foreign file workspace")
            if actor_kind == "foreign_tenant"
            else installation.tenant
        )
        TenantMembership.objects.create(tenant=tenant, user=actor, role=BuiltInRole.READ_ONLY)
        browser.force_login(actor)
    before = document.publications.count()
    response = browser.post(
        reverse(route, kwargs=kwargs),
        {
            "reason": "Denied file snapshot",
            "audience": "msp_internal",
            "retention": "permanent",
        },
        content_type="application/json",
    )
    assert response.status_code in {403, 404}
    assert document.publications.count() == before


def test_migration_does_not_promote_more_files_than_it_can_retain(file_history):
    from apps.core.document_migration_import import DocumentMigrationBlocked

    context, _files, _historical = file_history
    installation, workspace, document, _original = context
    for index in range(48):
        create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile(f"checklist-{index}.txt", b"Synthetic file.\n"),
        )
    assert document.attachments.count() == 51
    with pytest.raises(DocumentMigrationBlocked):
        prepare_document_import(workspace=workspace, document_id=document.id)
    assert document.attachments.count() == 51


def test_file_growth_cannot_strand_a_promoted_document_without_rollback(file_history):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_attachments import copy_attachment_content, create_repository_document_attachment
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
    from apps.core.documents import resolve_document

    context, files, historical = file_history
    installation, workspace, document, _original = context
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    expected = {str(record.entity_id): copy_attachment_content(record) for record in files}
    repository = workspace.repository
    fragment = read_authored_content(repository=repository, content_id=document.placements.get().block_id)
    author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Edited file-backed rollback instructions.\n",
        metadata_patch={},
    )
    for index in range(48):
        record = create_repository_document_attachment(
            repository=repository,
            content_id=document.id,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile(f"added-{index}.txt", b"File added after promotion.\n"),
        )
        expected[str(record.entity_id)] = b"File added after promotion.\n"
    assert document.attachments.count() == 51
    assert (
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="legacy",
            reader_workspace=reader,
        )
        == "transitioned"
    )
    assert resolve_document(document).markdown == "Edited file-backed rollback instructions.\n"
    browser = Client()
    browser.force_login(installation.owner)
    for entity_id, content in expected.items():
        response = browser.get(
            reverse(
                "msp-document-attachment-download",
                kwargs={
                    "document_entity_id": document.entity_id,
                    "attachment_entity_id": entity_id,
                },
            )
        )
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == content
    assert verify_retained_publication_custody(historical)
    with pytest.raises(DocumentAuthorityHandoffError, match="managed_file_retention_limit"):
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
        )
    assert document.attachments.count() == 51


@pytest.mark.parametrize("link_kind", ["primary", "missing", "foreign"])
def test_git_file_links_preserve_the_reversible_owner_boundary(file_history, link_kind):
    import uuid

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.documents import create_document, resolve_document
    from apps.core.repository_service import RepositoryInputError

    context, files, _historical = file_history
    installation, workspace, document, _original = context
    reader = resolve_msp_workspace(installation.owner)
    target = files[0].entity_id
    if link_kind == "missing":
        target = uuid.uuid4()
    elif link_kind == "foreign":
        other = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Sibling file owner",
            markdown="Other file owner.\n",
        )
        target = create_document_attachment(
            document=other,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("sibling.txt", b"Other document's private bytes.\n"),
        ).entity_id
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    repository = workspace.repository
    fragment = read_authored_content(repository=repository, content_id=document.placements.get().block_id)
    markdown = f"[Primary document](tekdocs://attachment/{target})\n"

    def write():
        return author_content(
            repository=repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="update",
            content_id=fragment.content_id,
            base_commit=fragment.accepted_commit,
            base_blob=fragment.source_blob,
            kind=None,
            path=None,
            title=None,
            markdown=markdown,
            metadata_patch={},
        )

    if link_kind != "primary":
        with pytest.raises(RepositoryInputError):
            write()
        repository.refresh_from_db()
        assert repository.accepted_commit.object_id == fragment.accepted_commit
    else:
        write()
        publication = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Retain primary link",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert verify_retained_publication_custody(publication)
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="legacy",
                reader_workspace=reader,
            )
            == "transitioned"
        )
        assert resolve_document(document).markdown == markdown


def test_file_publication_guard_reverse_and_reapply_preserves_custody(file_history):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.models import DocumentPublication

    context, _files, historical = file_history
    installation, workspace, document, original = context
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain every version across the guard upgrade cycle",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    snapshots = (original, historical, publication)
    fingerprints = {item.pk: (deepcopy(item.manifest), item.signature) for item in snapshots}
    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0196_internal_git_publication")])
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication()'::regprocedure)")
            assert "tekdocs-static-publication/v6" not in cursor.fetchone()[0]
        for item in snapshots:
            assert verify_retained_publication_custody(item)
    finally:
        MigrationExecutor(connection).migrate(head)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication()'::regprocedure)")
        assert "tekdocs-static-publication/v6" in cursor.fetchone()[0]
    for item in snapshots:
        retained = DocumentPublication.objects.get(pk=item.pk)
        assert (retained.manifest, retained.signature) == fingerprints[item.pk]
        assert verify_retained_publication_custody(retained)


@pytest.mark.parametrize("write_before_failure", [False, True])
def test_partial_file_snapshot_storage_failure_leaves_original_custody(
    file_history, monkeypatch, settings, write_before_failure,
):
    from pathlib import Path

    from apps.core.models import DocumentPublication, DocumentPublicationArtifact

    context, _files, historical = file_history
    installation, workspace, document, original = context
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    before_rows = set(DocumentPublication.objects.values_list("pk", flat=True))
    before_files = {
        path.relative_to(settings.MEDIA_ROOT) for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()
    }
    storage = DocumentPublicationArtifact._meta.get_field("file").storage
    save = storage.save
    attempts = []

    def fail_third_save(name, content, max_length=None):
        attempts.append(name)
        if len(attempts) == 3:
            if write_before_failure:
                save(name, content, max_length=max_length)
            raise OSError("Synthetic retained-storage failure")
        return save(name, content, max_length=max_length)

    monkeypatch.setattr(storage, "save", fail_third_save)
    with pytest.raises(OSError, match="Synthetic retained-storage failure"):
        publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Reject partial retained storage",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert len(attempts) == 3
    assert set(DocumentPublication.objects.values_list("pk", flat=True)) == before_rows
    assert {
        path.relative_to(settings.MEDIA_ROOT) for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()
    } == before_files
    assert verify_retained_publication_custody(original)
    assert verify_retained_publication_custody(historical)
