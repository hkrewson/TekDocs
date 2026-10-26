"""Internal STATIC snapshots for the proven single-fragment promoted shape."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import timedelta

from cryptography.hazmat.primitives import serialization
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .content_publication_sources import ContentPublicationSourceError, pinned_git_document_dependencies
from .models import (
    AuditEvent,
    ContentNode,
    Document,
    DocumentAttachment,
    DocumentAuthority,
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    WorkspaceRepository,
)
from .publications import (
    PendingArtifact,
    PublicationConflict,
    _artifact_descriptor,
    _timestamp,
    publication_signing_key,
    snapshot_payload,
    verify_publication,
    verify_retained_publication_custody,
)
from .rendering import render_markdown, render_pdf
from .repository_publication_preflight import repository_publication_preflight
from .workspaces import ResolvedWorkspace

GIT_STATIC_FORMAT = "tekdocs-static-publication/v5"


def verify_git_publication_source(publication: DocumentPublication) -> bool:
    """Check the signed source descriptor without consulting current Git state."""
    try:
        manifest = publication.manifest
        source = manifest["git_source"]
        sources = source["sources"]
        return bool(
            manifest["format"] == GIT_STATIC_FORMAT
            and publication.audience == manifest["audience"] == "msp_internal"
            and manifest["source_document_id"] == str(publication.document.entity_id)
            and source["format"] == "tekdocs.git-dependencies/v1"
            and source["content_id"] == str(publication.document_id)
            and source["workspace_id"] == str(publication.entity.workspace_id)
            and source["audience"] == "msp_internal"
            and source["markdown_sha256"] == hashlib.sha256(publication.canonical_markdown.encode()).hexdigest()
            and isinstance(sources, list)
            and len(sources) == 2
            and sources[0]["id"] == str(publication.document_id)
            and all(item["commit"] == source["accepted_commit"] for item in sources)
            and publication.document.tenant_id == publication.tenant_id
            and publication.document.organization_id == publication.organization_id
            and publication.document.entity.workspace_id == publication.entity.workspace_id
            and source["root_title"] == publication.title == manifest["title"]
            and manifest["publication_id"] == str(publication.id)
            and manifest["publication_entity_id"] == str(publication.entity_id)
            and len({item["id"] for item in sources}) == 2
        )
    except (KeyError, TypeError, ValueError, AttributeError, OSError, ImproperlyConfigured):
        return False


def verify_internal_git_publication(publication: DocumentPublication) -> bool:
    """Verify retained bytes and signed identity independently of live Git."""
    return bool(
        verify_git_publication_source(publication)
        and verify_publication(publication)["valid"]
        and verify_retained_publication_custody(publication)
    )


def publish_internal_git_document(
    *,
    workspace: ResolvedWorkspace,
    document: Document,
    actor: User,
    reason: str,
    supersedes_entity_id: uuid.UUID | None = None,
) -> DocumentPublication:
    """Append a signed internal snapshot for the bounded promoted shape."""
    member = require_permission(actor, PermissionKey.DOCUMENTS_PUBLISH, organization=workspace.organization)
    owner = document.entity.workspace
    if (
        member.tenant.id != document.tenant_id
        or workspace.member.tenant.id != document.tenant_id
        or document.organization_id != (workspace.organization.id if workspace.organization else None)
        or owner.tenant_id != document.tenant_id
    ):
        raise PublicationConflict("Publication scope does not match the document")
    repository = WorkspaceRepository.objects.get(workspace=owner, tenant_id=member.tenant.id)
    stored = []
    try:
        with (
            pinned_git_document_dependencies(
                repository_id=repository.id,
                content_id=document.id,
                audience="msp_internal",
            ) as source,
            transaction.atomic(),
        ):
            locked = (
                Document.objects.select_for_update(of=("self",))
                .select_related("entity", "organization")
                .get(
                    pk=document.pk,
                    tenant_id=member.tenant.id,
                    organization=workspace.organization,
                )
            )
            if (
                not DocumentAuthority.objects.filter(
                    workspace=owner,
                    content_id=locked.id,
                    authority="repository",
                ).exists()
                or locked.archived_at
                or locked.is_template
                or locked.review_state in {"pending", "changes_requested"}
            ):
                raise PublicationConflict("An active promoted ordinary document is required")
            placements = list(locked.placements.select_related("block"))
            if len(placements) != 1 or placements[0].block.source_document_id != locked.id:
                raise PublicationConflict("Publication shape is not supported")
            if {item["id"] for item in source["sources"]} != {str(locked.id), str(placements[0].block_id)}:
                raise PublicationConflict("Publication dependencies exceed the supported shape")
            node = ContentNode.objects.get(repository=repository, content_id=locked.id)
            variant = node.composition_variants.get("msp_internal", {})
            markdown = variant.get("markdown")
            if not isinstance(markdown, str) or (
                variant.get("digest") != source["composition_digest"]
                or hashlib.sha256(markdown.encode()).hexdigest() != source["markdown_sha256"]
            ):
                raise PublicationConflict("Indexed composition does not match the pinned Git source")
            if locked.review_state == "approved" and locked.review_content_sha256 != source["markdown_sha256"]:
                raise PublicationConflict("Approved review does not match the pinned Git content")
            if DocumentAttachment.objects.filter(owner_workspace=owner, owner_content_id=locked.id).exists():
                raise PublicationConflict("Managed files are outside this publication slice")
            preflight = repository_publication_preflight(
                markdown=markdown, audience="msp_internal", topic_type=node.topic_type or "unstructured"
            )
            if preflight["blockers"] or not markdown.strip() or len(markdown.encode()) > 2 * 1024 * 1024:
                raise PublicationConflict("Publication contains unsupported or unavailable dependencies")
            predecessor = None
            if supersedes_entity_id is not None:
                predecessor = (
                    DocumentPublication.objects.select_for_update()
                    .filter(
                        document=locked,
                        tenant_id=member.tenant.id,
                        organization=workspace.organization,
                        entity_id=supersedes_entity_id,
                    )
                    .first()
                )
                if (
                    predecessor is None
                    or predecessor.lifecycle_state not in {"published", "review_due", "withdrawn"}
                    or not verify_internal_git_publication(predecessor)
                ):
                    raise PublicationConflict("The selected Git publication cannot be superseded")
            created_at = timezone.now()
            publication_id, entity_id = uuid.uuid4(), uuid.uuid4()
            pdf = render_pdf(markdown, title=node.title)
            if not pdf.startswith(b"%PDF-") or len(pdf) > 8 * 1024 * 1024:
                raise PublicationConflict("Publication PDF is unavailable or exceeds its limit")
            pending = PendingArtifact(
                id=uuid.uuid4(),
                entity_id=uuid.uuid4(),
                kind="pdf",
                filename="snapshot.pdf",
                media_type="application/pdf",
                content=pdf,
                checksum=hashlib.sha256(pdf).hexdigest(),
            )
            manifest = {
                "format": GIT_STATIC_FORMAT,
                "publication_id": str(publication_id),
                "publication_entity_id": str(entity_id),
                "source_document_id": str(locked.entity_id),
                "workspace": {
                    "kind": "organization" if locked.organization_id else "msp",
                    "id": str(locked.organization.entity_id) if locked.organization else None,
                },
                "title": node.title,
                "category": locked.category,
                "reason": reason,
                "audience": "msp_internal",
                "retention": "permanent",
                "retention_review_on": None,
                "supersedes_id": str(predecessor.entity_id) if predecessor else None,
                "published_by": str(actor.id),
                "published_at": _timestamp(created_at),
                "git_source": source,
                "artifacts": [_artifact_descriptor(pending)],
                "entities": [],
                "attachments": [],
                "placements": [],
                "diagrams": [],
                "key_resolutions": [],
            }
            html = render_markdown(markdown)
            digest = hashlib.sha256(
                snapshot_payload(manifest=manifest, markdown=markdown, sanitized_html=html)
            ).digest()
            key = publication_signing_key()
            public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            entity = Entity.objects.create(
                id=entity_id,
                tenant_id=locked.tenant_id,
                organization=workspace.organization,
                workspace=owner,
                entity_type="document_publication",
                display_name=node.title,
                visibility="msp_private",
            )
            publication = DocumentPublication(
                id=publication_id,
                tenant_id=locked.tenant_id,
                organization=workspace.organization,
                document=locked,
                entity=entity,
                title=node.title,
                category=locked.category,
                reason=reason,
                audience="msp_internal",
                retention="permanent",
                supersedes=predecessor,
                canonical_markdown=markdown,
                sanitized_html=html,
                manifest=manifest,
                content_digest=digest.hex(),
                signature=base64.urlsafe_b64encode(key.sign(digest)).decode(),
                public_key=base64.urlsafe_b64encode(public).decode(),
                signature_algorithm="Ed25519",
                key_fingerprint=hashlib.sha256(public).hexdigest(),
                published_by=actor,
                published_at=created_at,
            )
            publication.full_clean()
            publication.save()  # type: ignore[no-untyped-call]
            for action in ("submitted", "approved"):
                event = DocumentPublicationControlEvent(
                    tenant_id=locked.tenant_id,
                    organization=workspace.organization,
                    publication=publication,
                    action=action,
                    reason=reason,
                    actor=actor,
                    occurred_at=created_at + (timedelta(microseconds=1) if action == "approved" else timedelta()),
                )
                event.full_clean()
                event.save()  # type: ignore[no-untyped-call]
            artifact_entity = Entity.objects.create(
                id=pending.entity_id,
                tenant_id=locked.tenant_id,
                organization=workspace.organization,
                workspace=owner,
                entity_type="document_publication_artifact",
                display_name="snapshot.pdf",
                visibility="msp_private",
            )
            artifact = DocumentPublicationArtifact(
                id=pending.id,
                tenant_id=locked.tenant_id,
                organization=workspace.organization,
                publication=publication,
                entity=artifact_entity,
                kind="pdf",
                original_filename=pending.filename,
                media_type=pending.media_type,
                size=len(pdf),
                checksum=pending.checksum,
                created_at=created_at,
            )
            artifact.file.save("retained", ContentFile(pdf), save=False)
            stored.append((artifact.file.storage, artifact.file.name))
            artifact.full_clean()
            artifact.save()  # type: ignore[no-untyped-call]
            AuditEvent.objects.create(
                tenant_id=locked.tenant_id,
                actor=actor,
                action="document.git_publication.created",
                entity_id=entity.id,
                metadata={"source_commit": source["accepted_commit"]},
            )
            return publication
    except Exception as exc:
        for storage, name in stored:
            storage.delete(name)
        if isinstance(exc, ContentPublicationSourceError | ContentNode.DoesNotExist | WorkspaceRepository.DoesNotExist):
            raise PublicationConflict("Git publication source is unavailable") from exc
        raise
