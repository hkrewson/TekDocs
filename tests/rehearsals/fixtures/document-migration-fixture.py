"""Fresh and 0.8.46-upgraded first-wave document-copy acceptance fixture."""

import hashlib
import json
import os

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.documents import add_document_placement, create_document, resolve_document
from apps.core.models import Document, InstallationState, PlacementResolutionMode, Workspace, WorkspaceKind


SOURCE_TITLE = "Migration rehearsal source"
TARGET_TITLE = "Migration rehearsal target"
TEMPLATE_TITLE = "Migration rehearsal deferred template"
PINNED_TITLE = "Migration rehearsal pinned consumer"


def original_evidence(document):
    from apps.core import publications

    publication = document.publications.order_by("published_at", "id").first()
    assert publication is not None and publications.verify_publication(publication)["valid"]
    # Creation also runs on 0.8.46, before the full custody helper existed.
    for artifact in publication.artifacts.all():
        publications.read_publication_artifact(artifact)
    if hasattr(publications, "verify_retained_publication_custody"):
        assert publications.verify_retained_publication_custody(publication)
    return {
        "id": str(publication.id), "signature": publication.signature,
        "manifest": hashlib.sha256(json.dumps(publication.manifest, sort_keys=True).encode()).hexdigest(),
        "pdf": hashlib.sha256(publications.read_publication_artifact(publication.artifacts.get(kind="pdf"))).hexdigest(),
    }


def records():
    owner = User.objects.get(email=os.environ["TEKDOCS_FIXTURE_EMAIL"])
    tenant = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID).tenant
    source = Document.objects.get(tenant=tenant, entity__display_name=SOURCE_TITLE)
    target = Document.objects.get(tenant=tenant, entity__display_name=TARGET_TITLE)
    template = Document.objects.get(tenant=tenant, entity__display_name=TEMPLATE_TITLE)
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    return owner, workspace, source, target, template


def identities(source, target, template):
    pinned = Document.objects.get(tenant=source.tenant, organization=source.organization, entity__display_name=PINNED_TITLE)
    return {
        "source": str(source.id),
        "source_block": str(source.placements.get().block_id),
        "source_revision": str(source.placements.get().block.current_revision_id),
        "target": str(target.id),
        "target_revision": str(target.placements.get(position=0).block.current_revision_id),
        "template": str(template.id),
        "pinned": str(pinned.id),
        "pinned_revision": str(pinned.placements.get(resolution_mode="pinned").pinned_revision_id),
        "publications": [original_evidence(document) for document in (source, target, pinned)],
    }


mode = os.environ["TEKDOCS_FIXTURE_MODE"]
if mode == "create":
    installation = bootstrap_owner(
        tenant_name="Migration rehearsal MSP",
        owner_email=os.environ["TEKDOCS_FIXTURE_EMAIL"],
        owner_display_name="Migration Rehearsal Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    source = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title=SOURCE_TITLE,
        markdown="Reusable setup instructions\n",
    )
    target = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title=TARGET_TITLE,
        markdown="Target introduction\n",
    )
    add_document_placement(
        document=target,
        source_document=source,
        actor_id=installation.owner.id,
        resolution_mode=PlacementResolutionMode.LIVE,
        pinned_revision_id=None,
        parent_id=None,
        position=1,
    )
    pinned = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title=PINNED_TITLE, markdown="Pinned introduction\n",
    )
    add_document_placement(
        document=pinned, source_document=source, actor_id=installation.owner.id,
        resolution_mode=PlacementResolutionMode.PINNED,
        pinned_revision_id=source.placements.get().block.current_revision_id, parent_id=None, position=1,
    )
    from apps.core.publications import publish_document
    from apps.core.workspaces import resolve_msp_workspace

    for document in (source, target, pinned):
        publish_document(
            workspace=resolve_msp_workspace(installation.owner), document=document, actor_id=installation.owner.id,
            reason="Retain pre-upgrade shared instructions", audience="msp_internal",
            retention="permanent", retention_review_on=None,
        )
    template = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title=TEMPLATE_TITLE,
        markdown="Template content\n",
        is_template=True,
    )
    print(json.dumps(identities(source, target, template), sort_keys=True))
elif mode == "identity":
    _owner, _workspace, source, target, template = records()
    assert InstallationState.objects.get(pk=InstallationState.SINGLETON_ID).is_bootstrapped
    assert resolve_document(source).markdown == "Reusable setup instructions\n"
    assert resolve_document(target).markdown == "Target introduction\n\nReusable setup instructions\n"
    print(json.dumps(identities(source, target, template), sort_keys=True))
elif mode == "exercise":
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_index import index_repository_content
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.document_git_publications import publish_internal_git_document, verify_internal_git_publication
    from apps.core.document_migration_coexistence import _document_copy_status
    from apps.core.document_migration_import import (
        DocumentMigrationBlocked,
        apply_document_import,
        prepare_document_import,
        rollback_document_import,
    )
    from apps.core.document_migration_inventory import inventory_legacy_documents
    from apps.core.models import AuditEvent, ContentNode
    from apps.core.repository_service import read_repository_markdown_files_at_commit
    from apps.core.workspaces import resolve_msp_workspace

    owner, workspace, source, target, template = records()
    TOTP.activate(owner, generate_totp_secret())
    index_repository_content(repository_id=workspace.repository.id)
    inventory = inventory_legacy_documents(workspace)
    rows = {row["document_id"]: row for row in inventory["documents"]}
    assert rows[str(source.id)]["disposition"] == "simple_candidate"
    # Signed-history parity also needs the borrowed source to have a Git copy.
    assert rows[str(target.id)]["reasons"] == [
        "cross_document_source_unavailable", "publication_parity_required"
    ], rows[str(target.id)]["reasons"]
    assert "template" in rows[str(template.id)]["reasons"]

    source_preview = prepare_document_import(workspace=workspace, document_id=source.id)
    assert source_preview.plan_sha256 == prepare_document_import(
        workspace=workspace, document_id=source.id
    ).plan_sha256
    try:
        apply_document_import(
            workspace=workspace,
            document_id=source.id,
            expected_base=source_preview.base_commit,
            plan_sha256="0" * 64,
            actor_id=owner.id,
        )
    except DocumentMigrationBlocked as exc:
        assert exc.codes == ("preview_changed",)
    else:
        raise AssertionError("A stale preview unexpectedly imported")
    assert not ContentNode.objects.filter(repository=workspace.repository, content_id=source.id).exists()

    source_import = apply_document_import(
        workspace=workspace,
        document_id=source.id,
        expected_base=source_preview.base_commit,
        plan_sha256=source_preview.plan_sha256,
        actor_id=owner.id,
    )
    assert source_import.status == "imported"
    source_status = _document_copy_status(workspace=workspace, document=source)
    assert source_status["content_copy_state"] == "in_sync"
    assert source_status["legacy_authoritative"] is True
    assert source_status["cutover_ready"] is False
    target_preview = prepare_document_import(workspace=workspace, document_id=target.id)
    assert target_preview.plan_sha256 == prepare_document_import(
        workspace=workspace, document_id=target.id
    ).plan_sha256
    target_import = apply_document_import(
        workspace=workspace,
        document_id=target.id,
        expected_base=target_preview.base_commit,
        plan_sha256=target_preview.plan_sha256,
        actor_id=owner.id,
    )
    assert target_import.status == "imported"
    target_status = _document_copy_status(workspace=workspace, document=target)
    assert target_status["content_copy_state"] == "in_sync"
    assert target_status["legacy_authoritative"] is True
    assert target_status["cutover_ready"] is False
    assert ContentNode.objects.get(repository=workspace.repository, content_id=target.id).composition_variants[
        "all"
    ]["markdown"] == resolve_document(target).markdown
    # Retained-history imports bind even idempotent retries to the current commit.
    try:
        apply_document_import(
            workspace=workspace, document_id=target.id,
            expected_base=target_preview.base_commit, plan_sha256=target_preview.plan_sha256,
            actor_id=owner.id,
        )
    except DocumentMigrationBlocked as exc:
        assert exc.codes == ("preview_changed",)
    else:
        raise AssertionError("A publication-bearing stale retry unexpectedly succeeded")
    present_preview = prepare_document_import(workspace=workspace, document_id=target.id)
    assert apply_document_import(
        workspace=workspace,
        document_id=target.id,
        expected_base=present_preview.base_commit,
        plan_sha256=present_preview.plan_sha256,
        actor_id=owner.id,
    ).status == "already_present"

    target_rollback = rollback_document_import(
        workspace=workspace,
        document_id=target.id,
        expected_commit=target_import.commit,
        actor_id=owner.id,
    )
    assert target_rollback.status == "rolled_back"
    source_rollback = rollback_document_import(
        workspace=workspace,
        document_id=source.id,
        expected_commit=target_rollback.commit,
        actor_id=owner.id,
    )
    assert source_rollback.status == "rolled_back"
    assert not ContentNode.objects.filter(repository=workspace.repository, content_id__in=(source.id, target.id)).exists()
    _historical_commit, historical_files = read_repository_markdown_files_at_commit(
        repository_id=workspace.repository.id, object_id=target_import.commit
    )
    assert f"docs/{target.id}.md" in dict(historical_files)
    assert AuditEvent.objects.filter(tenant=workspace.tenant, action="content.migration_import").count() == 2
    assert AuditEvent.objects.filter(tenant=workspace.tenant, action="content.migration_rollback").count() == 2
    assert source.placements.get().block.current_revision_id is not None
    assert target.placements.get(position=0).block.current_revision_id is not None
    # Re-import the shared group, retaining a legacy pinned-only consumer until
    # its own reviewed transition. Then prove live/pinned behavior and rollback.
    pinned = Document.objects.get(tenant=source.tenant, organization=source.organization, entity__display_name=PINNED_TITLE)
    before = [original_evidence(document) for document in (source, target, pinned)]
    for document in (source, target, pinned):
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        apply_document_import(
            workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=owner.id,
        )
    reader = resolve_msp_workspace(owner)
    group_ids = (source.id, target.id, pinned.id)
    group = prepare_authority_group(
        workspace=workspace, document_ids=group_ids, actor_id=owner.id, target="repository", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=group.document_ids, actor_id=owner.id, target="repository",
        reader_workspace=reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None, markdown="Migrated shared instructions\n", metadata_patch={},
    )
    snapshots = []
    for document, expected in (
        (target, "Target introduction\n\nMigrated shared instructions\n"),
        (pinned, "Pinned introduction\n\nReusable setup instructions\n"),
    ):
        snapshot = publish_internal_git_document(
            workspace=reader, document=document, actor=owner, reason="Retain upgraded shared composition",
            supersedes_entity_id=document.publications.order_by("published_at", "id").first().entity_id,
        )
        assert snapshot.manifest["format"] == "tekdocs-static-publication/v7"
        assert snapshot.canonical_markdown == expected
        assert verify_internal_git_publication(snapshot)
        snapshots.append(snapshot)
    group = prepare_authority_group(
        workspace=workspace, document_ids=group_ids, actor_id=owner.id, target="legacy", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=group.document_ids, actor_id=owner.id, target="legacy",
        reader_workspace=reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"
    assert resolve_document(target).markdown == "Target introduction\n\nMigrated shared instructions\n"
    assert resolve_document(pinned).markdown == "Pinned introduction\n\nReusable setup instructions\n"
    assert [original_evidence(document) for document in (source, target, pinned)] == before
    assert all(verify_internal_git_publication(snapshot) for snapshot in snapshots)
    print(
        json.dumps(
            {
                "documents": inventory["document_count"],
                "deferred_template": True,
                "source_markdown_sha256": hashlib.sha256(resolve_document(source).markdown.encode()).hexdigest(),
                "target_markdown_sha256": hashlib.sha256(resolve_document(target).markdown.encode()).hexdigest(),
                "imported": 2,
                "rolled_back": 2,
                "legacy_authoritative": target_status["legacy_authoritative"],
                "shared_authority_round_trip": True,
                "pinned_markdown_sha256": hashlib.sha256(resolve_document(pinned).markdown.encode()).hexdigest(),
            },
            sort_keys=True,
        )
    )
else:
    raise AssertionError("Unknown fixture mode")
