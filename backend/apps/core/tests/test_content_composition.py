from __future__ import annotations

import base64
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from types import SimpleNamespace

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core import content_composition, content_publication_sources, repository_service, repository_storage
from apps.core.content_composition import ContentCompositionError, ContentCompositionResolver
from apps.core.content_index import ContentIndexValidationError, content_graph_projection, index_repository_content
from apps.core.content_profile import parse_content
from apps.core.content_publication_sources import (
    ContentPublicationSourceError,
    freeze_git_document_dependencies,
    pinned_git_document_dependencies,
)
from apps.core.document_attachments import create_document_attachment, create_repository_document_attachment
from apps.core.document_key_models import DocumentKeyBinding
from apps.core.documents import create_document
from apps.core.models import (
    AuditEvent,
    ContentInclude,
    ContentNode,
    ContentTemplateSource,
    EntityVisibility,
    InstallationState,
    NotificationEmailDelivery,
    NotificationEmailState,
    OutboxEvent,
    RepositoryEvidenceAttachment,
    RepositoryEvidenceReviewDecision,
    RepositoryPackageAuthorization,
    RepositoryPublicationEvidence,
    RepositoryPublicationPackage,
    RepositoryStaticDeliveryAuthorization,
    RepositoryStaticPublication,
    RepositoryStaticPublicationControlEvent,
    Tenant,
    Workspace,
    WorkspaceKind,
    WorkspaceRepository,
)
from apps.core.notification_email import dispatch_due_notification_emails
from apps.core.organizations import create_organization
from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events
from apps.core.publications import publication_signing_key
from apps.core.repository_publication_evidence import (
    RepositoryPublicationEvidenceError,
    evidence_payload,
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from apps.core.repository_publication_packages import verify_repository_publication_package
from apps.core.repository_publication_preflight import repository_publication_preflight
from apps.core.repository_service import RepositoryFileNotFoundError
from apps.core.repository_static_delivery import _client_reference_projection_safe
from apps.core.repository_static_publications import verify_repository_static_publication
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset

pytestmark = pytest.mark.django_db(transaction=True)


def _content(
    *,
    content_id: uuid.UUID,
    title: str,
    body: str,
    kind: str = "document",
    metadata: str = "",
) -> bytes:
    return (
        f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\ntitle: {title}\n{metadata}---\n{body}"
    ).encode()


def _include(*, content_id: uuid.UUID, mode: str, audience: str, commit: str = "") -> str:
    value = f"  - id: {content_id}\n    mode: {mode}\n    audience: {audience}\n"
    return value + (f"    commit: {commit}\n" if commit else "")


@pytest.fixture
def composition_repository(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Composition MSP",
            owner_email="composition-owner@example.invalid",
            owner_display_name="Composition Owner",
            password="CompositionPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        yield installation, workspace, repository


def _accepted(repository) -> str | None:  # type: ignore[no-untyped-def]
    repository.refresh_from_db()
    return repository.accepted_commit.object_id if repository.accepted_commit_id else None


def test_publication_source_freeze_pins_exact_git_blobs_and_audience(composition_repository, monkeypatch):
    _installation, _workspace, repository = composition_repository
    source_id = uuid.uuid4()
    nested_id = uuid.uuid4()
    document_id = uuid.uuid4()
    first_source = _content(
        content_id=source_id,
        title="Shared procedure",
        kind="fragment",
        metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="shared"),
        body="First source.\n",
    )
    first_nested = _content(content_id=nested_id, title="Nested", kind="fragment", body="First nested.\n")
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"fragments/source.md": first_source, "fragments/nested.md": first_nested},
        message="Add first source versions",
    )
    second_source = _content(
        content_id=source_id,
        title="Shared procedure",
        kind="fragment",
        metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="msp_internal"),
        body="Second source.\n",
    )
    second_nested = _content(content_id=nested_id, title="Nested", kind="fragment", body="Second nested.\n")
    document_source = _content(
        content_id=document_id,
        title="Publication candidate",
        metadata=(
            "includes:\n"
            + _include(content_id=source_id, mode="pinned", audience="shared", commit=first.object_id)
            + _include(content_id=source_id, mode="live", audience="msp_internal")
        ),
        body="Root body.\n",
    )
    second = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/source.md": second_source,
            "fragments/nested.md": second_nested,
            "documents/candidate.md": document_source,
        },
        message="Add publication candidate",
    )
    index_repository_content(repository_id=repository.id)

    internal = freeze_git_document_dependencies(
        repository_id=repository.id, content_id=document_id, audience="msp_internal"
    )
    assert internal == freeze_git_document_dependencies(
        repository_id=repository.id, content_id=document_id, audience="msp_internal"
    )
    assert internal["accepted_commit"] == second.object_id
    assert [item["commit"] for item in internal["sources"]] == [
        second.object_id,
        first.object_id,
        first.object_id,
        second.object_id,
        second.object_id,
    ]
    assert [item["ordinal_path"] for item in internal["sources"]] == [[], [0], [0, 0], [1], [1, 0]]
    assert internal["sources"][1]["blob"] != internal["sources"][3]["blob"]
    assert internal["sources"][1]["path"] == "fragments/source.md"
    assert internal["sources"][0]["path"] == "documents/candidate.md"
    blob_input = f"blob {len(document_source)}\0".encode() + document_source
    assert internal["sources"][0]["blob"] == hashlib.sha1(blob_input).hexdigest()  # noqa: S324  # Git identity
    assert internal["sources"][0]["source_sha256"] == hashlib.sha256(document_source).hexdigest()

    client = freeze_git_document_dependencies(
        repository_id=repository.id, content_id=document_id, audience="client_visible"
    )
    assert [item["commit"] for item in client["sources"]] == [
        second.object_id,
        first.object_id,
        first.object_id,
    ]
    assert client["sources"][1:3] == internal["sources"][1:3]

    def missing_pinned_commit(*, repository_id, object_id):  # type: ignore[no-untyped-def]
        raise RepositoryFileNotFoundError("Pinned object is missing")

    monkeypatch.setattr(content_publication_sources, "read_repository_markdown_files_at_commit", missing_pinned_commit)
    with pytest.raises(ContentPublicationSourceError, match="source objects are unavailable"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")


def test_publication_source_freeze_rejects_stale_or_tampered_projection(composition_repository):
    _installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="First.\n")},
        message="Add candidate",
    )
    index_repository_content(repository_id=repository.id)
    ContentNode.objects.filter(repository=repository, content_id=document_id).update(composition_variants={})
    with pytest.raises(ContentPublicationSourceError, match="composition differs"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")

    index_repository_content(repository_id=repository.id, force=True)
    ContentNode.objects.filter(repository=repository, content_id=document_id).update(topic_type="procedure")
    with pytest.raises(ContentPublicationSourceError, match="metadata differs"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")

    index_repository_content(repository_id=repository.id, force=True)
    ContentNode.objects.filter(repository=repository, content_id=document_id).update(frontmatter={})
    with pytest.raises(ContentPublicationSourceError, match="metadata differs"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")

    index_repository_content(repository_id=repository.id, force=True)
    ContentNode.objects.filter(repository=repository, content_id=document_id).update(title="Forged title")
    with pytest.raises(ContentPublicationSourceError, match="metadata differs"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")

    index_repository_content(repository_id=repository.id, force=True)
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="Second.\n")},
        message="Advance candidate without indexing",
    )
    with pytest.raises(ContentPublicationSourceError, match="index is not current"):
        freeze_git_document_dependencies(repository_id=repository.id, content_id=document_id, audience="msp_internal")


def test_publication_source_pin_blocks_head_advance_until_retention_finishes(composition_repository):
    _installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="First.\n")},
        message="Add candidate",
    )
    index_repository_content(repository_id=repository.id)
    started = Event()

    def advance_head():
        started.set()
        return repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=first.object_id,
            changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="Next.\n")},
            message="Advance candidate",
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document_id, audience="msp_internal"
        ) as proof:
            assert proof["accepted_commit"] == first.object_id
            future = pool.submit(advance_head)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            assert _accepted(repository) == first.object_id
        assert future.result(timeout=10).created
    assert _accepted(repository) != first.object_id


def test_publication_source_pin_holds_database_row_through_outer_request_commit(composition_repository):
    _installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="First.\n")},
        message="Add candidate",
    )
    index_repository_content(repository_id=repository.id)
    started = Event()

    def advance_head():
        started.set()
        return repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=first.object_id,
            changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="Next.\n")},
            message="Advance candidate",
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            with pinned_git_document_dependencies(
                repository_id=repository.id, content_id=document_id, audience="msp_internal"
            ) as proof:
                assert proof["accepted_commit"] == first.object_id
                future = pool.submit(advance_head)
                assert started.wait(5)
                with pytest.raises(TimeoutError):
                    future.result(timeout=0.2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
        assert future.result(timeout=10).created


def test_publication_source_pin_rolls_back_retention_and_rejects_index_lag(composition_repository):
    _installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="First.\n")},
        message="Add candidate",
    )
    index_repository_content(repository_id=repository.id)
    with pytest.raises(RuntimeError, match="retention failed"):
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document_id, audience="msp_internal"
        ):
            ContentNode.objects.filter(repository=repository, content_id=document_id).update(title="Unretained")
            raise RuntimeError("retention failed")
    assert ContentNode.objects.get(repository=repository, content_id=document_id).title == "Candidate"

    with pytest.raises(ContentPublicationSourceError, match="cannot be pinned"):
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document_id, audience="msp_internal"
        ):
            WorkspaceRepository.objects.filter(pk=repository.id).update(indexed_commit=None)
    repository.refresh_from_db()
    assert repository.indexed_commit_id == repository.accepted_commit_id

    with transaction.atomic():
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document_id, audience="msp_internal"
        ) as proof:
            assert proof["accepted_commit"] == first.object_id

    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="Next.\n")},
        message="Advance without indexing",
    )
    with pytest.raises(ContentPublicationSourceError, match="cannot be pinned"):
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document_id, audience="msp_internal"
        ):
            pytest.fail("An unindexed source must never enter publication retention")


def test_repository_evidence_api_retains_safe_staff_summary_and_denies_portal(composition_repository):
    installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body="Private body.\n")},
        message="Add API publication candidate",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-repository-publication-evidence")
    payload = json.dumps({"content_id": str(document_id), "audience": "msp_internal"})
    assert browser.post(url, data=payload, content_type="application/json").status_code == 403
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    response = browser.post(url, data=payload, content_type="application/json")
    assert response.status_code == 201
    summary = response.json()
    assert summary["content_id"] == str(document_id)
    assert summary["verified"] is True
    assert summary["title"] == "Candidate"
    assert "Private body" not in response.content.decode()
    assert "manifest" not in summary and "pdf_file" not in summary
    listed = browser.get(url)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert len(listed.json()["results"]) == 1
    assert "verified" not in listed.json()["results"][0]
    assert browser.get(url, {"page": 2, "page_size": 1}).json()["results"] == []
    assert browser.get(url, {"page_size": 101}).status_code == 400
    detail_url = reverse("msp-repository-publication-evidence-detail", args=[summary["id"]])
    assert browser.get(detail_url).json()["verified"] is True
    review_url = reverse("msp-repository-publication-evidence-review", args=[summary["id"]])
    review_html_url = reverse("msp-repository-publication-evidence-review-html", args=[summary["id"]])
    review_pdf_url = reverse("msp-repository-publication-evidence-review-pdf", args=[summary["id"]])
    reviewed = browser.get(review_url)
    assert reviewed.status_code == 200
    assert "Private body." in reviewed.json()["canonical_markdown"]
    assert "manifest" not in reviewed.json() and "pdf_file" not in reviewed.json()
    reviewed_html = browser.get(review_html_url)
    assert reviewed_html.status_code == 200
    assert b"Private body." in reviewed_html.content
    assert reviewed_html["Content-Type"] == "text/html; charset=utf-8"
    assert reviewed_html["Cache-Control"] == "private, no-store"
    assert reviewed_html["X-Content-Type-Options"] == "nosniff"
    assert reviewed_html["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert reviewed_html["Content-Disposition"].startswith("attachment;")
    reviewed_pdf = browser.get(review_pdf_url)
    assert reviewed_pdf.status_code == 200
    assert reviewed_pdf.content.startswith(b"%PDF-")
    assert reviewed_pdf["Content-Type"] == "application/pdf"
    assert reviewed_pdf["Cache-Control"] == "private, no-store"
    assert reviewed_pdf["X-Content-Type-Options"] == "nosniff"
    assert reviewed_pdf["Content-Disposition"].startswith("attachment;")

    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Evidence Client",
        legal_name="Evidence Client LLC",
        website="",
        classifications=["client"],
    )
    client_user = User.objects.create_user(email="evidence-client@example.invalid", display_name="Client Reader")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=client_user,
        role=BuiltInRole.CLIENT_USER,
        organization=organization,
    )
    browser.force_login(client_user)
    assert browser.get(url).status_code == 403
    assert browser.get(detail_url).status_code == 403
    assert browser.get(review_url).status_code == 403
    assert browser.get(review_html_url).status_code == 403
    assert browser.get(review_pdf_url).status_code == 403
    assert browser.post(url, data=payload, content_type="application/json").status_code == 403


def test_repository_evidence_api_enforces_exact_organization_scope(composition_repository):
    installation, _workspace, _repository = composition_repository
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    first = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id,
        name="Evidence First", legal_name="Evidence First LLC", website="", classifications=["client"],
    )
    second = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id,
        name="Evidence Second", legal_name="Evidence Second LLC", website="", classifications=["client"],
    )
    first_workspace = Workspace.objects.get(organization=first)
    second_workspace = Workspace.objects.get(organization=second)
    first_repository = repository_storage.ensure_workspace_repository(first_workspace).repository
    repository_storage.ensure_workspace_repository(second_workspace)
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=first_repository.id,
        expected_base=_accepted(first_repository),
        changes={
            "documents/client-candidate.md": _content(
                content_id=document_id, title="Client candidate", body="Scoped body.\n"
            )
        },
        message="Add scoped publication candidate",
    )
    index_repository_content(repository_id=first_repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    first_url = reverse("organization-repository-publication-evidence", args=[first.entity_id])
    second_url = reverse("organization-repository-publication-evidence", args=[second.entity_id])
    response = browser.post(
        first_url,
        data=json.dumps({"content_id": str(document_id), "audience": "client_visible"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    evidence_id = response.json()["id"]
    assert browser.get(first_url).json()["count"] == 1
    assert browser.get(second_url).json()["results"] == []
    assert browser.get(first_url, {"content_id": str(document_id)}).json()["count"] == 1
    assert browser.get(second_url, {"content_id": str(document_id)}).json()["count"] == 0
    msp_url = reverse("msp-repository-publication-evidence")
    assert browser.get(msp_url, {"content_id": str(document_id)}).json()["count"] == 0
    other_detail = reverse("organization-repository-publication-evidence-detail", args=[second.entity_id, evidence_id])
    assert browser.get(other_detail).status_code == 404
    assert browser.get(reverse("msp-repository-publication-evidence-detail", args=[evidence_id])).status_code == 404
    own_review = reverse("organization-repository-publication-evidence-review", args=[first.entity_id, evidence_id])
    other_review = reverse("organization-repository-publication-evidence-review", args=[second.entity_id, evidence_id])
    own_review_pdf = reverse(
        "organization-repository-publication-evidence-review-pdf", args=[first.entity_id, evidence_id]
    )
    own_review_html = reverse(
        "organization-repository-publication-evidence-review-html", args=[first.entity_id, evidence_id]
    )
    other_review_html = reverse(
        "organization-repository-publication-evidence-review-html", args=[second.entity_id, evidence_id]
    )
    other_review_pdf = reverse(
        "organization-repository-publication-evidence-review-pdf", args=[second.entity_id, evidence_id]
    )
    assert browser.get(own_review).status_code == 200
    assert browser.get(other_review).status_code == 404
    assert browser.get(own_review_pdf).status_code == 200
    assert browser.get(own_review_html).status_code == 200
    assert browser.get(other_review_html).status_code == 404
    assert browser.get(other_review_pdf).status_code == 404
    foreign_tenant = Tenant.objects.create(name="Foreign review MSP", slug="foreign-review-msp")
    foreign_reviewer = User.objects.create_user(email="foreign-reviewer@example.invalid", display_name="Foreign")
    TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_reviewer, role=BuiltInRole.ADMINISTRATOR)
    browser.force_login(foreign_reviewer)
    assert browser.get(own_review_html).status_code in {403, 404}
    assert browser.get(own_review_pdf).status_code in {403, 404}


def test_repository_evidence_list_filters_one_document_before_pagination(composition_repository):
    installation, _workspace, repository = composition_repository
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/first.md": _content(content_id=first_id, title="First", body="First private body.\n"),
            "documents/second.md": _content(content_id=second_id, title="Second", body="Second private body.\n"),
        },
        message="Add two evidence candidates",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-repository-publication-evidence")
    for content_id in (first_id, second_id):
        created = browser.post(
            url,
            data=json.dumps({"content_id": str(content_id), "audience": "msp_internal"}),
            content_type="application/json",
        )
        assert created.status_code == 201, created.content
    selected = browser.get(url, {"content_id": str(first_id), "page_size": 1})
    assert selected.status_code == 200
    assert selected.json()["count"] == 1
    assert selected.json()["has_more"] is False
    assert [item["content_id"] for item in selected.json()["results"]] == [str(first_id)]
    assert browser.get(url, {"content_id": str(second_id)}).json()["count"] == 1
    assert browser.get(url, {"content_id": str(uuid.uuid4())}).json()["results"] == []
    assert browser.get(url, {"content_id": "not-a-uuid"}).status_code == 400
    reader = User.objects.create_user(email="evidence-list-reader@example.invalid", display_name="Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    browser.force_login(reader)
    assert browser.get(url, {"content_id": str(first_id)}).status_code == 403


@pytest.mark.parametrize("link_id_kind", ["entity_id", "id"])
def test_repository_evidence_attachment_review_enforces_organization_boundary(
    composition_repository, tmp_path, link_id_kind
):
    installation, _workspace, _repository = composition_repository
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        first = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id,
            name="Attachment First", legal_name="Attachment First LLC", website="", classifications=["client"],
        )
        second = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id,
            name="Attachment Second", legal_name="Attachment Second LLC", website="", classifications=["client"],
        )
        repository = repository_storage.ensure_workspace_repository(
            Workspace.objects.get(organization=first)
        ).repository
        document = create_document(
            tenant=installation.tenant, organization=first, actor_id=installation.owner.id,
            title="Client attachment", markdown="Legacy source.\n",
        )
        attachment = create_document_attachment(
            document=document, actor_id=installation.owner.id,
            upload=SimpleUploadedFile("private.txt", b"First client only"),
        )
        repository_service.commit_repository_files(
            repository_id=repository.id, expected_base=_accepted(repository),
            changes={"documents/client-attachment.md": _content(
                content_id=document.id, title="Client attachment",
                body=f"[Private](tekdocs://attachment/{getattr(attachment, link_id_kind)})\n",
            )},
            message="Add scoped attachment source",
        )
        index_repository_content(repository_id=repository.id)
        Authenticator.objects.create(
            user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
        )
        evidence = retain_repository_publication_evidence(
            repository_id=repository.id, content_id=document.id,
            audience="client_visible", actor=installation.owner,
        )
        artifact = RepositoryEvidenceAttachment.objects.get(evidence=evidence)
        own_url = reverse(
            "organization-repository-publication-evidence-review-attachment",
            args=[first.entity_id, evidence.id, artifact.id],
        )
        other_url = reverse(
            "organization-repository-publication-evidence-review-attachment",
            args=[second.entity_id, evidence.id, artifact.id],
        )
        msp_url = reverse("msp-repository-publication-evidence-review-attachment", args=[evidence.id, artifact.id])
        browser = Client()
        browser.force_login(installation.owner)
        assert browser.get(own_url).content == b"First client only"
        assert browser.get(other_url).status_code == 404
        assert browser.get(msp_url).status_code == 404
        Authenticator.objects.filter(user=installation.owner).delete()
        assert browser.get(own_url).status_code == 403

        client_user = User.objects.create_user(email="attachment-client@example.invalid", display_name="Client")
        TenantMembership.objects.create(
            tenant=installation.tenant, user=client_user, role=BuiltInRole.CLIENT_USER, organization=first,
        )
        browser.force_login(client_user)
        assert browser.get(own_url).status_code == 403

        foreign_tenant = Tenant.objects.create(name="Foreign attachment MSP", slug="foreign-attachment-msp")
        foreign_reviewer = User.objects.create_user(email="foreign-attachment@example.invalid", display_name="Foreign")
        TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_reviewer, role=BuiltInRole.ADMINISTRATOR)
        browser.force_login(foreign_reviewer)
        assert browser.get(own_url).status_code in {403, 404}


def test_repository_evidence_review_uses_retained_source_and_fails_closed(composition_repository, monkeypatch):
    installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    initial = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/review.md": _content(content_id=document_id, title="Review", body="Retained text.\n")},
        message="Add review source",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    browser = Client()
    browser.force_login(installation.owner)
    created = browser.post(
        reverse("msp-repository-publication-evidence"),
        data=json.dumps({"content_id": str(document_id), "audience": "msp_internal"}),
        content_type="application/json",
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]
    review_url = reverse("msp-repository-publication-evidence-review", args=[evidence_id])
    review_html_url = reverse("msp-repository-publication-evidence-review-html", args=[evidence_id])
    review_pdf_url = reverse("msp-repository-publication-evidence-review-pdf", args=[evidence_id])
    evidence = RepositoryPublicationEvidence.objects.get(pk=evidence_id)
    retained_html = evidence.manifest["rendered_snapshot"]["html"].encode("utf-8")
    with evidence.pdf_file.storage.open(evidence.pdf_file.name, "rb") as stream:
        retained_pdf = stream.read()
    updated = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=initial.object_id,
        changes={"documents/review.md": _content(content_id=document_id, title="Review", body="New text.\n")},
        message="Advance review source",
    )
    index_repository_content(repository_id=repository.id)
    assert updated.object_id != initial.object_id
    reviewed = browser.get(review_url)
    assert reviewed.status_code == 200
    assert reviewed.json()["source_commit"] == initial.object_id
    assert "Retained text." in reviewed.json()["canonical_markdown"]
    assert "New text." not in reviewed.content.decode()
    assert browser.get(review_html_url).content == retained_html
    assert browser.get(review_pdf_url).content == retained_pdf

    storage = evidence.pdf_file.storage
    original_open = storage.open
    reads = 0

    def changed_between_checks(name, mode="rb"):
        nonlocal reads
        if name != evidence.pdf_file.name:
            return original_open(name, mode)
        reads += 1
        return BytesIO(retained_pdf if reads == 1 else retained_pdf + b"altered")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "open", changed_between_checks)
        changed = browser.get(review_pdf_url)
    assert reads == 2
    assert changed.status_code == 409
    assert not changed.content.startswith(b"%PDF-")

    read_only_user = User.objects.create_user(email="review-reader@example.invalid", display_name="Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=read_only_user, role=BuiltInRole.READ_ONLY)
    browser.force_login(read_only_user)
    assert browser.get(review_url).status_code == 403
    assert browser.get(review_html_url).status_code == 403
    assert browser.get(review_pdf_url).status_code == 403

    evidence.pdf_file.storage.delete(evidence.pdf_file.name)
    browser.force_login(installation.owner)
    rejected = browser.get(review_url)
    assert rejected.status_code == 409
    assert "Retained text." not in rejected.content.decode()
    assert browser.get(review_html_url).status_code == 409
    assert browser.get(review_pdf_url).status_code == 409


@pytest.mark.parametrize("source_id_kind", ("record", "entity", "native"))
def test_repository_evidence_decision_is_separate_from_distribution(
    composition_repository, tmp_path, settings, monkeypatch, source_id_kind
):
    installation, _workspace, _repository = composition_repository
    settings.MEDIA_ROOT = str(tmp_path / "media")
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Decision Client",
        legal_name="Decision Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = Workspace.objects.get(organization=organization)
    repository = repository_storage.ensure_workspace_repository(workspace).repository
    if source_id_kind == "native":
        content_id = uuid.uuid4()
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=_accepted(repository),
            changes={"documents/decision.md": _content(
                content_id=content_id, title="Decision", body="Review me.\n",
            )},
            message="Add Git-owned review source",
        )
        index_repository_content(repository_id=repository.id)
        attachment = create_repository_document_attachment(
            repository=repository,
            content_id=content_id,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("decision-guide.txt", b"Client setup instructions"),
        )
        linked_attachment_id = attachment.entity_id
    else:
        document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Decision",
            markdown="Legacy source.\n",
        )
        attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("decision-guide.txt", b"Client setup instructions"),
        )
        linked_attachment_id = attachment.entity_id if source_id_kind == "entity" else attachment.id
        content_id = document.id
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/decision.md": _content(
            content_id=content_id, title="Decision",
            body=f"Review me.\n\n[Guide](tekdocs://attachment/{linked_attachment_id})\n",
        )},
        message="Add review decision source",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    browser = Client()
    if source_id_kind == "native":
        foreign_tenant = Tenant.objects.create(
            name="Native evidence foreign MSP", slug=f"native-evidence-{uuid.uuid4()}"
        )
        foreign_actor = User.objects.create_user(
            email="native-evidence-foreign@example.invalid", display_name="Foreign owner"
        )
        TenantMembership.objects.create(
            tenant=foreign_tenant, user=foreign_actor, role=BuiltInRole.ADMINISTRATOR
        )
        browser.force_login(foreign_actor)
        denied = browser.post(
            reverse("organization-repository-publication-evidence", args=[organization.entity_id]),
            data=json.dumps({"content_id": str(content_id), "audience": "client_visible"}),
            content_type="application/json",
        )
        assert denied.status_code in {403, 404}
    browser.force_login(installation.owner)
    created = browser.post(
        reverse("organization-repository-publication-evidence", args=[organization.entity_id]),
        data=json.dumps({"content_id": str(content_id), "audience": "client_visible"}),
        content_type="application/json",
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]
    url = reverse("organization-repository-publication-evidence-decision", args=[organization.entity_id, evidence_id])
    payload = json.dumps({"outcome": "accepted_for_packaging", "reason": "Exact source reviewed"})
    assert browser.post(url, data=payload, content_type="application/json").status_code == 409
    reviewer = User.objects.create_user(email="evidence-reviewer@example.invalid", display_name="Reviewer")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant, user=reviewer, role=BuiltInRole.ADMINISTRATOR
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=organization,
        membership=membership,
        created_by=installation.owner,
    )
    browser.force_login(reviewer)
    assert browser.post(url, data=payload, content_type="application/json").status_code == 403
    review_pdf_url = reverse(
        "organization-repository-publication-evidence-review-pdf", args=[organization.entity_id, evidence_id]
    )
    assert browser.get(review_pdf_url).status_code == 403
    Authenticator.objects.create(user=reviewer, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()})
    accepted = browser.post(url, data=payload, content_type="application/json")
    assert accepted.status_code == 201
    assert accepted.json()["permits_distribution"] is False
    package_url = reverse(
        "organization-repository-publication-evidence-package", args=[organization.entity_id, evidence_id]
    )
    assert browser.get(package_url).status_code == 404
    packaged = browser.post(package_url)
    assert packaged.status_code == 201, packaged.content
    assert packaged.json()["verified"] is True
    assert packaged.json()["permits_distribution"] is False
    package = RepositoryPublicationPackage.objects.get(pk=packaged.json()["id"])
    assert (
        package.manifest["evidence_digest"]
        == RepositoryPublicationEvidence.objects.get(pk=evidence_id).content_digest
    )
    assert package.manifest["pdf_sha256"]
    assert package.manifest["html_sha256"]
    assert browser.get(package_url).json()["manifest_digest"] == package.manifest_digest
    assert browser.post(package_url).status_code == 409
    authorization_url = reverse(
        "organization-repository-publication-evidence-package-authorization",
        args=[organization.entity_id, evidence_id],
    )
    static_url = reverse(
        "organization-repository-publication-evidence-static-publication",
        args=[organization.entity_id, evidence_id],
    )
    markdown_export_url = reverse(
        "organization-repository-publication-evidence-static-markdown-export",
        args=[organization.entity_id, evidence_id],
    )
    html_export_url = reverse(
        "organization-repository-publication-evidence-static-html-export",
        args=[organization.entity_id, evidence_id],
    )
    pdf_export_url = reverse(
        "organization-repository-publication-evidence-static-pdf-export",
        args=[organization.entity_id, evidence_id],
    )
    assert browser.get(static_url).status_code == 409
    assert browser.get(markdown_export_url).status_code == 404
    assert browser.get(html_export_url).status_code == 404
    assert browser.get(pdf_export_url).status_code == 404
    assert browser.post(static_url).status_code == 409
    authorization_payload = json.dumps(
        {"outcome": "authorized_for_publication", "reason": "Exact package approved for publication creation"}
    )
    assert browser.get(authorization_url).status_code == 404
    assert (
        browser.post(authorization_url, data=authorization_payload, content_type="application/json").status_code
        == 409
    )
    authorizer = User.objects.create_user(email="package-authorizer@example.invalid", display_name="Authorizer")
    authorizer_membership = TenantMembership.objects.create(
        tenant=installation.tenant, user=authorizer, role=BuiltInRole.ADMINISTRATOR
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=organization,
        membership=authorizer_membership,
        created_by=installation.owner,
    )
    browser.force_login(authorizer)
    assert (
        browser.post(authorization_url, data=authorization_payload, content_type="application/json").status_code
        == 403
    )
    Authenticator.objects.create(user=authorizer, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()})
    authorized = browser.post(authorization_url, data=authorization_payload, content_type="application/json")
    assert authorized.status_code == 201, authorized.content
    assert authorized.json()["permits_distribution"] is False
    assert authorized.json()["package_id"] == str(package.id)
    assert browser.get(authorization_url).json()["outcome"] == "authorized_for_publication"
    browser.force_login(reviewer)
    assert browser.get(static_url).status_code == 404
    retained_pdf = RepositoryPublicationEvidence.objects.get(pk=evidence_id).pdf_file
    with retained_pdf.open("rb") as source:
        pdf_bytes = source.read()
    try:
        retained_pdf.storage.delete(retained_pdf.name)
        assert browser.post(static_url).status_code == 409
        assert not RepositoryStaticPublication.objects.exists()
    finally:
        assert retained_pdf.storage.save(retained_pdf.name, ContentFile(pdf_bytes)) == retained_pdf.name
    recorded = browser.post(static_url)
    assert recorded.status_code == 201, recorded.content
    assert recorded.json()["verified"] is True
    assert recorded.json()["permits_distribution"] is False
    publication = RepositoryStaticPublication.objects.get(pk=recorded.json()["id"])
    evidence_record = RepositoryPublicationEvidence.objects.get(pk=evidence_id)
    signed_markdown = evidence_record.canonical_markdown.encode()
    exported_markdown = browser.get(markdown_export_url)
    assert exported_markdown.status_code == 200
    assert exported_markdown.content == signed_markdown
    assert exported_markdown["Content-Type"] == "text/markdown; charset=utf-8"
    assert exported_markdown["Content-Disposition"].startswith("attachment;")
    assert exported_markdown["Cache-Control"] == "private, no-store"
    assert exported_markdown["X-Content-Type-Options"] == "nosniff"
    assert exported_markdown["X-TekDocs-Export-Class"] == "immutable_static_publication"
    assert exported_markdown["X-TekDocs-Publication-Digest"] == publication.content_digest
    exported_html = browser.get(html_export_url)
    assert exported_html.status_code == 200
    assert exported_html.content == evidence_record.manifest["rendered_snapshot"]["html"].encode()
    assert exported_html["Content-Type"] == "text/html; charset=utf-8"
    assert exported_html["Content-Disposition"].startswith("attachment;")
    assert exported_html["Cache-Control"] == "private, no-store"
    assert exported_html["Content-Security-Policy"] == "sandbox; default-src 'none'"
    exported_pdf = browser.get(pdf_export_url)
    assert exported_pdf.status_code == 200
    assert exported_pdf.content == pdf_bytes
    assert exported_pdf["Content-Type"] == "application/pdf"
    assert exported_pdf["Content-Disposition"].startswith("attachment;")
    assert exported_pdf["X-TekDocs-Export-Class"] == "immutable_static_publication"
    assert AuditEvent.objects.filter(
        action="repository_static_publication.exported", entity_id=publication.id
    ).count() == 3
    original_open = retained_pdf.storage.open
    reads = 0

    def changed_pdf_between_checks(name, mode="rb"):
        nonlocal reads
        if name != retained_pdf.name:
            return original_open(name, mode)
        reads += 1
        return BytesIO(pdf_bytes if reads == 1 else b"Changed retained PDF")

    with monkeypatch.context() as patch:
        patch.setattr(retained_pdf.storage, "open", changed_pdf_between_checks)
        changed_pdf_export = browser.get(pdf_export_url)
    assert reads >= 2
    assert changed_pdf_export.status_code == 409
    assert changed_pdf_export.content != b"Changed retained PDF"
    assert AuditEvent.objects.filter(
        action="repository_static_publication.exported", entity_id=publication.id
    ).count() == 3
    control_url = reverse(
        "organization-repository-publication-evidence-static-control",
        args=[organization.entity_id, evidence_id],
    )
    delivery_url = reverse(
        "organization-repository-publication-evidence-static-delivery",
        args=[organization.entity_id, evidence_id],
    )
    delivery_payload = json.dumps({"reason": "Approve exact retained record for a future client path"})
    release_payload = json.dumps({"action": "released", "reason": "Exact package cleared for future delivery"})
    withdrawal_payload = json.dumps({"action": "withdrawn", "reason": "Withdraw before client delivery"})
    assert browser.get(control_url).json()["state"] == "recorded"
    assert browser.get(delivery_url).status_code == 404
    assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code == 409
    assert not OutboxEvent.objects.filter(topic=OutboxTopic.REPOSITORY_PUBLICATION_AVAILABLE).exists()
    with pytest.raises(DatabaseError):
        RepositoryStaticDeliveryAuthorization.objects.create(
            tenant=installation.tenant, organization=organization, workspace=workspace,
            publication=publication, reason="No active release", actor=authorizer,
        )
    assert browser.post(control_url, data=withdrawal_payload, content_type="application/json").status_code == 409
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 409
    with pytest.raises(DatabaseError):
        RepositoryStaticPublicationControlEvent.objects.create(
            tenant=installation.tenant,
            organization=organization,
            workspace=workspace,
            publication=publication,
            action="withdrawn",
            reason="Invalid direct withdrawal",
            actor=reviewer,
        )
    browser.force_login(authorizer)
    retained_pdf.storage.delete(retained_pdf.name)
    try:
        assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 409
        assert browser.get(markdown_export_url).status_code == 409
        assert browser.get(html_export_url).status_code == 409
        assert browser.get(pdf_export_url).status_code == 409
        assert AuditEvent.objects.filter(
            action="repository_static_publication.exported", entity_id=publication.id
        ).count() == 3
        assert not RepositoryStaticPublicationControlEvent.objects.exists()
    finally:
        assert retained_pdf.storage.save(retained_pdf.name, ContentFile(pdf_bytes)) == retained_pdf.name
    released = browser.post(control_url, data=release_payload, content_type="application/json")
    assert released.status_code == 201, released.content
    assert released.json()["state"] == "released"
    assert released.json()["verified"] is True
    assert released.json()["permits_distribution"] is False
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 409
    portal_user = User.objects.create_user(email="decision-client@example.invalid", display_name="Client")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=portal_user, role=BuiltInRole.CLIENT_USER, organization=organization
    )
    portal_list_url = reverse("client-portal-repository-publication-list")
    portal_detail_url = reverse("client-portal-repository-publication-detail", args=[publication.id])
    portal_pdf_url = reverse("client-portal-repository-publication-pdf", args=[publication.id])
    artifact = RepositoryEvidenceAttachment.objects.get(evidence_id=evidence_id)
    portal_attachment_url = reverse(
        "client-portal-repository-publication-attachment", args=[publication.id, artifact.id]
    )
    browser.force_login(portal_user)
    assert browser.get(markdown_export_url).status_code == 403
    assert browser.get(html_export_url).status_code == 403
    assert browser.get(pdf_export_url).status_code == 403
    inbox_url = reverse("client-portal-notification-list")
    assert browser.get(inbox_url).json()["results"] == []
    assert browser.get(portal_list_url).json()["results"] == []
    assert browser.get(portal_detail_url).status_code == 404
    assert browser.get(portal_pdf_url).status_code == 404
    assert browser.get(portal_attachment_url).status_code == 404
    browser.force_login(authorizer)
    release_event = RepositoryStaticPublicationControlEvent.objects.get(action="released")
    with pytest.raises(DatabaseError):
        RepositoryStaticDeliveryAuthorization.objects.create(
            tenant=installation.tenant, organization=organization, workspace=_workspace,
            publication=publication, reason="Wrong Workspace", actor=authorizer,
        )
    with pytest.raises(DatabaseError):
        RepositoryStaticDeliveryAuthorization.objects.create(
            tenant=installation.tenant, organization=organization, workspace=workspace,
            publication=publication, reason="Creator cannot self-authorize delivery", actor=reviewer,
        )
    retained_pdf.storage.delete(retained_pdf.name)
    try:
        assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code == 409
    finally:
        assert retained_pdf.storage.save(retained_pdf.name, ContentFile(pdf_bytes)) == retained_pdf.name
    delivery = browser.post(delivery_url, data=delivery_payload, content_type="application/json")
    assert delivery.status_code == 201, delivery.content
    assert delivery.json()["currently_effective"] is True
    assert delivery.json()["permits_distribution"] is True
    assert browser.get(delivery_url).json()["id"] == delivery.json()["id"]
    assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code == 409
    assert list(
        OutboxEvent.objects.filter(topic=OutboxTopic.REPOSITORY_PUBLICATION_AVAILABLE).values_list(
            "subject_id", flat=True
        )
    ) == [publication.id]
    assert dispatch_due_outbox_events(tenant=installation.tenant) == 1
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Package Sibling",
        legal_name="Package Sibling LLC",
        website="",
        classifications=["client"],
    )
    sibling_user = User.objects.create_user(email="package-sibling@example.invalid", display_name="Sibling")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=sibling_user, role=BuiltInRole.CLIENT_USER, organization=sibling
    )
    browser.force_login(portal_user)
    available_notices = browser.get(inbox_url).json()["results"]
    assert len(available_notices) == 1
    assert available_notices[0]["target"] == {
        "kind": "portal_repository_publication", "organization_id": None, "publication_id": str(publication.id),
    }
    portal_list = browser.get(portal_list_url)
    assert portal_list.status_code == 200
    assert portal_list["Cache-Control"] == "private, no-store"
    assert [item["id"] for item in portal_list.json()["results"]] == [str(publication.id)]
    portal_detail = browser.get(portal_detail_url)
    assert portal_detail.status_code == 200
    assert "Review me." in portal_detail.json()["rendered_html"]
    assert portal_detail.json()["attachments"] == [{
        "id": str(artifact.id), "filename": "decision-guide.txt",
        "media_type": artifact.media_type, "size": len(b"Client setup instructions"),
    }]
    portal_pdf = browser.get(portal_pdf_url)
    assert portal_pdf.status_code == 200
    assert portal_pdf.content.startswith(b"%PDF-")
    assert portal_pdf["Content-Disposition"].startswith("attachment;")
    portal_attachment = browser.get(portal_attachment_url)
    assert portal_attachment.status_code == 200
    assert portal_attachment.content == b"Client setup instructions"
    assert portal_attachment["Content-Type"] == "application/octet-stream"
    assert portal_attachment["Content-Disposition"].startswith("attachment;")
    assert portal_attachment["Cache-Control"] == "private, no-store"
    assert portal_attachment["X-Content-Type-Options"] == "nosniff"
    call_command("verify_recovery_publications")
    assert browser.get(reverse(
        "client-portal-repository-publication-attachment", args=[publication.id, uuid.uuid4()]
    )).status_code == 404
    stored = artifact.file.storage
    original_open = stored.open
    reads = 0

    def changed_between_checks(name, mode="rb"):
        nonlocal reads
        if name != artifact.file.name:
            return original_open(name, mode)
        reads += 1
        return BytesIO(b"Client setup instructions" if reads == 1 else b"Changed attachment bytes")

    with monkeypatch.context() as patch:
        patch.setattr(stored, "open", changed_between_checks)
        changed = browser.get(portal_attachment_url)
    assert reads >= 2
    assert changed.status_code == 404
    assert changed.content != b"Changed attachment bytes"
    retained_pdf.storage.delete(retained_pdf.name)
    try:
        with pytest.raises(CommandError, match="Retained repository publication integrity check failed"):
            call_command("verify_recovery_publications")
        assert browser.get(portal_list_url).json()["results"] == []
        assert browser.get(portal_detail_url).status_code == 404
        assert browser.get(portal_pdf_url).status_code == 404
        assert browser.get(portal_attachment_url).status_code == 404
    finally:
        assert retained_pdf.storage.save(retained_pdf.name, ContentFile(pdf_bytes)) == retained_pdf.name
    browser.force_login(sibling_user)
    assert browser.get(inbox_url).json()["results"] == []
    assert browser.get(portal_list_url).json()["results"] == []
    assert browser.get(portal_detail_url).status_code == 404
    assert browser.get(portal_pdf_url).status_code == 404
    assert browser.get(portal_attachment_url).status_code == 404
    browser.force_login(reviewer)
    assert browser.get(portal_list_url).status_code == 403
    assert browser.get(portal_detail_url).status_code == 403
    assert browser.get(portal_pdf_url).status_code == 403
    assert browser.get(portal_attachment_url).status_code == 403
    with pytest.raises(DatabaseError):
        RepositoryStaticDeliveryAuthorization.objects.filter(pk=delivery.json()["id"]).update(reason="Changed")
    with pytest.raises(DatabaseError):
        RepositoryStaticPublicationControlEvent.objects.filter(pk=release_event.id).update(reason="Changed")
    browser.force_login(installation.owner)
    candidate = browser.post(
        reverse("organization-repository-publication-evidence", args=[organization.entity_id]),
        data=json.dumps({"content_id": str(content_id), "audience": "client_visible"}),
        content_type="application/json",
    )
    assert candidate.status_code == 201, candidate.content
    candidate_evidence_id = candidate.json()["id"]
    browser.force_login(reviewer)
    assert browser.post(
        reverse(
            "organization-repository-publication-evidence-decision",
            args=[organization.entity_id, candidate_evidence_id],
        ),
        data=payload,
        content_type="application/json",
    ).status_code == 201
    assert browser.post(reverse(
        "organization-repository-publication-evidence-package", args=[organization.entity_id, candidate_evidence_id]
    )).status_code == 201
    browser.force_login(authorizer)
    assert browser.post(
        reverse(
            "organization-repository-publication-evidence-package-authorization",
            args=[organization.entity_id, candidate_evidence_id],
        ),
        data=authorization_payload,
        content_type="application/json",
    ).status_code == 201
    browser.force_login(reviewer)
    assert browser.post(reverse(
        "organization-repository-publication-evidence-static-publication",
        args=[organization.entity_id, candidate_evidence_id],
    )).status_code == 201
    candidate_control_url = reverse(
        "organization-repository-publication-evidence-static-control",
        args=[organization.entity_id, candidate_evidence_id],
    )
    candidate_delivery_url = reverse(
        "organization-repository-publication-evidence-static-delivery",
        args=[organization.entity_id, candidate_evidence_id],
    )
    browser.force_login(authorizer)
    assert browser.post(
        candidate_control_url, data=release_payload, content_type="application/json"
    ).status_code == 409
    candidate_publication = RepositoryStaticPublication.objects.get(
        authorization__package__decision__evidence_id=candidate_evidence_id
    )
    with pytest.raises(DatabaseError):
        RepositoryStaticPublicationControlEvent.objects.create(
            tenant=installation.tenant,
            organization=organization,
            workspace=workspace,
            publication=candidate_publication,
            action="released",
            reason="Missing explicit predecessor",
            actor=authorizer,
        )
    supersession_payload = json.dumps({
        "action": "released", "reason": "Replace the reviewed prior record",
        "supersedes_id": str(publication.id),
    })
    assert browser.post(
        candidate_control_url,
        data=json.dumps({"action": "released", "reason": "Wrong predecessor", "supersedes_id": str(uuid.uuid4())}),
        content_type="application/json",
    ).status_code == 409
    superseded = browser.post(candidate_control_url, data=supersession_payload, content_type="application/json")
    assert superseded.status_code == 201, superseded.content
    assert superseded.json()["state"] == "released"
    assert superseded.json()["events"][0]["supersedes_id"] == str(publication.id)
    assert browser.get(control_url).json()["state"] == "superseded"
    assert browser.get(delivery_url).json()["currently_effective"] is False
    assert OutboxEvent.objects.filter(
        topic=OutboxTopic.REPOSITORY_PUBLICATION_ACCESS_CHANGED, subject_id=publication.id
    ).count() == 1
    assert dispatch_due_outbox_events(tenant=installation.tenant) == 1
    dispatch_due_notification_emails(tenant=installation.tenant)
    assert NotificationEmailDelivery.objects.get(
        recipient=portal_user,
        notification__event__topic=OutboxTopic.REPOSITORY_PUBLICATION_AVAILABLE,
        notification__event__subject_id=publication.id,
    ).state == NotificationEmailState.SUPPRESSED
    browser.force_login(portal_user)
    notices = browser.get(inbox_url).json()["results"]
    assert [item["topic"] for item in notices] == [OutboxTopic.REPOSITORY_PUBLICATION_ACCESS_CHANGED]
    assert notices[0]["target"] is None
    assert browser.get(portal_list_url).json()["results"] == []
    assert browser.get(portal_detail_url).status_code == 404
    assert browser.get(portal_pdf_url).status_code == 404
    assert browser.get(portal_attachment_url).status_code == 404
    browser.force_login(authorizer)
    replacement_delivery = browser.post(
        candidate_delivery_url, data=delivery_payload, content_type="application/json"
    )
    assert replacement_delivery.status_code == 201, replacement_delivery.content
    assert replacement_delivery.json()["currently_effective"] is True
    assert replacement_delivery.json()["permits_distribution"] is True
    assert dispatch_due_outbox_events(tenant=installation.tenant) == 1
    candidate_portal_detail_url = reverse(
        "client-portal-repository-publication-detail", args=[candidate_publication.id]
    )
    browser.force_login(portal_user)
    assert [
        item["target"]["publication_id"]
        for item in browser.get(inbox_url).json()["results"]
        if item["target"]
    ] == [str(candidate_publication.id)]
    assert [item["id"] for item in browser.get(portal_list_url).json()["results"]] == [
        str(candidate_publication.id)
    ]
    assert browser.get(candidate_portal_detail_url).status_code == 200
    browser.force_login(authorizer)
    assert browser.post(control_url, data=withdrawal_payload, content_type="application/json").status_code == 409
    with pytest.raises(DatabaseError):
        RepositoryStaticPublicationControlEvent.objects.create(
            tenant=installation.tenant,
            organization=organization,
            workspace=workspace,
            publication=publication,
            action="withdrawn",
            reason="Cannot withdraw superseded record",
            actor=authorizer,
        )
    assert browser.post(
        candidate_control_url,
        data=json.dumps({"action": "withdrawn", "reason": "Invalid predecessor", "supersedes_id": str(publication.id)}),
        content_type="application/json",
    ).status_code == 409
    assert browser.post(
        candidate_control_url, data=supersession_payload, content_type="application/json"
    ).status_code == 409
    candidate_pdf = RepositoryPublicationEvidence.objects.get(pk=candidate_evidence_id).pdf_file
    with candidate_pdf.open("rb") as source:
        candidate_pdf_bytes = source.read()
    candidate_pdf.storage.delete(candidate_pdf.name)
    try:
        withdrawn = browser.post(candidate_control_url, data=withdrawal_payload, content_type="application/json")
        assert withdrawn.json()["verified"] is False
    finally:
        assert candidate_pdf.storage.save(candidate_pdf.name, ContentFile(candidate_pdf_bytes)) == candidate_pdf.name
    assert withdrawn.status_code == 201, withdrawn.content
    assert withdrawn.json()["state"] == "withdrawn"
    assert withdrawn.json()["permits_distribution"] is False
    assert dispatch_due_outbox_events(tenant=installation.tenant) == 1
    assert browser.get(candidate_delivery_url).json()["currently_effective"] is False
    assert browser.get(candidate_delivery_url).json()["permits_distribution"] is False
    browser.force_login(portal_user)
    final_notices = browser.get(inbox_url).json()["results"]
    assert [item["topic"] for item in final_notices] == [
        OutboxTopic.REPOSITORY_PUBLICATION_ACCESS_CHANGED,
        OutboxTopic.REPOSITORY_PUBLICATION_ACCESS_CHANGED,
    ]
    assert all(item["target"] is None for item in final_notices)
    assert browser.get(portal_list_url).json()["results"] == []
    assert browser.get(candidate_portal_detail_url).status_code == 404
    browser.force_login(authorizer)
    assert len(withdrawn.json()["events"]) == 2
    assert browser.get(control_url).json()["state"] == "superseded"
    assert browser.post(
        candidate_control_url, data=withdrawal_payload, content_type="application/json"
    ).status_code == 409
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 409
    assert browser.post(candidate_control_url, data=release_payload, content_type="application/json").status_code == 409
    browser.force_login(reviewer)
    assert publication.manifest["package_digest"] == package.manifest_digest
    assert browser.get(static_url).json()["content_digest"] == publication.content_digest
    assert browser.post(static_url).status_code == 409
    with pytest.raises(DatabaseError):
        RepositoryStaticPublication.objects.filter(pk=publication.id).update(content_digest="0" * 64)
    assert verify_repository_static_publication(publication)
    publication.manifest["source_commit"] = "tampered"
    assert not verify_repository_static_publication(publication)
    publication.refresh_from_db()
    assert (
        browser.post(authorization_url, data=authorization_payload, content_type="application/json").status_code
        == 409
    )
    with pytest.raises(DatabaseError):
        RepositoryPackageAuthorization.objects.filter(pk=authorized.json()["id"]).update(reason="Changed")
    browser.force_login(reviewer)
    sibling_url = reverse(
        "organization-repository-publication-evidence-package", args=[sibling.entity_id, evidence_id]
    )
    assert browser.get(sibling_url).status_code == 404
    assert browser.post(sibling_url).status_code == 404
    sibling_authorization_url = reverse(
        "organization-repository-publication-evidence-package-authorization",
        args=[sibling.entity_id, evidence_id],
    )
    assert browser.get(sibling_authorization_url).status_code == 404
    assert browser.post(
        sibling_authorization_url, data=authorization_payload, content_type="application/json"
    ).status_code == 404
    sibling_static_url = reverse(
        "organization-repository-publication-evidence-static-publication", args=[sibling.entity_id, evidence_id]
    )
    sibling_markdown_export_url = reverse(
        "organization-repository-publication-evidence-static-markdown-export",
        args=[sibling.entity_id, evidence_id],
    )
    sibling_html_export_url = reverse(
        "organization-repository-publication-evidence-static-html-export",
        args=[sibling.entity_id, evidence_id],
    )
    sibling_pdf_export_url = reverse(
        "organization-repository-publication-evidence-static-pdf-export",
        args=[sibling.entity_id, evidence_id],
    )
    assert browser.get(sibling_static_url).status_code == 404
    assert browser.get(sibling_markdown_export_url).status_code == 404
    assert browser.get(sibling_html_export_url).status_code == 404
    assert browser.get(sibling_pdf_export_url).status_code == 404
    assert browser.post(sibling_static_url).status_code == 404
    sibling_control_url = reverse(
        "organization-repository-publication-evidence-static-control", args=[sibling.entity_id, evidence_id]
    )
    sibling_delivery_url = reverse(
        "organization-repository-publication-evidence-static-delivery", args=[sibling.entity_id, evidence_id]
    )
    assert browser.get(sibling_control_url).status_code == 404
    assert browser.post(
        sibling_control_url, data=release_payload, content_type="application/json"
    ).status_code == 404
    assert browser.get(sibling_delivery_url).status_code == 404
    assert browser.post(sibling_delivery_url, data=delivery_payload, content_type="application/json").status_code == 404
    assert browser.get(reverse("msp-repository-publication-evidence-detail", args=[evidence_id])).status_code == 404
    foreign_tenant = Tenant.objects.create(name="Foreign package MSP", slug="foreign-package-msp")
    foreign_user = User.objects.create_user(email="foreign-package@example.invalid", display_name="Foreign")
    TenantMembership.objects.create(tenant=foreign_tenant, user=foreign_user, role=BuiltInRole.ADMINISTRATOR)
    foreign_organization = create_organization(
        tenant=foreign_tenant,
        actor_id=foreign_user.id,
        name="Foreign client",
        legal_name="Foreign client LLC",
        website="",
        classifications=["client"],
    )
    foreign_portal_user = User.objects.create_user(
        email="foreign-package-portal@example.invalid", display_name="Foreign client reader"
    )
    TenantMembership.objects.create(
        tenant=foreign_tenant,
        user=foreign_portal_user,
        role=BuiltInRole.CLIENT_USER,
        organization=foreign_organization,
    )
    browser.force_login(foreign_portal_user)
    assert browser.get(portal_list_url).status_code == 403
    assert browser.get(portal_detail_url).status_code == 403
    assert browser.get(portal_pdf_url).status_code == 403
    Authenticator.objects.create(
        user=foreign_user, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    browser.force_login(foreign_user)
    assert browser.get(portal_list_url).status_code == 403
    assert browser.get(portal_detail_url).status_code == 403
    assert browser.get(portal_pdf_url).status_code == 403
    assert browser.get(package_url).status_code in {403, 404}
    assert browser.post(package_url).status_code in {403, 404}
    assert browser.get(authorization_url).status_code in {403, 404}
    assert browser.post(
        authorization_url, data=authorization_payload, content_type="application/json"
    ).status_code in {403, 404}
    assert browser.get(static_url).status_code in {403, 404}
    assert browser.get(markdown_export_url).status_code in {403, 404}
    assert browser.get(html_export_url).status_code in {403, 404}
    assert browser.get(pdf_export_url).status_code in {403, 404}
    assert browser.post(static_url).status_code in {403, 404}
    assert browser.get(control_url).status_code in {403, 404}
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code in {403, 404}
    assert browser.get(delivery_url).status_code in {403, 404}
    assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code in {403, 404}
    read_only_user = User.objects.create_user(email="read-only-package@example.invalid", display_name="Read-only")
    read_only_membership = TenantMembership.objects.create(
        tenant=installation.tenant, user=read_only_user, role=BuiltInRole.READ_ONLY
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=organization,
        membership=read_only_membership,
        created_by=installation.owner,
    )
    Authenticator.objects.create(
        user=read_only_user, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    browser.force_login(read_only_user)
    assert browser.get(package_url).status_code == 403
    assert browser.post(package_url).status_code == 403
    assert browser.get(authorization_url).status_code == 403
    assert browser.post(
        authorization_url, data=authorization_payload, content_type="application/json"
    ).status_code == 403
    assert browser.get(static_url).status_code == 403
    assert browser.post(static_url).status_code == 403
    assert browser.get(control_url).status_code == 403
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 403
    assert browser.get(delivery_url).status_code == 403
    assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code == 403
    browser.force_login(reviewer)
    with pytest.raises(DatabaseError):
        RepositoryPublicationPackage.objects.filter(pk=package.id).update(manifest_digest="0" * 64)
    assert verify_repository_publication_package(package)
    assert verify_repository_static_publication(publication)
    package.manifest["source_commit"] = "tampered"
    assert not verify_repository_publication_package(package)
    package.refresh_from_db()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/decision.md": _content(content_id=content_id, title="Decision", body="Changed later.\n")},
        message="Advance accepted head after packaging",
    )
    assert verify_repository_publication_package(package)
    assert verify_repository_static_publication(publication)
    index_repository_content(repository_id=repository.id)
    assert browser.get(url).json()["outcome"] == "accepted_for_packaging"
    assert browser.post(url, data=payload, content_type="application/json").status_code == 409
    assert RepositoryEvidenceReviewDecision.objects.count() == 2
    assert browser.get(reverse("msp-repository-publication-evidence-detail", args=[evidence_id])).status_code == 404
    with pytest.raises(DatabaseError):
        RepositoryEvidenceReviewDecision.objects.filter(evidence_id=evidence_id).update(reason="Changed")

    browser.force_login(portal_user)
    assert browser.get(url).status_code == 403
    assert browser.post(url, data=payload, content_type="application/json").status_code == 403
    assert browser.get(package_url).status_code == 403
    assert browser.post(package_url).status_code == 403
    assert browser.get(authorization_url).status_code == 403
    assert browser.post(
        authorization_url, data=authorization_payload, content_type="application/json"
    ).status_code == 403
    assert browser.get(static_url).status_code == 403
    assert browser.post(static_url).status_code == 403
    assert browser.get(control_url).status_code == 403
    assert browser.post(control_url, data=release_payload, content_type="application/json").status_code == 403
    assert browser.get(delivery_url).status_code == 403
    assert browser.post(delivery_url, data=delivery_payload, content_type="application/json").status_code == 403

    browser.force_login(installation.owner)
    second = browser.post(
        reverse("organization-repository-publication-evidence", args=[organization.entity_id]),
        data=json.dumps({"content_id": str(content_id), "audience": "client_visible"}),
        content_type="application/json",
    )
    assert second.status_code == 201
    corrupt = RepositoryPublicationEvidence.objects.get(pk=second.json()["id"])
    with pytest.raises(DatabaseError):
        RepositoryEvidenceReviewDecision.objects.create(
            tenant=installation.tenant,
            organization=organization,
            workspace=_workspace,
            evidence=corrupt,
            outcome=RepositoryEvidenceReviewDecision.Outcome.ACCEPTED_FOR_PACKAGING,
            reason="Wrong workspace",
            actor=reviewer,
        )
    corrupt.pdf_file.storage.delete(corrupt.pdf_file.name)
    browser.force_login(reviewer)
    corrupt_url = reverse(
        "organization-repository-publication-evidence-decision", args=[organization.entity_id, corrupt.id]
    )
    assert browser.post(corrupt_url, data=payload, content_type="application/json").status_code == 409
    assert RepositoryEvidenceReviewDecision.objects.count() == 2
    assert browser.post(reverse(
        "organization-repository-publication-evidence-package", args=[organization.entity_id, corrupt.id]
    )).status_code == 409
    assert browser.post(
        reverse(
            "organization-repository-publication-evidence-package-authorization",
            args=[organization.entity_id, corrupt.id],
        ),
        data=authorization_payload,
        content_type="application/json",
    ).status_code == 409
    retained = RepositoryPublicationEvidence.objects.get(pk=evidence_id)
    retained.pdf_file.storage.delete(retained.pdf_file.name)
    assert not verify_repository_publication_package(package)
    assert not verify_repository_static_publication(publication)


def test_repository_static_delivery_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0176_repository_static_supersession")])
        assert "core_repositorystaticdeliveryauthorization" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorystaticdeliveryauthorization'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositorystaticdeliveryauthorization'::regclass "
                "AND tgname IN ('core_repositorystaticdeliveryauthorization_validate', "
                "'core_repositorystaticdeliveryauthorization_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_static_control_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0174_repository_static_publication")])
        assert "core_repositorystaticpublicationcontrolevent" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate([("core", "0175_repository_static_controls")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='core_repositorystaticpublicationcontrolevent' AND column_name='supersedes_id'"
            )
            assert cursor.fetchone() == (0,)
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='core_repositorystaticpublicationcontrolevent' AND column_name='supersedes_id'"
            )
            assert cursor.fetchone() == (1,)
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorystaticpublicationcontrolevent'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositorystaticpublicationcontrolevent'::regclass "
                "AND tgname IN ('core_repositorystaticpublicationcontrolevent_validate', "
                "'core_repositorystaticpublicationcontrolevent_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_static_publication_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0173_repository_package_authorization")])
        assert "core_repositorystaticpublication" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorystaticpublication'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositorystaticpublication'::regclass "
                "AND tgname IN ('core_repositorystaticpublication_validate', "
                "'core_repositorystaticpublication_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_publication_package_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0171_repository_evidence_review_decision")])
        assert "core_repositorypublicationpackage" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorypublicationpackage'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositorypublicationpackage'::regclass "
                "AND tgname IN ('core_repositorypublicationpackage_validate', "
                "'core_repositorypublicationpackage_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_package_authorization_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0172_repository_publication_package")])
        assert "core_repositorypackageauthorization" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorypackageauthorization'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositorypackageauthorization'::regclass "
                "AND tgname IN ('core_repositorypackageauthorization_validate', "
                "'core_repositorypackageauthorization_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_evidence_review_decision_upgrade_installs_forced_rls_and_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0170_repository_evidence_pdf")])
        assert "core_repositoryevidencereviewdecision" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositoryevidencereviewdecision'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgrelid = 'core_repositoryevidencereviewdecision'::regclass "
                "AND tgname IN ('core_repositoryevidencereviewdecision_validate', "
                "'core_repositoryevidencereviewdecision_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_publication_evidence_is_signed_append_only_and_independent_of_live_head(
    composition_repository,
    django_runtime_role,
    monkeypatch,
):
    installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    fragment_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/candidate.md": _content(
                content_id=document_id,
                title="Candidate",
                metadata="includes:\n" + _include(content_id=fragment_id, mode="live", audience="shared"),
                body="Root.\n",
            ),
            "fragments/part.md": _content(content_id=fragment_id, title="Part", kind="fragment", body="Included.\n"),
        },
        message="Add publication candidate",
    )
    index_repository_content(repository_id=repository.id)
    with pytest.raises(PermissionDenied):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document_id,
            audience="msp_internal",
            actor=installation.owner,
        )
    assert RepositoryPublicationEvidence.objects.count() == 0

    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    evidence = retain_repository_publication_evidence(
        repository_id=repository.id,
        content_id=document_id,
        audience="msp_internal",
        actor=installation.owner,
    )
    assert evidence.manifest["source"]["accepted_commit"] == first.object_id
    assert len(evidence.manifest["source"]["sources"]) == 2
    assert "Included." in evidence.canonical_markdown
    assert evidence.manifest["preflight"]["blockers"] == []
    assert evidence.manifest["preflight"]["markdown_sha256"] == evidence.manifest["source"]["markdown_sha256"]
    assert verify_repository_publication_evidence(evidence)["valid"]
    assert verify_repository_publication_evidence(evidence)["preflight_attested"]
    assert verify_repository_publication_evidence(evidence)["dependency_closure_attested"]
    assert "Root." in evidence.manifest["rendered_snapshot"]["html"]
    assert verify_repository_publication_evidence(evidence)["rendered_snapshot_attested"]
    assert evidence.manifest["pdf_snapshot"]["media_type"] == "application/pdf"
    assert evidence.manifest["pdf_snapshot"]["size"] == evidence.pdf_file.size
    assert verify_repository_publication_evidence(evidence)["pdf_snapshot_attested"]
    assert evidence.manifest["source"]["root_title"] == "Candidate"
    assert not verify_repository_publication_evidence(evidence)["renderer_comparison_performed"]
    assert verify_repository_publication_evidence(evidence, compare_current_renderer=True)[
        "rendered_snapshot_reproducible"
    ]
    assert verify_repository_publication_evidence(evidence, compare_current_renderer=True)["pdf_snapshot_reproducible"]

    # Historical integrity must survive a later renderer change. Reproduction
    # is an advisory diagnostic, not a validity gate for signed retained bytes.
    with monkeypatch.context() as changed_renderer:
        changed_renderer.setattr(
            "apps.core.repository_publication_render.render_markdown", lambda *_a, **_k: "<p>New renderer.</p>"
        )
        changed_renderer.setattr(
            "apps.core.repository_publication_render.render_pdf", lambda *_a, **_k: b"%PDF-new-renderer"
        )
        changed_result = verify_repository_publication_evidence(evidence, compare_current_renderer=True)
        assert changed_result["valid"]
        assert changed_result["rendered_snapshot_attested"]
        assert changed_result["pdf_snapshot_attested"]
        assert not changed_result["rendered_snapshot_reproducible"]
        assert not changed_result["pdf_snapshot_reproducible"]

    inconsistent_pdf = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    inconsistent_pdf.manifest["title"] = "Forged title"
    pdf_digest = hashlib.sha256(
        evidence_payload(manifest=inconsistent_pdf.manifest, markdown=inconsistent_pdf.canonical_markdown)
    ).digest()
    inconsistent_pdf.content_digest = pdf_digest.hex()
    inconsistent_pdf.signature = base64.urlsafe_b64encode(publication_signing_key().sign(pdf_digest)).decode("ascii")
    assert verify_repository_publication_evidence(inconsistent_pdf)["signature_valid"]
    assert not verify_repository_publication_evidence(inconsistent_pdf)["identity_valid"]
    assert not verify_repository_publication_evidence(inconsistent_pdf)["pdf_snapshot_attested"]
    assert not verify_repository_publication_evidence(inconsistent_pdf)["valid"]

    inconsistent_pdf_checksum = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    inconsistent_pdf_checksum.manifest["pdf_snapshot"]["sha256"] = "0" * 64
    checksum_digest = hashlib.sha256(
        evidence_payload(
            manifest=inconsistent_pdf_checksum.manifest,
            markdown=inconsistent_pdf_checksum.canonical_markdown,
        )
    ).digest()
    inconsistent_pdf_checksum.content_digest = checksum_digest.hex()
    inconsistent_pdf_checksum.signature = base64.urlsafe_b64encode(
        publication_signing_key().sign(checksum_digest)
    ).decode("ascii")
    assert verify_repository_publication_evidence(inconsistent_pdf_checksum)["signature_valid"]
    assert not verify_repository_publication_evidence(inconsistent_pdf_checksum)["pdf_snapshot_attested"]

    missing_pdf = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    missing_pdf.pdf_file.name += ".missing"
    assert not verify_repository_publication_evidence(missing_pdf)["pdf_snapshot_attested"]

    inconsistent_render = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    inconsistent_render.manifest["rendered_snapshot"]["html"] = "<p>Forged.</p>"
    render_digest = hashlib.sha256(
        evidence_payload(manifest=inconsistent_render.manifest, markdown=inconsistent_render.canonical_markdown)
    ).digest()
    inconsistent_render.content_digest = render_digest.hex()
    inconsistent_render.signature = base64.urlsafe_b64encode(
        publication_signing_key().sign(render_digest)
    ).decode("ascii")
    assert verify_repository_publication_evidence(inconsistent_render)["signature_valid"]
    assert not verify_repository_publication_evidence(inconsistent_render)["rendered_snapshot_attested"]
    assert not verify_repository_publication_evidence(inconsistent_render)["valid"]

    inconsistent = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    inconsistent.manifest["topic_type"] = "procedure"
    inconsistent_digest = hashlib.sha256(
        evidence_payload(manifest=inconsistent.manifest, markdown=inconsistent.canonical_markdown)
    ).digest()
    inconsistent.content_digest = inconsistent_digest.hex()
    inconsistent.signature = base64.urlsafe_b64encode(
        publication_signing_key().sign(inconsistent_digest)
    ).decode("ascii")
    assert verify_repository_publication_evidence(inconsistent)["signature_valid"]
    assert not verify_repository_publication_evidence(inconsistent)["dependency_closure_attested"]
    assert not verify_repository_publication_evidence(inconsistent)["valid"]
    inconsistent.manifest["topic_type"] = "unsupported-topic"
    assert not verify_repository_publication_evidence(inconsistent)["dependency_closure_attested"]

    prior_format = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    prior_format.manifest.pop("preflight")
    prior_digest = hashlib.sha256(
        evidence_payload(manifest=prior_format.manifest, markdown=prior_format.canonical_markdown)
    ).digest()
    prior_format.content_digest = prior_digest.hex()
    prior_format.signature = base64.urlsafe_b64encode(publication_signing_key().sign(prior_digest)).decode("ascii")
    assert verify_repository_publication_evidence(prior_format)["valid"]
    assert not verify_repository_publication_evidence(prior_format)["preflight_attested"]
    assert not verify_repository_publication_evidence(prior_format)["dependency_closure_attested"]

    legacy_format = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    legacy_format.manifest.pop("topic_type")
    legacy_digest = hashlib.sha256(
        evidence_payload(manifest=legacy_format.manifest, markdown=legacy_format.canonical_markdown)
    ).digest()
    legacy_format.content_digest = legacy_digest.hex()
    legacy_format.signature = base64.urlsafe_b64encode(publication_signing_key().sign(legacy_digest)).decode("ascii")
    assert verify_repository_publication_evidence(legacy_format)["valid"]
    assert not verify_repository_publication_evidence(legacy_format)["dependency_closure_attested"]

    prior_title_proof = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    prior_title_proof.manifest["source"].pop("root_title")
    prior_title_digest = hashlib.sha256(
        evidence_payload(manifest=prior_title_proof.manifest, markdown=prior_title_proof.canonical_markdown)
    ).digest()
    prior_title_proof.content_digest = prior_title_digest.hex()
    prior_title_proof.signature = base64.urlsafe_b64encode(
        publication_signing_key().sign(prior_title_digest)
    ).decode("ascii")
    assert verify_repository_publication_evidence(prior_title_proof)["valid"]

    prior_render = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    prior_render.manifest.pop("rendered_snapshot")
    prior_render_digest = hashlib.sha256(
        evidence_payload(manifest=prior_render.manifest, markdown=prior_render.canonical_markdown)
    ).digest()
    prior_render.content_digest = prior_render_digest.hex()
    prior_render.signature = base64.urlsafe_b64encode(
        publication_signing_key().sign(prior_render_digest)
    ).decode("ascii")
    assert verify_repository_publication_evidence(prior_render)["valid"]
    assert not verify_repository_publication_evidence(prior_render)["rendered_snapshot_attested"]

    prior_pdf = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    prior_pdf.manifest.pop("pdf_snapshot")
    prior_pdf.pdf_file.name = ""
    prior_pdf_digest = hashlib.sha256(
        evidence_payload(manifest=prior_pdf.manifest, markdown=prior_pdf.canonical_markdown)
    ).digest()
    prior_pdf.content_digest = prior_pdf_digest.hex()
    prior_pdf.signature = base64.urlsafe_b64encode(publication_signing_key().sign(prior_pdf_digest)).decode("ascii")
    assert verify_repository_publication_evidence(prior_pdf)["valid"]
    assert not verify_repository_publication_evidence(prior_pdf)["pdf_snapshot_attested"]

    foreign_tenant = Tenant.objects.create(name="Foreign evidence MSP", slug=f"foreign-evidence-{uuid.uuid4()}")
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert RepositoryPublicationEvidence.objects.filter(pk=evidence.id).exists()
        bind_local_rls_scope(DataScope.tenant(foreign_tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert not RepositoryPublicationEvidence.objects.filter(pk=evidence.id).exists()

    evidence.canonical_markdown += "Tampered."
    assert not verify_repository_publication_evidence(evidence)["valid"]
    evidence.refresh_from_db()
    evidence.manifest["source"]["sources"][1]["blob"] = "0" * 40
    assert not verify_repository_publication_evidence(evidence)["valid"]
    evidence.refresh_from_db()
    evidence.manifest["preflight"]["markdown_sha256"] = "0" * 64
    assert not verify_repository_publication_evidence(evidence)["identity_valid"]
    evidence.refresh_from_db()
    with pytest.raises(ValidationError, match="append-only"):
        evidence.save()
    with pytest.raises(ValidationError, match="append-only"):
        evidence.delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        RepositoryPublicationEvidence.objects.filter(pk=evidence.id).update(canonical_markdown="Tampered")
    with pytest.raises(DatabaseError), transaction.atomic():
        RepositoryPublicationEvidence.objects.filter(pk=evidence.id).delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        RepositoryPublicationEvidence.objects.filter(pk=evidence.id).update(pdf_file="forged.pdf")
    wrong_path = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    wrong_path.pk = uuid.uuid4()
    wrong_path.manifest["evidence_id"] = str(wrong_path.pk)
    wrong_path.pdf_file.name = "forged.pdf"
    with pytest.raises(DatabaseError), transaction.atomic():
        RepositoryPublicationEvidence.objects.bulk_create([wrong_path])
    forged = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
    forged.pk = uuid.uuid4()
    forged.manifest["evidence_id"] = str(forged.pk)
    forged.manifest["source"]["accepted_commit"] = "0" * 40
    with pytest.raises(DatabaseError), transaction.atomic():
        RepositoryPublicationEvidence.objects.bulk_create([forged])

    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/part.md": _content(
                content_id=fragment_id, title="Part", kind="fragment", body="Changed later.\n"
            )
        },
        message="Advance live fragment",
    )
    assert verify_repository_publication_evidence(evidence)["valid"]
    evidence.pdf_file.storage.delete(evidence.pdf_file.name)
    assert not verify_repository_publication_evidence(evidence)["pdf_snapshot_attested"]
    assert not verify_repository_publication_evidence(evidence)["valid"]


def test_repository_evidence_freezes_portable_field_keys_without_changing_git(composition_repository):
    installation, _msp_workspace, _msp_repository = composition_repository
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Key evidence client",
        legal_name="Key evidence client",
        website="",
        classifications=["client"],
    )
    workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
    repository = repository_storage.ensure_workspace_repository(workspace).repository
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="First laptop")
    document = create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        title="Laptop guide",
        markdown="Device <tekdocs://key/subject.name>.\n",
    )
    binding = DocumentKeyBinding.objects.create(
        tenant=installation.tenant,
        workspace=workspace,
        organization=organization,
        document=document,
        name="subject",
        target_entity=asset.entity,
        created_by=installation.owner,
    )
    body = "Device <tekdocs://key/subject.name>.\n"
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/laptop.md": _content(
                content_id=document.id,
                title="Laptop guide",
                metadata=f"key_bindings:\n  subject: {asset.entity_id}\n",
                body=body,
            )
        },
        message="Add portable key document",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    evidence = retain_repository_publication_evidence(
        repository_id=repository.id,
        content_id=document.id,
        audience="msp_internal",
        actor=installation.owner,
    )
    snapshot = evidence.manifest["key_snapshot"]
    assert evidence.canonical_markdown == body
    assert snapshot["markdown"] == "Device First laptop.\n"
    assert snapshot["records"][0]["value"] == "First laptop"
    assert verify_repository_publication_evidence(evidence)["key_snapshot_valid"]
    assert verify_repository_publication_evidence(evidence)["dependency_closure_attested"]
    assert "First laptop" in evidence.manifest["rendered_snapshot"]["html"]
    assert "tekdocs://key/" not in evidence.manifest["rendered_snapshot"]["html"]

    asset.entity.display_name = "Renamed laptop"
    asset.entity.save(update_fields=("display_name", "updated_at"))
    assert verify_repository_publication_evidence(evidence)["valid"]
    evidence.manifest["key_snapshot"]["markdown"] = "Device forged.\n"
    assert not verify_repository_publication_evidence(evidence)["key_snapshot_valid"]
    evidence.refresh_from_db()

    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.key.unavailable"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document.id,
            audience="client_visible",
            actor=installation.owner,
        )
    replacement = create_network_hardware_asset(
        installation=installation, organization=organization, name="Replacement laptop"
    )
    binding.target_entity = replacement.entity
    binding.save(update_fields=("target_entity", "updated_at"))
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.key.binding_mismatch"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document.id,
            audience="msp_internal",
            actor=installation.owner,
        )
    binding.name = "other"
    binding.save(update_fields=("name", "updated_at"))
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.key.unavailable"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document.id,
            audience="msp_internal",
            actor=installation.owner,
        )


@pytest.mark.parametrize("link_id_kind", ["entity_id", "id"])
def test_repository_evidence_retains_exact_managed_attachment_bytes(
    composition_repository, tmp_path, monkeypatch, link_id_kind
):
    installation, workspace, repository = composition_repository
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Attachment guide",
            markdown="Legacy source.\n",
        )
        attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("guide.txt", b"Original attachment bytes"),
        )
        source_id = getattr(attachment, link_id_kind)
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=_accepted(repository),
            changes={
                "documents/attachment-guide.md": _content(
                    content_id=document.id,
                    title="Attachment guide",
                    body=f"[Guide](tekdocs://attachment/{source_id})\n",
                )
            },
            message="Add attachment guide",
        )
        index_repository_content(repository_id=repository.id)
        Authenticator.objects.create(
            user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
        )
        evidence = retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document.id,
            audience="msp_internal",
            actor=installation.owner,
        )
        artifact = RepositoryEvidenceAttachment.objects.get(evidence=evidence)
        assert artifact.workspace_id == workspace.id
        assert (
            evidence.manifest["attachments"][0]["checksum"] == hashlib.sha256(b"Original attachment bytes").hexdigest()
        )
        assert verify_repository_publication_evidence(evidence)["valid"]
        assert verify_repository_publication_evidence(evidence)["dependency_closure_attested"]
        assert "guide.txt" in evidence.manifest["rendered_snapshot"]["html"]
        assert "href=" not in evidence.manifest["rendered_snapshot"]["html"]
        review_url = reverse("msp-repository-publication-evidence-review-attachment", args=[evidence.id, artifact.id])
        browser = Client()
        browser.force_login(installation.owner)
        review = browser.get(reverse("msp-repository-publication-evidence-review", args=[evidence.id]))
        assert review.status_code == 200
        assert review.json()["attachments"] == [{
            "id": str(artifact.id),
            "source_id": str(source_id),
            "filename": "guide.txt",
            "media_type": artifact.media_type,
            "size": len(b"Original attachment bytes"),
        }]
        reviewed = browser.get(review_url)
        assert reviewed.status_code == 200
        assert reviewed.content == b"Original attachment bytes"
        assert reviewed["Content-Type"] == "application/octet-stream"
        assert reviewed["Content-Disposition"].startswith("attachment;")
        assert reviewed["Cache-Control"] == "private, no-store"
        assert reviewed["X-Content-Type-Options"] == "nosniff"
        assert browser.get(
            reverse("msp-repository-publication-evidence-review-attachment", args=[evidence.id, uuid.uuid4()])
        ).status_code == 404
        stored = artifact.file.storage
        original_open = stored.open
        reads = 0

        def changed_between_checks(name, mode="rb"):
            nonlocal reads
            if name != artifact.file.name:
                return original_open(name, mode)
            reads += 1
            return BytesIO(b"Original attachment bytes" if reads == 1 else b"Changed attachment bytes")

        with monkeypatch.context() as patch:
            patch.setattr(stored, "open", changed_between_checks)
            changed = browser.get(review_url)
        assert reads == 2
        assert changed.status_code == 409
        assert changed.content != b"Changed attachment bytes"

        read_only_user = User.objects.create_user(email="attachment-reader@example.invalid", display_name="Reader")
        TenantMembership.objects.create(tenant=installation.tenant, user=read_only_user, role=BuiltInRole.READ_ONLY)
        browser.force_login(read_only_user)
        assert browser.get(review_url).status_code == 403
        browser.force_login(installation.owner)
        incomplete = RepositoryPublicationEvidence.objects.get(pk=evidence.id)
        incomplete.manifest["attachments"][0]["source_id"] = str(uuid.uuid4())
        incomplete_digest = hashlib.sha256(
            evidence_payload(manifest=incomplete.manifest, markdown=incomplete.canonical_markdown)
        ).digest()
        incomplete.content_digest = incomplete_digest.hex()
        incomplete.signature = base64.urlsafe_b64encode(
            publication_signing_key().sign(incomplete_digest)
        ).decode("ascii")
        assert verify_repository_publication_evidence(incomplete)["signature_valid"]
        assert not verify_repository_publication_evidence(incomplete)["dependency_closure_attested"]
        assert not verify_repository_publication_evidence(incomplete)["attachments_valid"]
        attachment.file.storage.delete(attachment.file.name)
        assert verify_repository_publication_evidence(evidence)["valid"]
        assert browser.get(review_url).content == b"Original attachment bytes"
        with pytest.raises(RepositoryPublicationEvidenceError, match="repository.attachment.integrity"):
            retain_repository_publication_evidence(
                repository_id=repository.id,
                content_id=document.id,
                audience="msp_internal",
                actor=installation.owner,
            )
        assert RepositoryPublicationEvidence.objects.count() == 1
        artifact.file.storage.delete(artifact.file.name)
        assert not verify_repository_publication_evidence(evidence)["attachments_valid"]
        assert browser.get(review_url).status_code == 409
        with pytest.raises(DatabaseError), transaction.atomic():
            RepositoryEvidenceAttachment.objects.filter(pk=artifact.pk).update(checksum="0" * 64)


def test_repository_evidence_rejects_attachment_without_exact_document(composition_repository):
    installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/unowned.md": _content(
                content_id=document_id,
                title="Unowned",
                body=f"[Guide](tekdocs://attachment/{uuid.uuid4()})\n",
            )
        },
        message="Add unowned attachment reference",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.attachment.unavailable"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document_id,
            audience="msp_internal",
            actor=installation.owner,
        )
    assert RepositoryPublicationEvidence.objects.count() == 0


@pytest.mark.parametrize("link_id_kind", ["entity_id", "id"])
@pytest.mark.parametrize("owner_kind", ["legacy", "native"])
def test_repository_evidence_rejects_sibling_client_attachment(
    composition_repository, tmp_path, link_id_kind, owner_kind
):
    installation, _workspace, _repository = composition_repository
    owner = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Attachment owner",
        legal_name="Attachment owner LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Attachment sibling",
        legal_name="Attachment sibling LLC",
        website="",
        classifications=["client"],
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        if owner_kind == "native":
            foreign_document_id = uuid.uuid4()
            owner_workspace = Workspace.objects.get(tenant=installation.tenant, organization=owner)
            owner_repository = repository_storage.ensure_workspace_repository(owner_workspace).repository
            repository_service.commit_repository_files(
                repository_id=owner_repository.id,
                expected_base=_accepted(owner_repository),
                changes={"documents/owner.md": _content(
                    content_id=foreign_document_id, title="Owner guide", body="Private.\n",
                )},
                message="Add native owner source",
            )
            index_repository_content(repository_id=owner_repository.id)
            foreign_attachment = create_repository_document_attachment(
                repository=owner_repository,
                content_id=foreign_document_id,
                actor_id=installation.owner.id,
                upload=SimpleUploadedFile("guide.txt", b"Owner bytes"),
            )
        else:
            foreign_document = create_document(
                tenant=installation.tenant,
                organization=owner,
                actor_id=installation.owner.id,
                title="Owner guide",
                markdown="Private.\n",
            )
            foreign_document_id = foreign_document.id
            foreign_attachment = create_document_attachment(
                document=foreign_document,
                actor_id=installation.owner.id,
                upload=SimpleUploadedFile("guide.txt", b"Owner bytes"),
            )
        workspace = Workspace.objects.get(tenant=installation.tenant, organization=sibling)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=_accepted(repository),
            changes={
                "documents/sibling.md": _content(
                    content_id=foreign_document_id,
                    title="Sibling guide",
                    body=f"[File](tekdocs://attachment/{getattr(foreign_attachment, link_id_kind)})\n",
                )
            },
            message="Add sibling reference",
        )
        index_repository_content(repository_id=repository.id)
        Authenticator.objects.create(
            user=installation.owner,
            type=Authenticator.Type.TOTP,
            data={"secret": generate_totp_secret()},
        )
        with pytest.raises(RepositoryPublicationEvidenceError, match="repository.attachment.unavailable"):
            retain_repository_publication_evidence(
                repository_id=repository.id,
                content_id=foreign_document_id,
                audience="client_visible",
                actor=installation.owner,
            )
        assert RepositoryPublicationEvidence.objects.count() == 0


def test_repository_evidence_freezes_exact_workspace_entity_cards(composition_repository):
    installation, _workspace, repository = composition_repository
    target = create_document(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        title="Original entity name",
        markdown="Target.\n",
    )
    content_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/entity.md": _content(
                content_id=content_id,
                title="Entity guide",
                body=f"[Target](tekdocs://entity/{target.entity_id})\n",
            )
        },
        message="Add entity reference",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner,
        type=Authenticator.Type.TOTP,
        data={"secret": generate_totp_secret()},
    )
    evidence = retain_repository_publication_evidence(
        repository_id=repository.id,
        content_id=content_id,
        audience="msp_internal",
        actor=installation.owner,
    )
    assert evidence.manifest["entity_cards"] == [
        {
            "id": str(target.entity_id),
            "display_name": "Original entity name",
            "entity_type": "document",
            "workspace_label": installation.tenant.name,
        }
    ]
    assert verify_repository_publication_evidence(evidence)["valid"]
    assert "Original entity name" in evidence.manifest["rendered_snapshot"]["html"]
    target.entity.display_name = "Renamed later"
    target.entity.save(update_fields=("display_name", "updated_at"))
    assert verify_repository_publication_evidence(evidence)["valid"]
    evidence.manifest["entity_cards"][0]["id"] = str(uuid.uuid4())
    assert not verify_repository_publication_evidence(evidence)["entity_cards_valid"]


def test_repository_evidence_entity_cards_require_client_visibility_and_exact_owner(composition_repository):
    installation, _workspace, _repository = composition_repository
    client = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Entity client",
        legal_name="Entity client LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Entity sibling",
        legal_name="Entity sibling LLC",
        website="",
        classifications=["client"],
    )
    target = create_document(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.id,
        title="Client-only target",
        markdown="Target.\n",
    )
    foreign = create_document(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        title="Sibling target",
        markdown="Target.\n",
    )
    workspace = Workspace.objects.get(tenant=installation.tenant, organization=client)
    repository = repository_storage.ensure_workspace_repository(workspace).repository
    repository.refresh_from_db()
    content_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/entity.md": _content(
                content_id=content_id,
                title="Client guide",
                body=f"[Target](tekdocs://entity/{target.entity_id})\n",
            )
        },
        message="Add client entity reference",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner,
        type=Authenticator.Type.TOTP,
        data={"secret": generate_totp_secret()},
    )
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.entity.unavailable"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=content_id,
            audience="client_visible",
            actor=installation.owner,
        )
    target.entity.visibility = EntityVisibility.CLIENT_VISIBLE
    target.entity.save(update_fields=("visibility", "updated_at"))
    evidence = retain_repository_publication_evidence(
        repository_id=repository.id,
        content_id=content_id,
        audience="client_visible",
        actor=installation.owner,
    )
    assert verify_repository_publication_evidence(evidence)["valid"]
    projection = SimpleNamespace(
        tenant_id=installation.tenant.id,
        organization_id=client.id,
        workspace_id=workspace.id,
        authorization=SimpleNamespace(
            package=SimpleNamespace(decision=SimpleNamespace(evidence=evidence))
        ),
    )
    assert _client_reference_projection_safe(projection)
    target.entity.visibility = EntityVisibility.MSP_PRIVATE
    target.entity.save(update_fields=("visibility", "updated_at"))
    assert not _client_reference_projection_safe(projection)
    target.entity.visibility = EntityVisibility.CLIENT_VISIBLE
    target.entity.save(update_fields=("visibility", "updated_at"))
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "documents/entity.md": _content(
                content_id=content_id,
                title="Client guide",
                body=f"[Target](tekdocs://entity/{foreign.entity_id})\n",
            )
        },
        message="Reference sibling entity",
    )
    index_repository_content(repository_id=repository.id)
    with pytest.raises(RepositoryPublicationEvidenceError, match="repository.entity.unavailable"):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=content_id,
            audience="client_visible",
            actor=installation.owner,
        )
    assert verify_repository_publication_evidence(evidence)["valid"]


@pytest.mark.parametrize(
    ("markdown", "code"),
    [
        ("   \n", "document.empty"),
        (f"[File](tekdocs://attachment/{uuid.uuid4()})\n", "repository.attachment.unfrozen"),
        ("Device <tekdocs://key/subject.serial_number>.\n", "repository.key.unfrozen"),
        (f"[Device](tekdocs://entity/{uuid.uuid4()})\n", "repository.entity.unfrozen"),
        ("[Secret](tekdocs://credential/example)\n", "repository.reference.unsupported"),
        ("![Remote](https://example.invalid/image.png)\n", "repository.image.unfrozen"),
        ("```mermaid\nflowchart LR\nA-->B\n```\n", "repository.diagram.unfrozen"),
    ],
)
def test_repository_publication_preflight_classifies_unfrozen_dependencies(markdown, code):
    result = repository_publication_preflight(markdown=markdown, audience="msp_internal", topic_type="")
    assert result["blockers"] == [code]
    assert result["markdown_sha256"] == hashlib.sha256(markdown.encode()).hexdigest()


def test_repository_publication_preflight_ignores_literal_examples_and_blocks_topic_gaps():
    literal = "`[Example](tekdocs://attachment/example)`\n\n```text\n![Example](https://example.invalid/a.png)\n```"
    assert repository_publication_preflight(markdown=literal, audience="msp_internal", topic_type="")["blockers"] == []
    topic = repository_publication_preflight(markdown="Body.\n", audience="msp_internal", topic_type="procedure")
    assert "topic.section.missing" in topic["blockers"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (f"[File](tekdocs://attachment/{uuid.uuid4()})\n", "repository.attachment.unavailable"),
        ("```mermaid\nflowchart LR\nA-->B\n```\n", "repository.diagram.unfrozen"),
    ],
)
def test_repository_publication_evidence_refuses_unfrozen_dependencies(composition_repository, body, code):
    installation, _workspace, repository = composition_repository
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={"documents/candidate.md": _content(content_id=document_id, title="Candidate", body=body)},
        message="Add unsupported publication candidate",
    )
    index_repository_content(repository_id=repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    with pytest.raises(RepositoryPublicationEvidenceError, match=code):
        retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document_id,
            audience="msp_internal",
            actor=installation.owner,
        )
    assert RepositoryPublicationEvidence.objects.count() == 0


def test_repository_publication_evidence_is_exact_client_workspace_scoped(composition_repository, django_runtime_role):
    installation, _workspace, _repository = composition_repository
    client = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Evidence Client",
        legal_name="Evidence Client LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Evidence Sibling",
        legal_name="Evidence Sibling LLC",
        website="",
        classifications=["client"],
    )
    client_workspace = Workspace.objects.get(tenant=installation.tenant, organization=client)
    client_repository = repository_storage.ensure_workspace_repository(client_workspace).repository
    client_repository.refresh_from_db()
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=client_repository.id,
        expected_base=_accepted(client_repository),
        changes={
            "documents/client-guide.md": _content(
                content_id=document_id, title="Client guide", body="Private client instructions.\n"
            )
        },
        message="Add client publication candidate",
    )
    index_repository_content(repository_id=client_repository.id)
    Authenticator.objects.create(
        user=installation.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    client_user = User.objects.create_user(
        email="evidence-client@example.invalid", display_name="Evidence Client Reader"
    )
    TenantMembership.objects.create(
        tenant=installation.tenant, user=client_user, role=BuiltInRole.CLIENT_USER, organization=client
    )
    with pytest.raises(PermissionDenied):
        retain_repository_publication_evidence(
            repository_id=client_repository.id,
            content_id=document_id,
            audience="client_visible",
            actor=client_user,
        )
    evidence = retain_repository_publication_evidence(
        repository_id=client_repository.id,
        content_id=document_id,
        audience="client_visible",
        actor=installation.owner,
    )
    assert verify_repository_publication_evidence(evidence)["valid"]

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(installation.tenant, client), organization_mode=OrganizationRLSMode.ORGANIZATION
        )
        assert RepositoryPublicationEvidence.objects.filter(pk=evidence.id).exists()
        bind_local_rls_scope(
            DataScope.organization(installation.tenant, sibling), organization_mode=OrganizationRLSMode.ORGANIZATION
        )
        assert not RepositoryPublicationEvidence.objects.filter(pk=evidence.id).exists()


def test_repository_publication_evidence_upgrade_installs_forced_rls_and_append_only_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0167_contententitylink")])
        assert "core_repositorypublicationevidence" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorypublicationevidence'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'core_repositorypublicationevidence'::regclass "
                "AND tgname IN ('core_repositorypublicationevidence_validate', "
                "'core_repositorypublicationevidence_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_evidence_attachment_upgrade_installs_forced_rls_and_append_only_guards():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0168_repositorypublicationevidence")])
        assert "core_repositoryevidenceattachment" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate([("core", "0178_repository_publication_notification_topics")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_functiondef('tekdocs_validate_repository_evidence_attachment()'::regprocedure)"
            )
            assert "attachment.entity_id::text" not in cursor.fetchone()[0]
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_functiondef('tekdocs_validate_repository_evidence_attachment()'::regprocedure)"
            )
            assert "attachment.entity_id::text" in cursor.fetchone()[0]
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositoryevidenceattachment'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'core_repositoryevidenceattachment'::regclass "
                "AND tgname IN ('core_repositoryevidenceattachment_validate', "
                "'core_repositoryevidenceattachment_immutable')"
            )
            assert cursor.fetchone() == (2,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_repository_evidence_pdf_upgrade_preserves_forced_rls_and_checks_path():
    from django.db.migrations.executor import MigrationExecutor

    head = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate([("core", "0169_repositoryevidenceattachment")])
        with connection.cursor() as cursor:
            assert "pdf_file" not in [column.name for column in connection.introspection.get_table_description(
                cursor, "core_repositorypublicationevidence"
            )]
        MigrationExecutor(connection).migrate(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'core_repositorypublicationevidence'"
            )
            assert cursor.fetchone() == (True, True)
            cursor.execute(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = "
                "'core_repositorypublicationevidence'::regclass "
                "AND conname = 'repository_evidence_pdf_manifest_match'"
            )
            assert cursor.fetchone() == (1,)
    finally:
        MigrationExecutor(connection).migrate(head)


def test_file_backed_composition_preserves_pins_audiences_copy_provenance_and_template_preview(
    composition_repository,
    django_runtime_role,
):
    installation, _workspace, repository = composition_repository
    source_id = uuid.uuid4()
    nested_id = uuid.uuid4()
    internal_id = uuid.uuid4()
    client_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "fragments/source.md": _content(
                content_id=source_id,
                title="Source fragment",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="shared"),
                body="Pinned source v1.\n",
            ),
            "fragments/nested.md": _content(
                content_id=nested_id,
                title="Nested fragment",
                kind="fragment",
                body="Nested v1.\n",
            ),
            "fragments/internal.md": _content(
                content_id=internal_id, title="Internal", kind="fragment", body="Internal only.\n"
            ),
            "fragments/client.md": _content(
                content_id=client_id, title="Client", kind="fragment", body="Client only.\n"
            ),
        },
        message="Add reusable fragment sources",
    )

    document_id = uuid.uuid4()
    audience_document_id = uuid.uuid4()
    copied_id = uuid.uuid4()
    template_id = uuid.uuid4()
    second = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/source.md": _content(
                content_id=source_id,
                title="Source fragment",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="shared"),
                body="Live source v2.\n",
            ),
            "docs/pinned-guide.md": _content(
                content_id=document_id,
                title="Pinned guide",
                metadata=(
                    "includes:\n"
                    + _include(content_id=source_id, mode="pinned", audience="shared", commit=first.object_id)
                ),
                body="Guide introduction.\n",
            ),
            "docs/audience-guide.md": _content(
                content_id=audience_document_id,
                title="Audience guide",
                metadata=(
                    "includes:\n"
                    + _include(content_id=internal_id, mode="live", audience="msp_internal")
                    + _include(content_id=client_id, mode="live", audience="client_visible")
                ),
                body="Shared introduction.\n",
            ),
            "fragments/copied.md": _content(
                content_id=copied_id,
                title="Independent copy",
                kind="fragment",
                metadata=f"derived_from:\n  id: {source_id}\n  commit: {first.object_id}\n",
                body="Customized independent copy.\n",
            ),
            "docs/template.md": _content(
                content_id=template_id,
                title="Template",
                metadata=f"template_sources:\n  - id: {source_id}\n    commit: {first.object_id}\n",
                body="Template introduction.\n",
            ),
        },
        message="Compose reusable fragments",
    )

    result = index_repository_content(repository_id=repository.id)
    repository.refresh_from_db()
    projection = content_graph_projection(repository=repository)

    assert result.object_id == second.object_id
    pinned = next(node for node in projection["nodes"] if node["id"] == str(document_id))
    assert pinned["composition"]["markdown"] == "Guide introduction.\n\nPinned source v1.\n\nNested v1.\n"
    assert pinned["includes"][0]["resolved_commit"] == first.object_id
    assert pinned["includes"][0]["mode"] == "pinned"
    source = next(node for node in projection["nodes"] if node["id"] == str(source_id))
    assert source["included_by"] == [str(document_id)]
    copied = next(node for node in projection["nodes"] if node["id"] == str(copied_id))
    assert copied["derived_from"] == {"id": str(source_id), "commit": first.object_id}
    assert "Pinned source v1." not in copied["composition"]["markdown"]
    template = next(node for node in projection["nodes"] if node["id"] == str(template_id))
    assert template["template_sources"][0]["state"] == "changed"
    assert "Pinned source v1." in template["template_sources"][0]["change_preview"]
    assert "Live source v2." in template["template_sources"][0]["change_preview"]
    assert ContentTemplateSource.objects.get(template__content_id=template_id).current_content_digest
    assert ContentInclude.objects.get(source__content_id=document_id).resolved_content_digest

    foreign_tenant = Tenant.objects.create(name="Other composition MSP", slug=f"other-{uuid.uuid4()}")
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
        )
        assert ContentInclude.objects.count() > 0
        assert ContentTemplateSource.objects.count() == 1
        bind_local_rls_scope(DataScope.tenant(foreign_tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert ContentInclude.objects.count() == 0
        assert ContentTemplateSource.objects.count() == 0

    browser = Client()
    browser.force_login(installation.owner)
    internal_response = browser.get(reverse("msp-content-graph"), {"audience": "msp_internal"})
    client_response = browser.get(reverse("msp-content-graph"), {"audience": "client_visible"})
    internal = next(node for node in internal_response.json()["nodes"] if node["id"] == str(audience_document_id))
    client = next(node for node in client_response.json()["nodes"] if node["id"] == str(audience_document_id))
    assert internal["composition"]["markdown"] == "Shared introduction.\n\nInternal only.\n"
    assert client["composition"]["markdown"] == "Shared introduction.\n\nClient only.\n"

    rebuilt = index_repository_content(repository_id=repository.id, force=True)
    repository.refresh_from_db()
    assert rebuilt.projection_digest == result.projection_digest
    assert content_graph_projection(repository=repository) == projection


def test_cycle_rejection_retains_the_last_known_good_composition(composition_repository):
    _installation, _workspace, repository = composition_repository
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    document_id = uuid.uuid4()
    valid = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                metadata="includes:\n" + _include(content_id=first_id, mode="live", audience="shared"),
                body="Guide.\n",
            ),
            "fragments/first.md": _content(content_id=first_id, title="First", kind="fragment", body="First.\n"),
            "fragments/second.md": _content(content_id=second_id, title="Second", kind="fragment", body="Second.\n"),
        },
        message="Add valid composition",
    )
    index_repository_content(repository_id=repository.id)
    before = ContentNode.objects.get(repository=repository, content_id=document_id).composition_variants
    invalid = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=valid.object_id,
        changes={
            "fragments/first.md": _content(
                content_id=first_id,
                title="First",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=second_id, mode="live", audience="shared"),
                body="First.\n",
            ),
            "fragments/second.md": _content(
                content_id=second_id,
                title="Second",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=first_id, mode="live", audience="shared"),
                body="Second.\n",
            ),
        },
        message="Introduce a composition cycle",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)

    repository.refresh_from_db()
    assert repository.indexed_commit.object_id == valid.object_id
    assert ContentNode.objects.get(repository=repository, content_id=document_id).composition_variants == before
    assert {item["code"] for item in captured.value.diagnostics} == {"include.cycle"}
    assert invalid.object_id not in str(captured.value.diagnostics)


def test_composition_limits_reject_excessive_depth_and_expanded_size(monkeypatch):
    ids = [uuid.uuid4() for _ in range(4)]
    sources = {}
    for index, content_id in enumerate(ids):
        metadata = ""
        if index + 1 < len(ids):
            metadata = "includes:\n" + _include(content_id=ids[index + 1], mode="live", audience="shared")
        sources[content_id] = parse_content(
            _content(content_id=content_id, title=f"Fragment {index}", kind="fragment", metadata=metadata, body="x\n")
        )
    resolver = ContentCompositionResolver(accepted_object_id="a" * 40, accepted=sources, loader=lambda _value: {})
    monkeypatch.setattr(content_composition, "MAX_COMPOSITION_DEPTH", 2)
    with pytest.raises(ContentCompositionError, match="depth") as depth:
        resolver.resolve(content_id=ids[0], audience=None)
    assert depth.value.code == "include.depth"

    target_id = uuid.uuid4()
    document_id = uuid.uuid4()
    target = parse_content(_content(content_id=target_id, title="Large", kind="fragment", body="x" * 40))
    document = parse_content(
        _content(
            content_id=document_id,
            title="Repeated",
            metadata=(
                "includes:\n"
                + _include(content_id=target_id, mode="live", audience="shared")
                + _include(content_id=target_id, mode="live", audience="shared")
            ),
            body="root\n",
        )
    )
    monkeypatch.setattr(content_composition, "MAX_COMPOSITION_DEPTH", 12)
    monkeypatch.setattr(content_composition, "MAX_EXPANDED_BYTES", 64)
    size_resolver = ContentCompositionResolver(
        accepted_object_id="a" * 40,
        accepted={document_id: document, target_id: target},
        loader=lambda _value: {},
    )
    with pytest.raises(ContentCompositionError, match="size") as size:
        size_resolver.resolve(content_id=document_id, audience=None)
    assert size.value.code == "include.size"


def test_rollback_is_a_new_commit_that_restores_the_prior_composition(composition_repository):
    _installation, _workspace, repository = composition_repository
    fragment_id = uuid.uuid4()
    document_id = uuid.uuid4()
    original_document = _content(
        content_id=document_id,
        title="Guide",
        metadata="includes:\n" + _include(content_id=fragment_id, mode="live", audience="shared"),
        body="Introduction.\n",
    )
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": original_document,
            "fragments/steps.md": _content(
                content_id=fragment_id, title="Steps", kind="fragment", body="Original steps.\n"
            ),
        },
        message="Add original composition",
    )
    index_repository_content(repository_id=repository.id)
    original_digest = ContentNode.objects.get(content_id=document_id).composition_variants["all"]["digest"]
    changed = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                body="Temporary standalone content.\n",
            )
        },
        message="Temporarily remove reuse",
    )
    index_repository_content(repository_id=repository.id)
    rollback = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=changed.object_id,
        changes={"docs/guide.md": original_document},
        message="Restore prior composition",
    )
    index_repository_content(repository_id=repository.id)

    restored = ContentNode.objects.get(content_id=document_id).composition_variants["all"]
    assert rollback.object_id not in {first.object_id, changed.object_id}
    assert restored["digest"] != original_digest
    assert restored["markdown"] == "Introduction.\n\nOriginal steps.\n"
    assert restored["manifest"][0]["commit"] == rollback.object_id


def test_pinned_include_cannot_resolve_a_commit_from_another_repository(composition_repository):
    _installation, _workspace, repository = composition_repository
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug=f"foreign-{uuid.uuid4()}")
    foreign_workspace = Workspace.objects.get(tenant=foreign_tenant, kind=WorkspaceKind.MSP)
    foreign_repository = repository_storage.ensure_workspace_repository(foreign_workspace).repository
    foreign_id = uuid.uuid4()
    foreign = repository_service.commit_repository_files(
        repository_id=foreign_repository.id,
        expected_base=_accepted(foreign_repository),
        changes={
            "fragments/private.md": _content(
                content_id=foreign_id,
                title="Private foreign fragment",
                kind="fragment",
                body="Foreign private content.\n",
            )
        },
        message="Add foreign fragment",
    )
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                metadata=(
                    "includes:\n"
                    + _include(
                        content_id=foreign_id,
                        mode="pinned",
                        audience="shared",
                        commit=foreign.object_id,
                    )
                ),
                body="Guide.\n",
            )
        },
        message="Attempt foreign reuse",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)

    diagnostics = list(captured.value.diagnostics)
    assert diagnostics[0]["code"] == "include.commit.unavailable"
    assert "Private foreign fragment" not in str(diagnostics)
    assert "Foreign private content" not in str(diagnostics)
    assert foreign.object_id not in str(diagnostics)


def test_fragment_identity_requires_the_reserved_repository_directory(composition_repository):
    _installation, _workspace, repository = composition_repository
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/misplaced.md": _content(
                content_id=uuid.uuid4(),
                title="Misplaced fragment",
                kind="fragment",
                body="Fragment content.\n",
            )
        },
        message="Add misplaced fragment",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)
    assert any(item["code"] == "content.path.fragment" for item in captured.value.diagnostics)


def test_client_portal_cannot_read_raw_repository_content_or_internal_fragments(composition_repository):
    installation, _workspace, _repository = composition_repository
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Composition Client",
        legal_name="Composition Client LLC",
        website="",
        classifications=["client"],
    )
    client_user = User.objects.create_user(
        email="composition-client@example.invalid", display_name="Composition Client Reader"
    )
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=client_user,
        role=BuiltInRole.CLIENT_USER,
        organization=organization,
    )
    browser = Client()
    browser.force_login(client_user)
    url = reverse("organization-content-graph", args=[organization.entity_id])

    for audience in ("all", "msp_internal", "client_visible"):
        response = browser.get(url, {"audience": audience})
        assert response.status_code == 403
        assert b"composition" not in response.content
    assert browser.post(url, data={"force": True}, content_type="application/json").status_code == 403
