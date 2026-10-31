"""Synthetic diagram custody, with seed imports compatible with 0.8.46."""

from __future__ import annotations

import hashlib
import json
import os

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.policy import require_installation_member
from apps.core.document_attachments import (
    copy_attachment_content,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.documents import create_document, resolve_document, update_document
from apps.core.models import Document, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Diagram migration acceptance guide"
ORIGINAL = "Original diagram recovery instructions."
CURRENT = "Current diagram recovery instructions."


def diagram_markdown(label):
    destination = "Backup" if label == CURRENT else "Archive" if label.startswith("First ") else "Server"
    return (f"{label}\n\n```mermaid\nflowchart LR\naccTitle: Recovery route\n"
            "accDescr: Traffic passes through the recovery gateway\n"
            f"Client --> Gateway --> {destination}\n```\n")


def _document(owner):
    return Document.objects.select_related("entity__workspace", "organization__entity").get(
        tenant=require_installation_member(owner).tenant, entity__display_name=TITLE,
    )


def seed_diagram_fixture(owner):
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=tenant, actor_id=owner.id, name="Diagram acceptance client",
        legal_name="", website="", classifications=["client"],
    )
    document = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=TITLE,
        markdown=diagram_markdown("First retained diagram revision."),
    )
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    first = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain first diagram revision",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("diagram-primary-v1.pdf", render_pdf("Original diagram primary file.")),
        purpose="primary_file", version_number=1,
    )
    replace_primary_document_file(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("diagram-primary-v2.pdf", render_pdf("Revised diagram primary file.")),
    )
    linked = create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("diagram-checklist.txt", b"Retained diagram checklist.\n"),
    )
    update_document(
        document=document, actor_id=owner.id, title=TITLE,
        markdown=diagram_markdown(ORIGINAL) + f"\n[Checklist](tekdocs://attachment/{linked.entity_id})\n",
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    second = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain second diagram revision",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )

    for field in ("source_checksum", "svg_checksum", "png_checksum"):
        assert first.manifest["diagrams"][0][field] != second.manifest["diagrams"][0][field]


def diagram_retained_state(owner):
    document = _document(owner)
    return {
        "id": str(document.id), "entity": str(document.entity_id),
        "revisions": [
            (str(revision.id), revision.revision_number, revision.checksum, revision.markdown, str(revision.parent_id),
             str(revision.created_by_id), revision.created_at.isoformat(),
             revision.topic_type, revision.topic_schema_version)
            for revision in document.placements.get().block.revisions.order_by("revision_number")
        ],
        "publications": [
            (str(item.id), item.manifest, item.signature, item.content_digest,
             [(str(artifact.id), str(artifact.entity_id), artifact.kind, artifact.checksum,
               hashlib.sha256(read_publication_artifact(artifact)).hexdigest())
              for artifact in item.artifacts.order_by("id")],
             [(str(event.id), event.action, event.reason, str(event.actor_id), event.occurred_at.isoformat())
              for event in item.control_events.order_by("occurred_at", "id")])
            for item in document.publications.order_by("id")
        ],
        "files": [
            (str(item.id), str(item.entity_id), item.version_number, str(item.replaces_id), item.checksum,
             hashlib.sha256(copy_attachment_content(item)).hexdigest())
            for item in document.attachments.order_by("id")
        ],
    }


def legacy_diagram_fingerprint(owner):
    return hashlib.sha256(json.dumps(diagram_retained_state(owner), sort_keys=True).encode()).hexdigest()


def promote_diagram_fixture(owner):
    from apps.core.content_index import index_repository_content
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.repository_storage import ensure_workspace_repository

    document = _document(owner)
    workspace = document.entity.workspace
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert apply_document_import(
        workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=owner.id,
    ).status == "imported"
    assert transition_document_authority(
        workspace=workspace, document_id=document.id, actor_id=owner.id, target="repository",
        reader_workspace=resolve_organization_workspace(owner, entity_id=document.organization.entity_id),
    ) == "transitioned"


def _assert_history_preserved(before, after):
    retained = dict(after)
    retained["revisions"] = retained["revisions"][:len(before["revisions"])]
    original_ids = {item[0] for item in before["publications"]}
    retained["publications"] = [item for item in retained["publications"] if item[0] in original_ids]
    assert retained == before


def diagram_recovery_fingerprint(owner):
    from apps.core.content_authoring import read_authored_content
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.models import DocumentAuthority
    from apps.core.publications import retained_publication_diagrams, verify_retained_publication_custody

    document = _document(owner)
    workspace = document.entity.workspace
    state = diagram_retained_state(owner)
    state["git"] = [
        (str(identity), source.accepted_commit, source.source_blob, hashlib.sha256(source.source.encode()).hexdigest())
        for identity in (document.id, document.placements.get().block_id)
        for source in (read_authored_content(repository=workspace.repository, content_id=identity),)
    ]
    state["authority"] = sorted(
        (str(identity), mode) for identity, mode in DocumentAuthority.objects.filter(
            workspace=workspace, content_id__in=(document.id, document.placements.get().block_id),
        ).values_list("content_id", "authority")
    )
    assert len(state["authority"]) == 2 and {mode for _identity, mode in state["authority"]} == {"repository"}
    for item in document.publications.all():
        assert verify_retained_publication_custody(item) and len(retained_publication_diagrams(item)) == 1
        if item.manifest["format"] == "tekdocs-static-publication/v11":
            assert verify_internal_git_publication(item)
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def exercise_diagram_fixture(owner):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.publications import withdraw_publication

    document = _document(owner)
    before = diagram_retained_state(owner)
    promote_diagram_fixture(owner)
    assert diagram_retained_state(owner) == before
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    first = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Freeze current Git diagram",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    assert first.manifest["format"] == "tekdocs-static-publication/v11"
    workspace = document.entity.workspace
    fragment = read_authored_content(repository=workspace.repository, content_id=document.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None,
        markdown=fragment.markdown.replace(ORIGINAL, CURRENT).replace("--> Server", "--> Backup"),
        metadata_patch={},
    )
    live = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")
    assert CURRENT in live["sanitized_html"] and "--> Backup" in live["markdown"]
    second = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Correct Git diagram",
        audience="msp_internal", retention="permanent", retention_review_on=None, supersedes_entity_id=first.entity_id,
    )
    assert second.manifest["diagrams"][0]["source_checksum"] != first.manifest["diagrams"][0]["source_checksum"]
    withdraw_publication(publication=second, actor_id=owner.id, reason="Retain withdrawn diagram")
    for target in ("legacy", "repository"):
        assert transition_document_authority(
            workspace=workspace, document_id=document.id, actor_id=owner.id, target=target, reader_workspace=reader,
        ) == "transitioned"
        if target == "legacy":
            assert CURRENT in resolve_document(document).markdown
    _assert_history_preserved(before, diagram_retained_state(owner))
    return diagram_recovery_fingerprint(owner)


def diagram_browser_state(owner):
    document = _document(owner)
    original = document.publications.order_by("published_at").last()
    assert original is not None
    pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    return {
        "organization_id": str(document.organization.entity_id), "document_id": str(document.entity_id),
        "content_id": str(document.id), "fragment_id": str(document.placements.get().block_id),
        "original_id": str(original.entity_id),
        "original_pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "edited_markdown": (resolve_document(document).markdown
                            .replace(ORIGINAL, CURRENT).replace("--> Server", "--> Backup")),
        "files": [{"filename": item.original_filename, "sha256": item.checksum}
                  for item in document.attachments.order_by("id")],
    }


def verify_diagram_browser_fixture(owner, before):
    from apps.core.document_authority_handoff import transition_document_authority

    document = _document(owner)
    _assert_history_preserved(before, diagram_retained_state(owner))
    publications = list(document.publications.filter(
        manifest__format="tekdocs-static-publication/v11",
    ).order_by("published_at"))
    assert len(publications) == 2 and publications[1].supersedes_id == publications[0].id
    assert publications[1].lifecycle_state == "withdrawn"
    assert all(CURRENT in item.canonical_markdown and "--> Backup" in item.canonical_markdown for item in publications)
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    for target in ("legacy", "repository"):
        assert transition_document_authority(
            workspace=document.entity.workspace, document_id=document.id, actor_id=owner.id, target=target,
            reader_workspace=reader,
        ) == "transitioned"
        if target == "legacy":
            assert CURRENT in resolve_document(document).markdown
    _assert_history_preserved(before, diagram_retained_state(owner))
    diagram_recovery_fingerprint(owner)


def run_diagram_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_diagram_fixture(owner)
    if mode == "seed":
        print("DIAGRAM_LEGACY_SHA256=" + legacy_diagram_fingerprint(owner))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert legacy_diagram_fingerprint(owner) == os.environ["TEKDOCS_DIAGRAM_LEGACY_SHA256"]
        digest = exercise_diagram_fixture(owner)
        if mode == "recovery_create":
            print("DIAGRAM_RECOVERY_SHA256=" + digest)
        print("Diagram revisions, signed graphics, file versions, PDFs and rollback verified")
    elif mode == "recovery_verify":
        assert diagram_recovery_fingerprint(owner) == os.environ["TEKDOCS_DIAGRAM_RECOVERY_SHA256"]
        print("Diagram revisions, signed graphics, file versions and PDFs recovered exactly")
    else:
        raise ValueError("Unknown diagram fixture mode")


if os.environ.get("TEKDOCS_DIAGRAM_FIXTURE_MODE"):
    run_diagram_fixture_mode(os.environ["TEKDOCS_DIAGRAM_FIXTURE_MODE"])
