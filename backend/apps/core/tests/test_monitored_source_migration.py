"""Monitored content crosses the public migration, review and apply interfaces."""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import close_old_connections, transaction
from django.test import Client
from django.urls import reverse

from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_read import document_detail
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_migration_import import DocumentMigrationBlocked, apply_document_import, prepare_document_import
from apps.core.document_source_git import preview_remote_observation
from apps.core.document_source_models import DocumentRemoteObservation, DocumentRemoteSource
from apps.core.document_source_state import monitored_source_fingerprint
from apps.core.document_sources import apply_remote_observation, fetch_remote_document
from apps.core.documents import PlacementConflict, resolve_document
from apps.core.models import AuditEvent
from apps.core.repository_service import (
    coordinated_repository_transaction,
    list_accepted_repository_history,
    pin_accepted_repository_for_publication,
)
from apps.core.workspaces import resolve_msp_workspace

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def retained_monitored_context(published_context):
    installation, workspace, document, publication = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    source = DocumentRemoteSource.objects.create(
        tenant=installation.tenant, organization=None, document=document,
        url="https://example.invalid/monitored-guide", source_kind="markdown",
        check_interval_minutes=120, created_by=installation.owner,
    )
    def observe(markdown):
        return DocumentRemoteObservation.objects.create(
            tenant=installation.tenant, organization=None, source=source, state="changed", status_code=200,
            content_type="text/markdown", canonical_markdown=markdown,
            content_digest=hashlib.sha256(markdown.encode()).hexdigest(),
        )
    original = observe("Historical instructions.\n")
    source.last_applied_observation = original
    source.save(update_fields=("last_applied_observation", "updated_at"))
    observed = observe("Current upstream instructions.\n")
    return installation, workspace, document, publication, source, observed


@pytest.fixture
def monitored_context(retained_monitored_context):
    installation, workspace, document, publication, source, observed = retained_monitored_context
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert apply_document_import(
        workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
    ).status == "imported"
    assert transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=installation.owner.id, target="repository",
        reader_workspace=resolve_msp_workspace(installation.owner),
    ) == "transitioned"
    return installation, workspace, document, publication, source, observed


@pytest.mark.parametrize("state", ["changed", "unchanged"])
def test_reviewed_monitored_update_writes_git_without_retiring_history(monitored_context, state):
    installation, _workspace, document, publication, source, observation = monitored_context
    signature, manifest = publication.signature, publication.manifest
    if state == "unchanged":
        observation = DocumentRemoteObservation.objects.create(
            tenant=installation.tenant, organization=None, source=source, state="unchanged", status_code=200,
            content_type="text/markdown", canonical_markdown=observation.canonical_markdown,
            content_digest=observation.content_digest,
        )
    review = preview_remote_observation(observation=observation)
    assert review and not review["blocker"]
    apply_remote_observation(
        observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
    )
    result = document_detail(
        workspace=resolve_msp_workspace(installation.owner), content_id=document.id, audience="msp_internal",
    )
    assert result["markdown"] == "Current upstream instructions.\n"
    assert document.placements.get().block.current_revision.markdown == "Historical instructions.\n"
    source.refresh_from_db()
    assert source.last_applied_observation_id == observation.id
    publication.refresh_from_db()
    assert (publication.signature, publication.manifest) == (signature, manifest)


def _snapshot(context):
    _installation, workspace, document, publication, _source, _observation = context
    repository = workspace.repository
    repository.refresh_from_db()
    fragment = read_authored_content(repository=repository, content_id=document.placements.get().block_id)
    return (
        monitored_source_fingerprint(document), repository.accepted_commit_id, repository.indexed_commit_id,
        fragment.source, list(list_accepted_repository_history(repository_id=repository.id)),
        list(document.placements.get().block.revisions.values_list("id", "markdown", "checksum")),
        list(AuditEvent.objects.filter(entity_id=document.entity_id).values_list("id", flat=True)),
        publication.signature, publication.manifest,
    )


def _edit(context, markdown):
    installation, workspace, document, *_rest = context
    current = read_authored_content(repository=workspace.repository, content_id=document.placements.get().block_id)
    return author_content(
        repository=workspace.repository, actor_id=installation.owner.id, request_id=None, operation="update",
        content_id=current.content_id, base_commit=current.accepted_commit, base_blob=current.source_blob,
        kind=None, path=None, title=None, markdown=markdown, metadata_patch={},
    )


@pytest.mark.parametrize("mutation", ["settings", "body", "index", "missing_review"])
def test_stale_source_review_preserves_git_and_sql(monitored_context, mutation):
    installation, workspace, _document, _publication, source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review and not review["blocker"]
    if mutation == "settings":
        source.check_interval_minutes = 180
        source.save(update_fields=("check_interval_minutes", "updated_at"))
    elif mutation == "body":
        _edit(monitored_context, "Historical instructions.\n\nLocal recovery note.\n")
    elif mutation == "index":
        repository = workspace.repository
        repository.indexed_commit = None
        repository.save(update_fields=("indexed_commit", "updated_at"))
    before = _snapshot(monitored_context)
    with pytest.raises(PlacementConflict):
        apply_remote_observation(
            observation=observation, actor_id=installation.owner.id,
            review_fingerprint=None if mutation == "missing_review" else review["fingerprint"],
        )
    assert _snapshot(monitored_context) == before


@pytest.mark.parametrize("missing_baseline", [False, True])
def test_local_edits_require_manual_integration(monitored_context, missing_baseline):
    installation, _workspace, _document, _publication, source, observation = monitored_context
    _edit(monitored_context, "Historical instructions.\n\nLocal recovery note.\n")
    if missing_baseline:
        source.last_applied_observation = None
        source.save(update_fields=("last_applied_observation", "updated_at"))
    review = preview_remote_observation(observation=observation)
    assert review and review["blocker"] == "local_edits_require_integration"
    assert "Local recovery note" in review["diff"]
    before = _snapshot(monitored_context)
    with pytest.raises(PlacementConflict, match="Local edits"):
        apply_remote_observation(
            observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
        )
    assert _snapshot(monitored_context) == before


def test_outer_transaction_failure_restores_git_reference_pointer_and_audit(monitored_context):
    installation, _workspace, _document, _publication, _source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review
    before = _snapshot(monitored_context)
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with coordinated_repository_transaction():
            apply_remote_observation(
                observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
            )
            raise RuntimeError("synthetic rollback")
    assert _snapshot(monitored_context) == before


def test_source_workflow_survives_rollback_and_repromotion(monitored_context):
    installation, workspace, document, _publication, _source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review
    _edit(monitored_context, "Historical instructions.\n\nLocal recovery note.\n")
    retained = monitored_source_fingerprint(document)
    for target in ("legacy", "repository"):
        assert transition_document_authority(
            workspace=workspace, document_id=document.id, actor_id=installation.owner.id,
            target=target, reader_workspace=resolve_msp_workspace(installation.owner),
        ) == "transitioned"
        assert monitored_source_fingerprint(document) == retained
        if target == "legacy":
            assert "Local recovery note" in resolve_document(document).markdown
            before = _snapshot(monitored_context)
            with pytest.raises(PlacementConflict, match="authority changed"):
                apply_remote_observation(
                    observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
                )
            assert _snapshot(monitored_context) == before


def test_reviewed_migration_detects_source_change_before_copy(retained_monitored_context):
    installation, workspace, document, _publication, source, _observation = retained_monitored_context
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert plan.export.monitored_source_sha256 == monitored_source_fingerprint(document)
    assert all(source.url.encode() not in body for _path, body in plan.export.files)
    source.enabled = False
    source.save(update_fields=("enabled", "updated_at"))
    with pytest.raises(DocumentMigrationBlocked, match="preview_changed"):
        apply_document_import(
            workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
        )


@pytest.mark.parametrize("mode", ["digest", "failed_applied", "invalid_url"])
def test_migration_refuses_invalid_retained_source_state(retained_monitored_context, mode):
    installation, workspace, document, _publication, source, _observation = retained_monitored_context
    if mode == "invalid_url":
        source.url = "https://127.0.0.1/private"
        source.save(update_fields=("url", "updated_at"))
    else:
        bad = DocumentRemoteObservation.objects.create(
            tenant=installation.tenant, organization=None, source=source,
            state="failed" if mode == "failed_applied" else "changed", status_code=200,
            error_code="remote_connection_failed" if mode == "failed_applied" else "",
            canonical_markdown="" if mode == "failed_applied" else "Invalid digest.\n", content_digest="",
        )
        if mode == "failed_applied":
            source.last_applied_observation = bad
            source.save(update_fields=("last_applied_observation", "updated_at"))
    with pytest.raises(DocumentMigrationBlocked, match="monitored_source_history_unavailable"):
        prepare_document_import(workspace=workspace, document_id=document.id)


def test_promoted_source_api_requires_current_review_and_reloads_retained_bytes(monitored_context):
    installation, _workspace, document, _publication, source, observation = monitored_context
    client = Client()
    client.force_login(installation.owner)
    names = {"document_entity_id": document.entity_id}
    listing = client.get(reverse("msp-document-remote-observations", kwargs=names))
    assert listing.status_code == 200
    record = next(item for item in listing.json()["results"] if item["id"] == str(observation.id))
    assert not record["apply_review"]["blocker"]
    endpoint = reverse("msp-document-remote-observation-apply", kwargs={**names, "observation_id": observation.id})
    assert client.post(endpoint, {}, content_type="application/json").status_code == 409
    assert client.post(endpoint, {"review_fingerprint": record["apply_review"]["fingerprint"]},
                       content_type="application/json").status_code == 200
    source.refresh_from_db()
    assert source.last_applied_observation_id == observation.id
    assert client.post(reverse("msp-document-remote-observation-apply", kwargs={
        **names, "observation_id": uuid.uuid4(),
    }), {}, content_type="application/json").status_code == 404


def test_supplied_observation_cannot_replace_immutable_bytes(monitored_context):
    installation, _workspace, _document, _publication, _source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review
    observation.canonical_markdown = "Unretained replacement.\n"
    apply_remote_observation(
        observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
    )
    observation.refresh_from_db()
    assert observation.canonical_markdown == "Current upstream instructions.\n"


def test_monitored_files_publications_observations_and_local_edits_survive_full_journey(published_context):
    from apps.core.tests.monitored_source_fixture import (
        exercise_monitored_source_fixture,
        seed_monitored_source_fixture,
    )

    installation, *_rest = published_context
    seed_monitored_source_fixture(installation.owner)
    assert len(exercise_monitored_source_fixture(installation.owner)) == 64


def test_legacy_monitored_fingerprint_excludes_post_baseline_owner_columns() -> None:
    from apps.core.tests.monitored_source_fixture import LEGACY_REMOTE_SOURCE_FIELDS, legacy_remote_source_state

    baseline_fields = tuple(
        field.attname
        for field in DocumentRemoteSource._meta.concrete_fields
        if field.attname not in {"repository_id", "content_id"}
    )
    source = SimpleNamespace(
        **{field: field for field in LEGACY_REMOTE_SOURCE_FIELDS},
        repository_id="post-baseline-repository",
        content_id="post-baseline-content",
    )
    retained = legacy_remote_source_state(source)
    assert baseline_fields == LEGACY_REMOTE_SOURCE_FIELDS
    assert tuple(retained) == LEGACY_REMOTE_SOURCE_FIELDS
    assert "repository_id" not in retained
    assert "content_id" not in retained


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_monitored_shared_group_retains_settings_history_and_local_edits(retained_monitored_context, mode):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.documents import add_document_placement, create_document

    installation, workspace, document, _publication, _source, observation = retained_monitored_context
    consumer = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Monitored shared consumer", markdown="Consumer local instructions.\n",
    )
    add_document_placement(
        document=consumer, source_document=document, actor_id=installation.owner.id, resolution_mode=mode,
        pinned_revision_id=document.placements.get().block.current_revision_id if mode == "pinned" else None,
        parent_id=None, position=1,
    )
    for candidate in (document, consumer):
        plan = prepare_document_import(workspace=workspace, document_id=candidate.id)
        assert apply_document_import(
            workspace=workspace, document_id=candidate.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
        ).status == "imported"
    reader = resolve_msp_workspace(installation.owner)
    def transition(target):
        group = prepare_authority_group(
            workspace=workspace, document_ids=(document.id, consumer.id), actor_id=installation.owner.id,
            target=target, reader_workspace=reader,
        )
        assert transition_authority_group(
            workspace=workspace, document_ids=group.document_ids, actor_id=installation.owner.id,
            target=target, reader_workspace=reader, plan_sha256=group.plan_sha256,
        ) == "transitioned"
    transition("repository")
    review = preview_remote_observation(observation=observation)
    assert review and not review["blocker"]
    apply_remote_observation(
        observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
    )
    retained = monitored_source_fingerprint(document)
    for target in ("legacy", "repository"):
        transition(target)
        assert monitored_source_fingerprint(document) == retained
        if target == "legacy":
            body = resolve_document(consumer).markdown
            assert "Consumer local instructions." in body
            assert ("Current upstream instructions." in body) == (mode == "live")


@pytest.mark.parametrize("actor_kind", ["read_only", "other_tenant", "missing_mfa"])
def test_git_apply_repeats_edit_mfa_and_tenant_policy(monitored_context, actor_kind):
    from allauth.mfa.models import Authenticator

    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core.models import Tenant

    installation, _workspace, _document, _publication, _source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review
    actor = installation.owner
    if actor_kind == "missing_mfa":
        Authenticator.objects.filter(user=actor).delete()
    else:
        actor = User.objects.create_user(email=f"source-denied-{uuid.uuid4()}@example.invalid")
        tenant = Tenant.objects.create(name="Other monitored fixture") if actor_kind == "other_tenant" else (
            installation.tenant
        )
        TenantMembership.objects.create(
            tenant=tenant, user=actor,
            role=BuiltInRole.ADMINISTRATOR if actor_kind == "other_tenant" else BuiltInRole.READ_ONLY,
        )
        TOTP.activate(actor, generate_totp_secret())
    before = _snapshot(monitored_context)
    with pytest.raises(PlacementConflict, match="permission to edit"):
        apply_remote_observation(observation=observation, actor_id=actor.id, review_fingerprint=review["fingerprint"])
    assert _snapshot(monitored_context) == before
    client = Client()
    client.force_login(actor)
    result = client.post(reverse("msp-document-remote-observation-apply", kwargs={
        "document_entity_id": observation.source.document.entity_id, "observation_id": observation.id,
    }), {"review_fingerprint": review["fingerprint"]}, content_type="application/json")
    assert result.status_code in {403, 404}
    assert _snapshot(monitored_context) == before


def test_client_source_route_cannot_apply_another_workspaces_observation(monitored_context):
    from apps.core.organizations import create_organization

    installation, _workspace, document, _publication, _source, observation = monitored_context
    organization = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name="Other monitored client",
        legal_name="", website="", classifications=["client"],
    )
    client = Client()
    client.force_login(installation.owner)
    before = _snapshot(monitored_context)
    response = client.post(reverse("organization-document-remote-observation-apply", kwargs={
        "organization_entity_id": organization.entity_id, "document_entity_id": document.entity_id,
        "observation_id": observation.id,
    }), {}, content_type="application/json")
    assert response.status_code == 404
    assert _snapshot(monitored_context) == before


@pytest.mark.parametrize("body", [f"[Unavailable](tekdocs://attachment/{uuid.uuid4()})\n",
                                  "Synthetic oversized source.\n" * 45000], ids=["unowned_file", "oversized"])
def test_unacceptable_source_body_cannot_advance_pointer_or_git(monitored_context, body):
    installation, _workspace, _document, _publication, source, _observation = monitored_context
    observation = DocumentRemoteObservation.objects.create(
        tenant=installation.tenant, organization=None, source=source, state="changed", status_code=200,
        content_type="text/markdown", canonical_markdown=body, content_digest=hashlib.sha256(body.encode()).hexdigest(),
    )
    review = preview_remote_observation(observation=observation)
    assert review and not review["blocker"]
    before = _snapshot(monitored_context)
    with pytest.raises(PlacementConflict):
        apply_remote_observation(
            observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
        )
    assert _snapshot(monitored_context) == before


def test_authority_roundtrip_invalidates_the_old_review_even_when_git_is_unchanged(monitored_context):
    installation, workspace, document, _publication, _source, observation = monitored_context
    review = preview_remote_observation(observation=observation)
    assert review
    for target in ("legacy", "repository"):
        transition_document_authority(
            workspace=workspace, document_id=document.id, actor_id=installation.owner.id, target=target,
            reader_workspace=resolve_msp_workspace(installation.owner),
        )
    before = _snapshot(monitored_context)
    with pytest.raises(PlacementConflict, match="changed after review"):
        apply_remote_observation(
            observation=observation, actor_id=installation.owner.id, review_fingerprint=review["fingerprint"],
        )
    assert _snapshot(monitored_context) == before


def test_legacy_source_apply_remains_nestable_with_a_repository(retained_monitored_context):
    installation, _workspace, document, _publication, source, observation = retained_monitored_context
    with transaction.atomic():
        apply_remote_observation(observation=observation, actor_id=installation.owner.id)
    assert resolve_document(document).markdown == observation.canonical_markdown
    source.refresh_from_db()
    assert source.last_applied_observation_id == observation.id


@pytest.fixture
def successful_source_transport(monkeypatch):
    from apps.core import document_sources

    def install(read=None):
        destinations = []
        def resolve(url, **_kwargs):
            destinations.append(url)
            return SimpleNamespace(path="/monitored-guide", hostname="example.invalid")
        response = SimpleNamespace(
            status=200, headers={"Content-Type": "text/markdown", "ETag": "synthetic-etag"},
            read=read or (lambda _limit: b"Observed without changing the document.\n"), close=lambda: None,
        )
        pool = SimpleNamespace(urlopen=lambda *_args, **_kwargs: response, close=lambda: None)
        monkeypatch.setattr(document_sources, "resolve_public_https_target", resolve)
        monkeypatch.setattr(document_sources, "pinned_https_pool", lambda *_args, **_kwargs: pool)
        return destinations
    return install


def test_successful_promoted_check_reloads_settings_and_preserves_authored_custody(
    monitored_context, successful_source_transport,
):
    _installation, _workspace, _document, _publication, source, _observation = monitored_context
    destinations = successful_source_transport()
    DocumentRemoteSource.objects.filter(pk=source.pk).update(
        url="https://example.invalid/revised-source", check_interval_minutes=240,
    )
    applied = source.last_applied_observation_id
    before = _snapshot(monitored_context)
    result = fetch_remote_document(source)
    assert result.state == "changed" and result.canonical_markdown == "Observed without changing the document.\n"
    assert destinations == ["https://example.invalid/revised-source"]
    source.refresh_from_db()
    assert source.last_applied_observation_id == applied
    assert (source.next_check_at - source.last_checked_at).total_seconds() == 240 * 60
    assert _snapshot(monitored_context)[1:] == before[1:]


def test_check_response_does_not_wait_for_git_while_holding_source(
    monitored_context, successful_source_transport,
):
    installation, workspace, document, _publication, source, _observation = monitored_context
    fetching, release_fetch, git_pinned, release_git = Event(), Event(), Event(), Event()
    def read(_limit):
        fetching.set()
        assert release_fetch.wait(10)
        return b"Observed under repository contention.\n"
    successful_source_transport(read)
    client = Client()
    client.force_login(installation.owner)
    before = _snapshot(monitored_context)
    def check():
        close_old_connections()
        try:
            return client.post(reverse("msp-document-remote-observations", kwargs={
                "document_entity_id": document.entity_id,
            }))
        finally:
            close_old_connections()
    def pin():
        close_old_connections()
        try:
            with pin_accepted_repository_for_publication(workspace.repository.id):
                git_pinned.set()
                assert release_git.wait(10)
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as workers:
        checking = workers.submit(check)
        assert fetching.wait(5)
        pinning = workers.submit(pin)
        try:
            assert git_pinned.wait(5)
            release_fetch.set()
            # The response must complete without acquiring the unrelated held
            # Git lock. Release in finally so a regression cannot strand threads.
            response = checking.result(timeout=3)
        finally:
            release_fetch.set()
            release_git.set()
            checking.result(timeout=10)
            pinning.result(timeout=10)
    assert response.status_code == 201
    assert response.json()["apply_review"]["blocker"] == "source_review_required"
    source.refresh_from_db()
    assert source.observations.first().canonical_markdown == "Observed under repository contention.\n"
    assert _snapshot(monitored_context)[1:] == before[1:]


@pytest.mark.parametrize("damaged", [False, True])
def test_migration_status_exposes_value_free_source_custody(monitored_context, damaged):
    installation, _workspace, document, _publication, source, _observation = monitored_context
    if damaged:
        DocumentRemoteObservation.objects.create(
            tenant=installation.tenant, organization=None, source=source, state="changed", status_code=200,
            canonical_markdown="Damaged synthetic observation.\n", content_digest="",
        )
    client = Client()
    client.force_login(installation.owner)
    response = client.get(reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id}))
    assert response.status_code == 200
    status = response.json()
    assert source.url not in response.content.decode()
    assert "Damaged synthetic observation." not in response.content.decode()
    if damaged:
        assert status["monitored_source_state"] == "unavailable" and status["monitored_source_sha256"] is None
        assert "monitored_source_history_unavailable" in status["handoff_blockers"]
    else:
        assert status["monitored_source_state"] == "retained_bytes_verified"
        assert status["monitored_source_sha256"] == monitored_source_fingerprint(document)


def test_source_custody_binds_full_timestamp_precision(retained_monitored_context):
    from django.utils import timezone

    _installation, _workspace, document, _publication, source, _observation = retained_monitored_context
    checked = timezone.now().replace(microsecond=100001)
    DocumentRemoteSource.objects.filter(pk=source.pk).update(last_checked_at=checked)
    before = monitored_source_fingerprint(document)
    DocumentRemoteSource.objects.filter(pk=source.pk).update(last_checked_at=checked.replace(microsecond=100002))
    assert monitored_source_fingerprint(document) != before


def test_large_observation_history_can_be_verified_with_bounded_memory(retained_monitored_context):
    import tracemalloc

    installation, _workspace, document, _publication, source, _observation = retained_monitored_context
    body = "Synthetic retained source.\n" * 75000
    digest = hashlib.sha256(body.encode()).hexdigest()
    for index in range(16):
        DocumentRemoteObservation.objects.create(
            tenant=installation.tenant, organization=None, source=source,
            state="changed" if index == 0 else "unchanged", status_code=200, content_type="text/markdown",
            canonical_markdown=body, content_digest=digest,
        )
    tracemalloc.start()
    try:
        fingerprint = monitored_source_fingerprint(document)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert fingerprint and len(fingerprint) == 64
    assert peak < 24 * 1024 * 1024
