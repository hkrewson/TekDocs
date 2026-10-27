"""Publication-bearing migration through supported operator/service boundaries."""

import uuid

import pytest
from django.db import transaction

from apps.core.content_index import index_repository_content
from apps.core.document_migration_import import DocumentMigrationBlocked, prepare_document_import
from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import create_document, update_document
from apps.core.models import DocumentAuthority, DocumentPublication, Tenant, Workspace
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, withdraw_publication
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


def test_published_document_migrates_publishes_and_rolls_back_without_rewriting_history(published_context):
    from copy import deepcopy

    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import
    from apps.core.documents import resolve_document
    from apps.core.publications import read_publication_artifact, verify_retained_publication_custody

    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    reader = resolve_msp_workspace(installation.owner)
    retained = (deepcopy(original.manifest), original.signature, original.content_digest)
    pdf = read_publication_artifact(original.artifacts.get())
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title="Retained guide",
        markdown="Draft after publication.\n",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
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
    assert (
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
        )
        == "transitioned"
    )
    fragment = read_authored_content(repository=workspace.repository, content_id=document.placements.get().block_id)
    author_content(
        repository=workspace.repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="New Git instructions.\n",
        metadata_patch={},
    )
    newer = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Updated Git instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    assert newer.canonical_markdown == "New Git instructions.\n"
    original.refresh_from_db()
    assert original.lifecycle_state == "superseded"
    withdraw_publication(publication=newer, actor_id=installation.owner.id, reason="Retain withdrawn history")
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
    assert resolve_document(document).markdown == "New Git instructions.\n"
    assert (
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
        )
        == "transitioned"
    )
    original.refresh_from_db()
    assert (original.manifest, original.signature, original.content_digest) == retained
    assert read_publication_artifact(original.artifacts.get()) == pdf
    assert verify_retained_publication_custody(original)
    assert verify_retained_publication_custody(newer)


@pytest.mark.parametrize("actor_kind", ["read_only", "missing_mfa", "foreign_tenant"])
def test_publication_history_import_requires_authorized_mfa_actor(published_context, actor_kind):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.document_migration_import import apply_document_import

    installation, workspace, document, _original = published_context
    actor = installation.owner
    if actor_kind != "missing_mfa":
        actor = User.objects.create_user(email=f"denied-{uuid.uuid4()}@example.invalid")
        tenant = installation.tenant if actor_kind == "read_only" else Tenant.objects.create(name="Other fixture")
        TenantMembership.objects.create(
            tenant=tenant,
            user=actor,
            role=BuiltInRole.READ_ONLY if actor_kind == "read_only" else BuiltInRole.ADMINISTRATOR,
        )
        TOTP.activate(actor, generate_totp_secret())
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    with pytest.raises(DocumentMigrationBlocked, match="publication_migration_not_authorized"):
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=actor.id,
        )
    workspace.repository.refresh_from_db()
    assert workspace.repository.accepted_commit.object_id == plan.base_commit
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"


@pytest.mark.parametrize("already_copied", [False, True])
def test_history_changes_invalidate_preview_even_for_existing_copy(published_context, already_copied):
    import json
    from io import StringIO

    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
    from django.core.management import call_command

    from apps.core.document_migration_import import apply_document_import

    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    output = StringIO()
    call_command("preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output)
    assert json.loads(output.getvalue())["plan_sha256"] == plan.plan_sha256
    if already_copied:
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        )
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
    withdraw_publication(publication=original, actor_id=installation.owner.id, reason="Control changed after preview")
    refreshed = prepare_document_import(workspace=workspace, document_id=document.id)
    assert refreshed.base_commit == plan.base_commit
    assert refreshed.plan_sha256 != plan.plan_sha256
    with pytest.raises(DocumentMigrationBlocked, match="preview_changed"):
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        )
    workspace.repository.refresh_from_db()
    assert workspace.repository.accepted_commit.object_id == plan.base_commit


@pytest.mark.parametrize("stage", ["promotion", "publication", "rollback"])
def test_damaged_history_blocks_each_handoff_stage(published_context, stage):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
    from apps.core.document_migration_import import apply_document_import
    from apps.core.publications import PublicationConflict, read_publication_artifact

    installation, workspace, document, original = published_context
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
    if stage != "promotion":
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
        )
    artifact = original.artifacts.get()
    pdf = read_publication_artifact(artifact)
    try:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(b"Corrupted synthetic retained PDF")
        if stage == "publication":
            with pytest.raises(PublicationConflict, match="history"):
                publish_document(
                    workspace=reader,
                    document=document,
                    actor_id=installation.owner.id,
                    reason="Must be refused",
                    audience="msp_internal",
                    retention="permanent",
                    retention_review_on=None,
                )
        else:
            with pytest.raises(DocumentAuthorityHandoffError, match="legacy_publication_history_present"):
                transition_document_authority(
                    workspace=workspace,
                    document_id=document.id,
                    actor_id=installation.owner.id,
                    target="repository" if stage == "promotion" else "legacy",
                    reader_workspace=reader,
                )
        assert DocumentPublication.objects.filter(document=document).count() == 1
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == (
            "legacy" if stage == "promotion" else "repository"
        )
    finally:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(pdf)


def test_history_bearing_copy_can_be_removed_without_removing_publication(published_context):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.core.document_migration_import import apply_document_import, rollback_document_import
    from apps.core.publications import read_publication_artifact, verify_retained_publication_custody

    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    pdf = read_publication_artifact(original.artifacts.get())
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    copied = apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    result = rollback_document_import(
        workspace=workspace, document_id=document.id, expected_commit=copied.commit, actor_id=installation.owner.id
    )
    assert result.status == "rolled_back" and result.indexed
    assert read_publication_artifact(original.artifacts.get()) == pdf
    assert verify_retained_publication_custody(original)
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"


def test_runtime_owner_can_migrate_publish_and_reverse_history(published_context, django_runtime_role):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import
    from apps.core.publications import verify_retained_publication_custody

    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    reader = resolve_msp_workspace(installation.owner)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=installation.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        assert apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        ).indexed
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="repository",
                reader_workspace=reader,
            )
            == "transitioned"
        )
        newer = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Runtime successor",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
            supersedes_entity_id=original.entity_id,
        )
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
        assert verify_retained_publication_custody(original)
        assert verify_retained_publication_custody(newer)
        legacy_successor = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Legacy successor after rollback",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
            supersedes_entity_id=newer.entity_id,
        )
        assert verify_retained_publication_custody(legacy_successor)
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="repository",
                reader_workspace=reader,
            )
            == "transitioned"
        )


def test_history_migration_refuses_actor_assigned_to_another_client(published_context):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
        User,
    )
    from apps.core.document_migration_import import apply_document_import
    from apps.core.workspaces import resolve_organization_workspace

    installation, _workspace, _document, _original = published_context
    organizations = [
        create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name=name,
            legal_name="",
            website="",
            classifications=["client"],
        )
        for name in ("Target fixture", "Other fixture")
    ]
    target, other = organizations
    workspace = Workspace.objects.get(organization=target)
    index_repository_content(repository_id=workspace.repository.id)
    document = create_document(
        tenant=installation.tenant,
        organization=target,
        actor_id=installation.owner.id,
        title="Client retained guide",
        markdown="Client instructions.\n",
    )
    publish_document(
        workspace=resolve_organization_workspace(installation.owner, entity_id=target.entity_id),
        document=document,
        actor_id=installation.owner.id,
        reason="Client fixture internal history",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    actor = User.objects.create_user(email=f"assigned-{uuid.uuid4()}@example.invalid")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=actor,
        role=BuiltInRole.ADMINISTRATOR,
        workspace_scope=MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant, organization=other, membership=membership, created_by=installation.owner
    )
    TOTP.activate(actor, generate_totp_secret())
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    with pytest.raises(DocumentMigrationBlocked, match="publication_migration_not_authorized"):
        apply_document_import(
            workspace=workspace,
            document_id=document.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=actor.id,
        )
    workspace.repository.refresh_from_db()
    assert workspace.repository.accepted_commit.object_id == plan.base_commit


@pytest.mark.parametrize("target", ["repository", "legacy"])
@pytest.mark.parametrize("actor_kind", ["read_only", "reader_mismatch"])
def test_history_authority_transition_enforces_operator_and_reader_identity(published_context, target, actor_kind):
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
    from apps.core.document_migration_import import apply_document_import

    installation, workspace, document, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    owner_reader = resolve_msp_workspace(installation.owner)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    if target == "legacy":
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=owner_reader,
        )
    actor = User.objects.create_user(email=f"reader-{uuid.uuid4()}@example.invalid")
    TenantMembership.objects.create(tenant=installation.tenant, user=actor, role=BuiltInRole.READ_ONLY)
    TOTP.activate(actor, generate_totp_secret())
    with pytest.raises(DocumentAuthorityHandoffError, match="publication_migration_not_authorized"):
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=actor.id if actor_kind == "read_only" else installation.owner.id,
            target=target,
            reader_workspace=resolve_msp_workspace(actor),
        )
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == (
        "legacy" if target == "repository" else "repository"
    )


def test_valid_history_with_review_retention_still_requires_broader_parity(published_context):
    from datetime import timedelta

    from django.utils import timezone

    installation, workspace, document, original = published_context
    publish_document(
        workspace=resolve_msp_workspace(installation.owner),
        document=document,
        actor_id=installation.owner.id,
        reason="Review retention fixture",
        audience="msp_internal",
        retention="review_on",
        retention_review_on=timezone.localdate() + timedelta(days=30),
        supersedes_entity_id=original.entity_id,
    )
    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"
    with pytest.raises(DocumentMigrationBlocked, match="publication_parity_required"):
        prepare_document_import(workspace=workspace, document_id=document.id)
