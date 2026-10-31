"""Synthetic template records for the opt-in real HTTP/browser acceptance journey."""

import hashlib
from copy import deepcopy
from dataclasses import dataclass

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.content_index import index_repository_content
from apps.core.document_attachments import create_document_attachment, replace_primary_document_file
from apps.core.document_migration_import import apply_document_import, prepare_document_import
from apps.core.document_template_migration import (
    prepare_template_library_handoff,
    transition_template_library_authority,
)
from apps.core.document_template_models import DocumentTemplateEnrollment
from apps.core.documents import create_document, create_document_block, instantiate_document_template, update_document
from apps.core.models import Document, DocumentPublication
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact, verify_retained_publication_custody
from apps.core.rendering import render_pdf
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace


@dataclass
class TemplateBrowserFixture:
    source: Document
    documents: tuple[Document, ...]
    publications: tuple[DocumentPublication, ...]
    original: tuple[tuple[dict, str, bytes], ...]
    browser: dict[str, object]


def prepare_template_browser_fixture(owner) -> TemplateBrowserFixture:
    from apps.accounts.policy import require_installation_member

    member = require_installation_member(owner)
    organization = create_organization(
        tenant=member.tenant, actor_id=owner.id, name="Template acceptance client",
        legal_name="", website="", classifications=["client"],
    )
    source = create_document(
        tenant=member.tenant, organization=None, actor_id=owner.id, title="Browser approved template",
        markdown="Browser template introduction.\n", is_template=True, library_visible=True,
    )
    section = create_document_block(
        document=source, actor_id=owner.id, markdown="Browser template procedure original.\n",
        kind="rich_text", name="Template procedure", parent_id=None, position=1,
    ).block
    section.library_visible = True
    section.save(update_fields=("library_visible", "updated_at"))
    create_document_attachment(
        document=source, actor_id=owner.id,
        upload=SimpleUploadedFile("template-primary-v1.pdf", render_pdf("Template file original.")),
        purpose="primary_file", version_number=1,
    )
    replace_primary_document_file(
        document=source, actor_id=owner.id,
        upload=SimpleUploadedFile("template-primary-v2.pdf", render_pdf("Template file revised.")),
    )
    documents = []
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    for mode in ("copy", "live", "pinned"):
        document = instantiate_document_template(
            source=source, tenant=member.tenant, organization=organization, actor_id=owner.id,
            title=f"Browser enrolled {mode}", category="guide", placement_rules={str(section.entity_id): mode},
        )
        update_document(
            document=document, actor_id=owner.id, title=document.entity.display_name,
            markdown=f"Browser client {mode} local introduction.\n", category="guide",
            base_revision_id=document.placements.get(position=0).block.current_revision_id,
        )
        documents.append(document)
    publications = []
    for document in (source, *documents):
        publications.append(publish_document(
            workspace=resolve_msp_workspace(owner) if document == source else reader,
            document=document, actor_id=owner.id, reason="Retain template browser evidence",
            audience="msp_internal", retention="permanent", retention_review_on=None,
        ))
    original = tuple((deepcopy(pub.manifest), pub.signature,
                      read_publication_artifact(pub.artifacts.get(kind="pdf"))) for pub in publications)
    for document in (source, *documents):
        workspace = document.entity.workspace
        ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        plan = prepare_document_import(workspace=workspace, document_id=document.id)
        assert apply_document_import(
            workspace=workspace, document_id=document.id, actor_id=owner.id,
            expected_base=plan.base_commit, plan_sha256=plan.plan_sha256,
        ).indexed
        if document == source:
            history = prepare_template_library_history(source=source, actor_id=owner.id)
            assert retain_template_library_history(
                source=source, actor_id=owner.id, plan_sha256=history.plan_sha256,
            ).indexed
    arguments = dict(
        source_workspace=source.entity.workspace, source_document_id=source.id,
        destination_document_ids=tuple(document.id for document in documents), actor_id=owner.id, target="repository",
    )
    plan = prepare_template_library_handoff(**arguments)
    transition_template_library_authority(**arguments, plan_sha256=plan.plan_sha256)
    return TemplateBrowserFixture(source, tuple(documents), tuple(publications), original, {
        "organization_id": str(organization.entity_id), "source_fragment_id": str(section.id),
        "documents": {
            mode: str(document.entity_id)
            for mode, document in zip(("copy", "live", "pinned"), documents, strict=True)
        },
        "pin_original_publication": str(publications[3].entity_id),
        "pin_original_pdf_sha256": hashlib.sha256(original[3][2]).hexdigest(),
        "files": [{"filename": item.original_filename, "sha256": item.checksum}
                  for item in source.attachments.filter(purpose="primary_file").order_by("version_number")],
    })


def verify_template_browser_fixture(fixture: TemplateBrowserFixture, owner) -> None:
    from apps.core.document_git_publications import verify_internal_git_publication

    for publication, original in zip(fixture.publications, fixture.original, strict=True):
        publication.refresh_from_db()
        assert original == (publication.manifest, publication.signature,
                            read_publication_artifact(publication.artifacts.get(kind="pdf")))
        assert verify_retained_publication_custody(publication)
    pinned = fixture.documents[2]
    current = list(pinned.publications.exclude(id=fixture.publications[3].id))
    assert len(current) == 1 and current[0].manifest["format"] == "tekdocs-static-publication/v8"
    assert verify_internal_git_publication(current[0])
    documents = tuple(Document.objects.filter(
        tenant=fixture.source.tenant,
        id__in=DocumentTemplateEnrollment.objects.filter(source_template=fixture.source).values("destination_document_id"),
    ).order_by("id"))
    assert len(documents) == 4
    for document in documents:
        versions = list(document.attachments.filter(purpose="primary_file").order_by("version_number"))
        assert [version.version_number for version in versions] == [1, 2]
        assert versions[1].replaces_id == versions[0].id
    arguments = dict(
        source_workspace=fixture.source.entity.workspace, source_document_id=fixture.source.id,
        destination_document_ids=tuple(document.id for document in documents), actor_id=owner.id,
    )
    for target in ("legacy", "repository"):
        if target == "repository":
            # Rollback can use retained SQL definitions, but a new promotion
            # still requires custody of every definition derived by the browser.
            history = prepare_template_library_history(source=fixture.source, actor_id=owner.id)
            assert retain_template_library_history(
                source=fixture.source, actor_id=owner.id, plan_sha256=history.plan_sha256,
            ).indexed
        plan = prepare_template_library_handoff(**arguments, target=target)
        transition_template_library_authority(**arguments, target=target, plan_sha256=plan.plan_sha256)
    assert verify_internal_git_publication(current[0])
