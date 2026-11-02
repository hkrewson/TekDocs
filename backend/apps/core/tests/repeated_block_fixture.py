"""Synthetic repeated-occurrence custody; standalone seed also runs on 0.8.46."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.serializers.json import DjangoJSONEncoder

from apps.accounts.policy import require_installation_member
from apps.core.document_attachments import (
    copy_attachment_content,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.documents import add_document_placement, create_document, resolve_document, update_document
from apps.core.models import Document, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Repeated shared-block acceptance guide"
SOURCE_TITLE = "Repeated shared-block source"
EDITIONS = ("First pinned shared edition.\n", "Second pinned shared edition.\n", "Current live shared edition.\n")
EDITED = "Updated live shared edition.\n"


def documents(owner):
    tenant = require_installation_member(owner).tenant
    return tuple(Document.objects.select_related("entity__workspace", "organization__entity").get(
        tenant=tenant, entity__display_name=title,
    ) for title in (SOURCE_TITLE, TITLE))


def reader_for(owner, document):
    return resolve_organization_workspace(owner, entity_id=document.organization.entity_id)


def publish(owner, document, reason):
    return publish_document(
        workspace=reader_for(owner, document), document=document, actor_id=owner.id,
        reason=reason, audience="msp_internal", retention="permanent", retention_review_on=None,
    )


def seed_repeated_block_fixture(owner):
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=tenant, actor_id=owner.id, name="Repeated shared-block acceptance client",
        legal_name="", website="", classifications=["client"],
    )
    source = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=SOURCE_TITLE, markdown=EDITIONS[0],
    )
    consumer = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=TITLE,
        markdown="Repeated shared-block recovery instructions.\n",
    )
    for position, body in enumerate(EDITIONS, 1):
        if position > 1:
            update_document(
                document=source, actor_id=owner.id, title=SOURCE_TITLE, markdown=body,
                base_revision_id=source.placements.get().block.current_revision_id,
            )
        add_document_placement(
            document=consumer, source_document=source, actor_id=owner.id,
            resolution_mode="live" if position == 3 else "pinned",
            pinned_revision_id=None if position == 3 else source.placements.get().block.current_revision_id,
            parent_id=None, position=position,
        )
    create_document_attachment(
        document=consumer, actor_id=owner.id,
        upload=SimpleUploadedFile("repeated-primary-v1.pdf", render_pdf("First retained repeated-block file.")),
        purpose="primary_file", version_number=1,
    )
    replace_primary_document_file(
        document=consumer, actor_id=owner.id,
        upload=SimpleUploadedFile("repeated-primary-v2.pdf", render_pdf("Second retained repeated-block file.")),
    )
    create_document_attachment(
        document=consumer, actor_id=owner.id,
        upload=SimpleUploadedFile("repeated-checklist.txt", b"Retained repeated-block checklist.\n"),
    )
    publish(owner, source, "Retain original shared source")
    publish(owner, consumer, "Retain original repeated occurrences")


class _RetainedJSONEncoder(DjangoJSONEncoder):
    def default(self, value):
        return value.isoformat() if isinstance(value, datetime) else super().default(value)


def fingerprint(state):
    return hashlib.sha256(json.dumps(state, cls=_RetainedJSONEncoder, sort_keys=True).encode()).hexdigest()


def retained_state(owner):
    result = []
    for document in documents(owner):
        blocks = {item.block_id: item.block for item in document.placements.filter(block__source_document=document)}
        result.append({
            "document": str(document.id), "entity": str(document.entity_id),
            "placements": list(document.placements.order_by("id").values()),
            "blocks": {str(identity): {field.attname: getattr(block, field.attname)
                                       for field in block._meta.concrete_fields}
                       for identity, block in sorted(blocks.items())},
            "revisions": {str(identity): list(block.revisions.order_by("revision_number").values())
                          for identity, block in sorted(blocks.items())},
            "publications": [
                (str(item.id), item.manifest, item.signature, item.content_digest,
                 [(str(artifact.id), str(artifact.entity_id), artifact.checksum,
                   hashlib.sha256(read_publication_artifact(artifact)).hexdigest())
                  for artifact in item.artifacts.order_by("id")],
                 list(item.control_events.order_by("occurred_at", "id").values()))
                for item in document.publications.order_by("id")
            ],
            "files": [({field: getattr(item, field) for field in (
                "id", "entity_id", "document_id", "original_filename", "media_type", "size", "checksum",
                "purpose", "version_number", "replaces_id", "storage_provider", "scan_status", "scan_engine",
                "scanned_at", "created_at", "created_by_id", "archived_at",
            )}, str(item.file.name), hashlib.sha256(copy_attachment_content(item)).hexdigest())
                      for item in document.attachments.order_by("id")],
        })
    return result


def assert_retained(before, after):
    for prior, current in zip(before, after, strict=True):
        retained = dict(current)
        original = {item[0] for item in prior["publications"]}
        retained["publications"] = [item for item in retained["publications"] if item[0] in original]
        retained["revisions"] = {identity: rows[:len(prior["revisions"][identity])]
                                 for identity, rows in retained["revisions"].items()}
        retained["blocks"] = {
            identity: {**row, "current_revision_id": prior["blocks"][identity]["current_revision_id"],
                       "updated_at": prior["blocks"][identity]["updated_at"]}
            for identity, row in retained["blocks"].items()
        }
        assert retained == prior


def copy_document(owner, document):
    from apps.core.document_migration_import import apply_document_import, prepare_document_import

    workspace = document.entity.workspace
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    result = apply_document_import(
        workspace=workspace, document_id=document.id, expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256, actor_id=owner.id,
    )
    assert result.status in {"imported", "already_present"}
    return result


def transition(owner, target):
    from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group

    source, consumer = documents(owner)
    workspace = consumer.entity.workspace
    reader = reader_for(owner, consumer)
    plan = prepare_authority_group(
        workspace=workspace, document_ids=(source.id, consumer.id), actor_id=owner.id,
        target=target, reader_workspace=reader,
    )
    assert transition_authority_group(
        workspace=workspace, document_ids=plan.document_ids, actor_id=owner.id,
        target=target, reader_workspace=reader, plan_sha256=plan.plan_sha256,
    ) == "transitioned"


def prepare_repeated_block_fixture(owner):
    from apps.core.content_authoring import read_authored_content
    from apps.core.content_index import index_repository_content
    from apps.core.repository_service import RepositoryAuditAttribution, commit_repository_files
    from apps.core.repository_storage import ensure_workspace_repository

    source, consumer = documents(owner)
    before = retained_state(owner)
    workspace = consumer.entity.workspace
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    copied = copy_document(owner, source)
    authored = read_authored_content(repository=workspace.repository, content_id=source.placements.get().block_id)
    header = authored.source.rsplit("\n---\n", 1)[0] + "\n---\n"
    base = copied.commit
    # This fixture explicitly prepares the existing accepted-history prerequisite.
    # Each historical body comes from a retained legacy revision, never a PDF.
    # Missing represented history remains a migration blocker in the application.
    revisions = list(source.placements.get().block.revisions.order_by("revision_number"))
    assert [item.markdown for item in revisions] == list(EDITIONS)
    for version in revisions:
        committed = commit_repository_files(
            repository_id=workspace.repository.id, expected_base=base,
            changes={authored.path: (header + version.markdown).encode()},
            message="Prepare synthetic retained shared edition",
            attribution=RepositoryAuditAttribution(actor_id=owner.id, action="content.migration_fixture_history"),
        )
        base = committed.object_id
    index_repository_content(repository_id=workspace.repository.id)
    copy_document(owner, consumer)
    transition(owner, "repository")
    assert retained_state(owner) == before
    return before


def recovery_fingerprint(owner):
    from apps.core.content_authoring import read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.models import DocumentAuthority
    from apps.core.publications import verify_retained_publication_custody
    from apps.core.repository_service import read_repository_markdown_files_at_commit

    source, consumer = documents(owner)
    workspace = consumer.entity.workspace
    identities = (source.id, consumer.id, source.placements.get().block_id,
                  consumer.placements.get(block__source_document=consumer).block_id)
    state = {"retained": retained_state(owner)}
    state["file_owners"] = [
        (str(item.id), str(item.owner_workspace_id), str(item.owner_content_id), item.updated_at)
        for document in (source, consumer) for item in document.attachments.order_by("id")
    ]
    state["authority"] = sorted((str(identity), mode) for identity, mode in DocumentAuthority.objects.filter(
        workspace=workspace, content_id__in=identities,
    ).values_list("content_id", "authority"))
    assert len(state["authority"]) == 4 and {mode for _identity, mode in state["authority"]} == {"repository"}
    state["git"] = [(str(identity), authored.accepted_commit, authored.source_blob,
                     hashlib.sha256(authored.source.encode()).hexdigest())
                    for identity in identities
                    for authored in (read_authored_content(repository=workspace.repository, content_id=identity),)]
    root = read_authored_content(repository=workspace.repository, content_id=consumer.id)
    from apps.core.content_profile import parse_content

    pins = [item for item in parse_content(root.source.encode()).includes if item.mode == "pinned"]
    assert len(pins) == 2 and len({item.pinned_object_id for item in pins}) == 2
    historical = []
    for pin in pins:
        _commit, files = read_repository_markdown_files_at_commit(
            repository_id=workspace.repository.id, object_id=pin.pinned_object_id,
        )
        body = dict(files)[f"fragments/{pin.target_content_id}.md"]
        historical.append((pin.pinned_object_id, hashlib.sha256(body).hexdigest()))
    state["pins"] = historical
    detail = document_detail(workspace=reader_for(owner, consumer), content_id=consumer.id, audience="msp_internal")
    state["markdown"] = detail["markdown"]
    for document in (source, consumer):
        assert all(verify_retained_publication_custody(item) for item in document.publications.all())
    return fingerprint(state)


def browser_state(owner):
    source, consumer = documents(owner)
    original = consumer.publications.get()
    return {
        "organization_id": str(consumer.organization.entity_id),
        "document_id": str(consumer.entity_id), "content_id": str(consumer.id),
        "fragment_id": str(source.placements.get().block_id),
        "original_id": str(original.entity_id),
        "original_pdf_sha256": hashlib.sha256(
            read_publication_artifact(original.artifacts.get(kind="pdf"))
        ).hexdigest(),
        "edited_markdown": EDITED,
        "files": [{"filename": item.original_filename,
                   "sha256": hashlib.sha256(copy_attachment_content(item)).hexdigest()}
                  for item in consumer.attachments.order_by("id")],
    }


def exercise_repeated_block_fixture(owner, before=None):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail

    if before is None:
        before = prepare_repeated_block_fixture(owner)
    source, consumer = documents(owner)
    reader = reader_for(owner, consumer)
    snapshot = publish(owner, consumer, "Freeze each repeated Git occurrence")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v12"
    proof = snapshot.manifest["git_source"]["sources"]
    assert [item["ordinal_path"] for item in proof] == [[], [0], [1], [2], [3]]
    assert proof[2]["commit"] != proof[3]["commit"]
    assert [item["mode"] for item in proof] == ["root", "live", "pinned", "pinned", "live"]
    fragment = read_authored_content(repository=consumer.entity.workspace.repository,
                                     content_id=source.placements.get().block_id)
    author_content(
        repository=consumer.entity.workspace.repository, actor_id=owner.id, request_id=None,
        operation="update", content_id=fragment.content_id, base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob, kind=None, path=None, title=None, markdown=EDITED, metadata_patch={},
    )
    current = document_detail(workspace=reader, content_id=consumer.id, audience="msp_internal")["markdown"]
    for body in (*EDITIONS[:2], EDITED):
        assert current.count(body.strip()) == 1
    assert EDITIONS[2].strip() not in current
    transition(owner, "legacy")
    assert resolve_document(consumer).markdown == current
    transition(owner, "repository")
    assert document_detail(workspace=reader, content_id=consumer.id, audience="msp_internal")["markdown"] == current
    assert_retained(before, retained_state(owner))
    return recovery_fingerprint(owner)


def run_repeated_block_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_repeated_block_fixture(owner)
    if mode == "seed":
        print("REPEATED_BLOCK_LEGACY_SHA256=" + fingerprint(retained_state(owner)))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert fingerprint(retained_state(owner)) == os.environ["TEKDOCS_REPEATED_BLOCK_LEGACY_SHA256"]
        digest = exercise_repeated_block_fixture(owner)
        if mode == "recovery_create":
            print("REPEATED_BLOCK_RECOVERY_SHA256=" + digest)
        print("Repeated shared occurrences, distinct pins, signatures, file versions, PDFs and rollback verified")
    elif mode == "recovery_verify":
        assert recovery_fingerprint(owner) == os.environ["TEKDOCS_REPEATED_BLOCK_RECOVERY_SHA256"]
        print("Repeated shared occurrences, distinct pins, signatures, file versions and PDFs recovered exactly")
    else:
        raise ValueError("Unknown repeated-block fixture mode")


if os.environ.get("TEKDOCS_REPEATED_BLOCK_FIXTURE_MODE"):
    run_repeated_block_fixture_mode(os.environ["TEKDOCS_REPEATED_BLOCK_FIXTURE_MODE"])
