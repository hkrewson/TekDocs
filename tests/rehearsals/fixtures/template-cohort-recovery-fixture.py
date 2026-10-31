"""Seed/verify synthetic enrolled templates in the hosted encrypted-recovery gate."""

import hashlib
import json
import os

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from apps.core.content_read import document_detail
from apps.core.document_attachments import copy_attachment_content
from apps.core.document_git_publications import publish_internal_git_document
from apps.core.document_migration_export import build_simple_document_export
from apps.core.document_template_migration import template_history_custody_matches
from apps.core.models import Document, InstallationState
from apps.core.publications import read_publication_artifact, verify_retained_publication_custody
from apps.core.repository_service import read_accepted_repository_file
from apps.core.tests.template_browser_fixture import prepare_template_browser_fixture
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace


def fingerprint(owner):
    source = Document.objects.get(tenant=owner_state.tenant, entity__display_name="Browser approved template")
    documents = [source, *Document.objects.filter(
        tenant=owner_state.tenant, template_enrollment__source_template=source,
    ).order_by("id")]
    assert len(documents) == 4
    assert template_history_custody_matches(source, source.entity.workspace.repository.id)
    proof = []
    for document in documents:
        workspace = document.entity.workspace
        reader = resolve_msp_workspace(owner) if document.organization is None else resolve_organization_workspace(
            owner, entity_id=document.organization.entity_id,
        )
        current = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")
        exported = build_simple_document_export(document)
        git_files = []
        for path, expected in exported.files:
            actual = read_accepted_repository_file(repository_id=workspace.repository.id, path=path)
            assert actual == expected
            git_files.append((path, hashlib.sha256(actual).hexdigest()))
        publications = []
        for publication in document.publications.order_by("id"):
            assert verify_retained_publication_custody(publication)
            artifacts = [(str(item.entity_id), item.kind, hashlib.sha256(read_publication_artifact(item)).hexdigest())
                         for item in publication.artifacts.order_by("entity_id")]
            publications.append((str(publication.entity_id), publication.signature, publication.manifest, artifacts))
        assert len(publications) == 2
        files = [(str(item.entity_id), item.version_number, str(item.replaces_id), item.checksum,
                  hashlib.sha256(copy_attachment_content(item)).hexdigest())
                 for item in document.attachments.order_by("entity_id")]
        assert len(files) == 2
        enrollment = getattr(document, "template_enrollment", None)
        proof.append({
            "id": str(document.id), "workspace": str(workspace.id), "git_files": git_files,
            "markdown_sha256": hashlib.sha256(current["markdown"].encode()).hexdigest(),
            "files": files, "publications": publications,
            "enrollment": None if enrollment is None else [str(enrollment.id), str(enrollment.applied_revision_id),
                                                           enrollment.placement_map],
        })
    return hashlib.sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


owner_state = InstallationState.objects.select_related("tenant", "owner").get(pk=InstallationState.SINGLETON_ID)
owner = owner_state.owner
assert owner is not None and owner_state.tenant is not None
mode = os.environ.get("TEKDOCS_TEMPLATE_RECOVERY_MODE")
if mode == "create":
    assert not Document.objects.filter(tenant=owner_state.tenant, entity__display_name="Browser approved template").exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    fixture = prepare_template_browser_fixture(owner)
    for document in (fixture.source, *fixture.documents):
        reader = resolve_msp_workspace(owner) if document.organization is None else resolve_organization_workspace(
            owner, entity_id=document.organization.entity_id,
        )
        publication = publish_internal_git_document(
            workspace=reader, document=document, actor=owner, reason="Retain template encrypted-recovery fixture",
        )
        if document == fixture.source or document.template_enrollment.placement_map[1]["mode"] != "copy":
            assert publication.manifest["format"] == "tekdocs-static-publication/v8"
    print("TEMPLATE_COHORT_SHA256=" + fingerprint(owner))
    print("Enrolled template encrypted-recovery fixture created")
elif mode == "verify":
    assert fingerprint(owner) == os.environ["TEKDOCS_TEMPLATE_RECOVERY_SHA256"]
    print("Enrolled template Git, enrollment, file versions, signatures and PDFs recovered exactly")
else:
    raise RuntimeError("Unsupported template recovery fixture mode")
