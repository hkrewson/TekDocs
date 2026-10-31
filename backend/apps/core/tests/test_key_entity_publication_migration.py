"""Preserve addressed-record meaning through the public migration workflow."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.documents import create_document, update_document
from apps.core.models import DocumentKeyBinding, workspace_for_owner
from apps.core.publications import (
    publish_document,
    read_publication_artifact,
    verify_publication,
    verify_retained_publication_custody,
)
from apps.core.sites import create_site
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace

pytest_plugins = ("apps.core.tests.test_document_migration_publications",)
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["msp", "client"])
def addressed_context(published_context, request):
    installation, workspace, document, predecessor = published_context
    TOTP.activate(installation.owner, generate_totp_secret())
    organization = None
    reader = resolve_msp_workspace(installation.owner)
    if request.param == "client":
        from apps.core.content_index import index_repository_content
        from apps.core.organizations import create_organization
        from apps.core.repository_storage import ensure_workspace_repository

        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Addressed client",
            legal_name="",
            website="",
            classifications=["client"],
        )
        workspace = workspace_for_owner(tenant=installation.tenant, organization=organization)
        ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        reader = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
        document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Client addressed guide",
            markdown="Historical client instructions.\n",
        )
        predecessor = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Retain client history",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    site = create_site(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Original operations site",
        code="OPS",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="",
        timezone="UTC",
        phone="",
    )
    binding = DocumentKeyBinding.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        organization=organization,
        document=document,
        name="subject",
        target_entity=site.entity,
        created_by=installation.owner,
    )
    source = f"Visit <tekdocs://key/subject.name>.\n\n[Site](tekdocs://entity/{site.entity_id})\n"
    update_document(
        document=document,
        actor_id=installation.owner.id,
        title=document.entity.display_name,
        markdown=source,
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    original = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain addressed site instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=predecessor.entity_id,
    )
    return SimpleNamespace(
        installation=installation,
        workspace=workspace,
        document=document,
        original=original,
        site=site,
        binding=binding,
        reader=reader,
        source=source,
        organization=organization,
    )


def promote(context):
    installation, workspace, document = context.installation, context.workspace, context.document
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
            reader_workspace=context.reader,
        )
        == "transitioned"
    )


def document_url(context, suffix, **identities):
    from django.urls import reverse

    scope = "organization" if context.organization is not None else "msp"
    values = {"document_entity_id": context.document.entity_id, **identities}
    if context.organization is not None:
        values["organization_entity_id"] = context.organization.entity_id
    return reverse(f"{scope}-document-{suffix}", kwargs=values)


def test_published_field_key_and_entity_reference_survive_migration(addressed_context):
    context = addressed_context
    installation, workspace, document = context.installation, context.workspace, context.document
    original = context.original
    reader, site, binding = context.reader, context.site, context.binding
    retained = (deepcopy(original.manifest), original.signature, original.content_digest)
    pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    assert "Original operations site" in original.sanitized_html
    promote(context)
    newer = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Publish the accepted Git instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    assert "Original operations site" in newer.sanitized_html
    assert newer.manifest["key_resolutions"][0]["value"] == "Original operations site"
    assert newer.manifest["entities"][0]["id"] == str(site.entity_id)
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
    binding.refresh_from_db()
    assert binding.target_entity_id == site.entity_id
    original.refresh_from_db()
    assert (original.manifest, original.signature, original.content_digest) == retained
    assert read_publication_artifact(original.artifacts.get(kind="pdf")) == pdf
    assert verify_publication(original)["valid"] and verify_publication(newer)["valid"]
    assert verify_retained_publication_custody(original) and verify_retained_publication_custody(newer)


def test_live_record_changes_cannot_rewrite_a_git_publication(addressed_context):
    from apps.core.content_read import document_detail
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.document_migration_publications import assess_retained_publications
    from apps.core.sites import archive_site, update_site

    context = addressed_context
    promote(context)
    publication = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Retain original record state",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    retained = (deepcopy(publication.manifest), publication.signature, publication.sanitized_html)
    pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
    update_site(site=context.site, actor_id=context.installation.owner.id, name="Renamed operations site")
    live = document_detail(workspace=context.reader, content_id=context.document.id, audience="msp_internal")
    assert "Renamed operations site" in live["sanitized_html"]
    assert "Original operations site" not in live["sanitized_html"]
    correction = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Retain changed record state",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=publication.entity_id,
    )
    assert correction.manifest["key_resolutions"][0]["value"] == "Renamed operations site"
    assert correction.manifest["entities"][0]["display_name"] == "Renamed operations site"
    archive_site(site=context.site, actor_id=context.installation.owner.id)
    publication.refresh_from_db()
    assert (publication.manifest, publication.signature, publication.sanitized_html) == retained
    assert read_publication_artifact(publication.artifacts.get(kind="pdf")) == pdf
    assert verify_internal_git_publication(publication)
    assert verify_internal_git_publication(correction)
    assert assess_retained_publications(workspace=context.workspace, document=context.document)["state"] == "verified"


@pytest.mark.parametrize("unavailable", ["missing_binding", "archived_record"])
def test_unavailable_reference_blocks_readiness_and_publishing_without_partial_history(addressed_context, unavailable):
    from django.test import Client
    from django.urls import reverse

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.publications import PublicationConflict
    from apps.core.sites import archive_site

    context = addressed_context
    promote(context)
    if unavailable == "missing_binding":
        fragment = read_authored_content(
            repository=context.workspace.repository,
            content_id=context.document.placements.get().block_id,
        )
        author_content(
            repository=context.workspace.repository,
            actor_id=context.installation.owner.id,
            request_id=None,
            operation="update",
            content_id=fragment.content_id,
            base_commit=fragment.accepted_commit,
            base_blob=fragment.source_blob,
            kind=None,
            path=None,
            title=None,
            markdown="Missing <tekdocs://key/unknown.name>.\n",
            metadata_patch={},
        )
    else:
        archive_site(site=context.site, actor_id=context.installation.owner.id)
    context.workspace.repository.refresh_from_db()
    accepted = context.workspace.repository.accepted_commit_id
    browser = Client()
    browser.force_login(context.installation.owner)
    route_scope = "organization" if context.organization is not None else "msp"
    route_ids = {"document_entity_id": context.document.entity_id}
    if context.organization is not None:
        route_ids["organization_entity_id"] = context.organization.entity_id
    history = reverse(f"{route_scope}-document-publication-list-create", kwargs=route_ids)
    before = browser.get(history).json()
    report = browser.get(
        reverse(f"{route_scope}-document-preflight", kwargs=route_ids),
        {"audience": "msp_internal"},
    )
    assert report.status_code == 200
    assert report.json()["valid"] is False
    assert "Original operations site" not in str(report.json())
    with pytest.raises(PublicationConflict, match="dependencies"):
        publish_document(
            workspace=context.reader,
            document=context.document,
            actor_id=context.installation.owner.id,
            reason="Cannot retain unavailable references",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert browser.get(history).json() == before
    context.workspace.repository.refresh_from_db()
    assert context.workspace.repository.accepted_commit_id == accepted


def test_promoted_key_report_reads_the_current_git_body(addressed_context):
    from django.test import Client

    from apps.core.content_authoring import author_content, read_authored_content

    context = addressed_context
    promote(context)
    fragment = read_authored_content(
        repository=context.workspace.repository,
        content_id=context.document.placements.get().block_id,
    )
    author_content(
        repository=context.workspace.repository,
        actor_id=context.installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Site code <tekdocs://key/subject.code>.\n",
        metadata_patch={},
    )
    browser = Client()
    browser.force_login(context.installation.owner)
    response = browser.get(document_url(context, "keys"))
    assert response.status_code == 200
    assert [row["expression"] for row in response.json()["results"]] == ["subject.code"]


def test_promoted_binding_configuration_cannot_drift_from_the_reversible_git_root(addressed_context):
    from django.test import Client

    context = addressed_context
    promote(context)
    browser = Client()
    browser.force_login(context.installation.owner)
    url = document_url(context, "key-binding-list-create")
    before = browser.get(url).json()
    response = browser.delete(document_url(context, "key-binding-detail", binding_id=context.binding.id))
    assert response.status_code == 409
    assert response.json()["code"] == "repository_binding_read_only"
    assert browser.get(url).json() == before


def test_constrained_role_migrates_publishes_and_rolls_back_addressed_history(addressed_context, django_runtime_role):
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.repository_service import coordinated_repository_transaction
    from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
    from apps.core.scoping import DataScope

    context = addressed_context
    with django_runtime_role(), coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.owner(context.installation.tenant, context.organization),
            organization_mode=(
                OrganizationRLSMode.ORGANIZATION if context.organization else OrganizationRLSMode.MSP_ONLY
            ),
            principal_mode=RLSPrincipalMode.USER,
            actor_user_id=context.installation.owner.id,
        )
        promote(context)
        publication = publish_document(
            workspace=context.reader,
            document=context.document,
            actor_id=context.installation.owner.id,
            reason="Constrained role addressed evidence",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert verify_internal_git_publication(publication)
        assert (
            transition_document_authority(
                workspace=context.workspace,
                document_id=context.document.id,
                actor_id=context.installation.owner.id,
                target="legacy",
                reader_workspace=context.reader,
            )
            == "transitioned"
        )
    assert verify_retained_publication_custody(publication)


@pytest.mark.parametrize("mutation", ["archive", "delete", "insert"])
def test_sql_cannot_change_a_promoted_binding_behind_the_git_root(addressed_context, mutation):
    from django.db import IntegrityError, transaction
    from django.utils import timezone

    context = addressed_context
    promote(context)
    with pytest.raises(IntegrityError, match="binding configuration is read-only"), transaction.atomic():
        if mutation == "archive":
            DocumentKeyBinding.objects.filter(pk=context.binding.id).update(archived_at=timezone.now())
        elif mutation == "delete":
            DocumentKeyBinding.objects.filter(pk=context.binding.id).delete()
        else:
            DocumentKeyBinding.objects.create(
                tenant=context.installation.tenant,
                workspace=context.workspace,
                organization=context.organization,
                document=context.document,
                name="second",
                target_entity=context.site.entity,
                created_by=context.installation.owner,
            )
    context.binding.refresh_from_db()
    assert context.binding.archived_at is None


@pytest.mark.parametrize(
    "damage",
    ["binding", "record", "card", "authored", "snapshot_hash", "missing_snapshot", "null_kind", "missing_kind"],
)
def test_sql_rejects_unbound_or_mismatched_addressed_proof(addressed_context, damage):
    import uuid

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity

    context = addressed_context
    promote(context)
    publication = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Valid source for scope checks",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    publication.refresh_from_db()
    candidate = DocumentPublication(
        **{field.attname: getattr(publication, field.attname) for field in DocumentPublication._meta.concrete_fields}
    )
    candidate.id = uuid.uuid4()
    candidate.manifest = deepcopy(publication.manifest)
    candidate.manifest["publication_id"] = str(candidate.id)
    if damage == "binding":
        candidate.manifest["key_bindings"]["subject"] = str(uuid.uuid4())
    elif damage == "record":
        candidate.manifest["key_resolutions"][0]["source_entity_id"] = str(uuid.uuid4())
        candidate.manifest["key_snapshot"]["records"] = deepcopy(candidate.manifest["key_resolutions"])
    elif damage in {"null_kind", "missing_kind"}:
        record = candidate.manifest["key_resolutions"][0]
        if damage == "null_kind":
            record["kind"] = None
        else:
            del record["kind"]
        candidate.manifest["key_snapshot"]["records"] = deepcopy(candidate.manifest["key_resolutions"])
    elif damage == "card":
        candidate.manifest["entities"][0]["id"] = str(uuid.uuid4())
    elif damage == "authored":
        candidate.manifest["authored_markdown"] += "Unaccepted source text.\n"
    elif damage == "snapshot_hash":
        candidate.manifest["key_snapshot"]["sha256"] = "0" * 64
    else:
        candidate.manifest["key_snapshot"] = None
    with pytest.raises(DatabaseError, match="publication.*invalid"), transaction.atomic():
        candidate.entity = Entity.objects.create(
            tenant=context.installation.tenant,
            workspace=context.workspace,
            organization=context.organization,
            entity_type="document_publication",
            display_name="Rejected identity proof",
        )
        candidate.manifest["publication_entity_id"] = str(candidate.entity_id)
        candidate.save(force_insert=True)


@pytest.mark.parametrize("actor_kind", ["read_only", "missing_mfa", "other_tenant", "other_client"])
def test_addressed_publication_denials_never_return_resolved_values(addressed_context, actor_kind):
    import uuid

    from django.test import Client

    from apps.accounts.models import (
        BuiltInRole,
        MembershipWorkspaceScope,
        OrganizationAccessAssignment,
        TenantMembership,
        User,
    )
    from apps.core.models import Tenant
    from apps.core.organizations import create_organization

    context = addressed_context
    promote(context)
    actor = User.objects.create_user(
        email=f"denied-publisher-{uuid.uuid4()}@example.invalid", display_name="Denied actor"
    )
    membership = TenantMembership.objects.create(
        tenant=(
            Tenant.objects.create(name="Other installation")
            if actor_kind == "other_tenant"
            else context.installation.tenant
        ),
        user=actor,
        role=BuiltInRole.READ_ONLY if actor_kind == "read_only" else BuiltInRole.ADMINISTRATOR,
        workspace_scope=(
            MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS
            if actor_kind == "other_client"
            else MembershipWorkspaceScope.TENANT
        ),
    )
    if actor_kind != "missing_mfa":
        TOTP.activate(actor, generate_totp_secret())
    if actor_kind == "other_client":
        other = create_organization(
            tenant=context.installation.tenant,
            actor_id=context.installation.owner.id,
            name="Other assigned client",
            legal_name="",
            website="",
            classifications=["client"],
        )
        OrganizationAccessAssignment.objects.create(
            tenant=context.installation.tenant,
            organization=other,
            membership=membership,
            created_by=context.installation.owner,
        )
    browser = Client()
    browser.force_login(actor)
    response = browser.post(
        document_url(context, "publication-list-create"),
        {
            "reason": "Denied publication attempt",
            "audience": "msp_internal",
            "retention": "permanent",
        },
        content_type="application/json",
    )
    assert response.status_code in {403, 404}
    assert "Original operations site" not in response.content.decode()


def test_addressed_migration_retains_all_primary_versions_and_linked_files(addressed_context):
    import hashlib

    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.rendering import render_pdf

    context = addressed_context
    first = create_document_attachment(
        document=context.document,
        actor_id=context.installation.owner.id,
        upload=SimpleUploadedFile("addressed-v1.pdf", render_pdf("First addressed file version.")),
        purpose="primary_file",
        version_number=1,
    )
    second = replace_primary_document_file(
        document=context.document,
        actor_id=context.installation.owner.id,
        upload=SimpleUploadedFile("addressed-v2.pdf", render_pdf("Second addressed file version.")),
    )
    linked = create_document_attachment(
        document=context.document,
        actor_id=context.installation.owner.id,
        upload=SimpleUploadedFile("addressed-checklist.txt", b"Addressed checklist bytes.\n"),
    )
    update_document(
        document=context.document,
        actor_id=context.installation.owner.id,
        title=context.document.entity.display_name,
        markdown=context.source + f"\n[Checklist](tekdocs://attachment/{linked.entity_id})\n",
        base_revision_id=context.document.placements.get().block.current_revision_id,
    )
    promote(context)
    publication = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Retain addressed file versions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert publication.manifest["format"] == "tekdocs-static-publication/v9"
    expected = {str(record.entity_id): record.checksum for record in (first, second, linked)}
    assert {record["id"]: record["checksum"] for record in publication.manifest["managed_files"]} == expected
    for artifact in publication.artifacts.filter(kind="attachment"):
        assert (
            hashlib.sha256(read_publication_artifact(artifact)).hexdigest()
            == expected[str(artifact.source_attachment.entity_id)]
        )
    assert verify_internal_git_publication(publication)
    assert (
        transition_document_authority(
            workspace=context.workspace,
            document_id=context.document.id,
            actor_id=context.installation.owner.id,
            target="legacy",
            reader_workspace=context.reader,
        )
        == "transitioned"
    )
    assert verify_retained_publication_custody(publication)


def test_addressed_guards_reverse_and_upgrade_without_rewriting_signed_history(addressed_context):
    from django.db import DatabaseError, connection
    from django.db.migrations.executor import MigrationExecutor

    context = addressed_context
    promote(context)
    publication = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Retain evidence through schema round trip",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    retained = (deepcopy(publication.manifest), publication.signature, publication.content_digest)
    pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
    head = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        MigrationExecutor(connection).migrate([("core", "0206_controlled_template_graph")])
        assert verify_retained_publication_custody(publication)
        with pytest.raises(DatabaseError, match="publication integrity metadata is invalid"):
            publish_document(
                workspace=context.reader,
                document=context.document,
                actor_id=context.installation.owner.id,
                reason="Old schema refuses a new format",
                audience="msp_internal",
                retention="permanent",
                retention_review_on=None,
            )
        MigrationExecutor(connection).migrate(head)
        successor = publish_document(
            workspace=context.reader,
            document=context.document,
            actor_id=context.installation.owner.id,
            reason="New schema accepts addressed evidence",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
            supersedes_entity_id=publication.entity_id,
        )
        assert verify_retained_publication_custody(successor)
    finally:
        MigrationExecutor(connection).migrate(head)
    publication.refresh_from_db()
    assert (publication.manifest, publication.signature, publication.content_digest) == retained
    assert read_publication_artifact(publication.artifacts.get(kind="pdf")) == pdf


def test_shared_browser_fixture_checks_git_edit_publish_and_authority_roundtrip(published_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.tests.key_entity_fixture import (
        promote_addressed_fixture,
        seed_addressed_fixture,
        verify_addressed_browser_fixture,
    )

    owner = published_context[0].owner
    fixture = seed_addressed_fixture(owner)
    promote_addressed_fixture(fixture, owner)
    fragment = read_authored_content(
        repository=fixture.document.entity.workspace.repository,
        content_id=fixture.document.placements.get().block_id,
    )
    author_content(
        repository=fixture.document.entity.workspace.repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=fixture.browser["edited_markdown"],
        metadata_patch={},
    )
    publish_document(
        workspace=resolve_organization_workspace(owner, entity_id=fixture.document.organization.entity_id),
        document=fixture.document,
        actor_id=owner.id,
        reason="Exercise the real browser fixture",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    verify_addressed_browser_fixture(fixture, owner)


def test_shared_recovery_verifier_refuses_corrupt_retained_pdf(published_context):
    from apps.core.tests.key_entity_fixture import (
        addressed_recovery_fingerprint,
        promote_addressed_fixture,
        seed_addressed_fixture,
    )

    owner = published_context[0].owner
    fixture = seed_addressed_fixture(owner)
    promote_addressed_fixture(fixture, owner)
    newer = publish_document(
        workspace=resolve_organization_workspace(owner, entity_id=fixture.document.organization.entity_id),
        document=fixture.document,
        actor_id=owner.id,
        reason="Exercise the encrypted-recovery verifier",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    expected = addressed_recovery_fingerprint(fixture, owner)
    pdf = newer.artifacts.get(kind="pdf")
    original = read_publication_artifact(pdf)
    try:
        with pdf.file.storage.open(pdf.file.name, "wb") as stream:
            stream.write(b"Corrupt retained PDF fixture.")
        with pytest.raises(AssertionError):
            addressed_recovery_fingerprint(fixture, owner)
    finally:
        with pdf.file.storage.open(pdf.file.name, "wb") as stream:
            stream.write(original)
    assert addressed_recovery_fingerprint(fixture, owner) == expected


def test_addressed_fixture_cannot_revert_another_promoted_document(addressed_context):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.tests.key_entity_fixture import promote_addressed_fixture, seed_addressed_fixture

    context = addressed_context
    promote(context)
    repository = context.workspace.repository
    fragment = read_authored_content(repository=repository, content_id=context.document.placements.get().block_id)
    author_content(
        repository=repository,
        actor_id=context.installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown="Existing accepted Git instructions.\n",
        metadata_patch={},
    )
    before = document_detail(workspace=context.reader, content_id=context.document.id, audience="msp_internal")
    other = seed_addressed_fixture(context.installation.owner)
    promote_addressed_fixture(other, context.installation.owner)
    after = document_detail(workspace=context.reader, content_id=context.document.id, audience="msp_internal")
    assert after["markdown"] == before["markdown"] == "Existing accepted Git instructions.\n"
    assert after["sanitized_html"] == before["sanitized_html"]


def test_http_readiness_accepts_current_git_key_expressions(addressed_context):
    from django.test import Client

    from apps.core.content_authoring import author_content, read_authored_content

    context = addressed_context
    promote(context)
    fragment = read_authored_content(
        repository=context.workspace.repository,
        content_id=context.document.placements.get().block_id,
    )
    author_content(
        repository=context.workspace.repository,
        actor_id=context.installation.owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=context.source + "\nSite code <tekdocs://key/subject.code>.\n",
        metadata_patch={},
    )
    browser = Client()
    browser.force_login(context.installation.owner)
    report = browser.get(document_url(context, "preflight"), {"audience": "msp_internal"})
    assert report.status_code == 200
    assert report.json()["valid"] is True, report.json()


@pytest.mark.parametrize("mutation", ["archive", "insert"])
def test_binding_writer_cannot_cross_an_uncommitted_authority_handoff(addressed_context, mutation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import IntegrityError, close_old_connections, connection
    from django.utils import timezone

    from apps.core.repository_service import coordinated_repository_transaction

    context = addressed_context
    plan = prepare_document_import(workspace=context.workspace, document_id=context.document.id)
    apply_document_import(
        workspace=context.workspace,
        document_id=context.document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=context.installation.owner.id,
    )
    attempted, finished = Event(), Event()

    def write_binding():
        close_old_connections()
        try:

            def observe_write(execute, sql, params, many, cursor_context):
                if '"core_documentkeybinding"' in sql and sql.startswith(("UPDATE", "INSERT")):
                    attempted.set()
                return execute(sql, params, many, cursor_context)

            with connection.execute_wrapper(observe_write):
                try:
                    if mutation == "archive":
                        DocumentKeyBinding.objects.filter(pk=context.binding.id).update(archived_at=timezone.now())
                    else:
                        DocumentKeyBinding.objects.create(
                            tenant=context.installation.tenant,
                            workspace=context.workspace,
                            organization=context.organization,
                            document=context.document,
                            name="racing",
                            target_entity=context.site.entity,
                            created_by=context.installation.owner,
                        )
                except IntegrityError as error:
                    assert "binding configuration is read-only" in str(error)
                    return "blocked"
                return "changed"
        finally:
            finished.set()
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with coordinated_repository_transaction():
            assert (
                transition_document_authority(
                    workspace=context.workspace,
                    document_id=context.document.id,
                    actor_id=context.installation.owner.id,
                    target="repository",
                    reader_workspace=context.reader,
                )
                == "transitioned"
            )
            pending = pool.submit(write_binding)
            assert attempted.wait(10)
            # Give the second connection a chance to enter the database guard
            # while handoff's owner lock and authority row are uncommitted.
            finished.wait(0.5)
        assert pending.result(timeout=10) == "blocked"
    context.binding.refresh_from_db()
    assert context.binding.archived_at is None
    assert not DocumentKeyBinding.objects.filter(document=context.document, name="racing").exists()


@pytest.mark.parametrize("journey", ["upgrade", "recovery"])
def test_hosted_addressed_mode_adapter_verifies_exact_source_and_rejects_mismatch(
    published_context,
    monkeypatch,
    capsys,
    journey,
):
    from apps.core.tests.key_entity_fixture import run_fixture_mode

    if journey == "upgrade":
        run_fixture_mode("seed")
        fingerprint = capsys.readouterr().out.split("ADDRESSED_LEGACY_SHA256=", 1)[1].splitlines()[0]
        variable = "TEKDOCS_ADDRESSED_LEGACY_SHA256"
        mode = "promote"
    else:
        run_fixture_mode("recovery_create")
        fingerprint = capsys.readouterr().out.split("ADDRESSED_RECOVERY_SHA256=", 1)[1].splitlines()[0]
        variable = "TEKDOCS_ADDRESSED_RECOVERY_SHA256"
        mode = "recovery_verify"
    assert len(fingerprint) == 64
    monkeypatch.setenv(variable, "0" * 64)
    with pytest.raises(AssertionError):
        run_fixture_mode(mode)
    monkeypatch.setenv(variable, fingerprint)
    run_fixture_mode(mode)
    assert ("recovered exactly" if journey == "recovery" else "verified") in capsys.readouterr().out


@pytest.mark.parametrize("shape", ["field_only", "entity_only", "literal_key"])
def test_addressed_publication_selects_only_parsed_dynamic_dependencies(addressed_context, shape):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.document_git_publications import verify_internal_git_publication

    context = addressed_context
    promote(context)
    markdown = {
        "field_only": "Visit <tekdocs://key/subject.name>.\n",
        "entity_only": f"[Site](tekdocs://entity/{context.site.entity_id})\n",
        "literal_key": "Example: `<tekdocs://key/subject.name>`.\n",
    }[shape]
    fragment = read_authored_content(
        repository=context.workspace.repository,
        content_id=context.document.placements.get().block_id,
    )
    author_content(
        repository=context.workspace.repository,
        actor_id=context.installation.owner.id,
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
    publication = publish_document(
        workspace=context.reader,
        document=context.document,
        actor_id=context.installation.owner.id,
        reason="Retain parsed dependency boundary",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    assert verify_internal_git_publication(publication)
    if shape == "literal_key":
        assert publication.manifest["format"] != "tekdocs-static-publication/v9"
        assert publication.canonical_markdown == markdown
    else:
        assert publication.manifest["format"] == "tekdocs-static-publication/v9"
        if shape == "field_only":
            assert publication.manifest["entities"] == []
            assert publication.canonical_markdown == "Visit Original operations site.\n"
        else:
            assert publication.manifest["key_snapshot"] is None
            assert publication.manifest["key_resolutions"] == []
            assert publication.manifest["entities"][0]["id"] == str(context.site.entity_id)


@pytest.mark.parametrize("reference", ["missing", "other_workspace"])
def test_migration_rejects_missing_or_foreign_record_mentions_without_partial_import(addressed_context, reference):
    import uuid

    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.organizations import create_organization

    context = addressed_context
    if reference == "other_workspace":
        other = create_organization(
            tenant=context.installation.tenant,
            actor_id=context.installation.owner.id,
            name="Foreign mention client",
            legal_name="",
            website="",
            classifications=["client"],
        )
        foreign_site = create_site(
            tenant=context.installation.tenant,
            organization=other,
            actor_id=context.installation.owner.id,
            name="Foreign client site",
            code="OTHER",
            address_line_1="",
            address_line_2="",
            city="",
            region="",
            postal_code="",
            country_code="",
            timezone="UTC",
            phone="",
        )
        assert foreign_site.entity.workspace_id != context.workspace.id
        identity = foreign_site.entity_id
    else:
        identity = uuid.uuid4()
    update_document(
        document=context.document,
        actor_id=context.installation.owner.id,
        title=context.document.entity.display_name,
        markdown=context.source + f"\n[Unavailable](tekdocs://entity/{identity})\n",
        base_revision_id=context.document.placements.get().block.current_revision_id,
    )
    repository = context.workspace.repository
    repository.refresh_from_db()
    head = repository.accepted_commit_id
    count = context.document.publications.count()
    with pytest.raises(DocumentMigrationBlocked, match="publication_parity_required"):
        prepare_document_import(workspace=context.workspace, document_id=context.document.id)
    repository.refresh_from_db()
    assert repository.accepted_commit_id == head
    assert context.document.publications.count() == count
    assert verify_retained_publication_custody(context.original)
