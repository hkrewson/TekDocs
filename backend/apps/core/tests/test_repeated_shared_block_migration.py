"""Occurrence-specific migration through guarded operator and publication boundaries."""

from copy import deepcopy

import pytest

from apps.core.tests.repeated_block_fixture import (
    copy_document,
    documents,
    exercise_repeated_block_fixture,
    fingerprint,
    prepare_repeated_block_fixture,
    publish,
    recovery_fingerprint,
    retained_state,
    seed_repeated_block_fixture,
)

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def repeated_context(published_context):
    installation, _workspace, _document, _publication = published_context
    seed_repeated_block_fixture(installation.owner)
    return installation


@pytest.mark.parametrize("runtime", [False, True])
def test_repeated_cohort_preserves_files_history_rollback_and_recovery(repeated_context, django_runtime_role, runtime):
    from contextlib import nullcontext

    from django.db import transaction

    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    owner = repeated_context.owner
    before = retained_state(owner)
    _source, consumer = documents(owner)
    scope = DataScope.owner(consumer.tenant, consumer.organization)
    with django_runtime_role() if runtime else nullcontext():
        with transaction.atomic():
            bind_local_rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION,
                                 principal_mode=RLSPrincipalMode.USER, actor_user_id=owner.id)
            digest = exercise_repeated_block_fixture(owner)
            assert recovery_fingerprint(owner) == digest
    after = retained_state(owner)
    assert before[1]["files"] == after[1]["files"]
    assert len(after[1]["files"]) == 3


def test_unrepresented_pins_stay_blocked_without_partial_consumer_copy(repeated_context):
    from apps.core.content_index import index_repository_content
    from apps.core.document_migration_export import DocumentMigrationReferenceError, build_simple_document_export
    from apps.core.document_migration_import import DocumentMigrationBlocked, prepare_document_import
    from apps.core.repository_storage import ensure_workspace_repository

    owner = repeated_context.owner
    source, consumer = documents(owner)
    workspace = consumer.entity.workspace
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    copy_document(owner, source)
    before = fingerprint(retained_state(owner))
    with pytest.raises(DocumentMigrationReferenceError, match="pinned_source_snapshot_required"):
        build_simple_document_export(consumer)
    with pytest.raises(DocumentMigrationBlocked, match="publication_parity_required"):
        prepare_document_import(workspace=workspace, document_id=consumer.id)
    assert fingerprint(retained_state(owner)) == before


@pytest.mark.parametrize("damage", ["duplicate_path", "pin", "drop", "order", "old_format", "content_format"])
def test_database_rejects_corrupt_occurrence_certificate(repeated_context, damage):
    import uuid

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity
    from apps.core.publications import verify_retained_publication_custody

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    _source, consumer = documents(owner)
    snapshot = publish(owner, consumer, "Retain occurrence certificate before corrupt insertion")
    candidate = DocumentPublication(
        **{field.attname: getattr(snapshot, field.attname) for field in DocumentPublication._meta.concrete_fields}
    )
    candidate.id = uuid.uuid4()
    candidate.manifest = deepcopy(snapshot.manifest)
    candidate.manifest["publication_id"] = str(candidate.id)
    proof = candidate.manifest["git_source"]["sources"]
    if damage == "duplicate_path":
        proof[3]["ordinal_path"] = proof[2]["ordinal_path"]
    elif damage == "pin":
        proof[2]["commit"] = proof[3]["commit"]
    elif damage == "drop":
        del proof[2]
    elif damage == "order":
        proof[2], proof[3] = proof[3], proof[2]
    elif damage == "old_format":
        candidate.manifest["format"] = candidate.manifest["occurrence_format"]
    else:
        candidate.manifest["occurrence_format"] = "tekdocs-static-publication/v4"
    assert not verify_retained_publication_custody(candidate)
    with pytest.raises(DatabaseError, match="publication.*(invalid|unsupported)"), transaction.atomic():
        candidate.entity = Entity.objects.create(
            tenant=consumer.tenant, organization=consumer.organization, workspace=consumer.entity.workspace,
            entity_type="document_publication", display_name="Rejected occurrence certificate",
        )
        candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
        candidate.save(force_insert=True)
    assert verify_retained_publication_custody(snapshot)


def test_historical_formats_do_not_admit_repeated_source_identities(repeated_context):
    from apps.core.document_git_publications import verify_git_publication_source

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    _source, consumer = documents(owner)
    snapshot = publish(owner, consumer, "Retain occurrence certificate")
    assert verify_git_publication_source(snapshot)
    snapshot.manifest = deepcopy(snapshot.manifest)
    snapshot.manifest["format"] = snapshot.manifest["occurrence_format"]
    # An extra v12-shaped field on a v7 certificate cannot relax v7 validation.
    assert not verify_git_publication_source(snapshot)



def test_occurrence_guard_reverse_reapply_preserves_existing_signed_rows(repeated_context):
    from django.db import DatabaseError, connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.publications import verify_retained_publication_custody

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    _source, consumer = documents(owner)
    snapshot = publish(owner, consumer, "Retain occurrence proof across schema rollback")
    before = fingerprint(retained_state(owner))
    targets = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        MigrationExecutor(connection).migrate([("core", "0212_client_git_publication")])
        assert verify_retained_publication_custody(snapshot)
        assert fingerprint(retained_state(owner)) == before
        with pytest.raises(DatabaseError), transaction.atomic():
            publish(owner, consumer, "Old schema refuses new occurrence certificates")
    finally:
        MigrationExecutor(connection).migrate(targets)
    assert fingerprint(retained_state(owner)) == before
    assert verify_retained_publication_custody(snapshot)
    assert publish(owner, consumer, "Reapplied occurrence guard permits new certificate").manifest["format"] == (
        "tekdocs-static-publication/v12"
    )


def test_late_rollback_failure_preserves_every_occurrence_and_revision(repeated_context):
    from django.db import DatabaseError, connection

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.tests.repeated_block_fixture import reader_for

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    source, consumer = documents(owner)
    workspace = consumer.entity.workspace
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None, markdown="Live edition before failed rollback.\n", metadata_patch={},
    )
    reader = reader_for(owner, consumer)
    plan = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, consumer.id), actor_id=owner.id,
        target="legacy", reader_workspace=reader,
    )
    before = recovery_fingerprint(owner)
    writes = []

    def fail_second_audit(execute, sql, params, many, context):
        if sql.startswith('INSERT INTO "core_auditevent"') and "document.authority_transitioned" in params:
            writes.append(True)
            if len(writes) == 2:
                raise DatabaseError("Synthetic late repeated-block rollback failure")
        return execute(sql, params, many, context)

    with connection.execute_wrapper(fail_second_audit), pytest.raises(DatabaseError, match="Synthetic late"):
        transition_authority_group(
            workspace=workspace, document_ids=plan.document_ids, actor_id=owner.id,
            target="legacy", reader_workspace=reader, plan_sha256=plan.plan_sha256,
        )
    assert len(writes) == 2
    assert recovery_fingerprint(owner) == before


def test_retained_occurrence_pdf_download_remains_exact_without_git(repeated_context):
    import hashlib

    from django.test import Client
    from django.urls import reverse

    from apps.core.publications import read_publication_artifact, verify_retained_publication_custody
    from apps.core.repository_storage import resolve_managed_repository_path

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    _source, consumer = documents(owner)
    snapshot = publish(owner, consumer, "Retain repeated source proof independently of Git")
    expected = hashlib.sha256(read_publication_artifact(snapshot.artifacts.get(kind="pdf"))).hexdigest()
    _root, path = resolve_managed_repository_path(consumer.entity.workspace.repository)
    unavailable = path.with_name(path.name + ".unavailable")
    browser = Client()
    browser.force_login(owner)
    path.rename(unavailable)
    try:
        assert verify_retained_publication_custody(snapshot)
        response = browser.get(reverse("organization-document-publication-export", kwargs={
            "organization_entity_id": consumer.organization.entity_id,
            "document_entity_id": consumer.entity_id, "publication_entity_id": snapshot.entity_id,
        }), {"export_format": "pdf"})
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == expected
        with pytest.raises((OSError, ValueError, RuntimeError)):
            recovery_fingerprint(owner)
    finally:
        unavailable.rename(path)
    assert recovery_fingerprint(owner)


def test_stale_pin_preview_cannot_apply_or_change_authority(repeated_context):
    from apps.core.document_migration_import import (
        DocumentMigrationBlocked,
        apply_document_import,
        prepare_document_import,
    )
    from apps.core.documents import update_document_placement
    from apps.core.tests.repeated_block_fixture import transition

    owner = repeated_context.owner
    prepare_repeated_block_fixture(owner)
    transition(owner, "legacy")
    _source, consumer = documents(owner)
    workspace = consumer.entity.workspace
    plan = prepare_document_import(workspace=workspace, document_id=consumer.id)
    first, second = list(consumer.placements.filter(resolution_mode="pinned").order_by("position"))
    update_document_placement(
        placement=first, actor_id=owner.id, resolution_mode="pinned", pinned_revision_id=second.pinned_revision_id,
    )
    before = fingerprint(retained_state(owner))
    with pytest.raises(DocumentMigrationBlocked):
        apply_document_import(
            workspace=workspace, document_id=consumer.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=owner.id,
        )
    assert fingerprint(retained_state(owner)) == before
    workspace.repository.refresh_from_db()
    assert workspace.repository.accepted_commit.object_id == plan.base_commit


@pytest.mark.parametrize("audience", ["msp_internal", "client_visible"])
def test_repeated_pin_audiences_do_not_leak_the_other_edition(repeated_context, audience):
    from apps.core.documents import update_document_placement
    from apps.core.publications import publish_document, verify_retained_publication_custody
    from apps.core.tests.repeated_block_fixture import reader_for

    owner = repeated_context.owner
    _source, consumer = documents(owner)
    for placement, profile in zip(consumer.placements.filter(resolution_mode="pinned").order_by("position"),
                                  ("msp_internal", "client_visible"), strict=True):
        update_document_placement(placement=placement, actor_id=owner.id, audience_profile=profile)
    prepare_repeated_block_fixture(owner)
    snapshot = publish_document(
        workspace=reader_for(owner, consumer), document=consumer, actor_id=owner.id,
        reason="Keep each repeated edition in its selected audience", audience=audience,
        retention="permanent", retention_review_on=None,
    )
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v12"
    included = "First pinned shared edition." if audience == "msp_internal" else "Second pinned shared edition."
    excluded = "Second pinned shared edition." if audience == "msp_internal" else "First pinned shared edition."
    assert included in snapshot.canonical_markdown
    assert excluded not in snapshot.canonical_markdown
    assert verify_retained_publication_custody(snapshot)
