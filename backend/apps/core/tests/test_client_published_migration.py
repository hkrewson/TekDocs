"""Client-published migration at operator, publication and portal boundaries."""

import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.access_control import assign_organization_staff
from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import repository_storage
from apps.core.content_index import index_repository_content
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.documents import create_document
from apps.core.models import InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import approve_publication, publish_document, read_publication_artifact
from apps.core.workspaces import resolve_organization_workspace

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def client_history(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"), MEDIA_ROOT=str(tmp_path / "media")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Client migration fixture",
            owner_email=f"owner-{uuid.uuid4()}@example.invalid",
            owner_display_name="Fixture owner",
            password=f"{secrets.token_urlsafe(24)}Aa7!",
        )
        TOTP.activate(installation.owner, generate_totp_secret())
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Migration client",
            legal_name="",
            website="",
            classifications=["client"],
        )
        reader = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
        workspace = organization.ownership_workspace
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        approver = User.objects.create_user(email=f"approver-{uuid.uuid4()}@example.invalid", display_name="Approver")
        TenantMembership.objects.create(tenant=installation.tenant, user=approver, role=BuiltInRole.ADMINISTRATOR)
        TOTP.activate(approver, generate_totp_secret())
        assign_organization_staff(
            actor=installation.owner,
            organization_entity_id=organization.entity_id,
            member_user_id=approver.id,
        )
        client_user = User.objects.create_user(email=f"client-{uuid.uuid4()}@example.invalid", display_name="Client")
        TenantMembership.objects.create(
            tenant=installation.tenant,
            user=client_user,
            role=BuiltInRole.CLIENT_USER,
            organization=organization,
        )
        document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Retained client guide",
            markdown="Retained client instructions.\n",
        )
        publication = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Original client release",
            audience="client_visible",
            retention="permanent",
            retention_review_on=None,
        )
        approve_publication(publication=publication, actor_id=approver.id, reason="Independent client approval")
        yield installation, reader, workspace, document, publication, approver, client_user


def test_client_keeps_original_publication_and_pdf_through_promotion(client_history):
    installation, reader, workspace, document, publication, _approver, client_user = client_history
    client = Client()
    client.force_login(client_user)
    url = reverse("client-portal-document-detail", args=[publication.entity_id])
    before = client.get(url)
    assert before.status_code == 200
    original_pdf = read_publication_artifact(publication.artifacts.get(kind="pdf"))
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
    assert client.get(url).json() == before.json()
    artifact = publication.artifacts.get(kind="pdf")
    downloaded = client.get(
        reverse(
            "client-portal-document-artifact-download",
            args=[publication.entity_id, artifact.entity_id],
        )
    )
    assert downloaded.status_code == 200
    assert downloaded.content == original_pdf


@pytest.fixture
def promoted_client_history(client_history):
    installation, reader, workspace, document, *_rest = client_history
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    return client_history


def test_git_client_correction_requires_independent_approval_before_replacing_portal_record(promoted_client_history):
    from apps.core.publications import PublicationConflict, verify_retained_publication_custody, withdraw_publication

    installation, reader, _workspace, document, original, approver, client_user = promoted_client_history
    client = Client()
    client.force_login(client_user)
    original_url = reverse("client-portal-document-detail", args=[original.entity_id])
    correction = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Client correction from Git",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    url = reverse("client-portal-document-detail", args=[correction.entity_id])
    assert correction.lifecycle_state == "pending_approval"
    assert correction.manifest["git_source"]["audience"] == "client_visible"
    assert correction.canonical_markdown == "Retained client instructions.\n"
    assert client.get(url).status_code == 404
    assert client.get(original_url).status_code == 200
    with pytest.raises(PublicationConflict, match="different authorized user"):
        approve_publication(publication=correction, actor_id=installation.owner.id, reason="Self approval denied")
    approve_publication(publication=correction, actor_id=approver.id, reason="Approve client correction")
    assert client.get(url).status_code == 200
    assert client.get(original_url).status_code == 404
    assert verify_retained_publication_custody(original)
    assert verify_retained_publication_custody(correction)
    withdraw_publication(publication=correction, actor_id=approver.id, reason="Withdraw client instructions")
    assert client.get(url).status_code == 404
    assert client.get(original_url).status_code == 404
    assert verify_retained_publication_custody(correction)


@pytest.fixture
def audience_client_history(client_history):
    from apps.core.documents import create_document_block

    installation, _reader, _workspace, document, *_rest = client_history
    for audience, markdown in (
        ("msp_internal", "Private staff procedure.\n"),
        ("client_visible", "Client-specific procedure.\n"),
    ):
        create_document_block(
            document=document,
            actor_id=installation.owner.id,
            markdown=markdown,
            kind="rich_text",
            name="Scoped procedure",
            parent_id=None,
            position=None,
            audience_profile=audience,
        )
    return client_history


def test_audience_sections_survive_migration_without_entering_the_other_signed_edition(audience_client_history):
    installation, reader, workspace, document, _original, _approver, _client = audience_client_history
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    expected = {
        "client_visible": "Retained client instructions.\n\nClient-specific procedure.\n",
        "msp_internal": "Retained client instructions.\n\nPrivate staff procedure.\n",
    }
    for audience, markdown in expected.items():
        publication = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Retain exact audience edition",
            audience=audience,
            retention="permanent",
            retention_review_on=None,
        )
        assert publication.canonical_markdown == markdown
        assert {item["id"] for item in publication.manifest["git_source"]["sources"]} == {
            str(document.id),
            *(str(item.block_id) for item in document.placements.filter(audience_profile__in=("shared", audience))),
        }


def test_client_snapshot_keeps_file_versions_but_excludes_staff_only_files(audience_client_history):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
    from apps.core.documents import create_document_block
    from apps.core.rendering import render_pdf

    installation, reader, workspace, document, _original, _approver, _client = audience_client_history
    first = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        purpose="primary_file",
        version_number=1,
        upload=SimpleUploadedFile("client-v1.pdf", render_pdf("Retained first client file.")),
    )
    second = replace_primary_document_file(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("client-v2.pdf", render_pdf("Retained second client file.")),
    )
    files = {}
    for audience, value in (("msp_internal", b"Staff-only bytes"), ("client_visible", b"Client bytes")):
        attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile(f"{audience}.txt", value),
        )
        files[audience] = attachment
        create_document_block(
            document=document,
            actor_id=installation.owner.id,
            kind="file_reference",
            name="Scoped file",
            markdown=f"[Selected file](tekdocs://attachment/{attachment.entity_id})\n",
            parent_id=None,
            position=None,
            audience_profile=audience,
        )
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Client file edition",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )
    assert {item.source_attachment_id for item in publication.artifacts.filter(kind="attachment")} == {
        first.id,
        second.id,
        files["client_visible"].id,
    }
    assert "msp_internal.txt" not in str(publication.manifest)
    assert str(files["msp_internal"].entity_id) not in str(publication.manifest)


def test_review_retention_dates_survive_client_migration_and_git_correction(client_history):
    from datetime import timedelta

    from django.utils import timezone

    installation, reader, workspace, document, original, approver, _client_user = client_history
    date = timezone.localdate() + timedelta(days=30)
    historical = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Client retention review",
        audience="client_visible",
        retention="review_on",
        retention_review_on=date,
        supersedes_entity_id=original.entity_id,
    )
    approve_publication(publication=historical, actor_id=approver.id, reason="Approve review retention")
    signature = historical.signature
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    correction = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Preserve date in Git correction",
        audience="client_visible",
        retention="review_on",
        retention_review_on=date,
        supersedes_entity_id=historical.entity_id,
    )
    assert correction.retention_review_on == date
    assert correction.manifest["retention_review_on"] == date.isoformat()
    assert correction.lifecycle_state == "pending_approval"
    historical.refresh_from_db()
    assert historical.signature == signature
    assert historical.retention_review_on == date


@pytest.mark.parametrize("other_scope", ["sibling", "foreign_tenant"])
def test_client_portal_keeps_exact_scope_after_migration(promoted_client_history, django_runtime_role, other_scope):
    from apps.core.models import Tenant

    installation, reader, _workspace, document, original, approver, client_user = promoted_client_history
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Scoped client snapshot",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    approve_publication(publication=publication, actor_id=approver.id, reason="Independent scoped approval")
    tenant = installation.tenant if other_scope == "sibling" else Tenant.objects.create(name="Foreign fixture tenant")
    organization = create_organization(
        tenant=tenant,
        actor_id=installation.owner.id,
        name="Unrelated fixture client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    other = User.objects.create_user(email=f"other-{uuid.uuid4()}@example.invalid", display_name="Other client")
    TenantMembership.objects.create(tenant=tenant, user=other, role=BuiltInRole.CLIENT_USER, organization=organization)
    allowed, denied = Client(), Client()
    allowed.force_login(client_user)
    denied.force_login(other)
    detail = reverse("client-portal-document-detail", args=[publication.entity_id])
    artifact = publication.artifacts.get(kind="pdf")
    download = reverse("client-portal-document-artifact-download", args=[publication.entity_id, artifact.entity_id])
    with django_runtime_role():
        assert allowed.get(detail).status_code == 200
        assert allowed.get(download).status_code == 200
        expected_denial = 404 if other_scope == "sibling" else 403
        assert denied.get(detail).status_code == expected_denial
        assert denied.get(download).status_code == expected_denial
        listed = denied.get(reverse("client-portal-document-list"))
        assert listed.status_code == (200 if other_scope == "sibling" else 403)
        assert str(publication.entity_id) not in str(listed.json())
        mutation = denied.post(
            reverse(
                "organization-document-publication-list-create",
                args=[
                    document.organization.entity_id,
                    document.entity_id,
                ],
            ),
            data={"audience": "client_visible", "retention": "permanent", "reason": "Denied client mutation"},
            content_type="application/json",
        )
        assert mutation.status_code == expected_denial
        own_mutation = allowed.post(
            reverse(
                "organization-document-publication-list-create",
                args=[
                    document.organization.entity_id,
                    document.entity_id,
                ],
            ),
            data={"audience": "client_visible", "retention": "permanent", "reason": "Denied client mutation"},
            content_type="application/json",
        )
        assert own_mutation.status_code == 403
        assert allowed.get(detail).status_code == 200


def test_client_access_and_signed_artifacts_survive_body_edit_rollback_and_repromotion(promoted_client_history):
    from copy import deepcopy

    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.documents import resolve_document
    from apps.core.publications import verify_retained_publication_custody

    installation, reader, workspace, document, original, _approver, client_user = promoted_client_history
    signed = deepcopy(original.manifest), original.signature, original.content_digest
    pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
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
        markdown="Current edited instructions.\n",
        metadata_patch={},
    )
    client = Client()
    client.force_login(client_user)
    for authority in ("legacy", "repository"):
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target=authority,
                reader_workspace=reader,
            )
            == "transitioned"
        )
        assert client.get(reverse("client-portal-document-detail", args=[original.entity_id])).status_code == 200
        original.refresh_from_db()
        assert (original.manifest, original.signature, original.content_digest) == signed
        assert read_publication_artifact(original.artifacts.get(kind="pdf")) == pdf
        assert verify_retained_publication_custody(original)
    assert resolve_document(document).markdown == "Current edited instructions.\n"


def test_client_key_snapshot_does_not_disclose_unused_staff_bindings(audience_client_history):
    from apps.core.document_key_models import DocumentKeyBinding
    from apps.core.documents import create_document_block
    from apps.core.sites import create_site

    installation, reader, workspace, document, _original, _approver, _client = audience_client_history
    sites = {}
    for name, audience in (("staff", "msp_internal"), ("client", "client_visible")):
        site = create_site(
            tenant=installation.tenant,
            organization=document.organization,
            actor_id=installation.owner.id,
            name=f"{name.title()} fixture site",
            code=name.upper(),
            address_line_1="",
            address_line_2="",
            city="",
            region="",
            postal_code="",
            country_code="",
            timezone="UTC",
            phone="",
        )
        sites[name] = site
        if name == "client":
            site.entity.visibility = "client_visible"
            site.entity.save(update_fields=("visibility",))
        DocumentKeyBinding.objects.create(
            tenant=installation.tenant,
            organization=document.organization,
            workspace=workspace,
            document=document,
            name=name,
            target_entity=site.entity,
            created_by=installation.owner,
        )
        create_document_block(
            document=document,
            actor_id=installation.owner.id,
            kind="rich_text",
            name="Scoped key",
            markdown=f"Visit <tekdocs://key/{name}.name>.\n",
            parent_id=None,
            position=None,
            audience_profile=audience,
        )
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Retain client fields only",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )
    assert "Client fixture site" in publication.canonical_markdown
    assert publication.manifest["key_bindings"] == {"client": str(sites["client"].entity_id)}
    assert str(sites["staff"].entity_id) not in str(publication.manifest)
    assert "Staff fixture site" not in str(publication.manifest)


@pytest.mark.parametrize("cached_audience", ["all", "msp_internal", "client_visible"])
def test_corrupt_audience_projection_stops_preflight_and_publication(promoted_client_history, cached_audience):
    from copy import deepcopy

    from apps.core.models import ContentNode

    installation, _reader, workspace, document, _original, _approver, _client = promoted_client_history
    node = ContentNode.objects.get(repository=workspace.repository, content_id=document.id)
    original = deepcopy(node.composition_variants)
    damaged = deepcopy(original)
    damaged[cached_audience]["markdown"] = "Changed disposable cached content.\n"
    ContentNode.objects.filter(pk=node.pk).update(composition_variants=damaged)
    staff = Client()
    staff.force_login(installation.owner)
    args = [document.organization.entity_id, document.entity_id]
    try:
        preflight = staff.get(reverse("organization-document-preflight", args=args), {"audience": "client_visible"})
        assert preflight.status_code == 200
        assert preflight.json()["valid"] is False
        response = staff.post(
            reverse("organization-document-publication-list-create", args=args),
            data={"audience": "client_visible", "retention": "permanent", "reason": "Corrupt cache denied"},
            content_type="application/json",
        )
        assert response.status_code == 409
    finally:
        ContentNode.objects.filter(pk=node.pk).update(composition_variants=original)


def test_existing_client_notification_keeps_its_target_without_duplicate_delivery(client_history):
    from apps.core.outbox import dispatch_due_outbox_events

    installation, reader, workspace, document, original, _approver, client_user = client_history
    while dispatch_due_outbox_events(tenant=installation.tenant):
        pass
    client = Client()
    client.force_login(client_user)
    notifications_url = reverse("client-portal-notification-list")
    before = client.get(notifications_url)
    assert before.status_code == 200
    expected = {"kind": "portal_document", "organization_id": None, "publication_id": str(original.entity_id)}
    assert [item["target"] for item in before.json()["results"]] == [expected]
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    while dispatch_due_outbox_events(tenant=installation.tenant):
        pass
    after = client.get(notifications_url)
    assert after.status_code == 200
    assert [item["id"] for item in after.json()["results"]] == [item["id"] for item in before.json()["results"]]
    assert [item["target"] for item in after.json()["results"]] == [expected]


def test_client_upgrade_and_recovery_cohort_preserves_original_custody(client_history):
    from apps.core.tests.client_publication_fixture import (
        client_publication_retained_state,
        exercise_client_publication_fixture,
        seed_client_publication_fixture,
    )

    installation, *_rest = client_history
    seed_client_publication_fixture(installation.owner)
    before = client_publication_retained_state(installation.owner)
    exercise_client_publication_fixture(installation.owner)
    after = client_publication_retained_state(installation.owner)
    assert before["files"] == after["files"]
    assert before["members"] == after["members"]
    assert all(after["publications"][identity] == value for identity, value in before["publications"].items())


def test_runtime_role_can_preflight_and_publish_the_client_browser_cohort(client_history, django_runtime_role):
    from apps.core.models import Document
    from apps.core.tests.client_publication_fixture import (
        TITLE,
        prepare_client_publication_fixture,
        seed_client_publication_fixture,
    )

    installation, *_rest = client_history
    seed_client_publication_fixture(installation.owner)
    prepare_client_publication_fixture(installation.owner)
    document = Document.objects.get(tenant=installation.tenant, entity__display_name=TITLE)
    staff = Client()
    staff.force_login(installation.owner)
    args = [document.organization.entity_id, document.entity_id]
    with django_runtime_role():
        preflight = staff.get(reverse("organization-document-preflight", args=args), {"audience": "client_visible"})
        assert preflight.status_code == 200
        response = staff.post(
            reverse("organization-document-publication-list-create", args=args),
            data={"audience": "client_visible", "retention": "permanent", "reason": "Runtime-role client publication"},
            content_type="application/json",
        )
        assert response.status_code == 201, response.json().get("detail", response.json().get("code"))
        assert preflight.json()["valid"] is True


def test_browser_approver_has_exact_workspace_access_and_can_approve_under_runtime_role(
    client_history, django_runtime_role
):
    from apps.core.models import Document
    from apps.core.tests.client_publication_fixture import (
        TITLE,
        prepare_client_publication_fixture,
        seed_client_publication_fixture,
    )

    installation, *_rest = client_history
    seed_client_publication_fixture(installation.owner)
    prepare_client_publication_fixture(installation.owner)
    document = Document.objects.get(tenant=installation.tenant, entity__display_name=TITLE)
    original = document.publications.get(reason="Retained original client release")
    approver = original.control_events.get(action="approved").actor
    reader = resolve_organization_workspace(installation.owner, entity_id=document.organization.entity_id)
    pending = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Runtime independent approval",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
        supersedes_entity_id=original.entity_id,
    )
    reviewer = Client()
    reviewer.force_login(approver)
    with django_runtime_role():
        workspace = reviewer.get(reverse("workspace-organization", args=[document.organization.entity_id]))
        assert workspace.status_code == 200
        unrelated = client_history[3].organization.entity_id
        assert reviewer.get(reverse("workspace-organization", args=[unrelated])).status_code == 404
        response = reviewer.post(
            reverse(
                "organization-document-publication-approve",
                args=[
                    document.organization.entity_id,
                    document.entity_id,
                    pending.entity_id,
                ],
            ),
            data={"reason": "Authorized independent approval"},
            content_type="application/json",
        )
        assert response.status_code == 200, response.json().get("detail", response.json().get("code"))
        assert response.json()["lifecycle_state"] == "published"


@pytest.mark.parametrize("damage", ["missing_filter_marker", "false_filter_marker", "wrong_root_audience"])
def test_database_rejects_invalid_client_audience_certificates(promoted_client_history, damage):
    import base64
    import hashlib
    from copy import deepcopy

    from django.db import DatabaseError, transaction

    from apps.core.models import DocumentPublication, Entity
    from apps.core.publications import publication_signing_key, snapshot_payload

    installation, reader, workspace, document, _original, _approver, _client = promoted_client_history
    publication = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Audience insertion guard fixture",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )

    def insert_clone(mutation=None):
        values = DocumentPublication.objects.values().get(pk=publication.pk)
        values["id"] = uuid.uuid4()
        entity = Entity.objects.create(
            tenant=installation.tenant,
            organization=document.organization,
            workspace=workspace,
            entity_type="document_publication",
            display_name=publication.title,
            visibility="client_visible",
        )
        values["entity_id"] = entity.id
        manifest = deepcopy(publication.manifest)
        manifest.update(publication_id=str(values["id"]), publication_entity_id=str(entity.id))
        if mutation == "missing_filter_marker":
            del manifest["git_source"]["audience_filtered"]
        elif mutation == "false_filter_marker":
            manifest["git_source"]["audience_filtered"] = False
        elif mutation == "wrong_root_audience":
            manifest["git_source"]["sources"][0]["audience"] = "msp_internal"
        digest = hashlib.sha256(
            snapshot_payload(
                manifest=manifest,
                markdown=publication.canonical_markdown,
                sanitized_html=publication.sanitized_html,
            )
        ).digest()
        values.update(
            manifest=manifest,
            content_digest=digest.hex(),
            signature=base64.urlsafe_b64encode(publication_signing_key().sign(digest)).decode(),
        )
        return DocumentPublication.objects.create(**values)

    # The same complete input inserts without the defect. Roll it back because
    # normal publication creation would append controls and retained files next.
    with transaction.atomic():
        assert insert_clone().audience == "client_visible"
        transaction.set_rollback(True)
    with pytest.raises(DatabaseError, match="Git publication audience proof is invalid"), transaction.atomic():
        insert_clone(damage)


def test_stale_client_history_plan_does_not_write_a_copy_or_change_access(client_history):
    from apps.core.document_migration_import import DocumentMigrationBlocked
    from apps.core.models import DocumentAuthority

    installation, reader, workspace, document, original, _approver, client_user = client_history
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    pending = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="History changed after preview",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )
    changed = prepare_document_import(workspace=workspace, document_id=document.id)
    assert changed.plan_sha256 != plan.plan_sha256
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
    assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "legacy"
    client = Client()
    client.force_login(client_user)
    assert client.get(reverse("client-portal-document-detail", args=[original.entity_id])).status_code == 200
    assert client.get(reverse("client-portal-document-detail", args=[pending.entity_id])).status_code == 404


def test_damaged_client_pdf_blocks_migration_and_download_until_exact_bytes_are_repaired(client_history):
    from apps.core.document_migration_import import DocumentMigrationBlocked

    _installation, _reader, workspace, document, original, _approver, client_user = client_history
    artifact = original.artifacts.get(kind="pdf")
    retained = read_publication_artifact(artifact)
    client = Client()
    client.force_login(client_user)
    url = reverse("client-portal-document-artifact-download", args=[original.entity_id, artifact.entity_id])
    try:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(b"Damaged synthetic PDF bytes")
        with pytest.raises(DocumentMigrationBlocked, match="publication_parity_required"):
            prepare_document_import(workspace=workspace, document_id=document.id)
        assert client.get(url).status_code == 409
    finally:
        with artifact.file.storage.open(artifact.file.name, "wb") as stream:
            stream.write(retained)
    assert client.get(url).content == retained
    assert prepare_document_import(workspace=workspace, document_id=document.id).publication_evidence_sha256


def test_client_snapshot_excludes_unreferenced_ordinary_files_without_dropping_authoring_custody(
    audience_client_history,
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.document_attachments import copy_attachment_content, create_document_attachment
    from apps.core.publications import verify_retained_publication_custody

    installation, reader, workspace, document, _original, _approver, _client = audience_client_history
    attachment = create_document_attachment(
        document=document,
        actor_id=installation.owner.id,
        upload=SimpleUploadedFile("unreferenced-staff-notes.txt", b"Unreferenced synthetic staff notes"),
    )
    retained = copy_attachment_content(attachment)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=installation.owner.id,
    )
    transition_document_authority(
        workspace=workspace,
        document_id=document.id,
        actor_id=installation.owner.id,
        target="repository",
        reader_workspace=reader,
    )
    snapshot = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="No client file references",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )
    assert snapshot.manifest["managed_files"] == []
    assert not snapshot.artifacts.filter(kind="attachment").exists()
    assert str(attachment.entity_id) not in str(snapshot.manifest)
    assert verify_retained_publication_custody(snapshot)
    for target in ("legacy", "repository"):
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target=target,
                reader_workspace=reader,
            )
            == "transitioned"
        )
        assert copy_attachment_content(attachment) == retained


def test_client_predecessor_cannot_be_corrected_into_a_staff_edition(promoted_client_history):
    from apps.core.publications import PublicationConflict

    installation, reader, _workspace, document, original, _approver, _client = promoted_client_history
    before = document.publications.count()
    with pytest.raises(PublicationConflict):
        publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Wrong audience correction",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
            supersedes_entity_id=original.entity_id,
        )
    assert document.publications.count() == before
    assert original.lifecycle_state == "published"


def test_client_guard_migration_round_trip_preserves_history_and_restores_head(promoted_client_history):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.publications import verify_retained_publication_custody

    installation, reader, _workspace, document, original, _approver, _client = promoted_client_history
    snapshot = publish_document(
        workspace=reader,
        document=document,
        actor_id=installation.owner.id,
        reason="Client guard round trip",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )
    retained = [
        (item.manifest, item.signature, read_publication_artifact(item.artifacts.get(kind="pdf")))
        for item in (original, snapshot)
    ]
    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0211_diagram_git_publication")])
        for item, (manifest, signature, pdf) in zip((original, snapshot), retained, strict=True):
            item.refresh_from_db()
            assert item.manifest == manifest and item.signature == signature
            assert read_publication_artifact(item.artifacts.get(kind="pdf")) == pdf
    finally:
        MigrationExecutor(connection).migrate(head)
    for item in (original, snapshot):
        assert verify_retained_publication_custody(item)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication()'::regprocedure)")
        assert "Git publication audience proof is invalid" in cursor.fetchone()[0]
