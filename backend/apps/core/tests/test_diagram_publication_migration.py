"""Diagram custody through public migration and publication operations."""

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import update_document
from apps.core.publications import publish_document
from apps.core.workspaces import resolve_msp_workspace

pytest_plugins = (
    "apps.core.tests.test_document_migration_publications",
    "apps.core.tests.test_content_key_publication_migration",
)
pytestmark = pytest.mark.django_db(transaction=True)

ORIGINAL = """# Diagram guide

```mermaid
flowchart LR
accTitle: Recovery route
accDescr: Traffic passes through the recovery gateway
Client --> Gateway --> Server
```
"""


@pytest.fixture
def diagram_context(published_context):
    installation, workspace, document, original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    update_document(
        document=document, actor_id=installation.owner.id, title=document.entity.display_name,
        markdown=ORIGINAL, base_revision_id=document.placements.get().block.current_revision_id,
    )
    publication = publish_document(
        workspace=resolve_msp_workspace(installation.owner), document=document,
        actor_id=installation.owner.id, reason="Retain diagram revision", audience="msp_internal",
        retention="permanent", retention_review_on=None,
    )
    assert publication.artifacts.filter(kind__in=("diagram_svg", "diagram_png")).count() == 2
    return installation, workspace, document, original, publication


def test_verified_diagram_history_is_eligible_for_migration(diagram_context):
    _installation, workspace, document, _original, _diagram = diagram_context
    report = assess_retained_publications(workspace=workspace, document=document)
    assert report["state"] == "verified", report["reasons"]
    assert report["publication_count"] == 2
    assert report["artifact_count"] == 4


def test_migrated_diagrams_publish_from_git_and_retain_historical_graphics(diagram_context):
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.publications import read_publication_artifact, retained_publication_diagrams

    installation, workspace, document, _original, historical = diagram_context
    before = [(item.entity_id, read_publication_artifact(item)) for item in historical.artifacts.order_by("id")]
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert apply_document_import(
        workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
    ).status == "imported"
    reader = resolve_msp_workspace(installation.owner)
    assert transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=installation.owner.id,
        target="repository", reader_workspace=reader,
    ) == "transitioned"
    publication = publish_document(
        workspace=reader, document=document, actor_id=installation.owner.id,
        reason="Freeze accepted diagram source", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v11"
    assert publication.canonical_markdown == ORIGINAL
    assert len(retained_publication_diagrams(publication)) == 1
    assert 'class="mermaid-diagram-export"' in publication.sanitized_html
    assert [(item.entity_id, read_publication_artifact(item)) for item in historical.artifacts.order_by("id")] == before


@pytest.mark.parametrize("kind", ("diagram_svg", "diagram_png"))
@pytest.mark.parametrize("damage", ("missing", "corrupt"))
def test_damaged_retained_diagram_blocks_migration_without_losing_history(diagram_context, kind, damage):
    from apps.core.document_migration_import import DocumentMigrationBlocked, prepare_document_import
    from apps.core.publications import read_publication_artifact

    _installation, workspace, document, _original, historical = diagram_context
    artifact = historical.artifacts.get(kind=kind)
    original = read_publication_artifact(artifact)
    try:
        if damage == "missing":
            artifact.file.storage.delete(artifact.file.name)
        else:
            with artifact.file.storage.open(artifact.file.name, "wb") as stream:
                stream.write(b"Altered synthetic graphic")
        report = assess_retained_publications(workspace=workspace, document=document)
        assert report["state"] == "blocked"
        with pytest.raises(DocumentMigrationBlocked):
            prepare_document_import(workspace=workspace, document_id=document.id)
        assert document.publications.count() == 2
    finally:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(original)
    assert assess_retained_publications(workspace=workspace, document=document)["state"] == "verified"


@pytest.fixture
def promoted_diagram(diagram_context):
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import

    installation, workspace, document, *_ = diagram_context
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=installation.owner.id,
        target="repository", reader_workspace=resolve_msp_workspace(installation.owner),
    )
    return diagram_context


def publish_diagram(context):
    installation, _workspace, document, *_ = context
    return publish_document(
        workspace=resolve_msp_workspace(installation.owner), document=document,
        actor_id=installation.owner.id, reason="Retain Git diagram proof", audience="msp_internal",
        retention="permanent", retention_review_on=None,
    )


@pytest.mark.parametrize("damage", ("source", "checksum", "identity", "renderer", "extra", "content_format"))
def test_offline_verification_rejects_incoherent_diagram_proof(promoted_diagram, damage):
    from copy import deepcopy

    from apps.core.document_git_publications import verify_git_publication_source

    publication = publish_diagram(promoted_diagram)
    publication.manifest = deepcopy(publication.manifest)
    record = publication.manifest["diagrams"][0]
    if damage == "source":
        record["source_checksum"] = "0" * 64
    elif damage == "checksum":
        record["png_checksum"] = "0" * 64
    elif damage == "identity":
        record["png_artifact_id"] = record["svg_artifact_id"]
    elif damage == "renderer":
        record["renderer_version"] = "not-rendered"
    elif damage == "extra":
        publication.manifest["artifacts"].append(deepcopy(publication.manifest["artifacts"][-1]))
    else:
        publication.manifest["content_format"] = "tekdocs-static-publication/v4"
    assert not verify_git_publication_source(publication)


def test_renderer_unavailability_blocks_publication_without_partial_artifacts(promoted_diagram, tmp_path):
    from django.test import override_settings

    from apps.core.publications import PublicationConflict

    _installation, _workspace, document, *_ = promoted_diagram
    count = document.publications.count()
    files = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    with override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY=""), pytest.raises(PublicationConflict, match="unavailable"):
        publish_diagram(promoted_diagram)
    assert document.publications.count() == count
    assert sorted(path for path in tmp_path.rglob("*") if path.is_file()) == files


@pytest.mark.parametrize("damage", ("checksum", "identity", "renderer", "content_format"))
def test_database_rejects_invalid_diagram_certificate(promoted_diagram, damage):
    import uuid
    from copy import deepcopy

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity

    installation, workspace, document, *_ = promoted_diagram
    publication = publish_diagram(promoted_diagram)
    candidate = DocumentPublication(
        **{field.attname: getattr(publication, field.attname) for field in DocumentPublication._meta.concrete_fields}
    )
    candidate.id = uuid.uuid4()
    candidate.manifest = deepcopy(publication.manifest)
    candidate.manifest["publication_id"] = str(candidate.id)
    record = candidate.manifest["diagrams"][0]
    if damage == "checksum":
        record["png_checksum"] = "0" * 64
    elif damage == "identity":
        record["png_artifact_id"] = record["svg_artifact_id"]
    elif damage == "renderer":
        record["renderer_version"] = "not-rendered"
    else:
        candidate.manifest["content_format"] = "tekdocs-static-publication/v4"
    with pytest.raises(DatabaseError, match="Git diagram publication proof is invalid"), transaction.atomic():
        candidate.entity = Entity.objects.create(
            tenant=installation.tenant, workspace=workspace, organization=document.organization,
            entity_type="document_publication", display_name="Rejected diagram proof",
        )
        candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
        candidate.save(force_insert=True)


def test_diagram_upgrade_recovery_adapter_preserves_every_revision_and_artifact(published_context, monkeypatch, capsys):
    from apps.core.tests.diagram_fixture import diagram_recovery_fingerprint, run_diagram_fixture_mode

    owner = published_context[0].owner
    run_diagram_fixture_mode("seed")
    expected = next(line.split("=", 1)[1] for line in capsys.readouterr().out.splitlines()
                    if line.startswith("DIAGRAM_LEGACY_SHA256="))
    monkeypatch.setenv("TEKDOCS_DIAGRAM_LEGACY_SHA256", "0" * 64)
    with pytest.raises(AssertionError):
        run_diagram_fixture_mode("promote")
    monkeypatch.setenv("TEKDOCS_DIAGRAM_LEGACY_SHA256", expected)
    run_diagram_fixture_mode("promote")
    assert "Diagram revisions, signed graphics, file versions, PDFs and rollback verified" in capsys.readouterr().out
    fingerprint = diagram_recovery_fingerprint(owner)
    monkeypatch.setenv("TEKDOCS_DIAGRAM_RECOVERY_SHA256", "0" * 64)
    with pytest.raises(AssertionError):
        run_diagram_fixture_mode("recovery_verify")
    monkeypatch.setenv("TEKDOCS_DIAGRAM_RECOVERY_SHA256", fingerprint)
    run_diagram_fixture_mode("recovery_verify")
    assert "recovered exactly" in capsys.readouterr().out


def test_content_key_diagrams_freeze_the_accepted_git_source(promoted_content_key_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.publications import retained_publication_diagrams
    from apps.core.tests.test_content_key_publication_migration import reader_for

    installation, workspace, document, source = promoted_content_key_context
    fragment = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob, kind=None, path=None, title=None, markdown=ORIGINAL, metadata_patch={},
    )
    publication = publish_document(
        workspace=reader_for(installation, document), document=document, actor_id=installation.owner.id,
        reason="Freeze diagram selected by content key", audience="msp_internal", retention="permanent",
        retention_review_on=None,
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v11"
    assert publication.manifest["content_format"] == "tekdocs-static-publication/v10"
    assert len(retained_publication_diagrams(publication)) == 1
    assert verify_internal_git_publication(publication)


@pytest.mark.parametrize("mode", ("live", "pinned"))
def test_shared_diagram_sources_preserve_live_and_pinned_revisions(published_context, mode):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.documents import add_document_placement, create_document
    from apps.core.publications import retained_publication_diagrams, verify_retained_publication_custody

    installation, workspace, document, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    source = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Shared diagram source", markdown=ORIGINAL,
    )
    add_document_placement(
        document=document, source_document=source, actor_id=installation.owner.id,
        resolution_mode=mode,
        pinned_revision_id=source.placements.get().block.current_revision_id if mode == "pinned" else None,
        parent_id=None, position=1,
    )
    for item in (source, document):
        plan = prepare_document_import(workspace=workspace, document_id=item.id)
        apply_document_import(
            workspace=workspace, document_id=item.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
        )
    reader = resolve_msp_workspace(installation.owner)
    group = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, document.id), actor_id=installation.owner.id,
        target="repository", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=group.document_ids, actor_id=installation.owner.id,
        target="repository", reader_workspace=reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"
    publication = publish_diagram((installation, workspace, document))
    assert publication.manifest["content_format"] == "tekdocs-static-publication/v7"
    assert publication.manifest["git_source"]["sources"][2]["mode"] == mode
    assert len(retained_publication_diagrams(publication)) == 1
    assert verify_retained_publication_custody(publication)


def test_diagram_guard_reverses_and_reapplies_without_rewriting_signed_history(promoted_diagram):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.publications import verify_retained_publication_custody

    publication = publish_diagram(promoted_diagram)
    before = (publication.manifest, publication.signature, publication.content_digest)
    try:
        MigrationExecutor(connection).migrate([("core", "0210_content_key_authority_closure")])
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
    publication.refresh_from_db()
    assert (publication.manifest, publication.signature, publication.content_digest) == before
    assert verify_retained_publication_custody(publication)
    assert verify_retained_publication_custody(publish_diagram(promoted_diagram))


def test_runtime_role_can_publish_and_roll_back_a_diagram_document(promoted_diagram, django_runtime_role):
    from django.db import transaction

    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.publications import verify_retained_publication_custody
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    installation, workspace, document, *_ = promoted_diagram
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.owner(installation.tenant, None), organization_mode=OrganizationRLSMode.MSP_ONLY,
            principal_mode=RLSPrincipalMode.USER, actor_user_id=installation.owner.id,
        )
        publication = publish_diagram(promoted_diagram)
        assert transition_document_authority(
            workspace=workspace, document_id=document.id, actor_id=installation.owner.id,
            target="legacy", reader_workspace=resolve_msp_workspace(installation.owner),
        ) == "transitioned"
    assert verify_retained_publication_custody(publication)


@pytest.mark.parametrize("actor_kind", ("read_only", "missing_mfa", "other_tenant", "other_client"))
def test_diagram_publication_denial_preserves_history_and_withholds_source(promoted_diagram, actor_kind):
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

    installation, _workspace, document, *_ = promoted_diagram
    actor = User.objects.create_user(
        email=f"diagram-denial-{uuid.uuid4()}@example.invalid", display_name="Denied actor",
    )
    membership = TenantMembership.objects.create(
        tenant=(Tenant.objects.create(name="Other diagram installation")
                if actor_kind == "other_tenant" else installation.tenant),
        user=actor, role=BuiltInRole.READ_ONLY if actor_kind == "read_only" else BuiltInRole.ADMINISTRATOR,
        workspace_scope=(MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS if actor_kind == "other_client"
                         else MembershipWorkspaceScope.TENANT),
    )
    if actor_kind != "missing_mfa":
        TOTP.activate(actor, generate_totp_secret())
    if actor_kind == "other_client":
        other = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Other assigned diagram client",
            legal_name="", website="", classifications=["client"],
        )
        OrganizationAccessAssignment.objects.create(
            tenant=installation.tenant, organization=other, membership=membership, created_by=installation.owner,
        )
    browser = Client()
    browser.force_login(actor)
    count = document.publications.count()
    response = browser.post(
        reverse("msp-document-publication-list-create", kwargs={"document_entity_id": document.entity_id}),
        {"reason": "Denied diagram publication", "audience": "msp_internal", "retention": "permanent"},
        content_type="application/json",
    )
    assert response.status_code in {403, 404}
    assert "Recovery route" not in response.content.decode()
    assert document.publications.count() == count


@pytest.mark.parametrize("kind", ("diagram_svg", "diagram_png"))
def test_damaged_diagram_blocks_rollback_without_retiring_git_authority(promoted_diagram, kind):
    from apps.core.document_authority_handoff import DocumentAuthorityHandoffError, transition_document_authority
    from apps.core.models import DocumentAuthority
    from apps.core.publications import read_publication_artifact

    installation, workspace, document, *_ = promoted_diagram
    publication = publish_diagram(promoted_diagram)
    artifact = publication.artifacts.get(kind=kind)
    original = read_publication_artifact(artifact)
    try:
        artifact.file.storage.delete(artifact.file.name)
        with pytest.raises(DocumentAuthorityHandoffError):
            transition_document_authority(
                workspace=workspace, document_id=document.id, actor_id=installation.owner.id,
                target="legacy", reader_workspace=resolve_msp_workspace(installation.owner),
            )
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "repository"
    finally:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(original)


def test_template_source_diagram_uses_the_existing_template_certificate(published_context):
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.documents import create_document
    from apps.core.publications import verify_retained_publication_custody

    installation, workspace, _document, _original = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    source = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Template diagram source", markdown=ORIGINAL, is_template=True,
    )
    plan = prepare_document_import(workspace=workspace, document_id=source.id)
    apply_document_import(
        workspace=workspace, document_id=source.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=installation.owner.id,
    )
    from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history

    history = prepare_template_library_history(source=source, actor_id=installation.owner.id)
    assert retain_template_library_history(
        source=source, actor_id=installation.owner.id, plan_sha256=history.plan_sha256,
    ).indexed
    assert transition_document_authority(
        workspace=workspace, document_id=source.id, actor_id=installation.owner.id,
        target="repository", reader_workspace=resolve_msp_workspace(installation.owner),
    ) == "transitioned"
    publication = publish_diagram((installation, workspace, source))
    assert publication.manifest["content_format"] == "tekdocs-static-publication/v8"
    assert publication.manifest["template_source"]["content_id"] == str(source.id)
    assert verify_retained_publication_custody(publication)


@pytest.mark.parametrize("source", ("flowchart LR\nA --> [", "%%{init: {'theme': 'dark'}}%%\nflowchart LR\nA-->B"))
def test_invalid_required_diagram_does_not_create_publication_or_files(promoted_diagram, source, settings):
    from pathlib import Path

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.publications import PublicationConflict

    installation, workspace, document, *_ = promoted_diagram
    fragment = read_authored_content(repository=workspace.repository, content_id=document.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=installation.owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None,
        markdown=f"Invalid draft diagram.\n\n```mermaid\n{source}\n```\n", metadata_patch={},
    )
    count = document.publications.count()
    files = sorted(path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file())
    with pytest.raises(PublicationConflict):
        publish_diagram(promoted_diagram)
    assert document.publications.count() == count
    assert sorted(path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()) == files
