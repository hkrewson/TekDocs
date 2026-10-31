"""Synthetic monitored-source custody; seed imports remain compatible with 0.8.46."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.accounts.policy import require_installation_member
from apps.core.document_attachments import (
    copy_attachment_content,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.document_source_models import DocumentRemoteObservation, DocumentRemoteSource
from apps.core.documents import create_document, resolve_document, update_document
from apps.core.models import Document, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Monitored-source migration acceptance guide"
ORIGINAL = "Original monitored recovery instructions."
LOCAL = "Local recovery note must survive."
CURRENT = "Current monitored recovery instructions."


def _document(owner):
    return Document.objects.select_related("entity__workspace", "organization__entity").get(
        tenant=require_installation_member(owner).tenant, entity__display_name=TITLE,
    )


def _observe(source, markdown, *, state="changed", error_code=""):
    return DocumentRemoteObservation.objects.create(
        tenant=source.tenant, organization=source.organization, source=source, state=state,
        status_code=200 if markdown else None, content_type="text/markdown" if markdown else "",
        canonical_markdown=markdown, content_digest=hashlib.sha256(markdown.encode()).hexdigest() if markdown else "",
        error_code=error_code, etag_digest=hashlib.sha256(b"synthetic-etag").hexdigest(),
        last_modified_digest=hashlib.sha256(b"synthetic-last-modified").hexdigest(),
    )


def seed_monitored_source_fixture(owner):
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=tenant, actor_id=owner.id, name="Monitored acceptance client", legal_name="", website="",
        classifications=["client"],
    )
    document = create_document(
        tenant=tenant, organization=organization, actor_id=owner.id, title=TITLE, markdown=ORIGINAL + "\n",
    )
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain original monitored instructions",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    source = DocumentRemoteSource.objects.create(
        tenant=tenant, organization=organization, document=document, created_by=owner,
        url="https://example.invalid/monitored-guide?edition=synthetic", source_kind="markdown", enabled=False,
        check_interval_minutes=180, last_checked_at=timezone.now(), next_check_at=timezone.now() + timedelta(hours=3),
    )
    original = _observe(source, ORIGINAL + "\n")
    source.last_applied_observation = original
    source.save(update_fields=("last_applied_observation", "updated_at"))
    _observe(source, ORIGINAL + "\n", state="unchanged")
    _observe(source, "", state="failed", error_code="remote_connection_failed")
    create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("monitored-primary-v1.pdf", render_pdf("Original monitored primary file.")),
        purpose="primary_file", version_number=1,
    )
    replace_primary_document_file(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("monitored-primary-v2.pdf", render_pdf("Revised monitored primary file.")),
    )
    linked = create_document_attachment(
        document=document, actor_id=owner.id,
        upload=SimpleUploadedFile("monitored-checklist.txt", b"Retained monitored checklist.\n"),
    )
    suffix = f"\n{LOCAL}\n\n[Checklist](tekdocs://attachment/{linked.entity_id})\n"
    update_document(
        document=document, actor_id=owner.id, title=TITLE, markdown=ORIGINAL + "\n" + suffix,
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain local monitored edits",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    _observe(source, CURRENT + "\n" + suffix)


def monitored_source_retained_state(owner):
    document = _document(owner)
    source = document.remote_source
    return {
        "id": str(document.id), "entity": str(document.entity_id),
        "source": {field.attname: getattr(source, field.attname) for field in source._meta.concrete_fields},
        "observations": list(source.observations.order_by("id").values()),
        "revisions": list(document.placements.get().block.revisions.order_by("revision_number").values()),
        "publications": [
            (str(item.id), item.manifest, item.signature, item.content_digest,
             [(str(artifact.id), str(artifact.entity_id), artifact.kind, artifact.checksum,
               hashlib.sha256(read_publication_artifact(artifact)).hexdigest())
              for artifact in item.artifacts.order_by("id")],
             list(item.control_events.order_by("occurred_at", "id").values()))
            for item in document.publications.order_by("id")
        ],
        "files": [
            (str(item.id), str(item.entity_id), item.version_number, str(item.replaces_id), item.checksum,
             hashlib.sha256(copy_attachment_content(item)).hexdigest())
            for item in document.attachments.order_by("id")
        ],
    }


class _RetainedJSONEncoder(DjangoJSONEncoder):
    # Kept in the standalone seed so the old image can fingerprint its own
    # records. Django's ordinary encoder truncates timestamps to milliseconds.
    def default(self, value):
        return value.isoformat() if isinstance(value, datetime) else super().default(value)


def _fingerprint(state):
    return hashlib.sha256(json.dumps(state, cls=_RetainedJSONEncoder, sort_keys=True).encode()).hexdigest()


def legacy_monitored_source_fingerprint(owner):
    return _fingerprint(monitored_source_retained_state(owner))


def promote_monitored_source_fixture(owner):
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
    # Applying is allowed to advance only the pointer and its modification time.
    retained["source"] = dict(retained["source"])
    for field in ("last_applied_observation_id", "updated_at"):
        retained["source"][field] = before["source"][field]
    assert retained == before


def monitored_source_recovery_fingerprint(owner):
    from apps.core.content_authoring import read_authored_content
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.document_source_state import monitored_source_fingerprint
    from apps.core.models import DocumentAuthority
    from apps.core.publications import verify_retained_publication_custody

    document = _document(owner)
    workspace = document.entity.workspace
    state = monitored_source_retained_state(owner)
    assert monitored_source_fingerprint(document)
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
        assert verify_retained_publication_custody(item)
        if item.manifest["format"].startswith("tekdocs-static-publication/v") and item.manifest.get("git_source"):
            assert verify_internal_git_publication(item)
    return _fingerprint(state)


def exercise_monitored_source_fixture(owner):
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_read import document_detail
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_source_git import preview_remote_observation
    from apps.core.document_sources import apply_remote_observation
    from apps.core.documents import PlacementConflict
    from apps.core.publications import withdraw_publication

    document = _document(owner)
    before = monitored_source_retained_state(owner)
    promote_monitored_source_fixture(owner)
    assert monitored_source_retained_state(owner) == before
    observation = document.remote_source.observations.filter(state="changed").first()
    review = preview_remote_observation(observation=observation)
    assert review and review["blocker"] == "local_edits_require_integration"
    try:
        apply_remote_observation(observation=observation, actor_id=owner.id, review_fingerprint=review["fingerprint"])
    except PlacementConflict:
        pass
    else:
        raise AssertionError("Local edits were overwritten")
    assert monitored_source_retained_state(owner) == before
    workspace = document.entity.workspace
    fragment = read_authored_content(repository=workspace.repository, content_id=document.placements.get().block_id)
    author_content(
        repository=workspace.repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=fragment.content_id, base_commit=fragment.accepted_commit, base_blob=fragment.source_blob,
        kind=None, path=None, title=None, markdown=observation.canonical_markdown, metadata_patch={},
    )
    review = preview_remote_observation(observation=observation)
    assert review and not review["blocker"]
    apply_remote_observation(observation=observation, actor_id=owner.id, review_fingerprint=review["fingerprint"])
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    assert document_detail(workspace=reader, content_id=document.id, audience="msp_internal")["markdown"] == (
        observation.canonical_markdown
    )
    first = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Retain reviewed monitored update",
        audience="msp_internal", retention="permanent", retention_review_on=None,
    )
    second = publish_document(
        workspace=reader, document=document, actor_id=owner.id, reason="Correct monitored publication",
        audience="msp_internal", retention="permanent", retention_review_on=None, supersedes_entity_id=first.entity_id,
    )
    withdraw_publication(publication=second, actor_id=owner.id, reason="Retain withdrawn monitored publication")
    for target in ("legacy", "repository"):
        assert transition_document_authority(
            workspace=workspace, document_id=document.id, actor_id=owner.id, target=target, reader_workspace=reader,
        ) == "transitioned"
        if target == "legacy":
            assert LOCAL in resolve_document(document).markdown and CURRENT in resolve_document(document).markdown
    _assert_history_preserved(before, monitored_source_retained_state(owner))
    return monitored_source_recovery_fingerprint(owner)


def monitored_source_browser_state(owner):
    document = _document(owner)
    original = document.publications.order_by("published_at").last()
    observation = document.remote_source.observations.filter(state="changed").first()
    return {
        "organization_id": str(document.organization.entity_id), "document_id": str(document.entity_id),
        "content_id": str(document.id), "fragment_id": str(document.placements.get().block_id),
        "observation_id": str(observation.id), "original_id": str(original.entity_id),
        "original_pdf_sha256": hashlib.sha256(
            read_publication_artifact(original.artifacts.get(kind="pdf")),
        ).hexdigest(),
        "edited_markdown": observation.canonical_markdown,
        "files": [{"filename": item.original_filename, "sha256": item.checksum}
                  for item in document.attachments.order_by("id")],
    }


def verify_monitored_source_browser_fixture(owner, before):
    from apps.core.document_authority_handoff import transition_document_authority

    document = _document(owner)
    _assert_history_preserved(before, monitored_source_retained_state(owner))
    source = document.remote_source
    assert source.last_applied_observation == source.observations.filter(state="changed").first()
    publications = list(document.publications.filter(manifest__format="tekdocs-static-publication/v6").order_by(
        "published_at",
    ))
    assert len(publications) == 2 and publications[1].supersedes_id == publications[0].id
    assert publications[1].lifecycle_state == "withdrawn"
    assert all(CURRENT in item.canonical_markdown and LOCAL in item.canonical_markdown for item in publications)
    for target in ("legacy", "repository"):
        assert transition_document_authority(
            workspace=document.entity.workspace, document_id=document.id, actor_id=owner.id, target=target,
            reader_workspace=resolve_organization_workspace(owner, entity_id=document.organization.entity_id),
        ) == "transitioned"
    _assert_history_preserved(before, monitored_source_retained_state(owner))
    monitored_source_recovery_fingerprint(owner)


def run_monitored_source_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_monitored_source_fixture(owner)
    if mode == "seed":
        print("MONITORED_SOURCE_LEGACY_SHA256=" + legacy_monitored_source_fingerprint(owner))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert legacy_monitored_source_fingerprint(owner) == os.environ["TEKDOCS_MONITORED_SOURCE_LEGACY_SHA256"]
        digest = exercise_monitored_source_fixture(owner)
        if mode == "recovery_create":
            print("MONITORED_SOURCE_RECOVERY_SHA256=" + digest)
        print("Monitored settings, observations, local edits, signed publications, files, PDFs and rollback verified")
    elif mode == "recovery_verify":
        assert monitored_source_recovery_fingerprint(owner) == os.environ["TEKDOCS_MONITORED_SOURCE_RECOVERY_SHA256"]
        print("Monitored settings, observations, local edits, signed publications, files and PDFs recovered exactly")
    else:
        raise ValueError("Unknown monitored-source fixture mode")


if os.environ.get("TEKDOCS_MONITORED_SOURCE_FIXTURE_MODE"):
    run_monitored_source_fixture_mode(os.environ["TEKDOCS_MONITORED_SOURCE_FIXTURE_MODE"])
