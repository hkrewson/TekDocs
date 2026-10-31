"""Template enrollment migration preserves control history through public operations."""

import json
import secrets
from copy import deepcopy
from dataclasses import dataclass

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.content_index import index_repository_content
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.documents import create_document, create_document_block, instantiate_document_template, update_document
from apps.core.models import Document, DocumentPublication, InstallationState, Workspace
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact, verify_retained_publication_custody
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.workspaces import ResolvedWorkspace, resolve_organization_workspace

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass(frozen=True)
class EnrollmentContext:
    owner: User
    source: Document
    document: Document
    workspace: Workspace
    reader: ResolvedWorkspace
    publication: DocumentPublication


@pytest.fixture
def copied_enrollment(tmp_path, settings):
    settings.TEKDOCS_REPOSITORY_ROOT = str(tmp_path / "repositories")
    settings.MEDIA_ROOT = str(tmp_path / "media")
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Template migration fixture",
        owner_email="template-migration@example.invalid",
        owner_display_name="Template owner",
        password=secrets.token_urlsafe(32) + "Aa7!",
    )
    owner = installation.owner
    TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=owner.id,
        name="Template migration client",
        legal_name="",
        website="",
        classifications=[],
    )
    source = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=owner.id,
        title="Reusable enrollment guide",
        markdown="Original template introduction.\n",
        is_template=True,
    )
    create_document_block(
        document=source,
        actor_id=owner.id,
        markdown="Copied enrollment instructions.\n",
        kind="rich_text",
        name="Enrollment",
        parent_id=None,
        position=1,
    )
    document = instantiate_document_template(
        source=source,
        tenant=installation.tenant,
        organization=organization,
        actor_id=owner.id,
        title="Client enrollment guide",
        category="guide",
    )
    primary = document.placements.get(position=0)
    update_document(
        document=document,
        actor_id=owner.id,
        title=document.entity.display_name,
        markdown="Client-specific local introduction.\n",
        base_revision_id=primary.block.current_revision_id,
    )
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=owner.id,
        reason="Retain template-derived instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    workspace = Workspace.objects.get(organization=organization)
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    return EnrollmentContext(owner, source, document, workspace, reader, publication)


def test_copied_enrollment_import_preserves_local_edits_lineage_and_signed_pdf(copied_enrollment):
    owner, document, workspace, publication = (
        copied_enrollment.owner,
        copied_enrollment.document,
        copied_enrollment.workspace,
        copied_enrollment.publication,
    )
    original = (
        deepcopy(publication.manifest),
        publication.signature,
        read_publication_artifact(publication.artifacts.get(kind="pdf")),
    )
    enrollment = document.template_enrollment
    lineage = (
        enrollment.id,
        enrollment.source_template_id,
        enrollment.applied_revision_id,
        deepcopy(enrollment.placement_map),
    )
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert (
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=owner.id,
        ).status
        == "imported"
    )
    enrollment.refresh_from_db()
    assert (
        enrollment.id,
        enrollment.source_template_id,
        enrollment.applied_revision_id,
        enrollment.placement_map,
    ) == lineage
    publication.refresh_from_db()
    assert (
        publication.manifest,
        publication.signature,
        read_publication_artifact(publication.artifacts.get(kind="pdf")),
    ) == original
    assert verify_retained_publication_custody(publication)


def test_copied_enrollment_authority_round_trip_preserves_lineage_and_publications(copied_enrollment):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.documents import resolve_document

    scene = copied_enrollment
    document, workspace, owner = scene.document, scene.workspace, scene.owner
    enrollment = document.template_enrollment
    retained_map = deepcopy(enrollment.placement_map)
    retained_revision = enrollment.applied_revision_id
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=owner.id,
    )
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(document.id,),
        actor_id=owner.id,
        target="repository",
        reader_workspace=scene.reader,
    )
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=plan.document_ids,
            actor_id=owner.id,
            target="repository",
            reader_workspace=scene.reader,
            plan_sha256=plan.plan_sha256,
        )
        == "transitioned"
    )
    assert (
        document_detail(workspace=scene.reader, content_id=document.id, audience="msp_internal")["markdown"]
        == "Client-specific local introduction.\n\nCopied enrollment instructions.\n"
    )
    fragment = read_authored_content(
        repository=workspace.repository, content_id=document.placements.get(position=0).block_id
    )
    author_content(
        repository=workspace.repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Locally edited Git introduction.\n",
        metadata_patch={},
    )
    snapshot = publish_document(
        workspace=scene.reader,
        document=document,
        actor_id=owner.id,
        reason="Retain migrated template copy",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert snapshot.canonical_markdown == "Locally edited Git introduction.\n\nCopied enrollment instructions.\n"
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(document.id,),
        actor_id=owner.id,
        target="legacy",
        reader_workspace=scene.reader,
    )
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=plan.document_ids,
            actor_id=owner.id,
            target="legacy",
            reader_workspace=scene.reader,
            plan_sha256=plan.plan_sha256,
        )
        == "transitioned"
    )
    assert resolve_document(document).markdown == snapshot.canonical_markdown
    enrollment.refresh_from_db()
    assert enrollment.placement_map == retained_map
    assert enrollment.applied_revision_id == retained_revision
    assert verify_retained_publication_custody(scene.publication)
    assert verify_retained_publication_custody(snapshot)


@pytest.mark.parametrize("stage", ["copy", "authority"])
def test_enrollment_metadata_change_invalidates_reviewed_migration_plan(copied_enrollment, stage):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.documents import apply_template_rollout, template_rollout_preview

    scene = copied_enrollment
    plan = prepare_document_import(workspace=scene.workspace, document_id=scene.document.id)
    if stage == "authority":
        apply_document_import(
            workspace=scene.workspace,
            document_id=scene.document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=scene.owner.id,
        )
        plan = prepare_authority_group(
            workspace=scene.workspace,
            document_ids=(scene.document.id,),
            actor_id=scene.owner.id,
            target="repository",
            reader_workspace=scene.reader,
        )
    enrollment = scene.document.template_enrollment
    primary = scene.source.placements.get(position=0)
    update_document(
        document=scene.source,
        actor_id=scene.owner.id,
        title="Retitled template source",
        markdown=primary.block.current_revision.markdown,
        base_revision_id=primary.block.current_revision_id,
        is_template=True,
    )
    scene.source.refresh_from_db()
    latest, preview = template_rollout_preview(enrollment=enrollment, actor_id=scene.owner.id)
    assert latest.id != enrollment.applied_revision_id
    assert preview["conflicts"] == []
    before_text = scene.document.placements.get(position=0).block.current_revision.markdown
    apply_template_rollout(
        enrollment=enrollment, actor_id=scene.owner.id, expected_applied_revision_id=enrollment.applied_revision_id
    )
    assert scene.document.placements.get(position=0).block.current_revision.markdown == before_text
    if stage == "copy":
        with pytest.raises(DocumentMigrationBlocked, match="preview_changed"):
            apply_document_import(
                workspace=scene.workspace,
                document_id=scene.document.id,
                expected_base=plan.base_commit,
                plan_sha256=plan.plan_sha256,
                actor_id=scene.owner.id,
            )
    else:
        with pytest.raises(DocumentAuthorityHandoffError, match="preview_changed"):
            transition_authority_group(
                workspace=scene.workspace,
                document_ids=plan.document_ids,
                actor_id=scene.owner.id,
                target="repository",
                reader_workspace=scene.reader,
                plan_sha256=plan.plan_sha256,
            )


def test_hidden_template_source_is_not_treated_as_absent_enrollment(copied_enrollment, django_runtime_role):
    from django.db import transaction

    from apps.core.models import DocumentTemplateEnrollment
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    scene = copied_enrollment
    scope = DataScope.organization(scene.document.tenant, scene.workspace.organization)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=scene.owner.id,
        )
        assert DocumentTemplateEnrollment.objects.filter(destination_document=scene.document).exists()
        assert not Document.objects.filter(pk=scene.source.id).exists()
        plan = prepare_document_import(workspace=scene.workspace, document_id=scene.document.id)
        assert plan.export.template_enrollment_sha256


def test_promotion_retires_a_concurrent_metadata_only_legacy_rollout(copied_enrollment):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, connection, transaction

    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.documents import PlacementConflict, apply_template_rollout

    scene = copied_enrollment
    document, owner, workspace = scene.document, scene.owner, scene.workspace
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=owner.id,
    )
    primary = scene.source.placements.get(position=0)
    update_document(
        document=scene.source,
        actor_id=owner.id,
        title="Template metadata revision",
        markdown=primary.block.current_revision.markdown,
        base_revision_id=primary.block.current_revision_id,
        is_template=True,
    )
    enrollment = document.template_enrollment
    original_revision = enrollment.applied_revision_id
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(document.id,),
        actor_id=owner.id,
        target="repository",
        reader_workspace=scene.reader,
    )
    checked, release = Event(), Event()

    def rollout():
        close_old_connections()
        try:

            def pause_after_authority_read(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if 'FROM "core_documentauthority"' in sql and not checked.is_set():
                    checked.set()
                    assert release.wait(10)
                return result

            with connection.execute_wrapper(pause_after_authority_read):
                try:
                    apply_template_rollout(
                        enrollment=enrollment, actor_id=owner.id, expected_applied_revision_id=original_revision
                    )
                except PlacementConflict:
                    return "blocked"
                return "applied"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with transaction.atomic():
                Document.objects.select_for_update().get(pk=document.id)
                future = pool.submit(rollout)
                # Before the fix, rollout ignores this destination lock and can
                # pass its legacy check while promotion is about to commit.
                checked.wait(0.5)
                assert (
                    transition_authority_group(
                        workspace=workspace,
                        document_ids=plan.document_ids,
                        actor_id=owner.id,
                        target="repository",
                        reader_workspace=scene.reader,
                        plan_sha256=plan.plan_sha256,
                    )
                    == "transitioned"
                )
        finally:
            release.set()
        assert future.result(timeout=10) == "blocked"
    enrollment.refresh_from_db()
    assert enrollment.applied_revision_id == original_revision


def test_rollout_apply_rejects_a_source_version_newer_than_the_reviewed_preview(copied_enrollment):
    from django.test import Client
    from django.urls import reverse

    scene = copied_enrollment
    enrollment = scene.document.template_enrollment
    client = Client()
    client.force_login(scene.owner)
    for name in ("Reviewed addition", "Unreviewed addition"):
        create_document_block(
            document=scene.source,
            actor_id=scene.owner.id,
            markdown=name + ".\n",
            kind="rich_text",
            name=name,
            parent_id=None,
            position=None,
        )
        if name == "Reviewed addition":
            response = client.post(
                reverse(
                    "organization-document-template-rollout-preview",
                    kwargs={"organization_entity_id": scene.workspace.organization.entity_id},
                ),
                {"enrollment_id": str(enrollment.id)},
                content_type="application/json",
            )
            assert response.status_code == 200
            preview = response.json()
    response = client.post(
        reverse(
            "organization-document-template-rollout-apply",
            kwargs={"organization_entity_id": scene.workspace.organization.entity_id},
        ),
        {
            "enrollment_id": str(enrollment.id),
            "expected_applied_revision_id": preview["applied_revision_id"],
            "expected_available_revision": preview["available_revision"],
        },
        content_type="application/json",
    )
    assert response.status_code == 409
    enrollment.refresh_from_db()
    assert str(enrollment.applied_revision_id) == preview["applied_revision_id"]
    assert scene.document.placements.count() == 2


@pytest.mark.parametrize("operator_kind", ["read_only", "missing_mfa"])
@pytest.mark.parametrize("stage", ["import", "rollback"])
def test_enrollment_import_without_publications_still_requires_edit_and_mfa(copied_enrollment, operator_kind, stage):
    from allauth.mfa.models import Authenticator

    from apps.accounts.models import BuiltInRole, TenantMembership
    from apps.core.document_migration_import import DocumentMigrationBlocked, rollback_document_import

    scene = copied_enrollment
    document = instantiate_document_template(
        source=scene.source,
        tenant=scene.document.tenant,
        organization=scene.workspace.organization,
        actor_id=scene.owner.id,
        title="Unpublished enrolled guide",
        category="guide",
    )
    if stage == "rollback":
        owned_plan = prepare_document_import(workspace=scene.workspace, document_id=document.id)
        apply_document_import(
            workspace=scene.workspace,
            document_id=document.id,
            expected_base=owned_plan.base_commit,
            plan_sha256=owned_plan.plan_sha256,
            actor_id=scene.owner.id,
        )
    if operator_kind == "read_only":
        operator = User.objects.create_user(email="template-reader@example.invalid", display_name="Reader")
        TenantMembership.objects.create(tenant=scene.document.tenant, user=operator, role=BuiltInRole.READ_ONLY)
        TOTP.activate(operator, generate_totp_secret())
    else:
        operator = scene.owner
        Authenticator.objects.filter(user=operator).delete()
    scene.workspace.repository.refresh_from_db()
    before = scene.workspace.repository.accepted_commit_id
    plan = prepare_document_import(workspace=scene.workspace, document_id=document.id)
    with pytest.raises(DocumentMigrationBlocked, match="migration_not_authorized"):
        if stage == "import":
            apply_document_import(
                workspace=scene.workspace,
                document_id=document.id,
                expected_base=plan.base_commit,
                plan_sha256=plan.plan_sha256,
                actor_id=operator.id,
            )
        else:
            rollback_document_import(
                workspace=scene.workspace,
                document_id=document.id,
                expected_commit=plan.base_commit,
                actor_id=operator.id,
            )
    scene.workspace.repository.refresh_from_db()
    assert scene.workspace.repository.accepted_commit_id == before


@pytest.fixture
def library_enrollments(copied_enrollment):
    context = copied_enrollment
    source = context.source
    source.library_visible = True
    source.save(update_fields=("library_visible", "updated_at"))
    section = source.placements.get(position=1).block
    section.library_visible = True
    section.save(update_fields=("library_visible", "updated_at"))
    clients = [context.document]
    for mode in ("live", "pinned"):
        clients.append(
            instantiate_document_template(
                source=source,
                tenant=source.tenant,
                organization=context.document.organization,
                actor_id=context.owner.id,
                title=f"Client {mode} enrollment",
                category="guide",
                placement_rules={str(section.entity_id): mode},
            )
        )
    return context, tuple(clients)


def test_template_cohort_plan_preserves_copy_live_and_pinned_evidence(library_enrollments):
    from apps.core.document_template_migration import prepare_template_library_migration
    from apps.core.document_template_models import DocumentTemplateEnrollment

    context, documents = library_enrollments
    plan = prepare_template_library_migration(
        source_workspace=context.source.entity.workspace,
        source_document_id=context.source.id,
        destination_document_ids=tuple(document.id for document in documents),
        actor_id=context.owner.id,
    )
    assert plan.source_document_id == context.source.id
    assert set(plan.destination_document_ids) == {document.id for document in documents}
    assert {mode for evidence in plan.enrollments for mode in evidence.modes} == {"copy", "live", "pinned"}
    assert {evidence.applied_revision_id for evidence in plan.enrollments} == set(
        DocumentTemplateEnrollment.objects.filter(destination_document__in=documents).values_list(
            "applied_revision_id", flat=True
        )
    )
    assert len(plan.plan_sha256) == 64
    assert plan == prepare_template_library_migration(
        source_workspace=context.source.entity.workspace,
        source_document_id=context.source.id,
        destination_document_ids=tuple(reversed([document.id for document in documents])),
        actor_id=context.owner.id,
    )


def test_template_cohort_plan_requires_all_live_consumers(library_enrollments):
    from apps.core.document_template_migration import TemplateMigrationError, prepare_template_library_migration

    context, documents = library_enrollments
    with pytest.raises(TemplateMigrationError, match="template_live_dependency_group_incomplete"):
        prepare_template_library_migration(
            source_workspace=context.source.entity.workspace,
            source_document_id=context.source.id,
            destination_document_ids=(documents[0].id, documents[2].id),
            actor_id=context.owner.id,
        )


def test_template_cohort_review_changes_when_client_copy_is_edited(library_enrollments):
    from apps.core.document_template_migration import prepare_template_library_migration

    context, documents = library_enrollments
    arguments = dict(
        source_workspace=context.source.entity.workspace,
        source_document_id=context.source.id,
        destination_document_ids=tuple(document.id for document in documents),
        actor_id=context.owner.id,
    )
    before = prepare_template_library_migration(**arguments)
    primary = context.document.placements.get(position=0)
    update_document(
        document=context.document,
        actor_id=context.owner.id,
        title=context.document.entity.display_name,
        markdown="New client-specific edit.\n",
        base_revision_id=primary.block.current_revision_id,
    )
    assert prepare_template_library_migration(**arguments).plan_sha256 != before.plan_sha256


def test_template_cohort_does_not_accept_unapplied_history_with_missing_source_revision(library_enrollments):
    import hashlib
    from uuid import uuid4

    from apps.core.document_template_migration import TemplateMigrationError, prepare_template_library_migration
    from apps.core.document_template_models import DocumentTemplateRevision
    from apps.core.publications import canonical_json

    context, documents = library_enrollments
    current = context.document.template_enrollment.applied_revision
    manifest = deepcopy(current.manifest)
    manifest["blocks"][1]["source_revision_id"] = str(uuid4())
    DocumentTemplateRevision.objects.create(
        tenant=context.source.tenant,
        template=context.source,
        revision_number=current.revision_number + 1,
        manifest=manifest,
        checksum=hashlib.sha256(canonical_json(manifest)).hexdigest(),
        created_by=context.owner,
    )
    with pytest.raises(TemplateMigrationError, match="template_revision_invalid"):
        prepare_template_library_migration(
            source_workspace=context.source.entity.workspace,
            source_document_id=context.source.id,
            destination_document_ids=tuple(document.id for document in documents),
            actor_id=context.owner.id,
        )


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_runtime_client_reads_only_its_enrolled_library_git_fragment(library_enrollments, django_runtime_role, mode):
    from django.db import transaction

    from apps.core.document_migration_export import build_simple_document_export
    from apps.core.repository_service import commit_repository_files, read_template_library_fragment
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, documents = library_enrollments
    source = context.source
    exported = build_simple_document_export(source)
    repository = source.entity.workspace.repository
    result = commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id,
        changes=dict(exported.files),
        message="Retain enrolled source fixture",
    )
    index_repository_content(repository_id=repository.id)
    document = documents[1 if mode == "live" else 2]
    source_section = source.placements.get(position=1).block
    scope = DataScope.organization(document.tenant, document.organization)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        selected = read_template_library_fragment(
            destination_document_id=document.id,
            library_workspace_id=source.entity.workspace_id,
            source_block_id=source_section.id,
            mode=mode,
            pinned_object_id=result.object_id if mode == "pinned" else "",
        )
        assert selected.object_id == result.object_id
        assert source_section.current_revision.markdown.encode() in selected.source
        assert selected.expected_body_sha256 == source_section.current_revision.checksum


@pytest.fixture
def indexed_library_source(library_enrollments):
    from apps.core.document_migration_export import build_simple_document_export
    from apps.core.repository_service import commit_repository_files

    context, documents = library_enrollments
    source = context.source
    exported = build_simple_document_export(source)
    repository = source.entity.workspace.repository
    result = commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id,
        changes=dict(exported.files),
        message="Retain enrolled library source fixture",
    )
    index_repository_content(repository_id=repository.id)
    return context, documents, result.object_id


def _commit_library_client(context, document, source_commit, mode):
    import yaml

    from apps.core.repository_service import commit_repository_files

    primary = document.placements.get(position=0).block
    section = context.source.placements.get(position=1).block
    source_workspace_id = context.source.entity.workspace_id
    include = dict(
        id=str(section.id),
        mode=mode,
        audience="shared",
        library_workspace=str(source_workspace_id),
        library_revision=str(document.template_enrollment.applied_revision_id),
    )
    if mode == "pinned":
        include["commit"] = source_commit

    def encoded(metadata, body=""):
        return ("---\n" + yaml.safe_dump(metadata) + "---\n" + body).encode()

    root = dict(
        schema="tekdocs.content/v1",
        id=str(document.id),
        kind="document",
        title=document.entity.display_name,
        includes=[dict(id=str(primary.id), mode="live", audience="shared"), include],
    )
    fragment = dict(schema="tekdocs.content/v1", id=str(primary.id), kind="fragment", title=primary.entity.display_name)
    repository = context.workspace.repository
    committed = commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id,
        changes={
            f"docs/{document.id}.md": encoded(root),
            f"fragments/{primary.id}.md": encoded(fragment, primary.current_revision.markdown),
        },
        message="Retain client template reference fixture",
    )
    return repository, committed


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_runtime_index_resolves_enrolled_foreign_library_fragment(indexed_library_source, django_runtime_role, mode):
    from django.db import transaction

    from apps.core.documents import resolve_document
    from apps.core.models import ContentInclude, ContentNode
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, documents, source_commit = indexed_library_source
    document = documents[1 if mode == "live" else 2]
    source_workspace_id = context.source.entity.workspace_id
    repository, committed = _commit_library_client(context, document, source_commit, mode)
    expected_markdown = resolve_document(document).markdown
    scope = DataScope.organization(document.tenant, document.organization)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        indexed = index_repository_content(repository_id=repository.id)
        assert indexed.object_id == committed.object_id
        node = ContentNode.objects.get(repository=repository, content_id=document.id)
        assert node.composition_variants["all"]["markdown"] == expected_markdown
        reference = ContentInclude.objects.get(source=node, ordinal=1)
        assert reference.target_id is None
        assert reference.library_workspace_id == source_workspace_id
        assert reference.resolved_object_id == source_commit


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_library_reader_refreshes_live_source_and_retains_pin(indexed_library_source, mode):
    from django.db import transaction

    from apps.core.content_read import document_detail
    from apps.core.documents import update_shared_block
    from apps.core.repository_service import commit_repository_files, read_accepted_repository_file

    context, documents, source_commit = indexed_library_source
    document = documents[1 if mode == "live" else 2]
    repository, _ = _commit_library_client(context, document, source_commit, mode)
    with transaction.atomic():
        index_repository_content(repository_id=repository.id)
    before = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
    placement = context.source.placements.get(position=1)
    original = placement.block.current_revision.markdown
    update_shared_block(
        placement=placement,
        actor_id=context.owner.id,
        markdown="Updated MSP enrollment instructions.\n",
        base_revision_id=placement.block.current_revision_id,
    )
    source_repository = context.source.entity.workspace.repository
    previous = read_accepted_repository_file(
        repository_id=source_repository.id,
        path=f"fragments/{placement.block_id}.md",
    )
    commit_repository_files(
        repository_id=source_repository.id,
        expected_base=source_commit,
        changes={
            f"fragments/{placement.block_id}.md": previous.replace(
                original.encode(), b"Updated MSP enrollment instructions.\n"
            )
        },
        message="Advance enrolled source fixture",
    )
    with transaction.atomic():
        after = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
    if mode == "live":
        assert "Updated MSP enrollment instructions." in after["markdown"]
        assert after["markdown"] != before["markdown"]
    else:
        assert after["markdown"] == before["markdown"]


@pytest.mark.parametrize("failure", ["archived_enrollment", "missing_git_fragment"])
def test_library_reader_never_returns_cached_content_when_source_is_unavailable(indexed_library_source, failure):
    from django.db import transaction

    from apps.core.content_read import RepositoryContentNotIndexed, document_detail
    from apps.core.repository_service import commit_repository_files

    context, documents, source_commit = indexed_library_source
    document = documents[1]
    repository, _ = _commit_library_client(context, document, source_commit, "live")
    with transaction.atomic():
        index_repository_content(repository_id=repository.id)
    assert (
        "Copied enrollment instructions."
        in document_detail(
            workspace=context.reader,
            content_id=document.id,
            audience="msp_internal",
        )["markdown"]
    )
    if failure == "archived_enrollment":
        from django.utils import timezone

        enrollment = document.template_enrollment
        enrollment.archived_at = timezone.now()
        enrollment.save(update_fields=("archived_at", "updated_at"))
    else:
        source_repository = context.source.entity.workspace.repository
        commit_repository_files(
            repository_id=source_repository.id,
            expected_base=source_commit,
            changes={f"fragments/{context.source.placements.get(position=1).block_id}.md": None},
            message="Remove source fixture fragment",
        )
    with pytest.raises(RepositoryContentNotIndexed):
        document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")


def test_runtime_library_read_cannot_use_another_client_enrollment(indexed_library_source, django_runtime_role):
    from django.db import transaction

    from apps.core.repository_service import RepositoryInputError, read_template_library_fragment
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, documents, _ = indexed_library_source
    sibling = create_organization(
        tenant=context.source.tenant,
        actor_id=context.owner.id,
        name="Isolated template fixture",
        legal_name="",
        website="",
        classifications=[],
    )
    scope = DataScope.organization(context.source.tenant, sibling)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        with pytest.raises(RepositoryInputError, match="unavailable"):
            read_template_library_fragment(
                destination_document_id=documents[1].id,
                library_workspace_id=context.source.entity.workspace_id,
                source_block_id=context.source.placements.get(position=1).block_id,
                mode="live",
            )


@pytest.mark.parametrize("owner", ["document", "block"])
def test_library_visibility_cannot_be_revoked_while_clients_reuse_it(indexed_library_source, owner):
    from django.db import DatabaseError, transaction

    context, _documents, _source_commit = indexed_library_source
    target = context.source if owner == "document" else context.source.placements.get(position=1).block
    target.library_visible = False
    with pytest.raises(DatabaseError, match="detach client block reuse"), transaction.atomic():
        target.save(update_fields=("library_visible", "updated_at"))
    target.refresh_from_db()
    assert target.library_visible


def test_template_source_copy_retains_each_selected_history_version(indexed_library_source):
    from apps.core.document_template_models import DocumentTemplateRevision
    from apps.core.documents import ensure_template_revision, update_shared_block
    from apps.core.repository_service import read_accepted_repository_file
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history

    context, _documents, _source_commit = indexed_library_source
    source = context.source
    placement = source.placements.get(position=1)
    original = placement.block.current_revision.markdown
    old_revision = context.document.template_enrollment.applied_revision
    update_shared_block(
        placement=placement,
        actor_id=context.owner.id,
        markdown="Second template source version.\n",
        base_revision_id=placement.block.current_revision_id,
    )
    latest = ensure_template_revision(source=source, actor_id=context.owner.id)
    assert latest.id != old_revision.id
    plan = prepare_template_library_history(source=source, actor_id=context.owner.id)
    assert {revision.id for revision in DocumentTemplateRevision.objects.filter(template=source)} == set(
        plan.revision_ids
    )
    retained = retain_template_library_history(source=source, actor_id=context.owner.id, plan_sha256=plan.plan_sha256)
    repository = source.entity.workspace.repository
    assert retained.indexed
    historical = read_accepted_repository_file(
        repository_id=repository.id,
        path=f"template-snapshots/{old_revision.id}/fragments/{placement.block_id}.content",
    )
    assert original.encode() in historical
    assert read_accepted_repository_file(
        repository_id=repository.id,
        path=f"template-snapshots/{old_revision.id}/manifest.json",
    ).decode() == json.dumps(old_revision.manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    repeated = prepare_template_library_history(source=source, actor_id=context.owner.id)
    assert repeated.already_present
    assert (
        retain_template_library_history(
            source=source,
            actor_id=context.owner.id,
            plan_sha256=repeated.plan_sha256,
        ).commit
        == retained.commit
    )


def test_library_pin_can_select_an_applied_version_that_predates_git(indexed_library_source):
    from django.db import transaction

    from apps.core.content_profile import ParsedInclude
    from apps.core.documents import ensure_template_revision, update_shared_block
    from apps.core.repository_service import commit_repository_files, read_accepted_repository_file
    from apps.core.template_library_content import template_library_loader
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history

    context, documents, initial = indexed_library_source
    document = documents[2]
    placement = context.source.placements.get(position=1)
    original = placement.block.current_revision.markdown
    update_shared_block(
        placement=placement,
        actor_id=context.owner.id,
        markdown="New canonical template text.\n",
        base_revision_id=placement.block.current_revision_id,
    )
    ensure_template_revision(source=context.source, actor_id=context.owner.id)
    plan = prepare_template_library_history(source=context.source, actor_id=context.owner.id)
    retained = retain_template_library_history(
        source=context.source,
        actor_id=context.owner.id,
        plan_sha256=plan.plan_sha256,
    )
    repository = context.source.entity.workspace.repository
    canonical = read_accepted_repository_file(repository_id=repository.id, path=f"fragments/{placement.block_id}.md")
    advanced = commit_repository_files(
        repository_id=repository.id,
        expected_base=retained.commit,
        changes={
            f"fragments/{placement.block_id}.md": canonical.replace(
                original.encode(), b"New canonical template text.\n"
            )
        },
        message="Advance current source while retaining selected template version",
    )
    with transaction.atomic():
        selected_commit, parsed = template_library_loader(context.workspace.repository)(
            document.id,
            ParsedInclude(
                target_content_id=placement.block_id,
                mode="pinned",
                audience="shared",
                pinned_object_id=advanced.object_id,
                ordinal=1,
                library_workspace_id=context.source.entity.workspace_id,
                library_revision_id=document.template_enrollment.applied_revision_id,
            ),
        )
    assert selected_commit == advanced.object_id
    assert parsed.markdown == original
    assert advanced.object_id != initial


def test_library_include_cannot_widen_the_enrolled_placement_audience(indexed_library_source):
    from django.db import transaction

    from apps.core.content_index import ContentIndexValidationError

    context, documents, source_commit = indexed_library_source
    document = documents[1]
    placement = document.placements.get(block__source_document=context.source)
    placement.audience_profile = "msp_internal"
    placement.save(update_fields=("audience_profile", "updated_at"))
    repository, _ = _commit_library_client(context, document, source_commit, "live")
    with pytest.raises(ContentIndexValidationError), transaction.atomic():
        index_repository_content(repository_id=repository.id)


def test_library_projection_sql_cannot_change_the_enrolled_audience(indexed_library_source):
    from django.db import DatabaseError, transaction

    from apps.core.models import ContentInclude

    context, documents, source_commit = indexed_library_source
    document = documents[1]
    repository, _ = _commit_library_client(context, document, source_commit, "live")
    with transaction.atomic():
        index_repository_content(repository_id=repository.id)
    reference = ContentInclude.objects.get(source__content_id=document.id, ordinal=1)
    with pytest.raises(DatabaseError, match="enrolled library include scope mismatch"), transaction.atomic():
        ContentInclude.objects.filter(id=reference.id).update(audience_profile="msp_internal")


def test_approved_template_source_import_requires_retained_history_before_handoff(library_enrollments):
    from apps.core.document_migration_coexistence import document_coexistence_status
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
    from apps.core.workspaces import resolve_msp_workspace

    context, _documents = library_enrollments
    workspace = context.source.entity.workspace
    index_repository_content(repository_id=workspace.repository.id)
    plan = prepare_document_import(workspace=workspace, document_id=context.source.id)
    imported = apply_document_import(
        workspace=workspace,
        document_id=context.source.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=context.owner.id,
    )
    assert imported.status == "imported"
    before = document_coexistence_status(
        workspace=workspace,
        document=context.source,
        reader_workspace=resolve_msp_workspace(context.owner),
    )
    assert "template_history_git_custody_unavailable" in before["handoff_blockers"]
    history = prepare_template_library_history(source=context.source, actor_id=context.owner.id)
    assert retain_template_library_history(
        source=context.source,
        actor_id=context.owner.id,
        plan_sha256=history.plan_sha256,
    ).indexed
    after = document_coexistence_status(
        workspace=workspace,
        document=context.source,
        reader_workspace=resolve_msp_workspace(context.owner),
    )
    assert "template_history_git_custody_unavailable" not in after["handoff_blockers"]
    assert "template_parity_not_verified" not in after["handoff_blockers"]


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_client_library_migration_import_preserves_references_and_signed_history(indexed_library_source, mode):
    from django.db import transaction

    from apps.core.document_migration_coexistence import document_coexistence_status
    from apps.core.models import ContentInclude

    context, documents, source_commit = indexed_library_source
    document = documents[1 if mode == "live" else 2]
    retained = publish_document(
        workspace=context.reader,
        document=document,
        actor_id=context.owner.id,
        reason="Retain selected template reference",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    with transaction.atomic():
        plan = prepare_document_import(workspace=context.workspace, document_id=document.id)
        result = apply_document_import(
            workspace=context.workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=context.owner.id,
        )
    assert result.status == "imported"
    reference = ContentInclude.objects.get(source__content_id=document.id, ordinal=1)
    assert reference.library_workspace_id == context.source.entity.workspace_id
    assert reference.library_revision_id == document.template_enrollment.applied_revision_id
    assert reference.resolution_mode == mode
    assert reference.resolved_object_id == source_commit
    status = document_coexistence_status(
        workspace=context.workspace, document=document, reader_workspace=context.reader
    )
    assert status["content_copy_state"] == "in_sync"
    assert status["read_projection_state"] == "matched"
    assert verify_retained_publication_custody(retained)


def test_runtime_template_cohort_checks_each_client_scope_and_restores_caller_scope(
    library_enrollments, django_runtime_role
):
    from django.db import transaction

    from apps.core.document_template_migration import prepare_template_library_migration
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope, current_rls_tenant_id
    from apps.core.scoping import DataScope

    context, documents = library_enrollments
    source_workspace = context.source.entity.workspace
    scope = DataScope.tenant(context.source.tenant)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        assert not Document.objects.filter(id=documents[0].id).exists()
        plan = prepare_template_library_migration(
            source_workspace=source_workspace,
            source_document_id=context.source.id,
            destination_document_ids=tuple(document.id for document in documents),
            actor_id=context.owner.id,
        )
        assert set(plan.destination_document_ids) == {document.id for document in documents}
        assert not Document.objects.filter(id=documents[0].id).exists()
        assert current_rls_tenant_id() == str(context.source.tenant_id)


def test_runtime_library_authority_is_read_only_and_never_exposes_other_client_roots(
    library_enrollments, django_runtime_role
):
    from django.db import transaction

    from apps.accounts.models import BuiltInRole, TenantMembership
    from apps.core.models import DocumentAuthority, Tenant
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, _documents = library_enrollments
    private = create_document(
        tenant=context.source.tenant,
        organization=None,
        actor_id=context.owner.id,
        title="Private source fixture",
        markdown="Private fixture text.\n",
        is_template=True,
    )
    sibling = create_organization(
        tenant=context.source.tenant,
        actor_id=context.owner.id,
        name="Other library fixture",
        legal_name="",
        website="",
        classifications=[],
    )
    sibling_template = create_document(
        tenant=context.source.tenant,
        organization=sibling,
        actor_id=context.owner.id,
        title="Client-owned template fixture",
        markdown="Client fixture text.\n",
        is_template=True,
        library_visible=True,
    )
    other_tenant = Tenant.objects.create(name="Other library tenant", slug="other-library-tenant")
    other_actor = User.objects.create_user(email="other-library-owner@example.invalid", display_name="Other fixture")
    TenantMembership.objects.create(tenant=other_tenant, user=other_actor, role=BuiltInRole.ADMINISTRATOR)
    foreign = create_document(
        tenant=other_tenant,
        organization=None,
        actor_id=other_actor.id,
        title="Foreign library fixture",
        markdown="Foreign fixture text.\n",
        is_template=True,
        library_visible=True,
    )
    scope = DataScope.organization(context.source.tenant, context.document.organization)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope,
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        state = DocumentAuthority.objects.get(content_id=context.source.id)
        assert state.authority == "legacy"
        assert not DocumentAuthority.objects.filter(
            content_id__in=[private.id, sibling_template.id, foreign.id]
        ).exists()
        assert DocumentAuthority.objects.filter(pk=state.pk).update(authority="repository") == 0
    state.refresh_from_db()
    assert state.authority == "legacy"


def test_git_template_source_edit_advances_derived_workflow_snapshot(copied_enrollment):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.documents import template_rollout_preview
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
    from apps.core.workspaces import resolve_msp_workspace

    context = copied_enrollment
    source = context.source
    source.library_visible = True
    source.save(update_fields=("library_visible", "updated_at"))
    workspace = source.entity.workspace
    index_repository_content(repository_id=workspace.repository.id)
    imported = prepare_document_import(workspace=workspace, document_id=source.id)
    apply_document_import(
        workspace=workspace,
        document_id=source.id,
        actor_id=context.owner.id,
        expected_base=imported.base_commit,
        plan_sha256=imported.plan_sha256,
    )
    history = prepare_template_library_history(source=source, actor_id=context.owner.id)
    retain_template_library_history(source=source, actor_id=context.owner.id, plan_sha256=history.plan_sha256)
    reader = resolve_msp_workspace(context.owner)
    handoff = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id,),
        actor_id=context.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    transition_authority_group(
        workspace=workspace,
        document_ids=handoff.document_ids,
        actor_id=context.owner.id,
        target="repository",
        reader_workspace=reader,
        plan_sha256=handoff.plan_sha256,
    )
    block = source.placements.get(position=1).block
    before = block.current_revision_id
    content = read_authored_content(repository=workspace.repository, content_id=block.id)
    author_content(
        repository=workspace.repository,
        actor_id=context.owner.id,
        request_id=None,
        operation="update",
        content_id=block.id,
        base_commit=content.accepted_commit,
        base_blob=content.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Git-backed template update.\n",
        metadata_patch={},
    )
    block.refresh_from_db()
    assert block.current_revision_id != before
    assert block.current_revision.markdown == "Git-backed template update.\n"
    latest, preview = template_rollout_preview(
        enrollment=context.document.template_enrollment, actor_id=context.owner.id
    )
    assert latest.id != context.document.template_enrollment.applied_revision_id
    assert [item["source_block_id"] for item in preview["changed"]] == [str(block.entity_id)]

    from apps.core.documents import PlacementConflict
    from apps.core.repository_storage import resolve_managed_repository_path

    _root, repository_path = resolve_managed_repository_path(workspace.repository)
    unavailable = repository_path.with_name(repository_path.name + ".unavailable")
    repository_path.rename(unavailable)
    try:
        with pytest.raises(PlacementConflict, match="unavailable"):
            template_rollout_preview(enrollment=context.document.template_enrollment, actor_id=context.owner.id)
        assert verify_retained_publication_custody(context.publication)
    finally:
        unavailable.rename(repository_path)


def test_client_member_can_read_approved_enrolled_git_source(indexed_library_source, django_runtime_role):
    from django.db import transaction

    from apps.accounts.models import BuiltInRole, TenantMembership
    from apps.core.content_profile import ParsedInclude
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.template_library_content import template_library_loader

    context, documents, source_commit = indexed_library_source
    actor = User.objects.create_user(email="library-client-member@example.invalid", display_name="Client fixture")
    TenantMembership.objects.create(
        tenant=context.source.tenant, organization=context.document.organization,
        user=actor, role=BuiltInRole.CLIENT_ADMINISTRATOR,
    )
    document = documents[1]
    section = context.source.placements.get(position=1).block
    selected = ParsedInclude(
        target_content_id=section.id, mode="live", audience="shared", pinned_object_id="", ordinal=1,
        library_workspace_id=context.source.entity.workspace_id,
        library_revision_id=document.template_enrollment.applied_revision_id,
    )
    repository = context.workspace.repository
    scope = DataScope.organization(context.source.tenant, context.document.organization)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            scope, organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=actor.id, principal_mode=RLSPrincipalMode.USER,
        )
        commit, parsed = template_library_loader(repository)(document.id, selected)
        assert commit == source_commit
        assert parsed.markdown == "Copied enrollment instructions.\n"


def test_nested_source_parent_keeps_legacy_section_body_semantics(library_enrollments):
    from django.db import transaction

    from apps.core.document_migration_export import build_simple_document_export
    from apps.core.documents import resolve_document, update_shared_block
    from apps.core.models import ContentNode
    from apps.core.repository_service import commit_repository_files

    context, _documents = library_enrollments
    parent = context.source.placements.get(position=1)
    create_document_block(
        document=context.source, actor_id=context.owner.id, markdown="Original nested child.\n",
        kind="rich_text", name="Nested source child", parent_id=parent.id, position=0,
    )
    document = instantiate_document_template(
        source=context.source, tenant=context.source.tenant, organization=context.document.organization,
        actor_id=context.owner.id, title="Nested enrollment fixture", category="guide",
        placement_rules={str(parent.block.entity_id): "live"},
    )
    child_copy = document.placements.get(position=2)
    update_shared_block(
        placement=child_copy, actor_id=context.owner.id, markdown="Locally edited nested child.\n",
        base_revision_id=child_copy.block.current_revision_id,
    )
    source_export = build_simple_document_export(context.source)
    source_repository = context.source.entity.workspace.repository
    source_repository.refresh_from_db()
    commit_repository_files(
        repository_id=source_repository.id, expected_base=source_repository.accepted_commit.object_id,
        changes=dict(source_export.files), message="Retain nested source fixture",
    )
    index_repository_content(repository_id=source_repository.id)
    expected = resolve_document(document).markdown
    with transaction.atomic():
        plan = prepare_document_import(workspace=context.workspace, document_id=document.id)
        imported = apply_document_import(
            workspace=context.workspace, document_id=document.id, actor_id=context.owner.id,
            expected_base=plan.base_commit, plan_sha256=plan.plan_sha256,
        )
    assert imported.status == "imported"
    node = ContentNode.objects.get(workspace=context.workspace, content_id=document.id)
    assert node.composition_variants["all"]["markdown"] == expected
    assert expected.count("Locally edited nested child.") == 1
    assert "Original nested child." not in expected


@pytest.fixture
def prepared_template_library(library_enrollments):
    return _prepare_template_library(*library_enrollments)


def _prepare_template_library(context, documents):
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
    for enrolled in documents:
        if not DocumentPublication.objects.filter(document=enrolled).exists():
            retained = publish_document(
                workspace=context.reader, document=enrolled, actor_id=context.owner.id,
                reason="Retain enrollment before grouped migration", audience="msp_internal",
                retention="permanent", retention_review_on=None,
            )
            assert verify_retained_publication_custody(retained)
    source_workspace = context.source.entity.workspace
    for workspace, document in [(source_workspace, context.source)] + [(context.workspace, d) for d in documents]:
        index_repository_content(repository_id=workspace.repository.id)
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        result = apply_document_import(
            workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=context.owner.id,
        )
        assert result.indexed
        if document == context.source:
            history = prepare_template_library_history(source=document, actor_id=context.owner.id)
            assert retain_template_library_history(
                source=document, actor_id=context.owner.id, plan_sha256=history.plan_sha256,
            ).indexed
    return context, documents


def test_template_library_authority_handoff_promotes_source_and_all_clients_together(prepared_template_library):
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id,
        target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    assert transition_template_library_authority(**args, plan_sha256=plan.plan_sha256) == "transitioned"
    roots = {context.source.id, *(d.id for d in documents)}
    assert set(DocumentAuthority.objects.filter(content_id__in=roots).values_list("authority", flat=True)) == {
        "repository",
    }
    assert verify_retained_publication_custody(context.publication)



@pytest.mark.parametrize("side", ["source", "live_client"])
def test_template_source_cannot_roll_back_without_repository_live_clients(prepared_template_library, side):
    from django.db import IntegrityError

    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority
    from apps.core.workspaces import resolve_msp_workspace

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    with pytest.raises(IntegrityError, match="live repository consumers"):
        transition_document_authority(
            workspace=context.source.entity.workspace if side == "source" else context.workspace,
            document_id=context.source.id if side == "source" else documents[1].id, actor_id=context.owner.id,
            target="legacy",
            reader_workspace=resolve_msp_workspace(context.owner) if side == "source" else context.reader,
        )
    assert DocumentAuthority.objects.get(content_id=context.source.id).authority == "repository"


def test_template_library_group_can_roll_back_without_rewriting_signed_history(prepared_template_library):
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority

    context, documents = prepared_template_library
    before = (context.publication.signature, deepcopy(context.publication.manifest),
              read_publication_artifact(context.publication.artifacts.get(kind="pdf")))
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id,
    )
    plan = prepare_template_library_handoff(**args, target="repository")
    transition_template_library_authority(**args, target="repository", plan_sha256=plan.plan_sha256)
    rollback = prepare_template_library_handoff(**args, target="legacy")
    assert transition_template_library_authority(
        **args, target="legacy", plan_sha256=rollback.plan_sha256,
    ) == "transitioned"
    assert set(DocumentAuthority.objects.filter(
        content_id__in=[context.source.id, *(d.id for d in documents)],
    ).values_list("authority", flat=True)) == {"legacy"}
    context.publication.refresh_from_db()
    assert before == (context.publication.signature, context.publication.manifest,
                      read_publication_artifact(context.publication.artifacts.get(kind="pdf")))
    assert verify_retained_publication_custody(context.publication)


@pytest.mark.parametrize("failure", ["stale", "late"])
def test_template_cohort_failure_preserves_every_legacy_authority(prepared_template_library, monkeypatch, failure):
    from apps.core import document_authority_handoff
    from apps.core.document_template_migration import (
        TemplateMigrationError,
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    if failure == "stale":
        enrollment = documents[0].template_enrollment
        enrollment.last_applied_at = enrollment.last_applied_at.replace(microsecond=0)
        enrollment.save(update_fields=("last_applied_at", "updated_at"))
        expected = TemplateMigrationError
    else:
        original = document_authority_handoff._transition_document_authority_locked
        calls = 0

        def fail_after_transition(**kwargs):
            nonlocal calls
            result = original(**kwargs)
            calls += 1
            if calls == 2:
                raise ValueError("late cohort failure")
            return result

        monkeypatch.setattr(document_authority_handoff, "_transition_document_authority_locked", fail_after_transition)
        expected = ValueError
    with pytest.raises(expected):
        transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    assert set(DocumentAuthority.objects.filter(
        tenant_id=context.source.tenant_id,
    ).values_list("authority", flat=True)) == {"legacy"}
    assert verify_retained_publication_custody(context.publication)


def test_runtime_template_group_handoff_and_rollback_restore_msp_scope(prepared_template_library, django_runtime_role):
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id,
    )
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.tenant(context.source.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=context.owner.id, principal_mode=RLSPrincipalMode.USER,
        )
        for target in ("repository", "legacy"):
            reviewed = prepare_template_library_handoff(**args, target=target)
            assert transition_template_library_authority(
                **args, target=target, plan_sha256=reviewed.plan_sha256,
            ) == "transitioned"
            assert DocumentAuthority.objects.get(content_id=context.source.id).authority == target
            assert not Document.objects.filter(id=documents[0].id).exists()
    assert verify_retained_publication_custody(context.publication)


def test_missing_library_repository_is_retryable_and_never_uses_database_body(indexed_library_source, settings):
    from pathlib import Path

    from apps.core.content_read import RepositoryContentNotIndexed, document_detail
    from apps.core.repository_storage import repository_path

    context, documents, source_commit = indexed_library_source
    document = documents[1]
    repository, _commit = _commit_library_client(context, document, source_commit, "live")
    index_repository_content(repository_id=repository.id)
    source_repository = context.source.entity.workspace.repository
    path = repository_path(
        root=Path(settings.TEKDOCS_REPOSITORY_ROOT), repository_id=source_repository.id,
        storage_relative_path=source_repository.storage_relative_path,
    )
    retained = path.with_name(path.name + ".unavailable-fixture")
    path.rename(retained)
    try:
        with pytest.raises(RepositoryContentNotIndexed):
            document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
    finally:
        retained.rename(path)


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_promoted_template_client_publication_retains_offline_foreign_source_proof(
    prepared_template_library, mode, settings,
):
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    document = documents[1 if mode == "live" else 2]
    publication = publish_internal_git_document(
        workspace=context.reader, document=document, actor=context.owner, reason="Freeze approved template source",
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v8"
    foreign = [s for s in publication.manifest["git_source"]["sources"] if s.get("library_workspace")]
    assert len(foreign) == 1
    assert foreign[0]["library_workspace"] == str(context.source.entity.workspace_id)
    assert foreign[0]["template_revision"] == str(document.template_enrollment.applied_revision_id)
    assert foreign[0]["body_only"] is True
    assert verify_internal_git_publication(publication)
    from pathlib import Path

    from apps.core.document_shared_publications import verify_template_publication_manifest

    for key, bad in (
        ("body_only", False), ("template_revision", "invalid"), ("template_checksum", "invalid"),
        ("library_workspace", str(context.workspace.id)), ("repository_id", "invalid"),
        ("path", "docs/unrelated.md"), ("object_format", "invalid"),
    ):
        tampered = deepcopy(publication.manifest)
        selected = next(s for s in tampered["git_source"]["sources"] if s.get("library_workspace"))
        selected[key] = bad
        assert not verify_template_publication_manifest(tampered, document.id), key
    pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
    root = Path(settings.TEKDOCS_REPOSITORY_ROOT)
    unavailable = root.with_name(root.name + ".offline-fixture")
    root.rename(unavailable)
    try:
        assert verify_internal_git_publication(publication)
        assert read_publication_artifact(publication.artifacts.get(kind="pdf")) == pdf
    finally:
        unavailable.rename(root)


@pytest.mark.parametrize("field", ["template_revision", "repository_id", "library_workspace", "body_only", "path"])
def test_template_publication_sql_rejects_forged_library_proof(prepared_template_library, monkeypatch, field):
    from uuid import uuid4

    from django.db import ProgrammingError

    from apps.core import content_publication_sources
    from apps.core.document_git_publications import publish_internal_git_document
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    original = content_publication_sources._library_source_record

    def forged(**kwargs):
        record = original(**kwargs)
        record[field] = False if field == "body_only" else "fragments/unrelated.md" if field == "path" else str(uuid4())
        return record

    monkeypatch.setattr(content_publication_sources, "_library_source_record", forged)
    before = DocumentPublication.objects.filter(tenant_id=context.source.tenant_id).count()
    with pytest.raises(ProgrammingError, match="template Git publication source is invalid"):
        publish_internal_git_document(
            workspace=context.reader, document=documents[1], actor=context.owner, reason="Reject forged source proof",
        )
    assert DocumentPublication.objects.filter(tenant_id=context.source.tenant_id).count() == before
    assert verify_retained_publication_custody(context.publication)


def test_runtime_independent_copy_migrates_without_reading_hidden_source(copied_enrollment, django_runtime_role):
    from django.db import transaction

    from apps.core.document_template_models import DocumentTemplateRevision
    from apps.core.documents import ensure_template_revision
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context = copied_enrollment
    from apps.core.template_library_scope import editable_template_workspace_scope

    with editable_template_workspace_scope(context.source.entity.workspace, context.owner.id):
        source_primary = context.source.placements.get(position=0).block
        update_document(
            document=context.source, actor_id=context.owner.id, title=context.source.entity.display_name,
            markdown="Later private template definition.\n", base_revision_id=source_primary.current_revision_id,
            is_template=True,
        )
        unselected = ensure_template_revision(source=context.source, actor_id=context.owner.id)
    applied = context.document.template_enrollment.applied_revision_id
    assert unselected.id != applied
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.reader.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION, actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        assert not Document.objects.filter(pk=context.source.id).exists()
        assert DocumentTemplateRevision.objects.filter(pk=applied).exists()
        assert not DocumentTemplateRevision.objects.filter(pk=unselected.id).exists()
        plan = prepare_document_import(workspace=context.workspace, document_id=context.document.id)
        assert plan.export.template_enrollment_sha256

    from apps.core.serializers import DocumentSerializer

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.reader.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION, actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        own_document = Document.objects.get(pk=context.document.id)
        serializer = DocumentSerializer()
        assert serializer.get_template_source_id(own_document) is None
        assert serializer.get_template_enrollment_id(own_document) is not None
        assert serializer.get_template_applied_revision_id(own_document) == applied


def test_runtime_client_publishes_only_its_approved_template_composition(
    prepared_template_library, django_runtime_role,
):
    from apps.core.content_publication_sources import ContentPublicationSourceError, freeze_git_document_dependencies
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.reader.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION, actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        publication = publish_internal_git_document(
            workspace=context.reader, document=documents[1], actor=context.owner,
            reason="Publish authorized enrolled client composition",
        )
        assert verify_internal_git_publication(publication)
        with pytest.raises(ContentPublicationSourceError):
            freeze_git_document_dependencies(
                repository_id=context.source.entity.workspace.repository.id,
                content_id=context.source.id, audience="msp_internal",
            )
    assert verify_internal_git_publication(publication)


def test_copied_template_attachment_links_rebase_without_losing_lineage(copied_enrollment):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import create_document_attachment
    from apps.core.document_template_migration import template_enrollment_evidence

    context = copied_enrollment
    attachment = create_document_attachment(
        document=context.source, actor_id=context.owner.id,
        upload=SimpleUploadedFile("template-checklist.txt", b"Retained enrollment checklist.\n"),
    )
    update_document(
        document=context.source, actor_id=context.owner.id, title=context.source.entity.display_name,
        markdown=f"Source checklist.\n\n[Checklist](tekdocs://attachment/{attachment.entity_id})\n",
        base_revision_id=context.source.placements.get(position=0).block.current_revision_id, is_template=True,
    )
    document = instantiate_document_template(
        source=context.source, tenant=context.source.tenant, organization=context.reader.organization,
        actor_id=context.owner.id, title="Client copied checklist", category="guide",
    )
    owned = document.attachments.get()
    assert owned.entity_id != attachment.entity_id
    assert owned.checksum == attachment.checksum
    evidence = template_enrollment_evidence(document)
    assert evidence is not None and set(evidence.modes) == {"copy"}
    plan = prepare_document_import(workspace=context.workspace, document_id=document.id)
    assert plan.export.template_enrollment_sha256 == evidence.fingerprint


@pytest.mark.parametrize("runtime", [False, True])
def test_promoted_pinned_template_rollout_rebinds_selected_git_version(
    prepared_template_library, django_runtime_role, runtime,
):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.template_git_workflows import apply_git_template_rollout, preview_git_template_rollout

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    source_repository = context.source.entity.workspace.repository
    block = context.source.placements.get(position=1).block
    content = read_authored_content(repository=source_repository, content_id=block.id)
    author_content(
        repository=source_repository, actor_id=context.owner.id, request_id=None, operation="update",
        content_id=block.id, base_commit=content.accepted_commit, base_blob=content.source_blob,
        kind=None, path=None, title=None, markdown="Revised selected template instructions.\n", metadata_patch={},
    )
    local_block = documents[2].placements.get(position=0).block
    local_content = read_authored_content(repository=context.workspace.repository, content_id=local_block.id)
    author_content(
        repository=context.workspace.repository, actor_id=context.owner.id, request_id=None, operation="update",
        content_id=local_block.id, base_commit=local_content.accepted_commit, base_blob=local_content.source_blob,
        kind=None, path=None, title=None, markdown="Client locally edited introduction.\n", metadata_patch={},
    )
    from contextlib import nullcontext

    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    with (django_runtime_role() if runtime else nullcontext()), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.reader.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION, actor_user_id=context.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        document = documents[2]
        before = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
        preview = preview_git_template_rollout(document=document, actor_id=context.owner.id)
        apply_git_template_rollout(
            document=document, actor_id=context.owner.id, expected_base=preview["base_commit"],
            expected_composition=preview["composition_digest"],
            expected_applied_revision_id=document.template_enrollment.applied_revision_id,
            expected_available_revision=preview["available_revision"],
        )
        after = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
        assert "Copied enrollment instructions." in before["markdown"]
        assert "Revised selected template instructions." in after["markdown"]
        assert "Copied enrollment instructions." not in after["markdown"]
        assert "Client locally edited introduction." in after["markdown"]
    assert verify_retained_publication_custody(context.publication)
    rollback_args = {**args, "target": "legacy"}
    rollback = prepare_template_library_handoff(**rollback_args)
    assert transition_template_library_authority(
        **rollback_args, plan_sha256=rollback.plan_sha256,
    ) == "transitioned"
    from apps.core.documents import resolve_document

    legacy = resolve_document(documents[2]).markdown
    assert "Client locally edited introduction." in legacy
    assert "Revised selected template instructions." in legacy
    assert verify_retained_publication_custody(context.publication)


@pytest.mark.parametrize("stage", ["read", "set"])
def test_template_operation_setup_failure_cannot_authorize_a_later_transaction(
    copied_enrollment, monkeypatch, stage,
):
    from django.db import OperationalError, transaction
    from django.db.backends.utils import CursorWrapper

    from apps.core.template_git_operation import permits_template_document, template_git_operation

    context = copied_enrollment
    execute = CursorWrapper.execute

    def fail_setup(cursor, sql, params=None):
        operation = "current_setting" if stage == "read" else "set_config"
        if f"{operation}('tekdocs.template_document_write'" in sql:
            raise OperationalError("injected template lease setup failure")
        return execute(cursor, sql, params)

    with monkeypatch.context() as patch:
        patch.setattr(CursorWrapper, "execute", fail_setup)
        with pytest.raises(OperationalError, match="lease setup failure"), transaction.atomic():
            with template_git_operation(context.document, context.workspace.repository, context.source.id):
                pytest.fail("The failed setup must not enter the operation")
    with transaction.atomic():
        assert not permits_template_document(context.document)


def test_template_lease_without_matching_git_projection_cannot_commit(prepared_template_library):
    from django.db import IntegrityError

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.documents import apply_template_rollout, template_rollout_preview
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.template_git_operation import template_git_operation
    from apps.core.template_git_workflows import _locked_template_client
    from apps.core.template_library_scope import editable_template_workspace_scope

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    repository = context.source.entity.workspace.repository
    block = context.source.placements.get(position=1).block
    authored = read_authored_content(repository=repository, content_id=block.id)
    author_content(
        repository=repository, actor_id=context.owner.id, request_id=None, operation="update", content_id=block.id,
        base_commit=authored.accepted_commit, base_blob=authored.source_blob, kind=None, path=None, title=None,
        markdown="Source update for deferred graph proof.\n", metadata_patch={},
    )
    original = documents[2].template_enrollment.applied_revision_id
    with pytest.raises(IntegrityError, match="template graph must match"), coordinated_repository_transaction():
        with (
            editable_template_workspace_scope(context.workspace, context.owner.id),
            _locked_template_client(documents[2], context.owner.id) as (document, enrollment, repo),
            template_git_operation(documents[2], context.workspace.repository, context.source.id),
        ):
            latest, _preview = template_rollout_preview(enrollment=enrollment, actor_id=context.owner.id)
            apply_template_rollout(
                enrollment=enrollment, actor_id=context.owner.id,
                expected_applied_revision_id=original, expected_available_revision=latest.revision_number,
            )
    documents[2].template_enrollment.refresh_from_db()
    assert documents[2].template_enrollment.applied_revision_id == original


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_promoted_template_detach_preserves_selected_body_and_enrollment(prepared_template_library, mode):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.template_git_workflows import detach_git_template_section, preview_git_template_rollout

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    source_repository = context.source.entity.workspace.repository
    source_block = context.source.placements.get(position=1).block
    content = read_authored_content(repository=source_repository, content_id=source_block.id)
    author_content(
        repository=source_repository, actor_id=context.owner.id, request_id=None, operation="update",
        content_id=source_block.id, base_commit=content.accepted_commit, base_blob=content.source_blob,
        kind=None, path=None, title=None, markdown="Current live source at detach.\n", metadata_patch={},
    )
    document = documents[1 if mode == "live" else 2]
    enrollment_id, applied_id = document.template_enrollment.id, document.template_enrollment.applied_revision_id
    before = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")["markdown"]
    reviewed = preview_git_template_rollout(document=document, actor_id=context.owner.id)
    placement = document.placements.get(position=1)
    detached = detach_git_template_section(
        document=document, actor_id=context.owner.id, placement_id=placement.id,
        expected_base=reviewed["base_commit"], expected_composition=reviewed["composition_digest"],
        expected_applied_revision_id=applied_id,
    )
    assert detached.block.source_document_id == document.id
    assert detached.resolution_mode == "live" and detached.pinned_revision_id is None
    document.template_enrollment.refresh_from_db()
    assert (document.template_enrollment.id, document.template_enrollment.applied_revision_id) == (
        enrollment_id, applied_id,
    )
    detail = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
    assert detail["markdown"] == before
    mapped = document.template_enrollment.placement_map[1]
    assert mapped["mode"] == "copy" and mapped["forked_from"]["mode"] == mode
    assert verify_retained_publication_custody(context.publication)
    from apps.core.document_template_migration import TemplateMigrationError, template_enrollment_evidence

    mapping = deepcopy(document.template_enrollment.placement_map)
    changed = deepcopy(mapping)
    changed[1]["forked_from"]["commit"] = "0" * 40
    document.template_enrollment.placement_map = changed
    document.template_enrollment.save(update_fields=("placement_map", "updated_at"))
    try:
        with pytest.raises(TemplateMigrationError, match="mapping_invalid"):
            template_enrollment_evidence(document)
    finally:
        document.template_enrollment.placement_map = mapping
        document.template_enrollment.save(update_fields=("placement_map", "updated_at"))


@pytest.mark.parametrize("mode", ["copy", "live", "pinned"])
def test_promoted_template_can_create_an_enrolled_git_client(prepared_template_library, mode):
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import DocumentAuthority
    from apps.core.template_git_workflows import instantiate_git_template, template_definition_sha256

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    section = context.source.placements.get(position=1).block
    definition = template_definition_sha256(context.source)
    created = instantiate_git_template(
        source=context.source, workspace=context.workspace, actor_id=context.owner.id,
        title=f"New Git-backed {mode} enrollment", category="guide",
        placement_rules={str(section.entity_id): mode}, expected_source_sha256=definition,
    )
    assert created.template_enrollment.source_template_id == context.source.id
    assert created.template_enrollment.placement_map[1]["mode"] == mode
    assert DocumentAuthority.objects.get(content_id=created.id).authority == "repository"
    placement = created.placements.get(position=1)
    assert (placement.block.source_document_id == created.id) == (mode == "copy")
    assert placement.resolution_mode == ("pinned" if mode == "pinned" else "live")


def test_promoted_template_controls_require_the_source_migration(copied_enrollment):
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.documents import PlacementConflict
    from apps.core.template_git_workflows import preview_git_template_rollout

    context = copied_enrollment
    context.source.library_visible = True
    context.source.save(update_fields=("library_visible", "updated_at"))
    plan = prepare_document_import(workspace=context.workspace, document_id=context.document.id)
    apply_document_import(
        workspace=context.workspace, document_id=context.document.id, actor_id=context.owner.id,
        expected_base=plan.base_commit, plan_sha256=plan.plan_sha256,
    )
    transition_document_authority(
        workspace=context.workspace, document_id=context.document.id, actor_id=context.owner.id,
        target="repository", reader_workspace=context.reader,
    )
    index_repository_content(repository_id=context.source.entity.workspace.repository.id)
    with pytest.raises(PlacementConflict, match="source template must finish migration"):
        preview_git_template_rollout(document=context.document, actor_id=context.owner.id)


def test_template_source_publications_survive_migration_and_remain_publishable(copied_enrollment):
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
    from apps.core.workspaces import resolve_msp_workspace

    context = copied_enrollment
    reader = resolve_msp_workspace(context.owner)
    historical = publish_document(
        workspace=reader, document=context.source, actor_id=context.owner.id,
        reason="Retain original template publication",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    original = (deepcopy(historical.manifest), historical.signature,
                read_publication_artifact(historical.artifacts.get(kind="pdf")))
    source_workspace = context.source.entity.workspace
    for workspace, document in ((source_workspace, context.source), (context.workspace, context.document)):
        index_repository_content(repository_id=workspace.repository.id)
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        assert apply_document_import(
            workspace=workspace, document_id=document.id, actor_id=context.owner.id,
            expected_base=plan.base_commit, plan_sha256=plan.plan_sha256,
        ).indexed
        if document == context.source:
            history = prepare_template_library_history(source=document, actor_id=context.owner.id)
            assert retain_template_library_history(
                source=document, actor_id=context.owner.id, plan_sha256=history.plan_sha256,
            ).indexed
    args = dict(
        source_workspace=source_workspace, source_document_id=context.source.id,
        destination_document_ids=(context.document.id,), actor_id=context.owner.id, target="repository",
    )
    reviewed = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=reviewed.plan_sha256)
    historical.refresh_from_db()
    assert original == (historical.manifest, historical.signature,
                        read_publication_artifact(historical.artifacts.get(kind="pdf")))
    assert verify_retained_publication_custody(historical)
    current = publish_internal_git_document(
        workspace=reader, document=context.source, actor=context.owner, reason="Publish migrated template source",
    )
    assert current.manifest["template_source"]["content_id"] == str(context.source.id)
    assert verify_internal_git_publication(current)


def test_git_template_api_returns_review_fences_and_accepts_only_reviewed_apply(prepared_template_library):
    from django.test import Client
    from django.urls import reverse

    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    browser = Client()
    browser.force_login(context.owner)
    scope = {"organization_entity_id": context.reader.organization.entity_id}
    enrollment = documents[2].template_enrollment
    review = browser.post(
        reverse("organization-document-template-rollout-preview", kwargs=scope),
        {"enrollment_id": str(enrollment.id)}, content_type="application/json",
    )
    assert review.status_code == 200
    payload = review.json()
    assert len(payload["base_commit"]) == 40 and len(payload["composition_digest"]) == 64
    assert payload["reused_sections"][0]["mode"] == "pinned"
    values = {"enrollment_id": str(enrollment.id), "expected_applied_revision_id": payload["applied_revision_id"],
              "expected_available_revision": payload["available_revision"]}
    apply_url = reverse("organization-document-template-rollout-apply", kwargs=scope)
    assert browser.post(apply_url, values, content_type="application/json").status_code == 400
    applied = browser.post(apply_url, {
        **values, "expected_base": payload["base_commit"], "expected_composition": payload["composition_digest"],
    }, content_type="application/json")
    assert applied.status_code == 200 and applied.json()["up_to_date"]


def test_git_template_catalog_exposes_reviewed_choices_and_creates_only_reviewed_version(prepared_template_library):
    from django.test import Client
    from django.urls import reverse

    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    browser = Client()
    browser.force_login(context.owner)
    scope = {"organization_entity_id": context.reader.organization.entity_id}
    response = browser.get(reverse("organization-document-template-library", kwargs=scope))
    assert response.status_code == 200
    source = next(item for item in response.json()["results"] if item["id"] == str(context.source.entity_id))
    assert source["placement_count"] == 2
    assert len(source["definition_sha256"]) == 64 and source["source_state"] == "ready"
    assert not {"publications", "owner", "review_due_on", "attachments"}.intersection(source)
    url = reverse("organization-document-template-instantiate", kwargs=scope)
    values = {"source_document_id": source["id"], "title": "Reviewed API enrollment", "category": "guide"}
    assert browser.post(url, values, content_type="application/json").status_code == 400
    assert browser.post(url, {**values, "expected_source_sha256": "0" * 64},
                        content_type="application/json").status_code == 409
    created = browser.post(url, {**values, "expected_source_sha256": source["definition_sha256"]},
                           content_type="application/json")
    assert created.status_code == 201, created.content
    assert created.json()["content_authority"] == "repository"


@pytest.fixture
def promoted_file_template(copied_enrollment):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import create_document_attachment
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.rendering import render_pdf
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history

    context = copied_enrollment
    context.source.library_visible = True
    context.source.save(update_fields=("library_visible", "updated_at"))
    primary = create_document_attachment(
        document=context.source, actor_id=context.owner.id,
        upload=SimpleUploadedFile("template-v1.pdf", render_pdf("Template file first version.")),
        purpose="primary_file", version_number=1,
    )
    source_workspace = context.source.entity.workspace
    for workspace, document in ((source_workspace, context.source), (context.workspace, context.document)):
        index_repository_content(repository_id=workspace.repository.id)
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        assert apply_document_import(
            workspace=workspace, document_id=document.id, actor_id=context.owner.id,
            expected_base=plan.base_commit, plan_sha256=plan.plan_sha256,
        ).indexed
        if document == context.source:
            history = prepare_template_library_history(source=document, actor_id=context.owner.id)
            assert retain_template_library_history(
                source=document, actor_id=context.owner.id, plan_sha256=history.plan_sha256,
            ).indexed
    args = dict(
        source_workspace=source_workspace, source_document_id=context.source.id,
        destination_document_ids=(context.document.id,), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    return context, primary


def test_new_template_enrollment_preserves_primary_file_version_chain(promoted_file_template):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import append_repository_primary_document_file, copy_attachment_content
    from apps.core.rendering import render_pdf
    from apps.core.template_git_workflows import instantiate_git_template, template_definition_sha256

    context, first = promoted_file_template
    second = append_repository_primary_document_file(
        repository=context.source.entity.workspace.repository, content_id=context.source.id,
        actor_id=context.owner.id, expected_current_entity_id=first.entity_id,
        upload=SimpleUploadedFile("template-v2.pdf", render_pdf("Template file second version.")),
    )
    created = instantiate_git_template(
        source=context.source, workspace=context.workspace, actor_id=context.owner.id,
        title="Copied versioned template", category="guide", placement_rules={},
        expected_source_sha256=template_definition_sha256(context.source),
    )
    copied = list(created.attachments.filter(purpose="primary_file").order_by("version_number"))
    assert [item.version_number for item in copied] == [1, 2]
    assert copied[0].replaces_id is None and copied[1].replaces_id == copied[0].id
    assert [copy_attachment_content(item) for item in copied] == [
        copy_attachment_content(item) for item in (first, second)
    ]


def test_enrollment_files_follow_outer_transaction_outcome(promoted_file_template, settings):
    from pathlib import Path

    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.template_git_workflows import instantiate_git_template, template_definition_sha256

    context, _primary = promoted_file_template
    before = set(path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file())
    with pytest.raises(RuntimeError, match="later request failure"):
        with coordinated_repository_transaction():
            instantiate_git_template(
                source=context.source, workspace=context.workspace, actor_id=context.owner.id,
                title="Rolled back file template", category="guide", placement_rules={},
                expected_source_sha256=template_definition_sha256(context.source),
            )
            raise RuntimeError("later request failure")
    assert set(path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()) == before


def test_committed_enrollment_files_survive_later_commit_callback_failure(promoted_file_template):
    from django.db import transaction

    from apps.core.document_attachments import copy_attachment_content
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.template_git_workflows import instantiate_git_template, template_definition_sha256

    context, primary = promoted_file_template

    def fail_after_commit():
        raise RuntimeError("callback after durable commit")

    with pytest.raises(RuntimeError, match="callback after durable commit"):
        with coordinated_repository_transaction():
            transaction.on_commit(fail_after_commit)
            created = instantiate_git_template(
                source=context.source, workspace=context.workspace, actor_id=context.owner.id,
                title="Committed file template", category="guide", placement_rules={},
                expected_source_sha256=template_definition_sha256(context.source),
            )
    assert Document.objects.filter(pk=created.id).exists()
    copied = created.attachments.get(purpose="primary_file")
    assert copy_attachment_content(copied) == copy_attachment_content(primary)


def test_template_library_reuse_nested_under_client_owned_section(library_enrollments):
    from apps.core.content_read import document_detail
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )

    context, documents = library_enrollments
    for document in documents[1:]:
        borrowed = document.placements.get(position=1)
        borrowed.parent = document.placements.get(position=0)
        borrowed.position = 0
        borrowed.save(update_fields=("parent", "position", "updated_at"))
    _prepare_template_library(context, documents)
    from apps.core.content_composition import ContentCompositionError
    from apps.core.content_profile import ParsedInclude
    from apps.core.template_library_content import template_library_loader

    nested = documents[1].placements.get(parent__isnull=False)
    include = ParsedInclude(
        target_content_id=nested.block_id, mode="live", audience="shared", pinned_object_id="", ordinal=1,
        library_workspace_id=context.source.entity.workspace_id,
        library_revision_id=documents[1].template_enrollment.applied_revision_id,
    )
    with pytest.raises(ContentCompositionError, match="parent"):
        template_library_loader(context.workspace.repository)(documents[1].id, include)
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    for document in documents[1:]:
        detail = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
        assert "Copied enrollment instructions." in detail["markdown"]
        assert document.placements.get(parent__isnull=False).parent_id == document.placements.get(parent=None).id


@pytest.mark.parametrize("mode", ["live", "pinned"])
@pytest.mark.parametrize("operation", ["detach", "publish"])
def test_nested_template_section_supports_detach_and_publication(library_enrollments, mode, operation):
    from apps.core.content_read import document_detail
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.template_git_workflows import detach_git_template_section, preview_git_template_rollout

    context, documents = library_enrollments
    document = documents[1 if mode == "live" else 2]
    borrowed = document.placements.get(position=1)
    borrowed.parent = document.placements.get(position=0)
    borrowed.position = 0
    borrowed.save(update_fields=("parent", "position", "updated_at"))
    _prepare_template_library(context, documents)
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(item.id for item in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    before = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")["markdown"]
    if operation == "detach":
        reviewed = preview_git_template_rollout(document=document, actor_id=context.owner.id)
        detached = detach_git_template_section(
            document=document, actor_id=context.owner.id, placement_id=borrowed.id,
            expected_base=reviewed["base_commit"], expected_composition=reviewed["composition_digest"],
            expected_applied_revision_id=document.template_enrollment.applied_revision_id,
        )
        assert detached.parent_id == borrowed.parent_id
        assert detached.block.source_document_id == document.id
    else:
        retained = publish_document(
            workspace=context.reader, document=document, actor_id=context.owner.id,
            reason="Freeze nested selected template section", audience="msp_internal",
            retention="permanent", retention_review_on=None,
        )
        assert verify_retained_publication_custody(retained)
    after = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
    assert after["markdown"] == before
    assert verify_retained_publication_custody(context.publication)


def test_operator_command_reviews_and_transitions_the_explicit_template_cohort(prepared_template_library):
    from io import StringIO

    from django.core.management import call_command

    context, documents = prepared_template_library
    arguments = ["--workspace", str(context.source.entity.workspace_id), "--source", str(context.source.id),
                 "--actor", str(context.owner.id)]
    for document in documents:
        arguments.extend(("--document", str(document.id)))

    def invoke(*extra):
        output = StringIO()
        call_command("transition_template_library_authority", *arguments, *extra, stdout=output)
        return json.loads(output.getvalue())

    plan = invoke("--authority", "repository")
    assert plan["status"] == "prepared" and len(plan["plan_sha256"]) == 64
    assert invoke("--authority", "repository", "--apply", "--plan-sha256", "0" * 64)["status"] == "blocked"
    assert invoke("--authority", "repository", "--apply", "--plan-sha256", plan["plan_sha256"]) == {
        "status": "transitioned", "authority": "repository",
    }
    rollback = invoke("--authority", "legacy")
    assert invoke("--authority", "legacy", "--apply", "--plan-sha256", rollback["plan_sha256"]) == {
        "status": "transitioned", "authority": "legacy",
    }


@pytest.mark.parametrize("mode", ["copy", "live", "pinned"])
def test_assigned_workspace_editor_creates_and_detaches_template_without_msp_write(
    prepared_template_library, django_runtime_role, mode,
):
    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
    )
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.template_git_workflows import (
        detach_git_template_section,
        instantiate_git_template,
        preview_git_template_rollout,
        template_definition_sha256,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    actor = User.objects.create_user(email="enrolling-client@example.invalid", display_name="Enrolling client")
    membership = TenantMembership.objects.create(
        tenant=context.source.tenant, user=actor, role=BuiltInRole.CONTRIBUTOR,
        workspace_scope=MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=context.source.tenant, organization=context.document.organization,
        membership=membership, created_by=context.owner,
    )
    TOTP.activate(actor, generate_totp_secret())
    definition = template_definition_sha256(context.source)
    block = context.source.placements.get(position=1).block
    context.source.entity.workspace.repository.refresh_from_db()
    source_head = context.source.entity.workspace.repository.accepted_commit_id
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.document.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=actor.id, principal_mode=RLSPrincipalMode.USER,
        )
        created = instantiate_git_template(
            source=context.source, workspace=context.workspace, actor_id=actor.id,
            title="Client authorized enrollment", category="guide", placement_rules={str(block.entity_id): mode},
            expected_source_sha256=definition,
        )
        if mode != "copy":
            preview = preview_git_template_rollout(document=created, actor_id=actor.id)
            detached = detach_git_template_section(
                document=created, placement_id=created.placements.get(position=1).id, actor_id=actor.id,
                expected_base=preview["base_commit"], expected_composition=preview["composition_digest"],
                expected_applied_revision_id=created.template_enrollment.applied_revision_id,
            )
            assert detached.block.source_document_id == created.id
    context.source.entity.workspace.repository.refresh_from_db()
    assert context.source.entity.workspace.repository.accepted_commit_id == source_head


def test_template_library_recovery_restores_foreign_git_and_signed_pdf_custody(
    prepared_template_library, tmp_path, settings,
):
    import shutil
    from io import StringIO
    from pathlib import Path

    from django.core.management import call_command
    from django.test import override_settings

    from apps.core.content_read import document_detail
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_recovery import (
        create_repository_recovery_archive,
        restore_repository_recovery_archive,
        verify_repository_recovery_database,
    )

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    current = publish_internal_git_document(
        workspace=context.reader, document=documents[1], actor=context.owner,
        reason="Recover enrolled library proof",
    )
    signed = (deepcopy(current.manifest), current.signature,
              read_publication_artifact(current.artifacts.get(kind="pdf")))
    prior_pdf = read_publication_artifact(context.publication.artifacts.get(kind="pdf"))
    archive = tmp_path / "repository-recovery.tar"
    manifest = create_repository_recovery_archive(archive)
    assert len(manifest["repositories"]) == 2
    restored = tmp_path / "restored-repositories"
    restored_media = tmp_path / "restored-media"
    restore_repository_recovery_archive(archive, restored)
    shutil.copytree(Path(settings.MEDIA_ROOT), restored_media)
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(restored), MEDIA_ROOT=str(restored_media)):
        assert verify_repository_recovery_database(archive) == manifest
        for workspace in (context.source.entity.workspace, context.workspace):
            index_repository_content(repository_id=workspace.repository.id, force=True)
        for document in documents[1:]:
            detail = document_detail(workspace=context.reader, content_id=document.id, audience="msp_internal")
            assert "Copied enrollment instructions." in detail["markdown"]
        current.refresh_from_db()
        assert signed == (current.manifest, current.signature,
                          read_publication_artifact(current.artifacts.get(kind="pdf")))
        assert verify_internal_git_publication(current)
        assert verify_retained_publication_custody(context.publication)
        assert read_publication_artifact(context.publication.artifacts.get(kind="pdf")) == prior_pdf
        call_command("verify_recovery_publications", stdout=StringIO())
        call_command("verify_recovery_managed_files", stdout=StringIO())


def test_template_api_missing_source_git_returns_retryable_conflict_without_cached_choices(prepared_template_library):
    from django.test import Client
    from django.urls import reverse

    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_storage import resolve_managed_repository_path
    from apps.core.template_git_workflows import template_definition_sha256

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    definition = template_definition_sha256(context.source)
    browser = Client(raise_request_exception=False)
    browser.force_login(context.owner)
    scope = {"organization_entity_id": context.reader.organization.entity_id}
    _root, path = resolve_managed_repository_path(context.source.entity.workspace.repository)
    unavailable = path.with_name(path.name + ".unavailable")
    path.rename(unavailable)
    try:
        catalog = browser.get(reverse("organization-document-template-library", kwargs=scope))
        assert catalog.status_code == 200
        source = next(item for item in catalog.json()["results"] if item["id"] == str(context.source.entity_id))
        assert source["source_state"] == "unavailable" and source["placements"] == []
        create = browser.post(reverse("organization-document-template-instantiate", kwargs=scope), {
            "source_document_id": str(context.source.entity_id), "title": "Missing source must not create",
            "category": "guide", "expected_source_sha256": definition,
        }, content_type="application/json")
        assert create.status_code == 409
        preview = browser.post(reverse("organization-document-template-rollout-preview", kwargs=scope), {
            "enrollment_id": str(documents[1].template_enrollment.id),
        }, content_type="application/json")
        assert preview.status_code == 409
        assert not Document.objects.filter(entity__display_name="Missing source must not create").exists()
    finally:
        unavailable.rename(path)


def test_template_schema_upgrade_preserves_enrollment_and_publication_history(library_enrollments):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.document_template_models import DocumentTemplateEnrollment

    context, documents = library_enrollments
    original = {
        item.id: (item.applied_revision_id, deepcopy(item.placement_map))
        for item in DocumentTemplateEnrollment.objects.filter(destination_document__in=documents)
    }
    pdf = read_publication_artifact(context.publication.artifacts.get(kind="pdf"))
    executor = MigrationExecutor(connection)
    head = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("core", "0200_shared_live_writer_guard")])
        MigrationExecutor(connection).migrate(head)
        for item in DocumentTemplateEnrollment.objects.filter(destination_document__in=documents):
            assert original[item.id] == (item.applied_revision_id, item.placement_map)
        assert verify_retained_publication_custody(context.publication)
        assert read_publication_artifact(context.publication.artifacts.get(kind="pdf")) == pdf
        _prepare_template_library(context, documents)
        args = dict(
            source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
            destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id,
        )
        plan = prepare_template_library_handoff(**args, target="repository")
        transition_template_library_authority(**args, target="repository", plan_sha256=plan.plan_sha256)
        rollback = prepare_template_library_handoff(**args, target="legacy")
        transition_template_library_authority(**args, target="legacy", plan_sha256=rollback.plan_sha256)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_history_operator_prepares_and_retains_reviewed_source_snapshots(copied_enrollment):
    from io import StringIO

    from django.core.management import call_command

    context = copied_enrollment
    repository = context.source.entity.workspace.repository
    index_repository_content(repository_id=repository.id)
    arguments = ["--workspace", str(repository.workspace_id), "--source", str(context.source.id),
                 "--actor", str(context.owner.id)]

    def invoke(*extra):
        output = StringIO()
        call_command("retain_template_library_history", *arguments, *extra, stdout=output)
        return json.loads(output.getvalue())

    plan = invoke()
    assert plan["status"] == "prepared" and plan["missing_files"] > 0
    assert invoke("--apply", "--plan-sha256", "0" * 64)["status"] == "blocked"
    applied = invoke("--apply", "--plan-sha256", plan["plan_sha256"])
    assert applied["status"] == "retained" and applied["indexed"]
    assert invoke()["missing_files"] == 0


def test_enrollment_registers_files_before_a_later_database_failure(promoted_file_template, monkeypatch, settings):
    from pathlib import Path

    from django.db import transaction
    from django.db.transaction import TransactionManagementError

    from apps.core import documents
    from apps.core.template_git_workflows import instantiate_git_template, template_definition_sha256

    context, _primary = promoted_file_template
    definition = template_definition_sha256(context.source)
    before = {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}
    original = documents.instantiate_document_template

    def later_database_failure(**kwargs):
        created = original(**kwargs)
        transaction.set_rollback(True)
        return created

    monkeypatch.setattr(documents, "instantiate_document_template", later_database_failure)
    with pytest.raises(TransactionManagementError):
        instantiate_git_template(
            source=context.source, workspace=context.workspace, actor_id=context.owner.id,
            title="Enrollment aborted after copy", category="guide", placement_rules={},
            expected_source_sha256=definition,
        )
    assert {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("link_kind", ["file", "escaped_file", "key", "entity", "inert", "copied_introduction"])
def test_live_template_source_cannot_accept_file_links_that_strand_enrolled_clients(library_enrollments, link_kind):
    from contextlib import nullcontext

    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_attachments import create_document_attachment
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_service import RepositoryInputError

    context, documents = library_enrollments
    file = create_document_attachment(
        document=context.source, actor_id=context.owner.id,
        upload=SimpleUploadedFile("source-only-checklist.txt", b"Source owned fixture checklist.\n"),
    )
    _prepare_template_library(context, documents)
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    repository = context.source.entity.workspace.repository
    block = context.source.placements.get(position=0 if link_kind == "copied_introduction" else 1).block
    content = read_authored_content(repository=repository, content_id=block.id)
    bodies = {
        "file": f"[Source-only file](tekdocs://attachment/{file.entity_id})\n",
        "escaped_file": f"[Source-only file](tekdocs://attach&#109;ent/{file.entity_id})\n",
        "key": "[Source key](tekdocs://key/fixture.value)\n",
        "entity": f"[Source entity](tekdocs://entity/{context.source.entity_id})\n",
        "inert": f"Copied enrollment instructions.\n\n`[Example](tekdocs://attachment/{file.entity_id})`\n",
        "copied_introduction": f"[Owned introduction file](tekdocs://attachment/{file.entity_id})\n",
    }
    expected = nullcontext() if link_kind in {"inert", "copied_introduction"} else pytest.raises(
        RepositoryInputError, match="template",
    )
    with expected:
        author_content(
            repository=repository, actor_id=context.owner.id, request_id=None, operation="update",
            content_id=block.id, base_commit=content.accepted_commit, base_blob=content.source_blob,
            kind=None, path=None, title=None,
            markdown=bodies[link_kind], metadata_patch={},
        )
    assert "Copied enrollment instructions." in document_detail(
        workspace=context.reader, content_id=documents[1].id, audience="msp_internal",
    )["markdown"]


@pytest.mark.parametrize("damage", ["checksum", "unknown_revision", "older_definition"])
def test_source_template_publication_sql_rejects_unbound_definition(prepared_template_library, monkeypatch, damage):
    from uuid import uuid4

    from django.db import ProgrammingError

    from apps.core import documents as document_services
    from apps.core.document_git_publications import publish_internal_git_document
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.document_template_models import DocumentTemplateRevision
    from apps.core.workspaces import resolve_msp_workspace

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    original = document_services.ensure_template_revision

    def forged(**kwargs):
        version = original(**kwargs)
        if damage == "older_definition":
            old = DocumentTemplateRevision.objects.filter(template=context.source).order_by("revision_number").first()
            assert old.id != version.id
            return old
        if damage == "checksum":
            version.checksum = "0" * 64
        else:
            version.id = uuid4()
        return version

    monkeypatch.setattr(document_services, "ensure_template_revision", forged)
    before = DocumentPublication.objects.filter(document=context.source).count()
    with pytest.raises(ProgrammingError, match="template Git publication source is invalid"):
        publish_internal_git_document(
            workspace=resolve_msp_workspace(context.owner), document=context.source, actor=context.owner,
            reason="Refuse unbound source definition",
        )
    assert DocumentPublication.objects.filter(document=context.source).count() == before


def test_assigned_editor_reviews_changed_source_and_updates_existing_pin(
    prepared_template_library, django_runtime_role,
):
    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
    )
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.template_git_workflows import apply_git_template_rollout, preview_git_template_rollout

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    actor = User.objects.create_user(email="assigned-template-reviewer@example.invalid", display_name="Assigned editor")
    membership = TenantMembership.objects.create(
        tenant=context.source.tenant, user=actor, role=BuiltInRole.CONTRIBUTOR,
        workspace_scope=MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=context.source.tenant, organization=context.document.organization,
        membership=membership, created_by=context.owner,
    )
    TOTP.activate(actor, generate_totp_secret())
    repository = context.source.entity.workspace.repository
    block = context.source.placements.get(position=1).block
    content = read_authored_content(repository=repository, content_id=block.id)
    author_content(
        repository=repository, actor_id=context.owner.id, request_id=None, operation="update",
        content_id=block.id, base_commit=content.accepted_commit, base_blob=content.source_blob,
        kind=None, path=None, title=None, markdown="Reviewed MSP source update.\n", metadata_patch={},
    )
    repository.refresh_from_db()
    source_head = repository.accepted_commit_id
    document = documents[2]
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.organization(context.source.tenant, context.document.organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=actor.id, principal_mode=RLSPrincipalMode.USER,
        )
        preview = preview_git_template_rollout(document=document, actor_id=actor.id)
        assert preview["available_revision"] > preview["current_revision"]
        result = apply_git_template_rollout(
            document=document, actor_id=actor.id, expected_base=preview["base_commit"],
            expected_composition=preview["composition_digest"],
            expected_applied_revision_id=document.template_enrollment.applied_revision_id,
            expected_available_revision=preview["available_revision"],
        )
        assert result["up_to_date"]
    repository.refresh_from_db()
    assert repository.accepted_commit_id == source_head
    assert document.placements.get(position=1).pinned_revision.markdown == "Reviewed MSP source update.\n"


@pytest.mark.parametrize("denial", ["read_only", "missing_mfa", "other_client", "other_tenant", "portal"])
def test_git_template_api_denials_preserve_the_complete_graph(prepared_template_library, denial):
    from allauth.mfa.models import Authenticator
    from django.test import Client
    from django.urls import reverse

    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
    )
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.models import Tenant
    from apps.core.template_git_workflows import preview_git_template_rollout, template_definition_sha256

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    document = documents[2]
    enrollment = document.template_enrollment
    reviewed = preview_git_template_rollout(document=document, actor_id=context.owner.id)
    definition = template_definition_sha256(context.source)
    before = (enrollment.applied_revision_id, deepcopy(enrollment.placement_map), Document.objects.count())
    context.workspace.repository.refresh_from_db()
    head = context.workspace.repository.accepted_commit_id
    if denial == "missing_mfa":
        actor = context.owner
        Authenticator.objects.filter(user=actor).delete()
    else:
        actor = User.objects.create_user(email="denied-template-action@example.invalid", display_name="Denied fixture")
        tenant = context.source.tenant
        if denial == "other_tenant":
            tenant = Tenant.objects.create(name="Other template fixture tenant", slug="other-template-fixture-tenant")
        member = TenantMembership.objects.create(
            tenant=tenant, user=actor,
            organization=context.document.organization if denial == "portal" else None,
            role=(BuiltInRole.CLIENT_ADMINISTRATOR if denial == "portal"
                  else BuiltInRole.READ_ONLY if denial == "read_only" else BuiltInRole.CONTRIBUTOR),
            workspace_scope=(MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS if denial == "other_client"
                             else MembershipWorkspaceScope.TENANT),
        )
        if denial == "other_client":
            other = create_organization(
                tenant=tenant, actor_id=context.owner.id, name="Other assigned template client",
                legal_name="", website="", classifications=["client"],
            )
            OrganizationAccessAssignment.objects.create(
                tenant=tenant, organization=other, membership=member, created_by=context.owner,
            )
        TOTP.activate(actor, generate_totp_secret())
    browser = Client()
    browser.force_login(actor)
    scope = {"organization_entity_id": context.reader.organization.entity_id}
    values = {"enrollment_id": str(enrollment.id), "expected_applied_revision_id": str(enrollment.applied_revision_id),
              "expected_available_revision": reviewed["available_revision"],
              "expected_base": reviewed["base_commit"], "expected_composition": reviewed["composition_digest"]}
    for route, kwargs, payload in (
        ("organization-document-template-instantiate", scope, {
            "source_document_id": str(context.source.entity_id), "title": "Denied enrollment must not exist",
            "category": "guide", "expected_source_sha256": definition,
        }),
        ("organization-document-template-rollout-preview", scope, {"enrollment_id": str(enrollment.id)}),
        ("organization-document-template-rollout-apply", scope, values),
        ("organization-document-placement-detach", {
            **scope, "document_entity_id": document.entity_id, "placement_id": document.placements.get(position=1).id,
        }, {key: values[key] for key in ("expected_applied_revision_id", "expected_base", "expected_composition")}),
    ):
        response = browser.post(reverse(route, kwargs=kwargs), payload, content_type="application/json")
        # Workspace resolution conceals staff scopes without edit permission.
        expected_status = 404 if denial in {"read_only", "other_client"} else 403
        assert response.status_code == expected_status, (route, response.status_code)
    enrollment.refresh_from_db()
    assert before == (enrollment.applied_revision_id, enrollment.placement_map, Document.objects.count())
    context.workspace.repository.refresh_from_db()
    assert context.workspace.repository.accepted_commit_id == head


@pytest.mark.parametrize("damage", ["order", "depth", "audience", "duplicate", "taxonomies"])
def test_source_template_certificate_binds_the_complete_blueprint(prepared_template_library, monkeypatch, damage):
    import hashlib

    from django.db import ProgrammingError

    from apps.core import documents as document_services
    from apps.core.document_git_publications import publish_internal_git_document
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.document_template_models import DocumentTemplateRevision
    from apps.core.publications import canonical_json
    from apps.core.workspaces import resolve_msp_workspace

    context, documents = prepared_template_library
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    current = document_services.ensure_template_revision(source=context.source, actor_id=context.owner.id)
    manifest = deepcopy(current.manifest)
    if damage == "order":
        manifest["blocks"].reverse()
    elif damage == "depth":
        manifest["blocks"][1]["depth"] = 1
    elif damage == "audience":
        manifest["blocks"][1]["audience_profile"] = "msp_internal"
    elif damage == "duplicate":
        manifest["blocks"][1] = deepcopy(manifest["blocks"][0])
    else:
        manifest["taxonomies"] = [{"taxonomy_key": "unselected", "taxonomy_version": 1,
                                  "label": "Unselected fixture taxonomy", "terms": []}]
    def forged_definition(**kwargs):
        # Inject at certificate construction, after the independent retained-history
        # gate. The database must still reject a mismatched newly returned blueprint.
        return DocumentTemplateRevision.objects.create(
            tenant=context.source.tenant, template=context.source, revision_number=current.revision_number + 1,
            manifest=manifest, checksum=hashlib.sha256(canonical_json(manifest)).hexdigest(), created_by=context.owner,
        )

    monkeypatch.setattr(document_services, "ensure_template_revision", forged_definition)
    with pytest.raises(ProgrammingError, match="template Git publication source is invalid"):
        publish_internal_git_document(
            workspace=resolve_msp_workspace(context.owner), document=context.source, actor=context.owner,
            reason="Refuse a different template blueprint",
        )


def test_source_certificate_accepts_current_nested_layout_and_taxonomy_selection(library_enrollments):
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_template_migration import (
        prepare_template_library_handoff,
        transition_template_library_authority,
    )
    from apps.core.documents import ensure_template_revision
    from apps.core.taxonomies import assign_document_terms, create_taxonomy
    from apps.core.workspaces import resolve_msp_workspace

    context, documents = library_enrollments
    section = context.source.placements.get(position=1)
    section.parent = context.source.placements.get(position=0)
    section.position = 0
    section.save(update_fields=("parent", "position", "updated_at"))
    taxonomy = create_taxonomy(
        tenant=context.source.tenant, actor_id=context.owner.id, key="template-proof-tags", binding="document_tags",
        label="Template proof tags", description="Fixture taxonomy", allow_local_terms=False,
        terms=[{"stable_key": "zulu-key", "label": "Alpha label", "sort_order": 0},
               {"stable_key": "alpha-key", "label": "Zulu label", "sort_order": 0}],
    )
    assign_document_terms(
        document=context.source, term_ids=list(taxonomy.current_version.terms.values_list("id", flat=True)),
        actor_id=context.owner.id,
    )
    ensure_template_revision(source=context.source, actor_id=context.owner.id)
    _prepare_template_library(context, documents)
    args = dict(
        source_workspace=context.source.entity.workspace, source_document_id=context.source.id,
        destination_document_ids=tuple(d.id for d in documents), actor_id=context.owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**args)
    transition_template_library_authority(**args, plan_sha256=plan.plan_sha256)
    publication = publish_internal_git_document(
        workspace=resolve_msp_workspace(context.owner), document=context.source, actor=context.owner,
        reason="Retain current ordered template and taxonomy",
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v8"
    assert verify_internal_git_publication(publication)


def test_source_template_publication_preserves_all_primary_file_versions(promoted_file_template, django_runtime_role):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import append_repository_primary_document_file
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.rendering import render_pdf
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope
    from apps.core.workspaces import resolve_msp_workspace

    context, first = promoted_file_template
    second = append_repository_primary_document_file(
        repository=context.source.entity.workspace.repository, content_id=context.source.id,
        actor_id=context.owner.id, expected_current_entity_id=first.entity_id,
        upload=SimpleUploadedFile("source-primary-v2.pdf", render_pdf("Second retained source version.")),
    )
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.tenant(context.source.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=context.owner.id, principal_mode=RLSPrincipalMode.USER,
        )
        publication = publish_internal_git_document(
            workspace=resolve_msp_workspace(context.owner), document=context.source, actor=context.owner,
            reason="Retain both source-template primary versions",
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v8"
        assert {item["id"] for item in publication.manifest["managed_files"]} == {
            str(first.entity_id), str(second.entity_id),
        }
        assert verify_internal_git_publication(publication)
