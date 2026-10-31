"""Content substitution crosses the existing migration and reader boundaries."""

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.core.content_read import document_detail
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.documents import create_document, update_document
from apps.core.models import DocumentKeyBinding
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace

pytest_plugins = (
    "apps.core.tests.test_document_migration_publications",
    "apps.core.tests.test_key_entity_publication_migration",
)
pytestmark = pytest.mark.django_db(transaction=True)


def reader_for(installation, document):
    return (
        resolve_organization_workspace(installation.owner, entity_id=document.organization.entity_id)
        if document.organization_id else resolve_msp_workspace(installation.owner)
    )


@pytest.fixture(params=("msp", "client"))
def content_key_context(published_context, request):
    installation, workspace, document, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    organization = None
    if request.param == "client":
        from apps.core.content_index import index_repository_content
        from apps.core.models import workspace_for_owner
        from apps.core.organizations import create_organization
        from apps.core.publications import publish_document
        from apps.core.repository_storage import ensure_workspace_repository

        organization = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Content-key client",
            legal_name="", website="", classifications=["client"],
        )
        workspace = workspace_for_owner(tenant=installation.tenant, organization=organization)
        ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        document = create_document(
            tenant=installation.tenant, organization=organization, actor_id=installation.owner.id,
            title="Client substitution guide", markdown="Historical client instructions.\n",
        )
        publish_document(
            workspace=reader_for(installation, document), document=document, actor_id=installation.owner.id,
            reason="Retain client history", audience="msp_internal", retention="permanent", retention_review_on=None,
        )
    source = create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        title="Substitution source",
        markdown="Reusable setup instructions.\n",
    )
    block = source.placements.get().block
    DocumentKeyBinding.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        organization=organization,
        document=document,
        name="setup",
        target_entity=block.entity,
        created_by=installation.owner,
    )
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title=document.entity.display_name,
        markdown="Before substitution.\n\n<tekdocs://key/setup.content>\n",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    DocumentKeyBinding.objects.create(
        tenant=installation.tenant, workspace=workspace, organization=organization,
        document=source, name="setup", target_entity=document.placements.get().block.entity,
        created_by=installation.owner,
    )
    for item in (source, document):
        plan = prepare_document_import(workspace=workspace, document_id=item.id)
        result = apply_document_import(
            workspace=workspace,
            document_id=item.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=installation.owner.id,
        )
        assert result.status == "imported"
    return installation, workspace, document, source


def test_copied_content_key_renders_the_accepted_block_body(content_key_context):
    installation, workspace, document, _source = content_key_context
    detail = document_detail(
        workspace=reader_for(installation, document), content_id=document.id, audience="msp_internal"
    )
    assert "Reusable setup instructions." in detail["sanitized_html"]
    assert "Before substitution." in detail["sanitized_html"]


def test_content_key_handoff_cannot_split_the_consumer_and_source(content_key_context):
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority

    installation, workspace, document, source = content_key_context
    for item in (source, document):
        with pytest.raises(DocumentAuthorityHandoffError, match="live_dependency_group_incomplete"):
            transition_document_authority(
                workspace=workspace, document_id=item.id, actor_id=installation.owner.id,
                target="repository", reader_workspace=reader_for(installation, item),
            )


def test_database_rejects_split_content_key_authority(content_key_context):
    from django.db import IntegrityError, connection, transaction

    _installation, workspace, _document, source = content_key_context
    with pytest.raises(IntegrityError, match="content-key authority"):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
            cursor.execute(
                "UPDATE core_documentauthority SET authority='repository' WHERE workspace_id=%s AND content_id=%s",
                (workspace.id, source.id),
            )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_content_key_import_preview_cannot_ignore_a_changed_source_revision(content_key_context):
    from apps.core.document_migration_import import DocumentMigrationBlocked

    installation, workspace, document, source = content_key_context
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    update_document(
        document=source, actor_id=installation.owner.id, title=source.entity.display_name,
        markdown="Changed retained source revision.\n",
        base_revision_id=source.placements.get().block.current_revision_id,
    )
    with pytest.raises(DocumentMigrationBlocked):
        apply_document_import(
            workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
        )


def test_missing_content_key_projection_shows_unavailable_instead_of_sql_text(content_key_context):
    from apps.core.models import ContentNode

    installation, workspace, document, source = content_key_context
    ContentNode.objects.filter(repository=workspace.repository, content_id=source.placements.get().block_id).delete()
    detail = document_detail(
        workspace=reader_for(installation, document), content_id=document.id, audience="msp_internal",
    )
    assert "Reusable setup instructions." not in detail["sanitized_html"]
    assert 'data-key-state="unresolvable"' in detail["sanitized_html"]


@pytest.fixture
def promoted_content_key_context(content_key_context):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group

    installation, workspace, document, source = content_key_context
    reader = reader_for(installation, document)
    plan = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
        target="repository", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=plan.document_ids, actor_id=installation.owner.id,
        target="repository", reader_workspace=reader, plan_sha256=plan.plan_sha256,
    ) == "transitioned"
    return content_key_context


def test_promoted_key_report_does_not_report_an_unindexed_block_as_resolved(promoted_content_key_context):
    from django.test import Client
    from django.urls import reverse

    from apps.core.models import ContentNode

    installation, workspace, document, source = promoted_content_key_context
    ContentNode.objects.filter(repository=workspace.repository, content_id=source.placements.get().block_id).delete()
    browser = Client()
    browser.force_login(installation.owner)
    values = {"document_entity_id": document.entity_id}
    scope = "msp"
    if document.organization_id:
        scope = "organization"
        values["organization_entity_id"] = document.organization.entity_id
    response = browser.get(reverse(f"{scope}-document-keys", kwargs=values))
    assert response.status_code == 200
    assert response.json()["unresolved_count"] == 1
    assert response.json()["results"][0]["state"] == "unresolvable"


@pytest.mark.parametrize("key", ["missing", "setup"])
def test_git_edit_cannot_make_a_substitution_source_impossible_to_roll_back(promoted_content_key_context, key):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.repository_service import RepositoryInputError

    installation, workspace, _document, source = promoted_content_key_context
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    with pytest.raises(RepositoryInputError):
        author_content(
            repository=workspace.repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
            base_blob=fragment.source_blob, kind=None, path=None, title=None,
            markdown=f"<tekdocs://key/{key}.content>\n", metadata_patch={},
        )
    unchanged = read_authored_content(repository=workspace.repository, content_id=fragment.content_id)
    assert unchanged.accepted_commit == fragment.accepted_commit
    assert unchanged.markdown == "Reusable setup instructions.\n"


def test_git_content_key_publication_freezes_substitution_and_preserves_history(content_key_context):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.publications import publish_document, read_publication_artifact, verify_retained_publication_custody

    installation, workspace, document, source = content_key_context
    original = document.publications.get()
    original_pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    reader = reader_for(installation, document)
    group = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
        target="repository", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=group.document_ids, actor_id=installation.owner.id,
        target="repository", reader_workspace=reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"
    publication = publish_document(
        workspace=reader, document=document, actor_id=installation.owner.id,
        reason="Retain accepted block substitution", audience="msp_internal",
        retention="permanent", retention_review_on=None,
    )
    assert "Reusable setup instructions." in publication.canonical_markdown
    assert "tekdocs://key/" not in publication.canonical_markdown
    assert publication.manifest["format"] == "tekdocs-static-publication/v10"
    assert verify_retained_publication_custody(publication)

    assert read_publication_artifact(original.artifacts.get(kind="pdf")) == original_pdf
    assert verify_retained_publication_custody(original)
    from apps.core.content_authoring import author_content, read_authored_content

    frozen_pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob, kind=None, path=None, title=None,
        markdown="Updated accepted Git instructions.\n", metadata_patch={},
    )
    live = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")
    assert "Updated accepted Git instructions." in live["sanitized_html"]
    assert "Reusable setup instructions." not in live["sanitized_html"]
    assert "Reusable setup instructions." in publication.canonical_markdown
    assert read_publication_artifact(publication.artifacts.get(kind="pdf")) == frozen_pdf
    assert verify_retained_publication_custody(publication)
    rollback = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
        target="legacy", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=rollback.document_ids, actor_id=installation.owner.id,
        target="legacy", reader_workspace=reader, plan_sha256=rollback.plan_sha256,
    ) == "transitioned"
    restored = publish_document(
        workspace=reader, document=document, actor_id=installation.owner.id,
        reason="Verify legacy recovery of Git edits", audience="msp_internal",
        retention="permanent", retention_review_on=None,
    )
    assert "Updated accepted Git instructions." in restored.canonical_markdown
    assert verify_retained_publication_custody(publication)


@pytest.fixture
def nested_content_key_context(addressed_context):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group

    context = addressed_context
    owner = context.installation.owner
    leaf = create_document(
        tenant=context.installation.tenant, organization=context.organization, actor_id=owner.id,
        title="Nested content leaf", markdown="Nested retained instructions.\n",
    )
    source = create_document(
        tenant=context.installation.tenant, organization=context.organization, actor_id=owner.id,
        title="Nested content parent",
        markdown=("Location: <tekdocs://key/subject.name>.\n\n<tekdocs://key/extra.content>\n\n"
                  f"[Site](tekdocs://entity/{context.site.entity_id})\n"),
    )
    for item in (source, context.document):
        if item == source:
            DocumentKeyBinding.objects.create(
                tenant=context.installation.tenant, workspace=context.workspace, organization=context.organization,
                document=item, name="subject", target_entity=context.site.entity, created_by=owner,
            )
        DocumentKeyBinding.objects.create(
            tenant=context.installation.tenant, workspace=context.workspace, organization=context.organization,
            document=item, name="extra", target_entity=leaf.placements.get().block.entity, created_by=owner,
        )
    DocumentKeyBinding.objects.create(
        tenant=context.installation.tenant, workspace=context.workspace, organization=context.organization,
        document=context.document, name="setup", target_entity=source.placements.get().block.entity, created_by=owner,
    )
    update_document(
        document=context.document, actor_id=owner.id, title=context.document.entity.display_name,
        markdown="<tekdocs://key/setup.content>\n",
        base_revision_id=context.document.placements.get().block.current_revision_id,
    )
    for item in (leaf, source, context.document):
        plan = prepare_document_import(workspace=context.workspace, document_id=item.id)
        assert apply_document_import(
            workspace=context.workspace, document_id=item.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=owner.id,
        ).status == "imported"
    group = prepare_authority_group(
        workspace=context.workspace, document_ids=(leaf.id, source.id, context.document.id), actor_id=owner.id,
        target="repository", reader_workspace=context.reader,
    )
    assert transition_authority_group(
        workspace=context.workspace, document_ids=group.document_ids, actor_id=owner.id,
        target="repository", reader_workspace=context.reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"
    return context, source, leaf


def test_nested_content_and_field_keys_freeze_as_the_consuming_document(nested_content_key_context):
    from apps.core.publications import publish_document, verify_retained_publication_custody

    context, _source, _leaf = nested_content_key_context
    owner = context.installation.owner
    publication = publish_document(
        workspace=context.reader, document=context.document, actor_id=owner.id,
        reason="Retain nested substitutions", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    assert "Location: Original operations site." in publication.canonical_markdown
    assert "Nested retained instructions." in publication.canonical_markdown
    assert [item["expression"] for item in publication.manifest["key_resolutions"]] == [
        "extra.content", "setup.content", "subject.name",
    ]
    assert verify_retained_publication_custody(publication)
    assert publication.manifest["entities"][0]["id"] == str(context.site.entity_id)


def test_inline_content_key_edit_is_rejected_before_git_changes(nested_content_key_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.repository_service import RepositoryInputError

    context, source, _leaf = nested_content_key_context
    fragment = read_authored_content(
        repository=context.workspace.repository, content_id=source.placements.get().block_id,
    )
    with pytest.raises(RepositoryInputError):
        author_content(
            repository=context.workspace.repository, actor_id=context.installation.owner.id, request_id=None,
            operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
            base_blob=fragment.source_blob, kind=None, path=None, title=None,
            markdown="Inline <tekdocs://key/extra.content> text.\n", metadata_patch={},
        )
    unchanged = read_authored_content(repository=context.workspace.repository, content_id=fragment.content_id)
    assert unchanged.accepted_commit == fragment.accepted_commit
    assert unchanged.markdown == fragment.markdown


def test_migration_preview_rejects_an_inline_content_key_with_a_valid_acyclic_binding(published_context):
    from apps.core.document_migration_import import DocumentMigrationBlocked

    installation, workspace, _historical, _publication = published_context
    source = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Valid leaf for inline refusal", markdown="Acyclic shared instructions.\n",
    )
    document = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Inline substitution is invalid", markdown="Inline <tekdocs://key/procedure.content> text.\n",
    )
    DocumentKeyBinding.objects.create(
        tenant=installation.tenant, workspace=workspace, organization=None, document=document,
        name="procedure", target_entity=source.placements.get().block.entity, created_by=installation.owner,
    )
    with pytest.raises(DocumentMigrationBlocked, match="content_key_placement"):
        prepare_document_import(workspace=workspace, document_id=document.id)


def test_content_key_upgrade_and_recovery_adapter_requires_exact_retained_state(published_context, monkeypatch, capsys):
    from apps.core.tests.content_key_fixture import (
        content_key_recovery_fingerprint,
        run_content_key_fixture_mode,
    )

    owner = published_context[0].owner
    run_content_key_fixture_mode("seed")
    output = capsys.readouterr().out
    expected = next(line.split("=", 1)[1] for line in output.splitlines()
                    if line.startswith("CONTENT_KEY_LEGACY_SHA256="))
    monkeypatch.setenv("TEKDOCS_CONTENT_KEY_LEGACY_SHA256", "0" * 64)
    with pytest.raises(AssertionError):
        run_content_key_fixture_mode("promote")
    monkeypatch.setenv("TEKDOCS_CONTENT_KEY_LEGACY_SHA256", expected)
    run_content_key_fixture_mode("promote")
    assert "Content-key graph, signed publications, file versions, PDFs and rollback verified" in (
        capsys.readouterr().out
    )
    recovery = content_key_recovery_fingerprint(owner)
    monkeypatch.setenv("TEKDOCS_CONTENT_KEY_RECOVERY_SHA256", "0" * 64)
    with pytest.raises(AssertionError):
        run_content_key_fixture_mode("recovery_verify")
    monkeypatch.setenv("TEKDOCS_CONTENT_KEY_RECOVERY_SHA256", recovery)
    run_content_key_fixture_mode("recovery_verify")
    assert "recovered exactly" in capsys.readouterr().out


def test_new_content_binding_cannot_cross_an_uncommitted_source_handoff(content_key_context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import IntegrityError, close_old_connections, connection

    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.repository_service import coordinated_repository_transaction

    installation, workspace, document, source = content_key_context
    outsider = create_document(
        tenant=installation.tenant, organization=document.organization, actor_id=installation.owner.id,
        title="Late content consumer", markdown="Independent instructions.\n",
    )
    target = source.placements.get().block.entity
    attempted, finished = Event(), Event()

    def bind_late_consumer():
        close_old_connections()
        try:
            def observe(execute, sql, params, many, context):
                if sql.startswith("INSERT") and '"core_documentkeybinding"' in sql:
                    attempted.set()
                return execute(sql, params, many, context)

            with connection.execute_wrapper(observe):
                try:
                    DocumentKeyBinding.objects.create(
                        tenant=installation.tenant, workspace=workspace, organization=document.organization,
                        document=outsider, name="late", target_entity=target, created_by=installation.owner,
                    )
                except IntegrityError as error:
                    assert "content-key binding requires legacy source authority" in str(error)
                    return "blocked"
                return "changed"
        finally:
            finished.set()
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with coordinated_repository_transaction():
            reader = reader_for(installation, document)
            plan = prepare_authority_group(
                workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
                target="repository", reader_workspace=reader,
            )
            assert transition_authority_group(
                workspace=workspace, document_ids=plan.document_ids, actor_id=installation.owner.id,
                target="repository", reader_workspace=reader, plan_sha256=plan.plan_sha256,
            ) == "transitioned"
            pending = pool.submit(bind_late_consumer)
            assert attempted.wait(10)
            assert not finished.wait(0.5)
        assert pending.result(timeout=10) == "blocked"
    assert not outsider.key_bindings.exists()


@pytest.mark.parametrize("damage", ["value", "source", "blob", "commit", "workspace", "chain", "binding"])
def test_offline_content_key_verification_rejects_incoherent_substitution_proof(promoted_content_key_context, damage):
    import uuid
    from copy import copy, deepcopy

    from apps.core.document_git_publications import verify_git_publication_source
    from apps.core.publications import publish_document

    installation, _workspace, document, _source = promoted_content_key_context
    publication = publish_document(
        workspace=reader_for(installation, document), document=document, actor_id=installation.owner.id,
        reason="Verify immutable substitution proof", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    assert verify_git_publication_source(publication)
    candidate = copy(publication)
    candidate.manifest = deepcopy(publication.manifest)
    record = candidate.manifest["key_resolutions"][0]
    if damage == "value":
        record["value"] = "Invented source text.\n"
    elif damage == "source":
        record["git_source"]["source"] += "Unaccepted source text.\n"
    elif damage == "blob":
        record["git_source"]["blob"] = "0" * len(record["git_source"]["blob"])
    elif damage == "commit":
        record["git_source"]["commit"] = "0" * len(record["git_source"]["commit"])
    elif damage == "workspace":
        record["git_source"]["workspace_id"] = str(uuid.uuid4())
    elif damage == "chain":
        record["dependency_chain"] = []
    else:
        candidate.manifest["key_bindings"]["setup"] = str(uuid.uuid4())
    candidate.manifest["key_snapshot"]["records"] = deepcopy(candidate.manifest["key_resolutions"])
    assert not verify_git_publication_source(candidate)


def test_content_key_schema_can_reverse_and_reapply_without_rewriting_retained_publications(published_context):
    from django.db import DatabaseError, connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.publications import publish_document, verify_retained_publication_custody
    from apps.core.tests.content_key_fixture import promote_content_key_fixture, seed_content_key_fixture

    owner = published_context[0].owner
    document = seed_content_key_fixture(owner)
    promote_content_key_fixture(owner)
    original = document.publications.get()
    executor = MigrationExecutor(connection)
    head = executor.loader.graph.leaf_nodes()
    arguments = dict(
        workspace=reader_for(published_context[0], document), document=document, actor_id=owner.id,
        reason="Verify additive schema guard", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    try:
        executor.migrate([("core", "0208_promoted_key_binding_guard")])
        with pytest.raises(DatabaseError, match="publication.*invalid"):
            publish_document(**arguments)
        assert document.publications.count() == 1
        assert verify_retained_publication_custody(original)
    finally:
        MigrationExecutor(connection).migrate(head)
    publication = publish_document(**arguments)
    assert publication.manifest["format"] == "tekdocs-static-publication/v10"
    assert verify_retained_publication_custody(publication) and verify_retained_publication_custody(original)


def test_constrained_role_reads_publishes_and_rolls_back_content_keys(content_key_context, django_runtime_role):
    from django.db import transaction

    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.publications import publish_document, verify_retained_publication_custody
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    installation, workspace, document, source = content_key_context
    reader = reader_for(installation, document)
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.owner(installation.tenant, document.organization),
            organization_mode=(
                OrganizationRLSMode.ORGANIZATION if document.organization_id else OrganizationRLSMode.MSP_ONLY
            ),
            principal_mode=RLSPrincipalMode.USER, actor_user_id=installation.owner.id,
        )
        for target in ("repository", "legacy"):
            plan = prepare_authority_group(
                workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
                target=target, reader_workspace=reader,
            )
            assert transition_authority_group(
                workspace=workspace, document_ids=plan.document_ids, actor_id=installation.owner.id,
                target=target, reader_workspace=reader, plan_sha256=plan.plan_sha256,
            ) == "transitioned"
            if target == "repository":
                detail = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")
                assert "Reusable setup instructions." in detail["sanitized_html"]
                publication = publish_document(
                    workspace=reader, document=document, actor_id=installation.owner.id,
                    reason="Constrained role substitution", audience="msp_internal", retention="permanent",
                    retention_review_on=None,
                )
                assert publication.manifest["format"] == "tekdocs-static-publication/v10"
    assert verify_retained_publication_custody(publication)


@pytest.mark.parametrize("actor_kind", ["read_only", "missing_mfa", "other_tenant", "other_client"])
def test_content_key_publication_denials_preserve_history_and_withhold_source_text(
    promoted_content_key_context, actor_kind,
):
    import uuid

    from django.test import Client
    from django.urls import reverse

    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
        User,
    )
    from apps.core.models import Tenant
    from apps.core.organizations import create_organization

    installation, _workspace, document, _source = promoted_content_key_context
    actor = User.objects.create_user(
        email=f"content-denial-{uuid.uuid4()}@example.invalid", display_name="Denied actor",
    )
    membership = TenantMembership.objects.create(
        tenant=(Tenant.objects.create(name="Other content installation")
                if actor_kind == "other_tenant" else installation.tenant),
        user=actor, role=BuiltInRole.READ_ONLY if actor_kind == "read_only" else BuiltInRole.ADMINISTRATOR,
        workspace_scope=MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS if actor_kind == "other_client"
        else MembershipWorkspaceScope.TENANT,
    )
    if actor_kind != "missing_mfa":
        TOTP.activate(actor, generate_totp_secret())
    if actor_kind == "other_client":
        other = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Other assigned content client",
            legal_name="", website="", classifications=["client"],
        )
        OrganizationAccessAssignment.objects.create(
            tenant=installation.tenant, organization=other, membership=membership, created_by=installation.owner,
        )
    values = {"document_entity_id": document.entity_id}
    scope = "msp"
    if document.organization_id:
        scope = "organization"
        values["organization_entity_id"] = document.organization.entity_id
    count = document.publications.count()
    browser = Client()
    browser.force_login(actor)
    response = browser.post(
        reverse(f"{scope}-document-publication-list-create", kwargs=values),
        {"reason": "Denied content-key publication", "audience": "msp_internal", "retention": "permanent"},
        content_type="application/json",
    )
    assert response.status_code in {403, 404}
    assert "Reusable setup instructions." not in response.content.decode()
    assert document.publications.count() == count


@pytest.mark.parametrize("damage", ["value", "workspace", "path", "revision"])
def test_database_rejects_content_key_proof_that_disagrees_with_the_selected_source(
    promoted_content_key_context, damage,
):
    import hashlib
    import uuid
    from copy import deepcopy

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity
    from apps.core.publications import publish_document

    installation, workspace, document, _source = promoted_content_key_context
    publication = publish_document(
        workspace=reader_for(installation, document), document=document, actor_id=installation.owner.id,
        reason="Valid source for SQL proof rejection", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    candidate = DocumentPublication(
        **{field.attname: getattr(publication, field.attname) for field in DocumentPublication._meta.concrete_fields}
    )
    candidate.id = uuid.uuid4()
    candidate.manifest = deepcopy(publication.manifest)
    candidate.manifest["publication_id"] = str(candidate.id)
    record = candidate.manifest["key_resolutions"][0]
    if damage == "value":
        record["value"] = "Invented content substitution.\n"
        record["source_fingerprint"] = hashlib.sha256(record["value"].encode()).hexdigest()
    elif damage == "workspace":
        record["git_source"]["workspace_id"] = str(uuid.uuid4())
    elif damage == "path":
        record["git_source"]["path"] = f"fragments/{uuid.uuid4()}.md"
    else:
        record["source_revision_id"] = str(uuid.uuid4())
        record["source_revision_number"] = 1
    candidate.manifest["key_snapshot"]["records"] = deepcopy(candidate.manifest["key_resolutions"])
    with pytest.raises(DatabaseError, match="Git content-key source proof is invalid"), transaction.atomic():
        candidate.entity = Entity.objects.create(
            tenant=installation.tenant, workspace=workspace, organization=document.organization,
            entity_type="document_publication", display_name="Rejected content proof",
        )
        candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
        candidate.save(force_insert=True)


def test_sql_closure_includes_a_legacy_consumer_before_it_is_copied(published_context):
    from django.db import IntegrityError, connection, transaction

    from apps.core.models import ContentNode, DocumentAuthority

    installation, workspace, source, _publication = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    plan = prepare_document_import(workspace=workspace, document_id=source.id)
    assert apply_document_import(
        workspace=workspace, document_id=source.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
    ).status == "imported"
    consumer = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Uncopied legacy consumer", markdown="<tekdocs://key/procedure.content>\n",
    )
    DocumentKeyBinding.objects.create(
        tenant=installation.tenant, workspace=workspace, organization=None, document=consumer,
        name="procedure", target_entity=source.placements.get().block.entity, created_by=installation.owner,
    )
    assert not ContentNode.objects.filter(repository=workspace.repository, content_id=consumer.id).exists()
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=consumer.id).authority == "legacy"
    with pytest.raises(IntegrityError, match="content-key authority"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
            cursor.execute(
                "UPDATE core_documentauthority SET authority='repository' WHERE workspace_id=%s AND content_id=%s",
                (workspace.id, source.id),
            )
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_old_repository_evidence_refuses_content_keys_without_creating_unverifiable_evidence(
    promoted_content_key_context,
):
    import hashlib
    from pathlib import Path

    from django.conf import settings

    from apps.core.models import RepositoryPublicationEvidence
    from apps.core.repository_publication_evidence import (
        RepositoryPublicationEvidenceError,
        retain_repository_publication_evidence,
    )

    installation, workspace, document, _source = promoted_content_key_context
    media = Path(settings.MEDIA_ROOT)
    before_files = {str(path.relative_to(media)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in media.rglob("*") if path.is_file()}
    count = RepositoryPublicationEvidence.objects.filter(repository=workspace.repository).count()
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.render.unavailable"):
        retain_repository_publication_evidence(
            repository_id=workspace.repository.id, content_id=document.id,
            audience="msp_internal", actor=installation.owner,
        )
    assert RepositoryPublicationEvidence.objects.filter(repository=workspace.repository).count() == count
    assert {str(path.relative_to(media)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in media.rglob("*") if path.is_file()} == before_files


def test_current_editable_export_uses_git_substitution_bytes_after_a_source_edit(promoted_content_key_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_exports import resolve_export_snapshot

    installation, workspace, document, source = promoted_content_key_context
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob, kind=None, path=None, title=None,
        markdown="Current Git export instructions.\n", metadata_patch={},
    )
    exported = resolve_export_snapshot(workspace=reader_for(installation, document), document=document)
    assert "Current Git export instructions." in exported.markdown
    assert "Current Git export instructions." in exported.sanitized_html
    assert "Reusable setup instructions." not in exported.markdown
    assert exported.manifest["format"] == "tekdocs-portable-document/v4"


def test_plain_source_document_keeps_existing_composition_capacity_without_content_expansion(published_context):
    from apps.core.documents import create_document_block

    installation, workspace, _historical, _publication = published_context
    body = "Plain retained source text. " * 27_000
    assert 2 * 1024 * 1024 < 3 * len(body.encode()) < 4 * 1024 * 1024
    source = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Large plain source composition", markdown=body,
    )
    for position in (1, 2):
        create_document_block(
            document=source, actor_id=installation.owner.id, markdown=body, kind="rich_text",
            name=f"Plain source section {position}", parent_id=None, position=position,
        )
    plan = prepare_document_import(workspace=workspace, document_id=source.id)
    assert len(plan.export.blocks) == 3
    assert len(plan.export.files) == 4
