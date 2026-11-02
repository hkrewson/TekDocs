"""Standalone legacy-compatible cross-Workspace custody for upgrade and recovery."""

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
from apps.core.documents import (
    add_block_placement,
    create_document,
    create_document_block,
    resolve_document,
    update_shared_block,
)
from apps.core.models import Document, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace

SOURCE_TITLE = "Cross-Workspace library acceptance source"
TITLE = "Cross-Workspace library acceptance guide"
EDITIONS = (
    "First retained library edition.\n",
    "Second retained library edition.\n",
    "Current live library edition.\n",
)
EDITED = "Updated live library edition.\n"


def documents(owner):
    tenant = require_installation_member(owner).tenant
    return tuple(
        Document.objects.select_related("entity__workspace", "organization__entity").get(
            tenant=tenant,
            entity__display_name=title,
        )
        for title in (SOURCE_TITLE, TITLE)
    )


def reader_for(owner, document):
    return (
        resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
        if document.organization_id
        else resolve_msp_workspace(owner)
    )


def publish(owner, document, reason):
    return publish_document(
        workspace=reader_for(owner, document),
        document=document,
        actor_id=owner.id,
        reason=reason,
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )


def seed_cross_workspace_fixture(owner):
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    source = create_document(
        tenant=tenant,
        organization=None,
        actor_id=owner.id,
        title=SOURCE_TITLE,
        markdown="Unreferenced MSP introduction.\n",
        library_visible=True,
    )
    section = create_document_block(
        document=source,
        actor_id=owner.id,
        markdown=EDITIONS[0],
        kind="rich_text",
        name="Library procedure",
        parent_id=None,
        position=1,
        library_visible=True,
    )
    create_document_block(
        document=source,
        actor_id=owner.id,
        markdown="Private MSP child is never reused.\n",
        kind="rich_text",
        name="Private child",
        parent_id=section.id,
        position=0,
    )
    organization = create_organization(
        tenant=tenant,
        actor_id=owner.id,
        name="Cross-Workspace acceptance client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    consumer = create_document(
        tenant=tenant,
        organization=organization,
        actor_id=owner.id,
        title=TITLE,
        markdown="Cross-Workspace recovery instructions.\n",
    )
    for position, body in enumerate(EDITIONS, 1):
        if position > 1:
            section.block.refresh_from_db()
            update_shared_block(
                placement=section, actor_id=owner.id, markdown=body, base_revision_id=section.block.current_revision_id
            )
        section.block.refresh_from_db()
        add_block_placement(
            document=consumer,
            block=section.block,
            actor_id=owner.id,
            resolution_mode="live" if position == 3 else "pinned",
            pinned_revision_id=None if position == 3 else section.block.current_revision_id,
            parent_id=None,
            position=position,
        )
    for document, label in ((source, "library-source"), (consumer, "library-client")):
        create_document_attachment(
            document=document,
            actor_id=owner.id,
            purpose="primary_file",
            version_number=1,
            upload=SimpleUploadedFile(f"{label}-v1.pdf", render_pdf("First retained library file.")),
        )
        replace_primary_document_file(
            document=document,
            actor_id=owner.id,
            upload=SimpleUploadedFile(f"{label}-v2.pdf", render_pdf("Second retained library file.")),
        )
        create_document_attachment(
            document=document,
            actor_id=owner.id,
            upload=SimpleUploadedFile(f"{label}-checklist.txt", b"Retained library checklist.\n"),
        )
        publish(owner, document, "Retain original cross-Workspace custody")


class _Encoder(DjangoJSONEncoder):
    def default(self, value):
        return value.isoformat() if isinstance(value, datetime) else super().default(value)


def fingerprint(state):
    return hashlib.sha256(json.dumps(state, cls=_Encoder, sort_keys=True).encode()).hexdigest()


def retained_state(owner):
    """Use legacy-stable fields so 0.8.46 and upgraded custody compare exactly."""
    return [
        {
            "document": str(document.id),
            "entity": str(document.entity_id),
            "placements": list(document.placements.order_by("id").values()),
            "revisions": {
                str(placement.block_id): list(placement.block.revisions.order_by("revision_number").values())
                for placement in document.placements.filter(block__source_document=document)
            },
            "publications": [
                (
                    str(item.id),
                    item.manifest,
                    item.signature,
                    item.content_digest,
                    [
                        (
                            str(artifact.id),
                            artifact.checksum,
                            hashlib.sha256(read_publication_artifact(artifact)).hexdigest(),
                        )
                        for artifact in item.artifacts.order_by("id")
                    ],
                    list(item.control_events.order_by("occurred_at", "id").values()),
                )
                for item in document.publications.order_by("id")
            ],
            "files": [
                (
                    {
                        field: getattr(item, field)
                        for field in (
                            "id",
                            "entity_id",
                            "document_id",
                            "original_filename",
                            "media_type",
                            "size",
                            "checksum",
                            "purpose",
                            "version_number",
                            "replaces_id",
                            "storage_provider",
                            "scan_status",
                            "scan_engine",
                            "scanned_at",
                            "created_at",
                            "created_by_id",
                            "archived_at",
                        )
                    },
                    str(item.file.name),
                    hashlib.sha256(copy_attachment_content(item)).hexdigest(),
                )
                for item in document.attachments.order_by("id")
            ],
        }
        for document in documents(owner)
    ]


def assert_retained(before, after):
    for prior, current in zip(before, after, strict=True):
        original = {item[0] for item in prior["publications"]}
        retained = {
            **current,
            "publications": [item for item in current["publications"] if item[0] in original],
            "revisions": {
                identity: rows[: len(prior["revisions"][identity])] for identity, rows in current["revisions"].items()
            },
        }
        assert retained == prior


def transition(owner, target):
    from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority

    source, consumer = documents(owner)
    arguments = dict(
        source_workspace=source.entity.workspace,
        source_document_id=source.id,
        destination_document_ids=(consumer.id,),
        actor_id=owner.id,
        target=target,
    )
    plan = prepare_shared_library_handoff(**arguments)
    assert transition_shared_library_authority(**arguments, plan_sha256=plan.plan_sha256) == "transitioned"


def prepare_cross_workspace_fixture(owner):
    from apps.core.content_index import index_repository_content
    from apps.core.repository_storage import ensure_workspace_repository
    from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
    from apps.core.tests.repeated_block_fixture import copy_document

    source, consumer = documents(owner)
    before = retained_state(owner)
    for document in (source, consumer):
        ensure_workspace_repository(document.entity.workspace)
        index_repository_content(repository_id=document.entity.workspace.repository.id)
    copy_document(owner, source)
    history = prepare_shared_library_history(source=source, actor_id=owner.id)
    retain_shared_library_history(source=source, actor_id=owner.id, plan_sha256=history.plan_sha256)
    copy_document(owner, consumer)
    transition(owner, "repository")
    assert retained_state(owner) == before
    return before


def recovery_fingerprint(owner):
    from django.db import transaction

    from apps.core.content_authoring import read_authored_content
    from apps.core.content_profile import parse_content
    from apps.core.content_read import document_detail
    from apps.core.models import DocumentAuthority
    from apps.core.publications import verify_retained_publication_custody
    from apps.core.repository_service import read_library_fragment

    source, consumer = documents(owner)
    state = {"retained": retained_state(owner), "git": [], "authority": [], "file_owners": []}
    for document in (source, consumer):
        ids = (
            document.id,
            *document.placements.filter(block__source_document=document).values_list("block_id", flat=True),
        )
        state["authority"].extend(
            sorted(
                (str(identity), mode)
                for identity, mode in DocumentAuthority.objects.filter(
                    workspace=document.entity.workspace,
                    content_id__in=ids,
                ).values_list("content_id", "authority")
            )
        )
        assert DocumentAuthority.objects.filter(
            workspace=document.entity.workspace, content_id__in=ids, authority="repository"
        ).count() == len(ids)
        for identity in ids:
            authored = read_authored_content(repository=document.entity.workspace.repository, content_id=identity)
            state["git"].append(
                (
                    str(identity),
                    authored.accepted_commit,
                    authored.source_blob,
                    hashlib.sha256(authored.source.encode()).hexdigest(),
                )
            )
        state["file_owners"].extend(
            (str(item.id), str(item.owner_workspace_id), str(item.owner_content_id), item.updated_at)
            for item in document.attachments.order_by("id")
        )
        assert all(verify_retained_publication_custody(item) for item in document.publications.all())
    root = read_authored_content(repository=consumer.entity.workspace.repository, content_id=consumer.id)
    pins = [item for item in parse_content(root.source.encode()).includes if item.mode == "pinned"]
    assert len(pins) == 2 and len({item.library_revision_id for item in pins}) == 2
    with transaction.atomic():
        state["pins"] = [
            (selected.object_id, selected.source_path, hashlib.sha256(selected.source).hexdigest())
            for item in pins
            for selected in (
                read_library_fragment(
                    tenant_id=consumer.tenant_id,
                    destination_document_id=consumer.id,
                    library_workspace_id=source.entity.workspace_id,
                    source_block_id=item.target_content_id,
                    mode="pinned",
                    pinned_object_id=item.pinned_object_id,
                    library_revision_id=item.library_revision_id,
                    library_source_id=source.id,
                ),
            )
        ]
    state["markdown"] = document_detail(
        workspace=reader_for(owner, consumer), content_id=consumer.id, audience="msp_internal"
    )["markdown"]
    return fingerprint(state)


def browser_state(owner):
    source, consumer = documents(owner)
    original = consumer.publications.get()
    return {
        "organization_id": str(consumer.organization.entity_id),
        "document_id": str(consumer.entity_id),
        "content_id": str(consumer.id),
        "fragment_id": str(source.placements.get(position=1).block_id),
        "source_msp": True,
        "original_id": str(original.entity_id),
        "edited_markdown": EDITED,
        "original_pdf_sha256": hashlib.sha256(
            read_publication_artifact(original.artifacts.get(kind="pdf"))
        ).hexdigest(),
        "files": [
            {"filename": item.original_filename, "sha256": hashlib.sha256(copy_attachment_content(item)).hexdigest()}
            for item in consumer.attachments.order_by("id")
        ],
    }


def exercise_cross_workspace_fixture(owner, before=None):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail

    if before is None:
        before = prepare_cross_workspace_fixture(owner)
    source, consumer = documents(owner)
    snapshot = publish(owner, consumer, "Freeze ordinary cross-Workspace dependencies")
    assert snapshot.manifest["format"] == "tekdocs-static-publication/v13"
    assert snapshot.manifest["library_format"] == "tekdocs-static-publication/v12"
    for body in (*EDITIONS[:2], EDITED if EDITED in snapshot.canonical_markdown else EDITIONS[2]):
        assert snapshot.canonical_markdown.count(body.strip()) == 1
    assert "Private MSP child" not in snapshot.canonical_markdown
    fragment = read_authored_content(
        repository=source.entity.workspace.repository, content_id=source.placements.get(position=1).block_id
    )
    author_content(
        repository=source.entity.workspace.repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=EDITED,
        metadata_patch={},
    )
    current = document_detail(workspace=reader_for(owner, consumer), content_id=consumer.id, audience="msp_internal")[
        "markdown"
    ]
    for body in (*EDITIONS[:2], EDITED):
        assert current.count(body.strip()) == 1
    transition(owner, "legacy")
    assert resolve_document(consumer).markdown == current
    transition(owner, "repository")
    assert_retained(before, retained_state(owner))
    return recovery_fingerprint(owner)


def run_cross_workspace_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_cross_workspace_fixture(owner)
    if mode == "seed":
        print("CROSS_WORKSPACE_LEGACY_SHA256=" + fingerprint(retained_state(owner)))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert fingerprint(retained_state(owner)) == os.environ["TEKDOCS_CROSS_WORKSPACE_LEGACY_SHA256"]
        digest = exercise_cross_workspace_fixture(owner)
        if mode == "recovery_create":
            print("CROSS_WORKSPACE_RECOVERY_SHA256=" + digest)
        print("Cross-Workspace isolation, pins, signed publications, files, PDFs and rollback verified")
    elif mode == "recovery_verify":
        assert recovery_fingerprint(owner) == os.environ["TEKDOCS_CROSS_WORKSPACE_RECOVERY_SHA256"]
        print("Cross-Workspace sources, pins, signed publications, file versions and PDFs recovered exactly")
    else:
        raise ValueError("Unknown cross-Workspace fixture mode")


if os.environ.get("TEKDOCS_CROSS_WORKSPACE_FIXTURE_MODE"):
    run_cross_workspace_fixture_mode(os.environ["TEKDOCS_CROSS_WORKSPACE_FIXTURE_MODE"])
