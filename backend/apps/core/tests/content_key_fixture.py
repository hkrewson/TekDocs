"""Synthetic content-key custody journey with a supported-0.8.46 seed adapter.

Only legacy APIs are imported at module load. Candidate-only migration, Git and
verification operations stay inside functions so hosted upgrade can seed the old image.
"""

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
from apps.core.models import Document, DocumentKeyBinding, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Content-key migration acceptance guide"
PARENT_TITLE = "Content-key acceptance parent"
LEAF_TITLE = "Content-key acceptance leaf"
ORIGINAL = "Original reusable recovery instructions."
CURRENT = "Current accepted reusable recovery instructions."


def _documents(owner):
    document = Document.objects.select_related("entity__workspace", "organization__entity").get(
        tenant=require_installation_member(owner).tenant, entity__display_name=TITLE,
    )
    parent = Document.objects.get(tenant=document.tenant, organization=document.organization,
                                  entity__display_name=PARENT_TITLE)
    leaf = Document.objects.get(tenant=document.tenant, organization=document.organization,
                                entity__display_name=LEAF_TITLE)
    return document, parent, leaf


def seed_content_key_fixture(owner):
    """Seed actual legacy content publications, managed-file versions and nested bindings."""
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=tenant, actor_id=owner.id, name="Content-key acceptance client",
        legal_name="", website="", classifications=["client"],
    )
    leaf = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=LEAF_TITLE, markdown=ORIGINAL + "\n",
    )
    parent = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=PARENT_TITLE,
        markdown="Reusable parent instructions.\n\n<tekdocs://key/leaf.content>\n",
    )
    document = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=TITLE, markdown="Initial instructions.\n",
    )
    for item, name, target in (
        (document, "procedure", parent), (document, "leaf", leaf), (parent, "leaf", leaf),
    ):
        DocumentKeyBinding.objects.create(
            tenant=tenant, workspace=item.entity.workspace, organization=organization,
            document=item, name=name, target_entity=target.placements.get().block.entity, created_by=owner,
        )
    create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("content-key-primary-v1.pdf", render_pdf("Content key primary original.")),
        purpose="primary_file", version_number=1,
    )
    replace_primary_document_file(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("content-key-primary-v2.pdf", render_pdf("Content key primary revised.")),
    )
    linked = create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("content-key-checklist.txt", b"Content-key retained checklist.\n"),
    )
    update_document(
        document=document, actor_id=owner.id, title=TITLE,
        markdown=("# Reused recovery instructions\n\n<tekdocs://key/procedure.content>\n\n"
                  f"[Checklist](tekdocs://attachment/{linked.entity_id})\n"),
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    for item in (leaf, parent, document):
        publication = publish_document(
            workspace=reader, document=item, actor_id=owner.id, reason="Retain legacy substitution custody",
            audience="msp_internal", retention="permanent", retention_review_on=None,
        )
        assert ORIGINAL in publication.canonical_markdown
    return document


def _retained_state(document, owner):
    """Read actual retained bytes, never replacement snapshots derived from current text."""
    documents = _documents(owner)
    return {
        "documents": [
            {
                "id": str(item.id), "entity": str(item.entity_id),
                "markdown": resolve_document(item).markdown,
                "bindings": [
                    (str(binding.id), binding.name, str(binding.target_entity_id))
                    for binding in item.key_bindings.filter(archived_at__isnull=True).order_by("name", "id")
                ],
                "publications": [
                    (str(publication.id), publication.manifest, publication.signature,
                     hashlib.sha256(read_publication_artifact(publication.artifacts.get(kind="pdf"))).hexdigest(),
                     [(str(event.id), event.action, event.reason, str(event.actor_id), event.occurred_at.isoformat())
                      for event in publication.control_events.order_by("occurred_at", "id")])
                    for publication in item.publications.order_by("id")
                ],
            }
            for item in sorted(documents, key=lambda item: str(item.id))
        ],
        "files": [
            (str(record.entity_id), record.version_number, str(record.replaces_id), record.checksum,
             hashlib.sha256(copy_attachment_content(record)).hexdigest())
            for record in document.attachments.order_by("entity_id")
        ],
    }


def legacy_content_key_fingerprint(owner):
    document, _parent, _leaf = _documents(owner)
    return hashlib.sha256(json.dumps(_retained_state(document, owner), sort_keys=True).encode()).hexdigest()


def promote_content_key_fixture(owner):
    from apps.core.content_index import index_repository_content
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.repository_storage import ensure_workspace_repository

    document, parent, leaf = _documents(owner)
    workspace = document.entity.workspace
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    for item in (leaf, parent, document):
        plan = prepare_document_import(workspace=workspace, document_id=item.id)
        assert apply_document_import(
            workspace=workspace, document_id=item.id, expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256, actor_id=owner.id,
        ).status == "imported"
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    group = prepare_authority_group(
        workspace=workspace, document_ids=(leaf.id, parent.id, document.id), actor_id=owner.id,
        target="repository", reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=group.document_ids, actor_id=owner.id, target="repository",
        reader_workspace=reader, plan_sha256=group.plan_sha256,
    ) == "transitioned"


def content_key_recovery_fingerprint(owner):
    from apps.core.content_authoring import read_authored_content
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.models import DocumentAuthority
    from apps.core.publications import verify_retained_publication_custody

    document, parent, leaf = _documents(owner)
    workspace = document.entity.workspace
    documents = (document, parent, leaf)
    state = _retained_state(document, owner)
    state["git"] = [
        (str(identity), authored.accepted_commit, authored.source_blob,
         hashlib.sha256(authored.source.encode()).hexdigest())
        for item in documents
        for identity in (item.id, item.placements.get().block_id)
        for authored in (read_authored_content(repository=workspace.repository, content_id=identity),)
    ]
    state["authority"] = sorted(
        (str(identity), mode) for identity, mode in DocumentAuthority.objects.filter(
            workspace=workspace,
            content_id__in=[identity for item in documents for identity in (item.id, item.placements.get().block_id)],
        ).values_list("content_id", "authority")
    )
    assert len(state["authority"]) == 6 and {mode for _identity, mode in state["authority"]} == {"repository"}
    for item in documents:
        for publication in item.publications.all():
            assert verify_retained_publication_custody(publication)
            if publication.manifest["format"] == "tekdocs-static-publication/v10":
                assert verify_internal_git_publication(publication)
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def exercise_content_key_fixture(owner):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
    from apps.core.publications import withdraw_publication

    document, parent, leaf = _documents(owner)
    before = _retained_state(document, owner)
    promote_content_key_fixture(owner)
    assert _retained_state(document, owner) == before
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    first = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain accepted substitutions",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    assert first.manifest["format"] == "tekdocs-static-publication/v10" and ORIGINAL in first.canonical_markdown
    frozen = (first.manifest, first.signature, read_publication_artifact(first.artifacts.get(kind="pdf")))
    workspace = document.entity.workspace
    fragment = read_authored_content(repository=workspace.repository, content_id=leaf.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None, markdown=CURRENT + "\n", metadata_patch={},
    )
    live = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")
    assert CURRENT in live["sanitized_html"]
    second = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Correct accepted substitutions",
        audience="msp_internal", retention="permanent", retention_review_on=None, supersedes_entity_id=first.entity_id,
    )
    assert CURRENT in second.canonical_markdown and ORIGINAL not in second.canonical_markdown
    withdraw_publication(publication=second, actor_id=owner.id, reason="Retain withdrawn substitution history")
    first.refresh_from_db()
    assert (first.manifest, first.signature, read_publication_artifact(first.artifacts.get(kind="pdf"))) == frozen
    for target in ("legacy", "repository"):
        plan = prepare_authority_group(
            workspace=workspace, document_ids=(leaf.id, parent.id, document.id), actor_id=owner.id,
            target=target, reader_workspace=reader,
        )
        assert transition_authority_group(
            workspace=workspace, document_ids=plan.document_ids, actor_id=owner.id, target=target,
            reader_workspace=reader, plan_sha256=plan.plan_sha256,
        ) == "transitioned"
    return content_key_recovery_fingerprint(owner)


def content_key_browser_state(owner):
    document, _parent, leaf = _documents(owner)
    original = document.publications.get()
    original_pdf = read_publication_artifact(original.artifacts.get(kind="pdf"))
    return {
        "organization_id": str(document.organization.entity_id), "document_id": str(document.entity_id),
        "content_id": str(document.id), "fragment_id": str(leaf.placements.get().block_id),
        "original_id": str(original.entity_id), "edited_markdown": CURRENT + "\n",
        "original_pdf_sha256": hashlib.sha256(original_pdf).hexdigest(),
        "files": [{"filename": record.original_filename, "sha256": record.checksum}
                  for record in document.attachments.order_by("entity_id")],
    }


def content_key_legacy_state(owner):
    return _retained_state(_documents(owner)[0], owner)


def verify_content_key_browser_fixture(owner, legacy_state):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group

    document, parent, leaf = _documents(owner)
    current = _retained_state(document, owner)
    for before, after in zip(legacy_state["documents"], current["documents"], strict=True):
        original_ids = {record[0] for record in before["publications"]}
        after["publications"] = [record for record in after["publications"] if record[0] in original_ids]
    assert current == legacy_state
    snapshots = list(document.publications.filter(
        manifest__format="tekdocs-static-publication/v10",
    ).order_by("published_at"))
    assert len(snapshots) == 2 and snapshots[1].supersedes_id == snapshots[0].id
    assert snapshots[1].lifecycle_state == "withdrawn"
    assert all(CURRENT in item.canonical_markdown and ORIGINAL not in item.canonical_markdown for item in snapshots)
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    for target in ("legacy", "repository"):
        plan = prepare_authority_group(
            workspace=document.entity.workspace, document_ids=(document.id, parent.id, leaf.id), actor_id=owner.id,
            target=target, reader_workspace=reader,
        )
        assert transition_authority_group(
            workspace=document.entity.workspace, document_ids=plan.document_ids, actor_id=owner.id,
            target=target, reader_workspace=reader, plan_sha256=plan.plan_sha256,
        ) == "transitioned"
        if target == "legacy":
            assert resolve_document(leaf).markdown == CURRENT + "\n"
    content_key_recovery_fingerprint(owner)


def run_content_key_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_content_key_fixture(owner)
    if mode == "seed":
        print("CONTENT_KEY_LEGACY_SHA256=" + legacy_content_key_fingerprint(owner))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert legacy_content_key_fingerprint(owner) == os.environ["TEKDOCS_CONTENT_KEY_LEGACY_SHA256"]
        digest = exercise_content_key_fixture(owner)
        if mode == "recovery_create":
            print("CONTENT_KEY_RECOVERY_SHA256=" + digest)
        print("Content-key graph, signed publications, file versions, PDFs and rollback verified")
    elif mode == "recovery_verify":
        assert content_key_recovery_fingerprint(owner) == os.environ["TEKDOCS_CONTENT_KEY_RECOVERY_SHA256"]
        print("Content-key graph, signed publications, file versions and PDFs recovered exactly")
    else:
        raise ValueError("Unknown content-key fixture mode")


if os.environ.get("TEKDOCS_CONTENT_KEY_FIXTURE_MODE"):
    run_content_key_fixture_mode(os.environ["TEKDOCS_CONTENT_KEY_FIXTURE_MODE"])
