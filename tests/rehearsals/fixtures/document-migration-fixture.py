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


def records():
    owner = User.objects.get(email=os.environ["TEKDOCS_FIXTURE_EMAIL"])
    tenant = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID).tenant
    source = Document.objects.get(tenant=tenant, entity__display_name=SOURCE_TITLE)
    target = Document.objects.get(tenant=tenant, entity__display_name=TARGET_TITLE)
    template = Document.objects.get(tenant=tenant, entity__display_name=TEMPLATE_TITLE)
    workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
    return owner, workspace, source, target, template


def identities(source, target, template):
    return {
        "source": str(source.id),
        "source_block": str(source.placements.get().block_id),
        "source_revision": str(source.placements.get().block.current_revision_id),
        "target": str(target.id),
        "target_revision": str(target.placements.get(position=0).block.current_revision_id),
        "template": str(template.id),
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
    from apps.core.content_index import index_repository_content
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

    owner, workspace, source, target, template = records()
    index_repository_content(repository_id=workspace.repository.id)
    inventory = inventory_legacy_documents(workspace)
    rows = {row["document_id"]: row for row in inventory["documents"]}
    assert rows[str(source.id)]["disposition"] == "simple_candidate"
    assert rows[str(target.id)]["reasons"] == ["cross_document_source_unavailable"]
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
    assert apply_document_import(
        workspace=workspace,
        document_id=target.id,
        expected_base=target_preview.base_commit,
        plan_sha256=target_preview.plan_sha256,
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
            },
            sort_keys=True,
        )
    )
else:
    raise AssertionError("Unknown fixture mode")
