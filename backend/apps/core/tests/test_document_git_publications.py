from __future__ import annotations

import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import override_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import document_migration_import, repository_storage
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_index import index_repository_content
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import create_document, resolve_document
from apps.core.models import InstallationState, Workspace, WorkspaceKind
from apps.core.publications import (
    PublicationConflict,
    publish_document,
    verify_retained_publication_custody,
    withdraw_publication,
)
from apps.core.workspaces import resolve_msp_workspace

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def promoted(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"), MEDIA_ROOT=str(tmp_path / "media")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Internal Git publication fixture",
            owner_email=f"git-static-{uuid.uuid4()}@example.invalid",
            owner_display_name="Fixture owner",
            password="MigrationPassword-2026!",
        )
        TOTP.activate(installation.owner, generate_totp_secret())
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        repository = workspace.repository
        index_repository_content(repository_id=repository.id)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Internal guide",
            markdown="Legacy instructions.\n",
        )
        plan = document_migration_import.prepare_document_import(workspace=workspace, document_id=document.id)
        document_migration_import.apply_document_import(
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
        yield installation, workspace, repository, document, reader


def edit_fragment(context, markdown):
    installation, _workspace, repository, document, _reader = context
    fragment = read_authored_content(repository=repository, content_id=document.placements.get().block_id)
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


def test_internal_git_publication_survives_edits_controls_and_rollback(promoted):
    installation, workspace, _repository, document, reader = promoted
    edited = edit_fragment(promoted, "Git-authored instructions.\n")
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain current Git instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert publication.canonical_markdown == "Git-authored instructions.\n"
    assert publication.manifest["git_source"]["accepted_commit"] == edited.accepted_commit
    assert verify_internal_git_publication(publication)
    first_digest = publication.content_digest
    edit_fragment(promoted, "Later Git instructions.\n")
    newer = publish_internal_git_document(
        workspace=reader,
        document=document,
        actor=installation.owner,
        reason="Retain correction",
        supersedes_entity_id=publication.entity_id,
    )
    withdraw_publication(publication=newer, actor_id=installation.owner.id, reason="Stop distribution")
    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"
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
    document.refresh_from_db()
    assert resolve_document(document).markdown == "Later Git instructions.\n"
    publication.refresh_from_db()
    newer.refresh_from_db()
    assert publication.content_digest == first_digest
    assert publication.canonical_markdown == "Git-authored instructions.\n"
    assert verify_internal_git_publication(publication)
    assert verify_internal_git_publication(newer)
    assert newer.lifecycle_state == "withdrawn"
    assert verify_retained_publication_custody(publication)


@pytest.mark.parametrize("mode", ["stale", "reference", "client"])
def test_unsupported_publication_leaves_no_snapshot(promoted, mode):
    installation, _workspace, repository, document, reader = promoted
    from apps.core.models import DocumentPublication

    if mode == "stale":
        repository.indexed_commit = None
        repository.save(update_fields=["indexed_commit"])
    if mode == "reference":
        edit_fragment(promoted, "Unfrozen link: [asset](tekdocs://entity/00000000-0000-4000-8000-000000000001).\n")
    with pytest.raises(PublicationConflict):
        publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Unsupported attempt",
            audience="client_visible" if mode == "client" else "msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert not DocumentPublication.objects.filter(document=document).exists()


def test_damaged_snapshot_blocks_rollback(promoted):
    installation, workspace, _repository, document, reader = promoted
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
    from apps.core.models import DocumentAuthority

    publication = publish_internal_git_document(
        workspace=reader,
        document=document,
        actor=installation.owner,
        reason="Retain snapshot",
    )
    artifact = publication.artifacts.get()
    with artifact.file.storage.open(artifact.file.name, "rb") as stream:
        original = stream.read()
    try:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(b"Damaged fixture PDF")
        with pytest.raises(DocumentAuthorityHandoffError, match="legacy_publication_history_present"):
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="legacy",
                reader_workspace=reader,
            )
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "repository"
    finally:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(original)


def test_publication_permission_and_workspace_are_enforced(promoted):
    from rest_framework.exceptions import PermissionDenied

    from apps.accounts.models import User
    from apps.core.organizations import create_organization
    from apps.core.workspaces import resolve_organization_workspace

    installation, _workspace, _repository, document, reader = promoted
    outsider = User.objects.create_user(
        email=f"outsider-{uuid.uuid4()}@example.invalid", password="FixturePassword-2026!"
    )
    with pytest.raises(PermissionDenied):
        publish_internal_git_document(workspace=reader, document=document, actor=outsider, reason="Denied")
    other = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling fixture",
        legal_name="",
        website="",
        classifications=[],
    )
    wrong_workspace = resolve_organization_workspace(installation.owner, entity_id=other.entity_id)
    with pytest.raises(PublicationConflict, match="scope"):
        publish_internal_git_document(
            workspace=wrong_workspace,
            document=document,
            actor=installation.owner,
            reason="Wrong workspace",
        )


def test_internal_git_publication_requires_mfa_before_creating_snapshot(promoted):
    from allauth.mfa.models import Authenticator

    from apps.accounts.policy import PrivilegedMFARequired
    from apps.core.models import DocumentAuthority, DocumentPublication, DocumentPublicationArtifact

    installation, workspace, _repository, document, reader = promoted
    Authenticator.objects.filter(user=installation.owner).delete()
    with pytest.raises(PrivilegedMFARequired):
        publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="MFA must precede publication",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert not DocumentPublication.objects.filter(document=document).exists()
    assert not DocumentPublicationArtifact.objects.exists()
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "repository"


def test_guard_upgrade_cycle_retains_snapshots_and_restores_head(promoted):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.models import DocumentPublication

    installation, _workspace, _repository, document, reader = promoted
    publication = publish_internal_git_document(
        workspace=reader,
        document=document,
        actor=installation.owner,
        reason="Retained through guard migration",
    )
    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0195_retained_asset_supplier_anchor")])
        assert DocumentPublication.objects.get(pk=publication.pk).content_digest == publication.content_digest
    finally:
        MigrationExecutor(connection).migrate(head)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication()'::regprocedure)")
        assert "tekdocs-static-publication/v5" in cursor.fetchone()[0]
    assert verify_internal_git_publication(publication)


def test_database_rejects_stale_git_source_metadata(promoted):
    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity

    installation, workspace, _repository, document, reader = promoted
    publication = publish_internal_git_document(
        workspace=reader,
        document=document,
        actor=installation.owner,
        reason="Current source",
    )
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        entity_type="document_publication",
        display_name="Rejected fixture",
        visibility="msp_private",
    )
    values = {
        field.attname: getattr(publication, field.attname)
        for field in DocumentPublication._meta.concrete_fields
        if field.name not in {"id", "entity"}
    }
    publication_id = uuid.uuid4()
    values["manifest"] = {
        **publication.manifest,
        "publication_id": str(publication_id),
        "publication_entity_id": str(entity.id),
        "git_source": {**publication.manifest["git_source"], "accepted_commit": "0" * 40},
    }
    with pytest.raises(DatabaseError, match="internal Git publication source is invalid"), transaction.atomic():
        DocumentPublication.objects.create(id=publication_id, entity=entity, **values)
    assert DocumentPublication.objects.filter(document=document).count() == 1


def test_authenticated_publication_endpoint_uses_git_content(promoted):
    from django.test import Client
    from django.urls import reverse

    from apps.core.models import DocumentPublication

    installation, _workspace, _repository, document, _reader = promoted
    edit_fragment(promoted, "API Git snapshot body.\n")
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.post(
        reverse("msp-document-publication-list-create", kwargs={"document_entity_id": document.entity_id}),
        data={"reason": "Publish Git snapshot", "audience": "msp_internal", "retention": "permanent"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    publication = DocumentPublication.objects.get(document=document)
    assert publication.canonical_markdown == "API Git snapshot body.\n"
    assert verify_internal_git_publication(publication)


def test_runtime_role_can_publish_only_in_its_bound_scope(promoted, django_runtime_role):
    from django.db import transaction

    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    installation, _workspace, _repository, document, reader = promoted
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=installation.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        publication = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Runtime role Git snapshot",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert verify_internal_git_publication(publication)


def test_stale_approved_review_cannot_publish_changed_git(promoted):
    from apps.core.document_operations import decide_document_review, request_document_review

    installation, _workspace, _repository, document, reader = promoted
    request_document_review(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reviewer_id=installation.owner.id,
        note="Review current Git text",
    )
    decide_document_review(
        document=document,
        actor_id=installation.owner.id,
        decision="approved",
        note="Current text approved",
    )
    edit_fragment(promoted, "Unreviewed replacement text.\n")
    with pytest.raises(PublicationConflict, match="review"):
        publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Stale approval attempt",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
