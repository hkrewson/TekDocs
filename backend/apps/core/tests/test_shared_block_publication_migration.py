"""Shared live/pinned content crosses the same operator boundaries as ordinary content."""

from copy import deepcopy

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.documents import add_document_placement, create_document
from apps.core.publications import publish_document, read_publication_artifact, verify_retained_publication_custody
from apps.core.workspaces import resolve_msp_workspace

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("mode", ["live", "pinned"])
@pytest.mark.parametrize("late_storage_failure", [False, True])
def test_shared_signed_history_can_be_copied_without_rewriting_evidence(
    published_context,
    mode,
    late_storage_failure,
):
    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    source = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title="Shared setup source",
        markdown="Shared original instructions.\n",
    )
    placement = source.placements.get()
    add_document_placement(
        document=document,
        source_document=source,
        actor_id=installation.owner.id,
        resolution_mode=mode,
        pinned_revision_id=placement.block.current_revision_id if mode == "pinned" else None,
        parent_id=None,
        position=1,
    )
    signed = publish_document(
        workspace=resolve_msp_workspace(installation.owner),
        document=document,
        actor_id=installation.owner.id,
        reason="Retain shared content before migration",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    snapshots = (original, signed)
    before = [
        (deepcopy(p.manifest), p.signature, read_publication_artifact(p.artifacts.get(kind="pdf"))) for p in snapshots
    ]
    source_plan = prepare_document_import(workspace=workspace, document_id=source.id)
    apply_document_import(
        workspace=workspace,
        document_id=source.id,
        expected_base=source_plan.base_commit,
        plan_sha256=source_plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    result = apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    assert result.status == "imported"
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.models import DocumentAuthority

    reader = resolve_msp_workspace(installation.owner)
    group = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id, document.id),
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=group.document_ids,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
            plan_sha256=group.plan_sha256,
        )
        == "transitioned"
    )
    assert set(
        DocumentAuthority.objects.filter(
            workspace=workspace,
            content_id__in=(source.id, document.id, placement.block_id),
        ).values_list("authority", flat=True)
    ) == {"repository"}
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain exact shared Git composition",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v7"
    assert len(publication.manifest["git_source"]["sources"]) == 3
    borrowed = publication.manifest["git_source"]["sources"][2]
    assert borrowed["id"] == str(placement.block_id)
    assert borrowed["mode"] == mode
    assert "Shared original instructions." in publication.canonical_markdown
    assert verify_retained_publication_custody(publication)
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.documents import resolve_document

    retained_pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
    fragment = read_authored_content(repository=workspace.repository, content_id=placement.block_id)
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
        markdown="Shared edited Git instructions.\n",
        metadata_patch={},
    )
    own_fragment = read_authored_content(
        repository=workspace.repository,
        content_id=document.placements.get(block__source_document=document).block_id,
    )
    author_content(
        repository=workspace.repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="update",
        content_id=own_fragment.content_id,
        base_commit=own_fragment.accepted_commit,
        base_blob=own_fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Consumer edited Git instructions.\n",
        metadata_patch={},
    )
    current = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")["markdown"]
    expected = "Shared edited Git instructions." if mode == "live" else "Shared original instructions."
    assert expected in current
    assert publication.canonical_markdown.endswith("Shared original instructions.\n")
    assert verify_retained_publication_custody(publication)
    from django.test import Client
    from django.urls import reverse

    from apps.core.repository_storage import resolve_managed_repository_path

    _root, git_path = resolve_managed_repository_path(workspace.repository)
    unavailable = git_path.with_name(git_path.name + ".unavailable")
    git_path.rename(unavailable)
    try:
        assert verify_retained_publication_custody(publication)
        browser = Client()
        browser.force_login(installation.owner)
        response = browser.get(
            reverse(
                "msp-document-publication-export",
                kwargs={
                    "document_entity_id": document.entity_id,
                    "publication_entity_id": publication.entity_id,
                },
            ),
            {"export_format": "pdf"},
        )
        assert response.status_code == 200
        assert response.content == retained_pdf
    finally:
        unavailable.rename(git_path)
    if mode == "live":
        from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority

        with pytest.raises(DocumentAuthorityHandoffError):
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="legacy",
                reader_workspace=reader,
            )
    rollback = prepare_authority_group(
        workspace=workspace,
        document_ids=group.document_ids,
        actor_id=installation.owner.id,
        target="legacy",
        reader_workspace=reader,
    )
    if late_storage_failure:
        from django.db import DatabaseError, connection

        from apps.core.models import AuditEvent, Block

        members = (source.id, document.id)
        revisions = dict(Block.objects.filter(source_document_id__in=members).values_list("id", "current_revision_id"))
        audit_count = AuditEvent.objects.count()
        writes = []

        def reject_second_authority_audit(execute, sql, params, many, context):
            if sql.startswith('INSERT INTO "core_auditevent"') and "document.authority_transitioned" in params:
                writes.append(True)
                if len(writes) == 2:
                    raise DatabaseError("Synthetic audit storage failure")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(reject_second_authority_audit):
            with pytest.raises(DatabaseError, match="Synthetic audit storage failure"):
                transition_authority_group(
                    workspace=workspace,
                    document_ids=rollback.document_ids,
                    actor_id=installation.owner.id,
                    target="legacy",
                    reader_workspace=reader,
                    plan_sha256=rollback.plan_sha256,
                )
        assert len(writes) == 2
        assert (
            dict(Block.objects.filter(source_document_id__in=members).values_list("id", "current_revision_id"))
            == revisions
        )
        assert AuditEvent.objects.count() == audit_count
        assert set(
            DocumentAuthority.objects.filter(
                workspace=workspace,
                content_id__in=members,
            ).values_list("authority", flat=True)
        ) == {"repository"}
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=rollback.document_ids,
            actor_id=installation.owner.id,
            target="legacy",
            reader_workspace=reader,
            plan_sha256=rollback.plan_sha256,
        )
        == "transitioned"
    )
    assert expected in resolve_document(document).markdown
    assert "Consumer edited Git instructions." in resolve_document(document).markdown
    assert resolve_document(source).markdown == "Shared edited Git instructions.\n"
    assert read_publication_artifact(publication.artifacts.get(kind="pdf")) == retained_pdf
    assert verify_retained_publication_custody(publication)
    for snapshot, fingerprint in zip(snapshots, before, strict=True):
        snapshot.refresh_from_db()
        assert (
            snapshot.manifest,
            snapshot.signature,
            read_publication_artifact(snapshot.artifacts.get(kind="pdf")),
        ) == fingerprint
        assert verify_retained_publication_custody(snapshot)


def _copy(workspace, document, actor):
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    return apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=actor.id,
    )


def _consumer(installation, source, mode):
    consumer = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title="Shared consumer",
        markdown="Consumer instructions.\n",
    )
    block = source.placements.get().block
    add_document_placement(
        document=consumer,
        source_document=source,
        actor_id=installation.owner.id,
        resolution_mode=mode,
        pinned_revision_id=block.current_revision_id if mode == "pinned" else None,
        parent_id=None,
        position=1,
    )
    return consumer


def test_single_document_transition_cannot_split_live_owner_and_consumer(published_context):
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
    from apps.core.models import DocumentAuthority

    installation, workspace, source, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "live")
    _copy(workspace, source, installation.owner)
    _copy(workspace, consumer, installation.owner)
    with pytest.raises(DocumentAuthorityHandoffError):
        transition_document_authority(
            workspace=workspace,
            document_id=consumer.id,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=resolve_msp_workspace(installation.owner),
        )
    assert set(
        DocumentAuthority.objects.filter(
            workspace=workspace,
            content_id__in=(source.id, consumer.id),
        ).values_list("authority", flat=True)
    ) == {"legacy"}


def test_pinned_only_consumer_does_not_prevent_source_handoff(published_context):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.models import DocumentAuthority

    installation, workspace, source, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "pinned")
    _copy(workspace, source, installation.owner)
    _copy(workspace, consumer, installation.owner)
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id,),
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=plan.document_ids,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
            plan_sha256=plan.plan_sha256,
        )
        == "transitioned"
    )
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=consumer.id).authority == "legacy"
    from apps.core.documents import PlacementConflict, update_document_placement

    pinned = consumer.placements.get(resolution_mode="pinned")
    with pytest.raises(PlacementConflict):
        update_document_placement(
            placement=pinned,
            actor_id=installation.owner.id,
            resolution_mode="live",
            pinned_revision_id=None,
        )
    pinned.refresh_from_db()
    assert pinned.resolution_mode == "pinned"
    from django.db import DatabaseError, transaction

    with pytest.raises(DatabaseError, match="live placements require legacy source authority"), transaction.atomic():
        consumer.placements.filter(pk=pinned.pk).update(resolution_mode="live", pinned_revision=None)
    assert verify_retained_publication_custody(original)


@pytest.mark.parametrize("actor_kind", ["read_only", "missing_mfa", "foreign_tenant", "wrong_workspace"])
def test_denied_group_operator_cannot_probe_unavailable_git_storage(published_context, actor_kind):
    import uuid

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.document_authority_groups import prepare_authority_group
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
    from apps.core.models import Tenant
    from apps.core.organizations import create_organization
    from apps.core.repository_storage import resolve_managed_repository_path
    from apps.core.workspaces import resolve_organization_workspace

    installation, workspace, source, _original = published_context
    if actor_kind in {"missing_mfa", "wrong_workspace"}:
        actor = installation.owner
    else:
        actor = User.objects.create_user(email=f"shared-reader-{uuid.uuid4()}@example.invalid", display_name="Reader")
        tenant = (
            Tenant.objects.create(name="Foreign shared fixture")
            if actor_kind == "foreign_tenant"
            else installation.tenant
        )
        TenantMembership.objects.create(
            tenant=tenant,
            user=actor,
            role=BuiltInRole.ADMINISTRATOR if actor_kind == "foreign_tenant" else BuiltInRole.READ_ONLY,
        )
    if actor_kind != "missing_mfa":
        TOTP.activate(actor, generate_totp_secret())
    if actor_kind == "wrong_workspace":
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=actor.id,
            name="Other shared workspace",
            legal_name="",
            website="",
            classifications=[],
        )
        reader = resolve_organization_workspace(actor, entity_id=organization.entity_id)
    else:
        reader = resolve_msp_workspace(installation.owner if actor_kind == "foreign_tenant" else actor)
    _root, path = resolve_managed_repository_path(workspace.repository)
    unavailable = path.with_name(path.name + ".unavailable")
    path.rename(unavailable)
    try:
        with pytest.raises(DocumentAuthorityHandoffError, match="publication_migration_not_authorized"):
            prepare_authority_group(
                workspace=workspace,
                document_ids=(source.id,),
                actor_id=actor.id,
                target="repository",
                reader_workspace=reader,
            )
    finally:
        unavailable.rename(path)


@pytest.mark.parametrize("change", ["inbound_live", "revision", "file", "withdrawal"])
def test_group_preview_rejects_changed_dependencies_without_partial_transition(published_context, change):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import create_document_attachment
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
    from apps.core.documents import update_document
    from apps.core.models import Block, DocumentAuthority
    from apps.core.publications import withdraw_publication

    installation, workspace, source, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "live")
    _copy(workspace, source, installation.owner)
    _copy(workspace, consumer, installation.owner)
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id, consumer.id),
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    if change == "inbound_live":
        _consumer(installation, source, "live")
    elif change == "revision":
        update_document(
            document=source,
            actor_id=installation.owner.id,
            title=source.entity.display_name,
            markdown="Legacy edit after preview.\n",
            base_revision_id=source.placements.get().block.current_revision_id,
        )
    elif change == "file":
        create_document_attachment(
            document=source,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("later.txt", b"File added after preview.\n"),
        )
    else:
        withdraw_publication(publication=original, actor_id=installation.owner.id, reason="After preview")
    before = dict(
        Block.objects.filter(source_document_id__in=plan.document_ids).values_list("id", "current_revision_id")
    )
    with pytest.raises(DocumentAuthorityHandoffError):
        transition_authority_group(
            workspace=workspace,
            document_ids=plan.document_ids,
            actor_id=installation.owner.id,
            target="repository",
            reader_workspace=reader,
            plan_sha256=plan.plan_sha256,
        )
    assert set(
        DocumentAuthority.objects.filter(
            workspace=workspace,
            content_id__in=plan.document_ids,
        ).values_list("authority", flat=True)
    ) == {"legacy"}
    assert (
        dict(Block.objects.filter(source_document_id__in=plan.document_ids).values_list("id", "current_revision_id"))
        == before
    )
    assert verify_retained_publication_custody(original)


def test_runtime_role_can_transition_publish_and_roll_back_a_shared_group(published_context, django_runtime_role):
    from django.db import transaction

    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    installation, workspace, source, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "live")
    _copy(workspace, source, installation.owner)
    _copy(workspace, consumer, installation.owner)
    reader = resolve_msp_workspace(installation.owner)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=installation.owner.id,
        )
        for target in ("repository", "legacy"):
            plan = prepare_authority_group(
                workspace=workspace,
                document_ids=(source.id, consumer.id),
                actor_id=installation.owner.id,
                target=target,
                reader_workspace=reader,
            )
            assert (
                transition_authority_group(
                    workspace=workspace,
                    document_ids=plan.document_ids,
                    actor_id=installation.owner.id,
                    target=target,
                    reader_workspace=reader,
                    plan_sha256=plan.plan_sha256,
                )
                == "transitioned"
            )
            if target == "repository":
                snapshot = publish_document(
                    workspace=reader,
                    document=consumer,
                    actor_id=installation.owner.id,
                    reason="Constrained-role shared snapshot",
                    audience="msp_internal",
                    retention="permanent",
                    retention_review_on=None,
                )
                assert snapshot.manifest["format"] == "tekdocs-static-publication/v7"
        assert verify_retained_publication_custody(original)
        assert verify_retained_publication_custody(snapshot)


@pytest.mark.parametrize("damage", ["root_title", "order", "pin_commit"])
def test_database_rejects_shared_snapshot_with_incoherent_source_proof(published_context, damage):
    import uuid

    from django.db import DatabaseError, transaction

    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.models import DocumentPublication, Entity

    installation, workspace, source, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "pinned")
    _copy(workspace, source, installation.owner)
    _copy(workspace, consumer, installation.owner)
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id, consumer.id),
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    transition_authority_group(
        workspace=workspace,
        document_ids=plan.document_ids,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
        plan_sha256=plan.plan_sha256,
    )
    publication = publish_document(
        workspace=reader,
        document=consumer,
        actor_id=installation.owner.id,
        reason="Intact pinned proof",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    entity = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        entity_type="document_publication",
        display_name="Rejected shared snapshot",
        visibility="msp_private",
    )
    values = {
        f.attname: getattr(publication, f.attname)
        for f in DocumentPublication._meta.concrete_fields
        if f.name not in {"id", "entity", "manifest"}
    }
    publication_id = uuid.uuid4()
    manifest = deepcopy(publication.manifest)
    manifest.update(publication_id=str(publication_id), publication_entity_id=str(entity.id))
    if damage == "root_title":
        manifest["git_source"]["root_title"] = "Different root title"
    elif damage == "order":
        sources = manifest["git_source"]["sources"]
        sources[1], sources[2] = sources[2], sources[1]
    else:
        manifest["git_source"]["sources"][2]["commit"] = "f" * 40
    with pytest.raises(DatabaseError, match="shared Git publication source is invalid"), transaction.atomic():
        DocumentPublication.objects.create(id=publication_id, entity=entity, manifest=manifest, **values)
        raise AssertionError("Invalid shared proof accepted before deferred artifact checks")


def test_group_operator_command_round_trip_and_reversible_schema(published_context):
    import io
    import json

    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    installation, workspace, source, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "live")
    for document in (source, consumer):
        _copy(workspace, document, installation.owner)
    arguments = ["--workspace", str(workspace.id), "--actor", str(installation.owner.id)]
    for document in (source, consumer):
        arguments += ["--document", str(document.id)]

    def invoke(target, *extra):
        output = io.StringIO()
        call_command("transition_document_authority_group", *arguments, "--authority", target, *extra, stdout=output)
        return json.loads(output.getvalue())

    plan = invoke("repository")
    assert plan["status"] == "prepared"
    assert invoke("repository", "--apply", "--plan-sha256", "0" * 64)["status"] == "blocked"
    assert invoke("repository", "--apply", "--plan-sha256", plan["plan_sha256"])["status"] == "transitioned"
    publication = publish_document(
        workspace=resolve_msp_workspace(installation.owner),
        document=consumer,
        actor_id=installation.owner.id,
        reason="Verify reversible shared schema",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    evidence = (
        deepcopy(publication.manifest),
        publication.signature,
        read_publication_artifact(publication.artifacts.get(kind="pdf")),
    )
    rollback = invoke("legacy")
    assert invoke("legacy", "--apply", "--plan-sha256", rollback["plan_sha256"])["status"] == "transitioned"
    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0197_file_git_publication")])
        assert verify_retained_publication_custody(original)
        assert verify_retained_publication_custody(publication)
    finally:
        MigrationExecutor(connection).migrate(head)
    publication.refresh_from_db()
    assert (
        publication.manifest,
        publication.signature,
        read_publication_artifact(publication.artifacts.get(kind="pdf")),
    ) == evidence
    plan = invoke("repository")
    assert invoke("repository", "--apply", "--plan-sha256", plan["plan_sha256"])["status"] == "transitioned"
    assert verify_retained_publication_custody(publication)


def test_repeated_shared_block_occurrences_are_explicitly_blocked(published_context):
    from apps.core.document_migration_import import DocumentMigrationBlocked

    installation, workspace, source, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    consumer = _consumer(installation, source, "pinned")
    add_document_placement(
        document=consumer,
        source_document=source,
        actor_id=installation.owner.id,
        resolution_mode="live",
        pinned_revision_id=None,
        parent_id=None,
        position=2,
    )
    _copy(workspace, source, installation.owner)
    with pytest.raises(DocumentMigrationBlocked, match="unsupported_placement_graph"):
        prepare_document_import(workspace=workspace, document_id=consumer.id)


def test_database_authority_transition_serializes_with_placement_destination(published_context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, connection, transaction

    from apps.core.models import Document, DocumentAuthority

    installation, workspace, source, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    _copy(workspace, source, installation.owner)
    started, finished = Event(), Event()

    def transition_root():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
                started.set()
                DocumentAuthority.objects.filter(workspace=workspace, content_id=source.id).update(
                    authority="repository"
                )
            finished.set()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            # The placement trigger holds exactly this destination lock until commit.
            Document.objects.select_for_update().get(pk=source.id)
            future = executor.submit(transition_root)
            assert started.wait(5)
            completed_while_placement_locked = finished.wait(0.5)
        future.result(timeout=10)
    assert not completed_while_placement_locked


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_source_file_link_edits_preserve_shared_consumer_rollback(published_context, mode):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_attachments import create_document_attachment
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.repository_service import RepositoryInputError

    installation, workspace, source, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    attachment = create_document_attachment(
        document=source,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("source-owned.txt", b"Retain source-owned bytes.\n"),
    )
    consumer = _consumer(installation, source, mode)
    for document in (source, consumer):
        _copy(workspace, document, installation.owner)
    reader = resolve_msp_workspace(installation.owner)
    plan = prepare_authority_group(
        workspace=workspace,
        document_ids=(source.id, consumer.id),
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    transition_authority_group(
        workspace=workspace,
        document_ids=plan.document_ids,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
        plan_sha256=plan.plan_sha256,
    )
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    arguments = dict(
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
        metadata_patch={},
        markdown=f"[Source file](tekdocs://attachment/{attachment.entity_id})\n",
    )
    if mode == "live":
        with pytest.raises(RepositoryInputError, match="kept reversible"):
            author_content(**arguments)
        assert (
            read_authored_content(repository=workspace.repository, content_id=fragment.content_id).accepted_commit
            == fragment.accepted_commit
        )
    else:
        author_content(**arguments)
        assert (
            "tekdocs://attachment"
            not in document_detail(workspace=reader, content_id=consumer.id, audience="msp_internal")["markdown"]
        )
    rollback = prepare_authority_group(
        workspace=workspace,
        document_ids=plan.document_ids,
        actor_id=installation.owner.id,
        target="legacy",
        reader_workspace=reader,
    )
    assert (
        transition_authority_group(
            workspace=workspace,
            document_ids=plan.document_ids,
            actor_id=installation.owner.id,
            target="legacy",
            reader_workspace=reader,
            plan_sha256=rollback.plan_sha256,
        )
        == "transitioned"
    )
    assert verify_retained_publication_custody(original)
