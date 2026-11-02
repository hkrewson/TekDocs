"""Ordinary shared MSP blocks migrate through the existing guarded boundaries."""

import pytest

from apps.core.content_index import index_repository_content
from apps.core.document_migration_import import prepare_document_import
from apps.core.documents import add_block_placement, create_document, create_document_block
from apps.core.models import Document, Workspace
from apps.core.organizations import create_organization
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.tests.repeated_block_fixture import copy_document

pytest_plugins = (
    "apps.core.tests.test_document_migration_publications",
    "apps.core.tests.test_template_enrollment_migration",
)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ordinary_library(published_context):
    installation, source_workspace, _unused, _publication = published_context
    owner = installation.owner
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    TOTP.activate(owner, generate_totp_secret())
    source = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=owner.id,
        title="Ordinary shared library",
        markdown="Unshared source introduction.\n",
        library_visible=True,
    )
    section = create_document_block(
        document=source,
        actor_id=owner.id,
        markdown="Approved shared instructions.\n",
        name="Shared section",
        kind="rich_text",
        parent_id=None,
        position=1,
        library_visible=True,
    )
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=owner.id,
        name="Library client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    consumer = create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=owner.id,
        title="Ordinary library consumer",
        markdown="Client introduction.\n",
    )
    add_block_placement(
        document=consumer,
        block=section.block,
        actor_id=owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=1,
    )
    workspace = Workspace.objects.get(organization=organization)
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    source = Document.objects.select_related("entity__workspace").get(pk=source.id)
    consumer = Document.objects.select_related("entity__workspace").get(pk=consumer.id)
    return owner, source_workspace, source, workspace, consumer


def test_ordinary_library_import_does_not_require_template_enrollment(ordinary_library):
    owner, _source_workspace, source, workspace, consumer = ordinary_library
    assert source.is_template is False
    assert not hasattr(consumer, "template_enrollment")
    copy_document(owner, source)
    prepared = prepare_document_import(workspace=workspace, document_id=consumer.id)
    assert prepared.export.library_references
    result = copy_document(owner, consumer)
    assert result.status == "imported" and result.indexed


@pytest.mark.parametrize("runtime", [False, True])
def test_ordinary_library_authority_round_trip(ordinary_library, django_runtime_role, runtime):
    from contextlib import nullcontext

    from django.db import transaction

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.documents import resolve_document
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.workspaces import resolve_organization_workspace

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    copy_document(owner, source)
    copy_document(owner, consumer)
    before = resolve_document(consumer).markdown
    arguments = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
    )
    reader = resolve_organization_workspace(owner, entity_id=consumer.organization.entity_id)
    with django_runtime_role() if runtime else nullcontext(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(consumer.tenant, consumer.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=owner.id,
        )
        for index, target in enumerate(("repository", "legacy", "repository")):
            plan = prepare_shared_library_handoff(**arguments, target=target)
            assert (
                transition_shared_library_authority(
                    **arguments,
                    target=target,
                    plan_sha256=plan.plan_sha256,
                )
                == "transitioned"
            )
            if index == 0:
                from apps.core.template_library_scope import editable_template_workspace_scope

                with editable_template_workspace_scope(source_workspace, owner.id):
                    fragment = read_authored_content(
                        repository=source_workspace.repository, content_id=source.placements.get(position=1).block_id
                    )
                    author_content(
                        repository=source_workspace.repository,
                        actor_id=owner.id,
                        request_id=None,
                        operation="update",
                        content_id=fragment.content_id,
                        base_commit=fragment.accepted_commit,
                        base_blob=fragment.source_blob,
                        kind=None,
                        path=None,
                        title=None,
                        markdown="Changed shared instructions.\n",
                        metadata_patch={},
                    )
                before = before.replace("Approved shared instructions.", "Changed shared instructions.")
            if target == "repository":
                assert (
                    document_detail(
                        workspace=reader,
                        content_id=consumer.id,
                        audience="msp_internal",
                    )["markdown"]
                    == before
                )
            else:
                assert resolve_document(consumer).markdown == before


@pytest.mark.parametrize("runtime", [False, True])
def test_ordinary_library_publication_has_truthful_offline_source_proof(
    ordinary_library,
    django_runtime_role,
    runtime,
):
    from contextlib import nullcontext

    from apps.core.publications import verify_retained_publication_custody
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.tests.repeated_block_fixture import publish

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    original = publish(owner, consumer, "Retain original ordinary library instructions")
    copy_document(owner, source)
    copy_document(owner, consumer)
    arguments = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**arguments)
    transition_shared_library_authority(**arguments, plan_sha256=plan.plan_sha256)
    with django_runtime_role() if runtime else nullcontext(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.organization(consumer.tenant, consumer.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=owner.id,
        )
        snapshot = publish(owner, consumer, "Freeze ordinary shared library custody")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    proof = snapshot.manifest["git_source"]["sources"][-1]
    assert proof["library_source"] == str(source.id)
    assert "template_revision" not in proof and "template_checksum" not in proof
    assert verify_retained_publication_custody(snapshot)
    assert verify_retained_publication_custody(original)


def test_distinct_pre_git_pins_preserve_body_only_semantics_and_all_file_versions(ordinary_library):
    import hashlib

    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import (
        copy_attachment_content,
        create_document_attachment,
        replace_primary_document_file,
    )
    from apps.core.documents import resolve_document, update_shared_block
    from apps.core.publications import read_publication_artifact, verify_retained_publication_custody
    from apps.core.rendering import render_pdf
    from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.tests.repeated_block_fixture import publish

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    section = source.placements.get(position=1)
    create_document_block(
        document=source,
        actor_id=owner.id,
        markdown="Source child is not reused.\n",
        name="Private source child",
        kind="rich_text",
        parent_id=section.id,
        position=0,
    )
    for position, body in enumerate(("Second shared edition.\n", "Current shared edition.\n"), 2):
        section.block.refresh_from_db()
        add_block_placement(
            document=consumer,
            block=section.block,
            actor_id=owner.id,
            resolution_mode="pinned",
            pinned_revision_id=section.block.current_revision_id,
            parent_id=None,
            position=position,
        )
        update_shared_block(
            placement=section, actor_id=owner.id, markdown=body, base_revision_id=section.block.current_revision_id
        )
    create_document_attachment(
        document=consumer,
        actor_id=owner.id,
        purpose="primary_file",
        version_number=1,
        upload=SimpleUploadedFile("library-primary-v1.pdf", render_pdf("First retained shared-library file.")),
    )
    replace_primary_document_file(
        document=consumer,
        actor_id=owner.id,
        upload=SimpleUploadedFile("library-primary-v2.pdf", render_pdf("Second retained shared-library file.")),
    )
    files = [(item.id, item.checksum, copy_attachment_content(item)) for item in consumer.attachments.order_by("id")]
    original = publish(owner, consumer, "Retain original cross-Workspace pins")
    original_pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    before = resolve_document(consumer).markdown
    assert "Source child is not reused." not in before
    copy_document(owner, source)
    history = prepare_shared_library_history(source=source, actor_id=owner.id)
    current = source_workspace.repository.accepted_commit.object_id
    retained = retain_shared_library_history(source=source, actor_id=owner.id, plan_sha256=history.plan_sha256)
    assert retained != current
    assert not prepare_shared_library_history(source=source, actor_id=owner.id).missing_paths
    copy_document(owner, consumer)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
    )
    for target in ("repository", "legacy", "repository"):
        plan = prepare_shared_library_handoff(**args, target=target)
        transition_shared_library_authority(**args, target=target, plan_sha256=plan.plan_sha256)
    snapshot = publish(owner, consumer, "Freeze ordinary cross-Workspace pins")
    assert snapshot.canonical_markdown == before
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    assert snapshot.manifest["library_format"] == "tekdocs-static-publication/v12"
    foreign = [item for item in snapshot.manifest["git_source"]["sources"] if "library_source" in item]
    assert len(foreign) == 3 and len({item["block_revision"] for item in foreign}) == 3
    assert all(item["path"].startswith("shared-snapshots/") for item in foreign if item["mode"] == "pinned")
    assert verify_retained_publication_custody(snapshot) and verify_retained_publication_custody(original)
    assert hashlib.sha256(read_publication_artifact(original.artifacts.get(kind="pdf"))).digest() == (
        hashlib.sha256(original_pdf).digest()
    )
    assert [
        (item.id, item.checksum, copy_attachment_content(item)) for item in consumer.attachments.order_by("id")
    ] == files


@pytest.fixture
def promoted_library(ordinary_library):
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    copy_document(owner, source)
    copy_document(owner, consumer)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    return ordinary_library


@pytest.mark.parametrize(
    "damage",
    [
        "library_source",
        "block_revision",
        "block_checksum",
        "library_workspace",
        "repository_id",
        "commit",
        "content_digest",
        "path",
        "audience",
        "ordinal_path",
        "old_format",
        "template_revision",
    ],
)
def test_database_rejects_forged_ordinary_library_certificate(promoted_library, damage):
    import uuid
    from copy import deepcopy

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity
    from apps.core.publications import verify_retained_publication_custody
    from apps.core.tests.repeated_block_fixture import publish

    owner, _source_workspace, _source, workspace, consumer = promoted_library
    snapshot = publish(owner, consumer, "Retain ordinary-library certificate before denial")
    candidate = DocumentPublication(
        **{field.attname: getattr(snapshot, field.attname) for field in DocumentPublication._meta.concrete_fields}
    )
    candidate.id = uuid.uuid4()
    candidate.manifest = deepcopy(snapshot.manifest)
    candidate.manifest["publication_id"] = str(candidate.id)
    proof = candidate.manifest["git_source"]["sources"][-1]
    if damage in {"library_source", "block_revision", "library_workspace", "repository_id", "template_revision"}:
        proof[damage] = str(uuid.uuid4())
    elif damage in {"block_checksum", "content_digest"}:
        proof[damage] = "a" * 64
    elif damage == "commit":
        proof[damage] = "a" * 40
    elif damage == "old_format":
        candidate.manifest["format"] = candidate.manifest["library_format"]
        candidate.manifest["git_source"]["format"] = "tekdocs.git-dependencies/v2"
    elif damage == "path":
        proof[damage] = "fragments/" + str(uuid.uuid4()) + ".md"
    elif damage == "audience":
        proof[damage] = "client_visible"
    else:
        proof[damage] = [3]
    assert not verify_retained_publication_custody(candidate)
    with pytest.raises(DatabaseError), transaction.atomic():
        candidate.entity = Entity.objects.create(
            tenant=consumer.tenant,
            organization=consumer.organization,
            workspace=workspace,
            entity_type="document_publication",
            display_name="Rejected ordinary-library certificate",
        )
        candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
        candidate.save(force_insert=True)
    assert verify_retained_publication_custody(snapshot)


def test_cross_workspace_upgrade_and_recovery_fixture_retains_complete_custody(published_context):
    from apps.core.tests.cross_workspace_fixture import (
        exercise_cross_workspace_fixture,
        recovery_fingerprint,
        seed_cross_workspace_fixture,
    )

    installation, _workspace, _document, _publication = published_context
    seed_cross_workspace_fixture(installation.owner)
    digest = exercise_cross_workspace_fixture(installation.owner)
    assert recovery_fingerprint(installation.owner) == digest


def test_cross_workspace_recovery_records_final_backup_state_after_later_writes(
    published_context, monkeypatch, capsys,
):
    import uuid

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.tests.cross_workspace_fixture import (
        documents,
        exercise_cross_workspace_fixture,
        run_cross_workspace_fixture_mode,
        seed_cross_workspace_fixture,
    )

    installation, workspace, _document, _publication = published_context
    seed_cross_workspace_fixture(installation.owner)
    early_digest = exercise_cross_workspace_fixture(installation.owner)
    workspace.repository.refresh_from_db()
    author_content(
        repository=workspace.repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="create",
        content_id=uuid.uuid4(),
        base_commit=workspace.repository.accepted_commit.object_id,
        base_blob=None,
        kind="document",
        path="docs/later-recovery-guide.md",
        title="Later recovery fixture",
        markdown="Unrelated retained recovery guide.\n",
        metadata_patch={},
    )
    # A later fixture advances the shared MSP repository before backup. The
    # original baseline must still fail: dropping commit checks would hide it.
    monkeypatch.setenv("TEKDOCS_CROSS_WORKSPACE_RECOVERY_SHA256", early_digest)
    with pytest.raises(AssertionError):
        run_cross_workspace_fixture_mode("recovery_verify")
    capsys.readouterr()
    run_cross_workspace_fixture_mode("recovery_record")
    output = capsys.readouterr().out.strip()
    prefix = "CROSS_WORKSPACE_RECOVERY_SHA256="
    assert output.startswith(prefix)
    backup_digest = output.removeprefix(prefix)
    assert len(backup_digest) == 64 and backup_digest != early_digest
    monkeypatch.setenv("TEKDOCS_CROSS_WORKSPACE_RECOVERY_SHA256", backup_digest)
    run_cross_workspace_fixture_mode("recovery_verify")
    assert "recovered exactly" in capsys.readouterr().out

    # A real source change after the backup baseline still invalidates custody.
    source, _consumer = documents(installation.owner)
    fragment = read_authored_content(
        repository=source.entity.workspace.repository,
        content_id=source.placements.get(position=1).block_id,
    )
    author_content(
        repository=source.entity.workspace.repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Unexpected source change after backup.\n",
        metadata_patch={},
    )
    with pytest.raises(AssertionError):
        run_cross_workspace_fixture_mode("recovery_verify")


@pytest.mark.parametrize("kind", ["template_without_enrollment", "client_listing"])
def test_other_valid_legacy_sharing_paths_migrate_without_changing_their_access(ordinary_library, kind):
    from apps.core.documents import add_document_placement, add_listing_reference, remove_document_placement
    from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.tests.repeated_block_fixture import publish

    owner, source_workspace, _original_source, workspace, consumer = ordinary_library
    remove_document_placement(placement=consumer.placements.get(position=1), actor_id=owner.id)
    source = create_document(
        tenant=consumer.tenant,
        organization=None,
        actor_id=owner.id,
        title="Alternate valid MSP source",
        markdown="Alternate shared source instructions.\n",
        is_template=kind == "template_without_enrollment",
        library_visible=kind == "template_without_enrollment",
    )
    if kind == "client_listing":
        add_listing_reference(document=source, organization=consumer.organization, actor_id=owner.id)
    add_document_placement(
        document=consumer,
        source_document=source,
        actor_id=owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=1,
    )
    copy_document(owner, source)
    assert prepare_document_import(workspace=workspace, document_id=consumer.id).export.library_references
    history = prepare_shared_library_history(source=source, actor_id=owner.id)
    retain_shared_library_history(source=source, actor_id=owner.id, plan_sha256=history.plan_sha256)
    copy_document(owner, consumer)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    snapshot = publish(owner, consumer, "Freeze retained alternate sharing boundary")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    assert snapshot.manifest["git_source"]["sources"][-1]["library_source"] == str(source.id)


def test_public_source_with_its_own_shared_dependency_remains_editable(ordinary_library):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.documents import add_document_placement
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.template_library_scope import editable_template_workspace_scope
    from apps.core.workspaces import resolve_organization_workspace

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    upstream = create_document(
        tenant=source.tenant,
        organization=None,
        actor_id=owner.id,
        title="MSP-local upstream source",
        markdown="Upstream source instructions.\n",
    )
    add_document_placement(
        document=source,
        source_document=upstream,
        actor_id=owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=2,
    )
    for document in (upstream, source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id, upstream.id),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    with editable_template_workspace_scope(source_workspace, owner.id):
        fragment = read_authored_content(
            repository=source_workspace.repository, content_id=source.placements.get(position=1).block_id
        )
        author_content(
            repository=source_workspace.repository,
            actor_id=owner.id,
            request_id=None,
            operation="update",
            content_id=fragment.content_id,
            base_commit=fragment.accepted_commit,
            base_blob=fragment.source_blob,
            kind=None,
            path=None,
            title=None,
            markdown="Changed nested library source.\n",
            metadata_patch={},
        )
    reader = resolve_organization_workspace(owner, entity_id=consumer.organization.entity_id)
    current = document_detail(workspace=reader, content_id=consumer.id, audience="msp_internal")["markdown"]
    assert "Changed nested library source." in current and "Upstream source instructions." not in current


def test_ordinary_source_cannot_accept_a_file_link_that_strands_hidden_live_clients(ordinary_library):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_attachments import create_document_attachment
    from apps.core.repository_service import RepositoryInputError
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.template_library_scope import editable_template_workspace_scope

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    file = create_document_attachment(
        document=source, actor_id=owner.id, upload=SimpleUploadedFile("source-owned.txt", b"Source file custody.\n")
    )
    for document in (source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    with editable_template_workspace_scope(source_workspace, owner.id):
        fragment = read_authored_content(
            repository=source_workspace.repository, content_id=source.placements.get(position=1).block_id
        )
        with pytest.raises(RepositoryInputError):
            author_content(
                repository=source_workspace.repository,
                actor_id=owner.id,
                request_id=None,
                operation="update",
                content_id=fragment.content_id,
                base_commit=fragment.accepted_commit,
                base_blob=fragment.source_blob,
                kind=None,
                path=None,
                title=None,
                markdown=f"[Source file](tekdocs://attachment/{file.entity_id})\n",
                metadata_patch={},
            )


def test_client_field_keys_combine_with_repeated_foreign_occurrence_proof(ordinary_library):
    from apps.core.documents import update_document
    from apps.core.models import DocumentKeyBinding
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.sites import create_site
    from apps.core.tests.repeated_block_fixture import publish

    owner, source_workspace, source, workspace, consumer = ordinary_library
    site = create_site(
        tenant=consumer.tenant,
        organization=consumer.organization,
        actor_id=owner.id,
        name="Current library client site",
        code="LIB",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="",
        timezone="UTC",
        phone="",
    )
    DocumentKeyBinding.objects.create(
        tenant=consumer.tenant,
        organization=consumer.organization,
        workspace=workspace,
        document=consumer,
        name="subject",
        target_entity=site.entity,
        created_by=owner,
    )
    update_document(
        document=consumer,
        actor_id=owner.id,
        title=consumer.entity.display_name,
        markdown="Visit <tekdocs://key/subject.name>.\n",
        base_revision_id=consumer.placements.get(position=0).block.current_revision_id,
    )
    add_block_placement(
        document=consumer,
        block=source.placements.get(position=1).block,
        actor_id=owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=2,
    )
    for document in (source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    snapshot = publish(owner, consumer, "Freeze client keys and repeated library occurrences")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    assert snapshot.manifest["library_format"] == "tekdocs-static-publication/v12"
    assert snapshot.manifest["occurrence_format"] == "tekdocs-static-publication/v9"
    assert "Visit Current library client site." in snapshot.canonical_markdown


def test_runtime_client_library_reads_are_exact_and_never_grant_foreign_writes(ordinary_library, django_runtime_role):
    from dataclasses import replace

    from django.db import transaction

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.content_composition import ContentCompositionError
    from apps.core.content_profile import ParsedInclude
    from apps.core.models import Block, DocumentAuthority, Tenant
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.template_library_content import template_library_loader

    owner, source_workspace, source, workspace, consumer = ordinary_library
    private = create_document(
        tenant=source.tenant,
        organization=None,
        actor_id=owner.id,
        title="Private MSP source",
        markdown="Private MSP text.\n",
    )
    private_section = create_document_block(
        document=source,
        actor_id=owner.id,
        markdown="Private source section.\n",
        kind="rich_text",
        name="Private",
        parent_id=None,
        position=2,
    )
    sibling = create_organization(
        tenant=source.tenant,
        actor_id=owner.id,
        name="Unrelated library client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    sibling_document = create_document(
        tenant=source.tenant,
        organization=sibling,
        actor_id=owner.id,
        title="Sibling client source",
        markdown="Sibling client text.\n",
        library_visible=True,
    )
    foreign_tenant = Tenant.objects.create(name="Foreign library tenant", slug="foreign-library-fixture")
    foreign_actor = User.objects.create_user(email="foreign-library-fixture@example.invalid", display_name="Foreign")
    TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_actor, role=BuiltInRole.ADMINISTRATOR)
    foreign = create_document(
        tenant=foreign_tenant,
        organization=None,
        actor_id=foreign_actor.id,
        title="Foreign shared source",
        markdown="Foreign text.\n",
        library_visible=True,
    )
    actor = User.objects.create_user(email="library-client-fixture@example.invalid", display_name="Client")
    TenantMembership.objects.create(
        tenant=source.tenant, organization=consumer.organization, user=actor, role=BuiltInRole.CLIENT_ADMINISTRATOR
    )
    for document in (source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    selected = ParsedInclude(
        target_content_id=source.placements.get(position=1).block_id,
        mode="live",
        audience="shared",
        pinned_object_id="",
        ordinal=1,
        library_workspace_id=source_workspace.id,
        library_source_id=source.id,
    )
    unreferenced_id = source.placements.get(position=0).block_id
    foreign_ids = [private.id, sibling_document.id, foreign.id]
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(source.tenant, consumer.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=actor.id,
        )
        loader = template_library_loader(workspace.repository)
        _commit, parsed = loader(consumer.id, selected)
        assert parsed.markdown == "Approved shared instructions.\n"
        assert not Document.objects.filter(id__in=foreign_ids).exists()
        assert not Block.objects.filter(pk=private_section.block_id).exists()
        assert not DocumentAuthority.objects.filter(content_id__in=foreign_ids).exists()
        assert Document.objects.filter(pk=source.id).update(category="denied") == 0
        assert Block.objects.filter(pk=selected.target_content_id).update(library_visible=False) == 0
        assert DocumentAuthority.objects.filter(content_id=source.id).update(authority="legacy") == 0
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM core_documentplacement WHERE tenant_id=%s AND document_id=%s",
                [
                    source.tenant_id,
                    source.id,
                ],
            )
            assert cursor.rowcount == 0
        for forged in (
            replace(selected, target_content_id=unreferenced_id),
            replace(selected, target_content_id=private_section.block_id),
            replace(selected, library_workspace_id=workspace.id),
            replace(selected, library_source_id=private.id),
            replace(selected, library_source_id=foreign.id),
            replace(selected, audience="client_visible"),
            replace(selected, ordinal=0),
            replace(selected, mode="pinned", pinned_object_id=_commit),
        ):
            with pytest.raises(ContentCompositionError):
                loader(consumer.id, forged)
        with pytest.raises(ContentCompositionError):
            loader(sibling_document.id, selected)


@pytest.mark.parametrize("actor_kind", ["read_only", "missing_mfa", "foreign_tenant", "unassigned_client"])
def test_denied_library_operators_cannot_probe_source_git(ordinary_library, actor_kind):
    from allauth.mfa.models import Authenticator
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.document_template_migration import TemplateMigrationError
    from apps.core.models import Tenant
    from apps.core.repository_storage import resolve_managed_repository_path
    from apps.core.shared_library_migration import prepare_shared_library_handoff

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    if actor_kind == "missing_mfa":
        actor = owner
        Authenticator.objects.filter(user=actor).delete()
    else:
        actor = User.objects.create_user(email=f"{actor_kind}-library@example.invalid", display_name="Denied operator")
        tenant = (
            Tenant.objects.create(name="Denied foreign library tenant", slug="denied-library-tenant")
            if actor_kind == "foreign_tenant"
            else source.tenant
        )
        TenantMembership.objects.create(
            tenant=tenant,
            user=actor,
            role=BuiltInRole.READ_ONLY if actor_kind == "read_only" else BuiltInRole.ADMINISTRATOR,
        )
        TOTP.activate(actor, generate_totp_secret())
    _root, path = resolve_managed_repository_path(source_workspace.repository)
    unavailable = path.with_name(path.name + ".unavailable")
    path.rename(unavailable)
    try:
        with pytest.raises(TemplateMigrationError, match="not_authorized|destination_unavailable"):
            prepare_shared_library_handoff(
                source_workspace=source_workspace,
                source_document_id=source.id,
                destination_document_ids=(consumer.id,),
                actor_id=actor.id,
                target="repository",
            )
    finally:
        unavailable.rename(path)


def test_late_library_transition_failure_rolls_back_every_authority(ordinary_library, monkeypatch):
    from apps.core import document_authority_handoff
    from apps.core.models import DocumentAuthority
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority

    owner, source_workspace, source, workspace, consumer = ordinary_library
    for document in (source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    before = list(
        DocumentAuthority.objects.filter(workspace_id__in=(source_workspace.id, workspace.id)).order_by("id").values()
    )
    transition = document_authority_handoff._transition_document_authority_locked
    calls = []

    def fail_late(**arguments):
        calls.append(arguments["document_id"])
        result = transition(**arguments)
        if len(calls) == 2:
            raise RuntimeError("Synthetic failure after both document transitions")
        return result

    monkeypatch.setattr(document_authority_handoff, "_transition_document_authority_locked", fail_late)
    with pytest.raises(RuntimeError, match="after both"):
        transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    assert len(calls) == 2
    assert (
        list(
            DocumentAuthority.objects.filter(workspace_id__in=(source_workspace.id, workspace.id))
            .order_by("id")
            .values()
        )
        == before
    )


def test_new_signed_history_invalidates_the_reviewed_library_plan(ordinary_library):
    from apps.core.document_template_migration import TemplateMigrationError
    from apps.core.models import DocumentAuthority
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
    from apps.core.tests.repeated_block_fixture import publish

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    for document in (source, consumer):
        copy_document(owner, document)
    args = dict(
        source_workspace=source_workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target="repository",
    )
    plan = prepare_shared_library_handoff(**args)
    snapshot = publish(owner, consumer, "Retain a publication after handoff review")
    with pytest.raises(TemplateMigrationError, match="preview_changed"):
        transition_shared_library_authority(**args, plan_sha256=plan.plan_sha256)
    assert snapshot.document_id == consumer.id
    assert not DocumentAuthority.objects.filter(
        content_id__in=(source.id, consumer.id), authority="repository"
    ).exists()


def test_missing_library_git_is_retryable_and_never_uses_the_database_copy(promoted_library):
    from django.test import Client
    from django.urls import reverse

    from apps.core.repository_storage import resolve_managed_repository_path

    owner, source_workspace, _source, _workspace, consumer = promoted_library
    browser = Client()
    browser.force_login(owner)
    url = reverse(
        "organization-content-document-detail",
        kwargs={
            "organization_entity_id": consumer.organization.entity_id,
            "content_id": consumer.id,
        },
    )
    assert browser.get(url).status_code == 200
    _root, path = resolve_managed_repository_path(source_workspace.repository)
    unavailable = path.with_name(path.name + ".unavailable")
    path.rename(unavailable)
    try:
        response = browser.get(url)
        assert response.status_code == 409
        assert b"Approved shared instructions." not in response.content
    finally:
        unavailable.rename(path)
    assert browser.get(url).status_code == 200


def test_library_loader_cannot_swap_the_distinct_pin_at_another_occurrence(published_context):
    from dataclasses import replace

    from apps.core.content_authoring import read_authored_content
    from apps.core.content_composition import ContentCompositionError
    from apps.core.content_profile import parse_content
    from apps.core.template_library_content import template_library_loader
    from apps.core.tests.cross_workspace_fixture import (
        documents,
        prepare_cross_workspace_fixture,
        seed_cross_workspace_fixture,
    )

    installation, _workspace, _document, _publication = published_context
    seed_cross_workspace_fixture(installation.owner)
    prepare_cross_workspace_fixture(installation.owner)
    _source, consumer = documents(installation.owner)
    authored = read_authored_content(repository=consumer.entity.workspace.repository, content_id=consumer.id)
    pins = [item for item in parse_content(authored.source.encode()).includes if item.mode == "pinned"]
    assert len(pins) == 2 and pins[0].library_revision_id != pins[1].library_revision_id
    with pytest.raises(ContentCompositionError):
        template_library_loader(consumer.entity.workspace.repository)(
            consumer.id,
            replace(pins[0], library_revision_id=pins[1].library_revision_id),
        )


def test_operator_command_reviews_history_and_full_authority_round_trip(ordinary_library):
    import io
    import json

    from django.core.management import call_command

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    copy_document(owner, source)
    base = dict(workspace=str(source_workspace.id), source=str(source.id), actor=str(owner.id))

    def invoke(**options):
        output = io.StringIO()
        call_command("migrate_shared_library", **base, **options, stdout=output)
        return json.loads(output.getvalue())

    history = invoke(operation="history")
    assert history["status"] == "prepared" and history["missing_files"] > 0
    retained = invoke(operation="history", apply=True, plan_sha256=history["plan_sha256"])
    assert retained["status"] == "retained" and retained["indexed"] is True
    copy_document(owner, consumer)
    for operation, authority in (("promote", "repository"), ("rollback", "legacy"), ("promote", "repository")):
        review = invoke(operation=operation, document=[str(consumer.id)])
        assert review["status"] == "prepared"
        result = invoke(operation=operation, document=[str(consumer.id)], apply=True, plan_sha256=review["plan_sha256"])
        assert result == {"status": "transitioned", "authority": authority}


def test_publication_guard_reverse_and_reapply_preserves_v13_custody(promoted_library):
    import uuid
    from copy import deepcopy

    from django.db import DatabaseError, connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.models import DocumentPublication, Entity
    from apps.core.publications import verify_retained_publication_custody
    from apps.core.tests.repeated_block_fixture import publish

    owner, _source_workspace, _source, workspace, consumer = promoted_library
    snapshot = publish(owner, consumer, "Retain ordinary-library proof across guard downgrade")
    before = deepcopy(snapshot.manifest), snapshot.signature, snapshot.content_digest
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        MigrationExecutor(connection).migrate([("core", "0214_ordinary_library_includes")])
        assert verify_retained_publication_custody(snapshot)
        candidate = DocumentPublication(
            **{field.attname: getattr(snapshot, field.attname) for field in DocumentPublication._meta.concrete_fields}
        )
        candidate.id = uuid.uuid4()
        candidate.manifest = deepcopy(snapshot.manifest)
        candidate.manifest["publication_id"] = str(candidate.id)
        with pytest.raises(DatabaseError), transaction.atomic():
            candidate.entity = Entity.objects.create(
                tenant=consumer.tenant,
                organization=consumer.organization,
                workspace=workspace,
                entity_type="document_publication",
                display_name="Rejected old-guard snapshot",
            )
            candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
            candidate.save(force_insert=True)
    finally:
        MigrationExecutor(connection).migrate(targets)
    snapshot.refresh_from_db()
    assert (snapshot.manifest, snapshot.signature, snapshot.content_digest) == before
    assert verify_retained_publication_custody(snapshot)
    assert (
        publish(owner, consumer, "Reapplied library proof guard").manifest["format"] == "tekdocs-static-publication/v13"
    )


def test_enrolled_and_unenrolled_occurrences_of_one_template_block_remain_distinct(library_enrollments):
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.tests.test_template_enrollment_migration import _prepare_template_library

    context, documents = library_enrollments
    consumer = documents[1]
    block = context.source.placements.get(position=1).block
    add_block_placement(
        document=consumer,
        block=block,
        actor_id=context.owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=2,
    )
    _prepare_template_library(context, documents)
    args = dict(
        source_workspace=context.source.entity.workspace,
        source_document_id=context.source.id,
        destination_document_ids=tuple(item.id for item in documents),
        actor_id=context.owner.id,
        target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    from apps.core.tests.repeated_block_fixture import publish

    snapshot = publish(context.owner, consumer, "Freeze distinct enrollment and ordinary reuse provenance")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    assert snapshot.manifest["library_format"] == "tekdocs-static-publication/v12"
    assert snapshot.manifest["occurrence_format"] == "tekdocs-static-publication/v8"
    sources = [item for item in snapshot.manifest["git_source"]["sources"] if item["id"] == str(block.id)]
    assert len(sources) == 2
    assert "template_revision" in sources[0] and "library_source" not in sources[0]
    assert "library_source" in sources[1] and "template_revision" not in sources[1]


def test_source_without_a_configured_repository_has_a_clear_import_blocker(settings, tmp_path):
    import secrets

    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.accounts.bootstrap import bootstrap_owner
    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.models import InstallationState, WorkspaceRepository
    from apps.core.repository_service import RepositoryAuditAttribution, commit_repository_files

    settings.TEKDOCS_REPOSITORY_ROOT = ""
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Unconfigured library fixture",
        owner_email="unconfigured-library@example.invalid",
        owner_display_name="Fixture owner",
        password=secrets.token_urlsafe(32) + "Aa7!",
    )
    owner = installation.owner
    TOTP.activate(owner, generate_totp_secret())
    source = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=owner.id,
        title="Legacy library before Git configuration",
        markdown="Legacy library text.\n",
        library_visible=True,
    )
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=owner.id,
        name="Unconfigured library client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    consumer = create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=owner.id,
        title="Legacy consumer before Git configuration",
        markdown="Client introduction.\n",
    )
    add_block_placement(
        document=consumer,
        block=source.placements.get().block,
        actor_id=owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=1,
    )
    assert not WorkspaceRepository.objects.filter(workspace_id=source.entity.workspace_id).exists()
    settings.TEKDOCS_REPOSITORY_ROOT = str(tmp_path / "configured-repositories")
    workspace = Workspace.objects.get(organization=organization)
    ensure_workspace_repository(workspace)
    commit_repository_files(
        repository_id=workspace.repository.id,
        expected_base=None,
        changes={"README.txt": b"Initialized synthetic target Workspace.\n"},
        message="Initialize target fixture",
        attribution=RepositoryAuditAttribution(actor_id=owner.id, action="content.migration_fixture_initialize"),
    )
    index_repository_content(repository_id=workspace.repository.id)
    with pytest.raises(DocumentMigrationBlocked, match="source_unavailable"):
        prepare_document_import(workspace=workspace, document_id=consumer.id)


def test_cross_workspace_publication_refreshes_foreign_live_custody_without_a_prior_read(published_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.tests.cross_workspace_fixture import (
        EDITED,
        documents,
        exercise_cross_workspace_fixture,
        prepare_cross_workspace_fixture,
        seed_cross_workspace_fixture,
    )

    owner = published_context[0].owner
    seed_cross_workspace_fixture(owner)
    before = prepare_cross_workspace_fixture(owner)
    source, _consumer = documents(owner)
    fragment = read_authored_content(
        repository=source.entity.workspace.repository, content_id=source.placements.get(position=1).block_id
    )
    author_content(
        repository=source.entity.workspace.repository, actor_id=owner.id, request_id=None,
        operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob, kind=None, path=None, title=None, markdown=EDITED, metadata_patch={},
    )
    exercise_cross_workspace_fixture(owner, before)


def test_publication_pins_foreign_heads_for_the_entire_refreshed_repository(promoted_library, monkeypatch):
    from contextlib import contextmanager

    from apps.core import content_publication_sources

    owner, _source_workspace, source, workspace, consumer = promoted_library
    local = create_document(
        tenant=consumer.tenant, organization=consumer.organization, actor_id=owner.id,
        title="Independent consumer Workspace guide", markdown="Local instructions.\n",
    )
    copy_document(owner, local)
    selected = []
    original = content_publication_sources.pin_accepted_repository_for_publication

    @contextmanager
    def record_pin(repository_id):
        selected.append(repository_id)
        with original(repository_id) as pinned:
            yield pinned

    monkeypatch.setattr(content_publication_sources, "pin_accepted_repository_for_publication", record_pin)
    with content_publication_sources.pinned_git_document_dependencies(
        repository_id=workspace.repository.id, content_id=local.id, audience="msp_internal",
    ) as proof:
        assert proof["content_id"] == str(local.id)
        assert selected == sorted([workspace.repository.id, source.entity.workspace.repository.id])


@pytest.mark.parametrize("boundary", ["coordinator", "single", "sql", "sql_runtime", "concurrent"])
def test_library_handoff_cannot_omit_a_legacy_pinned_foreign_owner(ordinary_library, django_runtime_role, boundary):
    from apps.core.document_template_migration import TemplateMigrationError
    from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
    from apps.core.shared_library_migration import prepare_shared_library_handoff

    owner, source_workspace, source, _workspace, consumer = ordinary_library
    pinned_source = create_document(
        tenant=source.tenant, organization=None, actor_id=owner.id,
        title="Additional pinned library", markdown="Pinned library introduction.\n", library_visible=True,
    )
    section = create_document_block(
        document=pinned_source, actor_id=owner.id, markdown="Additional pinned instructions.\n",
        name="Pinned shared section", kind="rich_text", parent_id=None, position=1, library_visible=True,
    )
    add_block_placement(
        document=consumer, block=section.block, actor_id=owner.id, resolution_mode="pinned",
        pinned_revision_id=section.block.current_revision_id, parent_id=None, position=2,
    )
    other = None
    if boundary == "coordinator":
        other = create_document(
            tenant=consumer.tenant, organization=consumer.organization, actor_id=owner.id,
            title="Another library consumer", markdown="Other client instructions.\n",
        )
        add_block_placement(
            document=other, block=section.block, actor_id=owner.id, resolution_mode="live",
            pinned_revision_id=None, parent_id=None, position=1,
        )
    for document in (source, pinned_source):
        copy_document(owner, document)
    history = prepare_shared_library_history(source=pinned_source, actor_id=owner.id)
    retain_shared_library_history(source=pinned_source, actor_id=owner.id, plan_sha256=history.plan_sha256)
    copy_document(owner, consumer)
    if other is not None:
        copy_document(owner, other)
    args = dict(
        source_workspace=source_workspace, source_document_id=source.id,
        actor_id=owner.id, target="repository",
    )
    with pytest.raises(TemplateMigrationError, match="library_pinned_dependency_group_incomplete"):
        prepare_shared_library_handoff(**args, destination_document_ids=(consumer.id,))
    from apps.core.shared_library_migration import transition_shared_library_authority

    destinations = (consumer.id, pinned_source.id, *((other.id,) if other else ()))
    complete = prepare_shared_library_handoff(**args, destination_document_ids=destinations)
    transition_shared_library_authority(**args, destination_document_ids=destinations, plan_sha256=complete.plan_sha256)
    # An omitted pin owner is safe when its authority is already repository-backed.
    assert prepare_shared_library_handoff(**args, destination_document_ids=(consumer.id,)).plan_sha256
    if boundary == "single":
        from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
        from apps.core.template_library_scope import editable_template_workspace_scope
        from apps.core.workspaces import resolve_msp_workspace

        with editable_template_workspace_scope(source_workspace, owner.id):
            with pytest.raises(DocumentAuthorityHandoffError, match="library_pinned_dependency_group_incomplete"):
                transition_document_authority(
                    workspace=source_workspace, document_id=pinned_source.id, actor_id=owner.id,
                    target="legacy", reader_workspace=resolve_msp_workspace(owner),
                )
    elif boundary in {"sql", "sql_runtime"}:
        from contextlib import nullcontext

        from django.db import IntegrityError, connection, transaction

        from apps.core.models import DocumentAuthority
        from apps.core.template_library_scope import editable_template_workspace_scope

        with pytest.raises(IntegrityError, match="pinned repository consumers"):
            role = django_runtime_role() if boundary == "sql_runtime" else nullcontext()
            with role, editable_template_workspace_scope(source_workspace, owner.id), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
                DocumentAuthority.objects.filter(
                    tenant_id=source.tenant_id, workspace=source_workspace, content_id=pinned_source.id,
                ).update(authority="legacy")
    elif boundary == "concurrent":
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import IntegrityError, close_old_connections, connection, transaction

        from apps.core.models import Block, DocumentAuthority
        from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
        from apps.core.scoping import DataScope

        rollback_args = {**args, "target": "legacy", "destination_document_ids": (consumer.id,)}
        review = prepare_shared_library_handoff(**rollback_args)
        transition_shared_library_authority(**rollback_args, plan_sha256=review.plan_sha256)
        barrier = Barrier(2)

        def race(documents, target):
            close_old_connections()
            try:
                with transaction.atomic():
                    bind_local_rls_scope(
                        DataScope.tenant(source.tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
                        principal_mode=RLSPrincipalMode.SYSTEM, actor_user_id=None,
                    )
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '5s'")
                        cursor.execute("SET LOCAL statement_timeout = '10s'")
                        cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
                    roots = {item.id for item in documents}
                    fragments = set(Block.objects.filter(
                        tenant_id=source.tenant_id, source_document__in=documents,
                    ).values_list("id", flat=True))
                    # Match the coordinator: stage every root before fragments.
                    for identities in (roots, fragments):
                        DocumentAuthority.objects.filter(
                            tenant_id=source.tenant_id, content_id__in=identities,
                        ).update(authority=target)
                    barrier.wait(timeout=10)
                return "committed"
            except IntegrityError as error:
                assert error.__cause__.sqlstate == "23514"
                return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            promotion = pool.submit(race, (source, consumer), "repository")
            rollback = pool.submit(race, (pinned_source,), "legacy")
            assert sorted((promotion.result(timeout=20), rollback.result(timeout=20))) == ["committed", "rejected"]
        state = dict(DocumentAuthority.objects.filter(
            tenant_id=source.tenant_id, content_id__in=(consumer.id, pinned_source.id),
        ).values_list("content_id", "authority"))
        assert state[consumer.id] != "repository" or state[pinned_source.id] == "repository"
    else:
        assert other is not None
        other_args = dict(
            source_workspace=source_workspace, source_document_id=pinned_source.id,
            destination_document_ids=(other.id,), actor_id=owner.id,
        )
        with pytest.raises(TemplateMigrationError, match="library_pinned_dependency_group_incomplete"):
            prepare_shared_library_handoff(**other_args, target="legacy")


def test_publication_rejects_dependency_scope_drift_before_refresh(promoted_library, monkeypatch):
    from apps.core import content_publication_sources, template_library_content

    _owner, _source_workspace, _source, workspace, consumer = promoted_library
    discover = content_publication_sources._publication_repository_ids
    calls = 0

    def changed_scope(**kwargs):
        nonlocal calls
        calls += 1
        return (workspace.repository.id,) if calls == 1 else discover(**kwargs)

    monkeypatch.setattr(content_publication_sources, "_publication_repository_ids", changed_scope)
    refreshed = []
    monkeypatch.setattr(template_library_content, "refresh_template_library_projection", refreshed.append)
    with pytest.raises(content_publication_sources.ContentPublicationSourceError, match="dependency scope changed"):
        with content_publication_sources.pinned_git_document_dependencies(
            repository_id=workspace.repository.id, content_id=consumer.id, audience="msp_internal",
        ):
            pytest.fail("Drifting source scope must not yield publication proof")
    assert not refreshed


def test_same_workspace_service_handoff_with_an_explicit_reader_scope(published_context):
    from django.db import transaction

    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.tests.test_shared_block_publication_migration import (
        test_shared_signed_history_can_be_copied_without_rewriting_evidence,
    )

    installation = published_context[0]
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.SYSTEM, actor_user_id=None,
        )
        test_shared_signed_history_can_be_copied_without_rewriting_evidence(
            published_context, mode="live", late_storage_failure=False,
        )


@pytest.mark.parametrize("actor_kind", ["owner", "read_only", "foreign_tenant", "client_portal"])
def test_handoff_scope_preserves_policy_and_restores_the_parent_principal(published_context, actor_kind):
    from allauth.mfa.models import Authenticator
    from django.db import connection, transaction
    from rest_framework.exceptions import PermissionDenied

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.models import Tenant
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.workspace_scope import editable_workspace_scope

    installation, workspace, _document, _publication = published_context
    actor = installation.owner
    if actor_kind != "owner":
        actor = User.objects.create_user(email=f"{actor_kind}-scope@example.invalid", display_name="Scope reader")
        tenant = (Tenant.objects.create(name="Foreign scope tenant", slug="foreign-scope-tenant")
                  if actor_kind == "foreign_tenant" else installation.tenant)
        organization = None
        if actor_kind == "client_portal":
            organization = create_organization(
                tenant=tenant, actor_id=installation.owner.id, name="Assigned scope client", legal_name="",
                website="", classifications=["client"],
            )
        TenantMembership.objects.create(
            tenant=tenant, user=actor, organization=organization,
            role=(BuiltInRole.READ_ONLY if actor_kind == "read_only" else
                  BuiltInRole.CLIENT_ADMINISTRATOR if actor_kind == "client_portal" else BuiltInRole.ADMINISTRATOR),
        )
    assert not Authenticator.objects.filter(user=actor).exists()
    settings = (
        "tekdocs.tenant_id", "tekdocs.workspace_id", "tekdocs.organization_id",
        "tekdocs.organization_mode", "tekdocs.user_id", "tekdocs.principal_mode",
    )

    def current_scope():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + ", ".join("COALESCE(current_setting(%s, true), '')" for _name in settings), list(settings),
            )
            return cursor.fetchone()

    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.SYSTEM, actor_user_id=None,
        )
        before = current_scope()
        if actor_kind == "owner":
            with editable_workspace_scope(workspace, actor.id):
                assert current_scope()[4:] == (str(actor.id), "user")
            assert current_scope() == before
            with pytest.raises(ValueError, match="scope rollback probe"):
                with editable_workspace_scope(workspace, actor.id):
                    raise ValueError("scope rollback probe")
        else:
            with pytest.raises(PermissionDenied), editable_workspace_scope(workspace, actor.id):
                pytest.fail("Denied actor must not enter the Workspace scope")
        assert current_scope() == before


def test_plain_document_handoff_does_not_gain_an_unrelated_mfa_requirement(published_context):
    from allauth.mfa.models import Authenticator

    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.workspaces import resolve_msp_workspace

    installation, workspace, _document, _publication = published_context
    owner = installation.owner
    assert not Authenticator.objects.filter(user=owner).exists()
    document = create_document(
        tenant=installation.tenant, organization=None, actor_id=owner.id,
        title="Ordinary scope compatibility guide", markdown="Ordinary instructions.\n",
    )
    copy_document(owner, document)
    assert transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=owner.id,
        target="repository", reader_workspace=resolve_msp_workspace(owner),
    ) == "transitioned"


@pytest.mark.parametrize("participant", ["source", "consumer"])
def test_single_document_library_handoff_keeps_its_mfa_boundary(ordinary_library, participant, monkeypatch):
    from allauth.mfa.models import Authenticator

    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
    from apps.core.documents import update_document_placement
    from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
    from apps.core.tests.cross_workspace_fixture import reader_for

    owner, source_workspace, source, workspace, consumer = ordinary_library
    placement = consumer.placements.get(block__source_document=source)
    update_document_placement(
        placement=placement, actor_id=owner.id, resolution_mode="pinned",
        pinned_revision_id=placement.block.current_revision_id,
    )
    copy_document(owner, source)
    history = prepare_shared_library_history(source=source, actor_id=owner.id)
    retain_shared_library_history(source=source, actor_id=owner.id, plan_sha256=history.plan_sha256)
    copy_document(owner, consumer)
    if participant == "consumer":
        assert transition_document_authority(
            workspace=source_workspace, document_id=source.id, actor_id=owner.id,
            target="repository", reader_workspace=reader_for(owner, source),
        ) == "transitioned"
    document = source if participant == "source" else consumer
    selected_workspace = source_workspace if participant == "source" else workspace
    assert not document.publications.exists()
    Authenticator.objects.filter(user=owner).delete()

    def reject_git_access(*args, **kwargs):
        pytest.fail("Denied library actor must not probe Git storage")

    monkeypatch.setattr(
        "apps.core.document_authority_handoff.pin_accepted_repository_for_publication", reject_git_access,
    )
    with pytest.raises(DocumentAuthorityHandoffError, match="publication_migration_not_authorized"):
        transition_document_authority(
            workspace=selected_workspace, document_id=document.id, actor_id=owner.id,
            target="repository", reader_workspace=reader_for(owner, document),
        )


def test_source_blocks_are_locked_before_the_authorization_recheck(published_context, monkeypatch):
    from django.db import DatabaseError, connection

    from apps.core import document_authority_handoff
    from apps.core.workspaces import resolve_msp_workspace

    installation, workspace, _document, _publication = published_context
    owner = installation.owner
    document = create_document(
        tenant=installation.tenant, organization=None, actor_id=owner.id,
        title="Serialized ordinary handoff", markdown="Source instructions.\n",
    )
    copy_document(owner, document)
    authorize = document_authority_handoff._authorize_document_handoff_actor
    calls = 0

    def verify_lock_before_authorizing(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            other = connection.copy(alias="source_lock_probe")
            try:
                with pytest.raises(DatabaseError) as denied, other.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM core_block WHERE tenant_id=%s AND source_document_id=%s "
                        "ORDER BY id FOR UPDATE NOWAIT", [installation.tenant.id, document.id],
                    )
                assert denied.value.__cause__.sqlstate == "55P03"
            finally:
                other.close()
        return authorize(**kwargs)

    monkeypatch.setattr(document_authority_handoff, "_authorize_document_handoff_actor", verify_lock_before_authorizing)
    assert document_authority_handoff.transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=owner.id,
        target="repository", reader_workspace=resolve_msp_workspace(owner),
    ) == "transitioned"
    assert calls == 2


@pytest.mark.parametrize("other_client", [False, True])
@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_ordinary_legacy_reuse_cannot_accept_a_promoted_foreign_revision_cache(
    promoted_library, django_runtime_role, other_client, mode,
):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
    from django.db import transaction

    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
        User,
    )
    from apps.core.documents import PlacementConflict
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    owner, _source_workspace, source, _workspace, consumer = promoted_library
    organization = consumer.organization
    if other_client:
        organization = create_organization(
            tenant=source.tenant, actor_id=owner.id, name="New library client", legal_name="",
            website="", classifications=["client"],
        )
    destination = create_document(
        tenant=source.tenant, organization=organization, actor_id=owner.id,
        title="Unenrolled legacy library reader", markdown="Client instructions.\n",
    )
    actor = User.objects.create_user(email="ordinary-reuse@example.invalid", display_name="Assigned library editor")
    membership = TenantMembership.objects.create(
        tenant=source.tenant, user=actor, role=BuiltInRole.CONTRIBUTOR,
        workspace_scope=MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=source.tenant, organization=organization, membership=membership, created_by=owner,
    )
    TOTP.activate(actor, generate_totp_secret())
    block = source.placements.get(position=1).block
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(source.tenant, organization), organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=actor.id, principal_mode=RLSPrincipalMode.USER,
        )
        with pytest.raises(PlacementConflict, match="Git-authoritative"):
            add_block_placement(
                document=destination, block=block, actor_id=actor.id, resolution_mode=mode,
                pinned_revision_id=block.current_revision_id if mode == "pinned" else None,
                parent_id=None, position=1,
            )
        assert destination.placements.count() == 1
