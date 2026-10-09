from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from django.db import transaction
from django.test import Client, override_settings
from django.urls import reverse
from docx import Document as read_word_document

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import repository_service, repository_storage
from apps.core.content_index import index_repository_content
from apps.core.models import AuditEvent, ContentEntityLink, InstallationState, Tenant, Workspace, WorkspaceKind
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset

pytestmark = pytest.mark.django_db(transaction=True)


def _content(*, content_id: uuid.UUID, title: str, body: str, metadata: str = "", kind: str = "document") -> bytes:
    return (
        f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\ntitle: {title}\n{metadata}---\n{body}"
    ).encode()


@pytest.fixture
def read_context(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Content read MSP",
            owner_email="content-read-owner@example.invalid",
            owner_display_name="Content Reader",
            password="ContentReadPassword-2026!",
        )
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Reader client",
            legal_name="Reader client",
            website="https://example.invalid",
            classifications=["client"],
        )
        asset = create_network_hardware_asset(
            installation=installation, organization=organization, name="Reader laptop"
        )
        workspace = Workspace.objects.get(
            tenant=installation.tenant, kind=WorkspaceKind.ORGANIZATION, organization=organization
        )
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        yield installation, organization, asset, repository


def test_asset_backlinks_classification_and_document_context_use_stable_ids(read_context, django_runtime_role):
    installation, organization, asset, repository = read_context
    exact_id, model_id, class_id, fragment_id, repair_id, unresolved_id = (uuid.uuid4() for _ in range(6))
    fragment_commit = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={
            "fragments/repair.md": _content(
                content_id=fragment_id,
                title="Repair steps",
                kind="fragment",
                metadata=f"entity_links:\n  - id: {asset.entity_id}\n    relationship: repair_event\n",
                body="Record the repair outcome.\n",
            )
        },
        message="Add repair fragment",
    )
    commit = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=fragment_commit.object_id,
        changes={
            "docs/setup.md": _content(
                content_id=exact_id,
                title="Laptop setup",
                metadata=f"entity_links:\n  - id: {asset.entity_id}\n    relationship: setup\n",
                body=f"Set up [this device](tekdocs://entity/{asset.entity_id}).\n",
            ),
            "docs/model.md": _content(
                content_id=model_id,
                title="Model enrollment",
                metadata=f"entity_links:\n  - id: {asset.model.entity_id}\n    relationship: enrollment\n",
                body="Enroll supported laptops.\n",
            ),
            "docs/class.md": _content(
                content_id=class_id,
                title="Product troubleshooting",
                metadata=f"entity_links:\n  - id: {asset.product.entity_id}\n    relationship: troubleshooting\n",
                body="Check power.\n",
            ),
            "docs/repair.md": _content(
                content_id=repair_id,
                title="Repair event guide",
                metadata=(
                    f"includes:\n  - id: {fragment_id}\n    mode: pinned\n"
                    f"    audience: shared\n    commit: {fragment_commit.object_id}\n"
                ),
                body="Follow the retained repair steps.\n",
            ),
            "docs/unresolved.md": _content(
                content_id=unresolved_id,
                title="Needs a reference",
                body=f"See [[{uuid.uuid4()}]] for details.\n",
            ),
        },
        message="Link content to one asset and its catalog context",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    kwargs = {"organization_entity_id": organization.entity_id}
    entity_url = reverse("organization-content-entity-documentation", kwargs={**kwargs, "entity_id": asset.entity_id})
    response = browser.get(entity_url)
    assert response.status_code == 200, response.content
    assert {(row["title"], row["relationship"], row["scope"]) for row in response.json()["documents"]} == {
        ("Laptop setup", "setup", "exact"),
        ("Laptop setup", "mention", "exact"),
        ("Model enrollment", "enrollment", "model"),
        ("Product troubleshooting", "troubleshooting", "class"),
        ("Repair steps", "repair_event", "exact"),
        ("Repair event guide", "repair_event", "exact"),
    }
    detail_url = reverse("organization-content-document-detail", kwargs={**kwargs, "content_id": exact_id})
    detail = browser.get(detail_url)
    assert detail.status_code == 200, detail.content
    assert detail.json()["indexed_commit"] == commit.object_id
    assert detail.json()["entity_context"][0]["display_name"] == "Reader laptop"
    assert "Reader laptop" in detail.json()["sanitized_html"]
    assert "tekdocs://entity/" not in detail.json()["sanitized_html"]

    asset.entity.display_name = "Renamed laptop"
    asset.entity.save(update_fields=["display_name"])
    renamed = browser.get(detail_url).json()
    assert renamed["entity_context"][0]["display_name"] == "Renamed laptop"
    assert "Reader laptop" not in renamed["sanitized_html"]

    collection = browser.get(reverse("organization-content-documents", kwargs=kwargs), {"q": "Laptop"}).json()
    assert collection["count"] == 2
    assert {row["id"] for row in collection["results"]} == {str(exact_id), str(model_id)}
    assert browser.get(reverse("organization-content-documents", kwargs=kwargs), {"page_size": 101}).status_code == 400
    health = browser.get(reverse("organization-content-documents", kwargs=kwargs), {"has_findings": "true"}).json()
    assert [row["id"] for row in health["results"]] == [str(unresolved_id)]
    unresolved = browser.get(
        reverse("organization-content-documents", kwargs=kwargs), {"unresolved_only": "true"}
    ).json()
    assert unresolved["results"] == health["results"]

    foreign = Tenant.objects.create(name="Other content read MSP", slug=f"other-{uuid.uuid4()}")
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(installation.tenant, organization),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        assert ContentEntityLink.objects.count() == 6
        bind_local_rls_scope(DataScope.tenant(foreign), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert ContentEntityLink.objects.count() == 0


def test_cross_organization_entity_and_content_are_unavailable(read_context):
    installation, organization, asset, repository = read_context
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={"docs/private.md": _content(content_id=document_id, title="Private guide", body="Private.\n")},
        message="Add scoped content",
    )
    index_repository_content(repository_id=repository.id)
    other = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Other client",
        legal_name="Other client",
        website="https://example.invalid",
        classifications=["client"],
    )
    browser = Client()
    browser.force_login(installation.owner)
    assert (
        browser.get(
            reverse(
                "organization-content-document-detail",
                kwargs={"organization_entity_id": other.entity_id, "content_id": document_id},
            )
        ).status_code
        == 404
    )
    assert (
        browser.get(
            reverse(
                "organization-content-entity-documentation",
                kwargs={"organization_entity_id": other.entity_id, "entity_id": asset.entity_id},
            )
        ).status_code
        == 404
    )
    assert Client().get(
        reverse("organization-content-documents", kwargs={"organization_entity_id": organization.entity_id})
    ).status_code in {401, 403}


def test_staff_html_export_uses_only_a_fully_indexed_repository_document(read_context):
    installation, organization, _asset, repository = read_context
    document_id, fragment_id = uuid.uuid4(), uuid.uuid4()
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={
            "docs/export.md": _content(content_id=document_id, title="Export guide", body="## Setup\nSafe text.\n"),
            "fragments/notes.md": _content(
                content_id=fragment_id, title="Notes", body="Fragment text.\n", kind="fragment"
            ),
        },
        message="Add HTML export source",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    kwargs = {"organization_entity_id": organization.entity_id, "content_id": document_id}
    export_url = reverse("organization-content-document-html-export", kwargs=kwargs)
    exported = browser.get(export_url)
    assert exported.status_code == 200, exported.content
    assert exported["Content-Type"] == "text/html; charset=utf-8"
    assert exported["Content-Disposition"] == 'attachment; filename="repository-document.html"'
    assert exported["Cache-Control"] == "private, no-store"
    assert exported["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert exported["X-Content-Type-Options"] == "nosniff"
    assert exported["X-TekDocs-Export-Class"] == "live_repository_revision"
    assert exported["X-TekDocs-Repository-Commit"] == accepted.object_id
    assert b"<h2>Setup</h2>" in exported.content
    assert b"Safe text." in exported.content
    assert b"Fragment text." not in exported.content
    assert AuditEvent.objects.filter(action="repository_document.exported", entity_id=document_id).count() == 1

    fragment_url = reverse(
        "organization-content-document-html-export",
        kwargs={"organization_entity_id": organization.entity_id, "content_id": fragment_id},
    )
    assert browser.get(fragment_url).status_code == 404
    other = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Export sibling",
        legal_name="Export sibling",
        website="https://example.invalid",
        classifications=["client"],
    )
    sibling_url = reverse(
        "organization-content-document-html-export",
        kwargs={"organization_entity_id": other.entity_id, "content_id": document_id},
    )
    assert browser.get(sibling_url).status_code == 404
    portal_user = User.objects.create_user(email="content-export-client@example.invalid", display_name="Client")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=portal_user, role=BuiltInRole.CLIENT_USER, organization=organization
    )
    browser.force_login(portal_user)
    assert browser.get(export_url).status_code == 403
    browser.force_login(installation.owner)

    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=accepted.object_id,
        changes={"docs/export.md": _content(content_id=document_id, title="Export guide", body="New text.\n")},
        message="Advance accepted source before indexing",
    )
    assert browser.get(export_url).status_code == 409
    assert AuditEvent.objects.filter(action="repository_document.exported", entity_id=document_id).count() == 1


def test_staff_pdf_export_is_live_permission_scoped_and_refuses_stale_or_foreign_source(read_context):
    installation, organization, asset, repository = read_context
    document_id, fragment_id = uuid.uuid4(), uuid.uuid4()
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={
            "docs/pdf.md": _content(
                content_id=document_id, title="PDF guide",
                body=f"## Setup\nSee [laptop](tekdocs://entity/{asset.entity_id}).\n",
            ),
            "fragments/pdf.md": _content(
                content_id=fragment_id, title="PDF notes", body="Private fragment.\n", kind="fragment"
            ),
        },
        message="Add PDF export source",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    kwargs = {"organization_entity_id": organization.entity_id, "content_id": document_id}
    export_url = reverse("organization-content-document-pdf-export", kwargs=kwargs)
    exported = browser.get(export_url)
    assert exported.status_code == 200, exported.content
    assert exported.content.startswith(b"%PDF-")
    assert exported["Content-Type"] == "application/pdf"
    assert exported["Content-Disposition"] == 'attachment; filename="repository-document.pdf"'
    assert exported["Cache-Control"] == "private, no-store"
    assert exported["X-Content-Type-Options"] == "nosniff"
    assert exported["X-TekDocs-Export-Class"] == "live_repository_revision"
    assert exported["X-TekDocs-Repository-Commit"] == accepted.object_id
    assert AuditEvent.objects.filter(
        action="repository_document.exported", entity_id=document_id, metadata__format="pdf"
    ).count() == 1
    assert browser.get(reverse(
        "organization-content-document-pdf-export",
        kwargs={"organization_entity_id": organization.entity_id, "content_id": fragment_id},
    )).status_code == 404
    sibling = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name="PDF sibling",
        legal_name="PDF sibling", website="https://example.invalid", classifications=["client"],
    )
    assert browser.get(reverse(
        "organization-content-document-pdf-export",
        kwargs={"organization_entity_id": sibling.entity_id, "content_id": document_id},
    )).status_code == 404
    portal_user = User.objects.create_user(email="pdf-client@example.invalid", display_name="PDF client")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=portal_user, role=BuiltInRole.CLIENT_USER, organization=organization
    )
    browser.force_login(portal_user)
    assert browser.get(export_url).status_code == 403
    browser.force_login(installation.owner)
    repository_service.commit_repository_files(
        repository_id=repository.id, expected_base=accepted.object_id,
        changes={"docs/pdf.md": _content(content_id=document_id, title="PDF guide", body="New text.\n")},
        message="Advance PDF source before indexing",
    )
    assert browser.get(export_url).status_code == 409
    assert AuditEvent.objects.filter(
        action="repository_document.exported", entity_id=document_id, metadata__format="pdf"
    ).count() == 1


def test_staff_docx_export_resolves_reader_context_and_refuses_stale_or_foreign_source(read_context, monkeypatch):
    installation, organization, asset, repository = read_context
    document_id, fragment_id = uuid.uuid4(), uuid.uuid4()
    accepted = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={
            "docs/docx.md": _content(
                content_id=document_id, title="DOCX guide",
                body=f"## Setup\nSee [laptop](tekdocs://entity/{asset.entity_id}).\n",
            ),
            "fragments/docx.md": _content(
                content_id=fragment_id, title="DOCX notes", body="Private fragment.\n", kind="fragment"
            ),
        },
        message="Add DOCX export source",
    )
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    kwargs = {"organization_entity_id": organization.entity_id, "content_id": document_id}
    export_url = reverse("organization-content-document-docx-export", kwargs=kwargs)
    exported = browser.get(export_url)
    assert exported.status_code == 200, exported.content
    assert exported.content.startswith(b"PK\x03\x04")
    assert exported["Content-Type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert exported["Content-Disposition"] == 'attachment; filename="repository-document.docx"'
    assert exported["Cache-Control"] == "private, no-store"
    assert exported["X-Content-Type-Options"] == "nosniff"
    assert exported["X-TekDocs-Export-Class"] == "live_repository_revision"
    assert exported["X-TekDocs-Repository-Commit"] == accepted.object_id
    word_document = read_word_document(BytesIO(exported.content))
    text = "\n".join(paragraph.text for paragraph in word_document.paragraphs)
    assert "Reader laptop" in text
    assert "tekdocs://entity/" not in text
    assert AuditEvent.objects.filter(
        action="repository_document.exported", entity_id=document_id, metadata__format="docx"
    ).count() == 1
    assert browser.get(reverse(
        "organization-content-document-docx-export",
        kwargs={"organization_entity_id": organization.entity_id, "content_id": fragment_id},
    )).status_code == 404
    sibling = create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name="DOCX sibling",
        legal_name="DOCX sibling", website="https://example.invalid", classifications=["client"],
    )
    assert browser.get(reverse(
        "organization-content-document-docx-export",
        kwargs={"organization_entity_id": sibling.entity_id, "content_id": document_id},
    )).status_code == 404
    portal_user = User.objects.create_user(email="docx-client@example.invalid", display_name="DOCX client")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=portal_user, role=BuiltInRole.CLIENT_USER, organization=organization
    )
    browser.force_login(portal_user)
    assert browser.get(export_url).status_code == 403
    browser.force_login(installation.owner)
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr("apps.core.content_read_views.MAX_DOCX_EXPORT_BYTES", 64)
        assert browser.get(export_url).status_code == 409
    repository_service.commit_repository_files(
        repository_id=repository.id, expected_base=accepted.object_id,
        changes={"docs/docx.md": _content(content_id=document_id, title="DOCX guide", body="New text.\n")},
        message="Advance DOCX source before indexing",
    )
    assert browser.get(export_url).status_code == 409
    assert AuditEvent.objects.filter(
        action="repository_document.exported", entity_id=document_id, metadata__format="docx"
    ).count() == 1
