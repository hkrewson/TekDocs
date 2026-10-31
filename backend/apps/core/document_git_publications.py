"""Internal STATIC snapshots for supported promoted documents and shared sources."""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from cryptography.hazmat.primitives import serialization
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .content_publication_sources import ContentPublicationSourceError, pinned_git_document_dependencies
from .document_addressed_publications import ADDRESSED_GIT_STATIC_FORMAT, verify_addressed_publication_manifest
from .document_content_key_publications import CONTENT_KEY_GIT_STATIC_FORMAT
from .document_keys import key_targets_in_markdown
from .document_migration_shape import owned_placement_tree
from .document_publication_files import (
    FILE_GIT_STATIC_FORMAT,
    PublicationFile,
    prepare_publication_files,
    verify_publication_file_manifest,
)
from .document_shared_publications import (
    SHARED_GIT_STATIC_FORMAT,
    TEMPLATE_GIT_STATIC_FORMAT,
    verify_shared_publication_manifest,
    verify_template_publication_manifest,
)
from .models import (
    AuditEvent,
    ContentNode,
    Document,
    DocumentAuthority,
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    WorkspaceRepository,
)
from .preflight import FINDING_CATALOG
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
from .rendering import RenderedAttachment, RenderedEntityMention, entity_ids_in_markdown, render_markdown, render_pdf
from .repository_publication_dependencies import (
    RepositoryPublicationDependencyError,
    freeze_repository_entity_cards,
    freeze_repository_key_snapshot,
)
from .repository_publication_preflight import repository_publication_preflight
from .workspaces import ResolvedWorkspace

GIT_STATIC_FORMAT = "tekdocs-static-publication/v5"


@dataclass(frozen=True, slots=True)
class PreparedGitPublication:
    node: ContentNode
    authored_markdown: str
    markdown: str
    preflight: dict[str, Any]
    files: tuple[PublicationFile, ...]
    key_snapshot: dict[str, Any] | None
    entities: tuple[RenderedEntityMention, ...]

    @property
    def addressed(self) -> bool:
        return self.key_snapshot is not None or bool(self.entities)


def verify_git_publication_source(publication: DocumentPublication) -> bool:
    """Check the signed source descriptor without consulting current Git state."""
    try:
        manifest = publication.manifest
        source = manifest["git_source"]
        sources = source["sources"]
        addressed = manifest["format"] in {ADDRESSED_GIT_STATIC_FORMAT, CONTENT_KEY_GIT_STATIC_FORMAT}
        shared = addressed or manifest["format"] in {SHARED_GIT_STATIC_FORMAT, TEMPLATE_GIT_STATIC_FORMAT}
        return bool(
            manifest["format"] in {
                GIT_STATIC_FORMAT, FILE_GIT_STATIC_FORMAT, SHARED_GIT_STATIC_FORMAT, TEMPLATE_GIT_STATIC_FORMAT,
                ADDRESSED_GIT_STATIC_FORMAT, CONTENT_KEY_GIT_STATIC_FORMAT,
            }
            and (not addressed or verify_addressed_publication_manifest(
                manifest, publication.document_id, publication.canonical_markdown,
            ))
            and (manifest["format"] != TEMPLATE_GIT_STATIC_FORMAT
                 or verify_template_publication_manifest(manifest, publication.document_id))
            and (manifest["format"] != SHARED_GIT_STATIC_FORMAT
                 or verify_shared_publication_manifest(manifest, publication.document_id))
            and (
                manifest["format"] != FILE_GIT_STATIC_FORMAT
                or verify_publication_file_manifest(manifest, publication.document_id)
            )
            and publication.audience == manifest["audience"] == "msp_internal"
            and manifest["source_document_id"] == str(publication.document.entity_id)
            and (addressed or source["format"] == (
                "tekdocs.git-dependencies/v2" if manifest["format"] == TEMPLATE_GIT_STATIC_FORMAT
                else "tekdocs.git-dependencies/v1"
            ))
            and source["content_id"] == str(publication.document_id)
            and source["workspace_id"] == str(publication.entity.workspace_id)
            and source["audience"] == "msp_internal"
            and source["markdown_sha256"] == hashlib.sha256(
                (manifest["authored_markdown"] if addressed else publication.canonical_markdown).encode()
            ).hexdigest()
            and isinstance(sources, list)
            and (shared or len(sources) == 2)
            and sources[0]["id"] == str(publication.document_id)
            and (shared
                 or all(item["commit"] == source["accepted_commit"] for item in sources))
            and publication.document.tenant_id == publication.tenant_id
            and publication.document.organization_id == publication.organization_id
            and publication.document.entity.workspace_id == publication.entity.workspace_id
            and source["root_title"] == publication.title == manifest["title"]
            and manifest["publication_id"] == str(publication.id)
            and manifest["publication_entity_id"] == str(publication.entity_id)
            and len({(item.get("library_workspace", source["workspace_id"]), item["id"])
                     for item in sources}) == len(sources)
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


def _validated_git_publication_content(
    *, document: Document, repository: WorkspaceRepository, source: dict[str, Any],
    actor: User | None = None, signed_at: str = "",
) -> PreparedGitPublication:
    """Share the publisher's exact content and custody gates with readiness checks."""
    if (
        not DocumentAuthority.objects.filter(
            workspace=document.entity.workspace,
            content_id=document.id,
            authority="repository",
        ).exists()
        or document.archived_at
        or document.review_state in {"pending", "changes_requested"}
    ):
        raise PublicationConflict("An active promoted ordinary document is required")
    if document.is_template:
        from .document_template_migration import TemplateMigrationError, template_source_fingerprint

        try:
            template_source_fingerprint(document)
        except TemplateMigrationError as exc:
            raise PublicationConflict("Template source history is unavailable or unsupported") from exc
    placements = list(document.placements.select_related("block", "pinned_revision"))
    try:
        owned_placement_tree(document, placements)
    except ValueError as exc:
        raise PublicationConflict("Publication shape is not supported") from exc
    if (not any(p.block.source_document_id == document.id for p in placements)
        or {item["id"] for item in source["sources"]} != {str(document.id), *(str(p.block_id) for p in placements)}):
        raise PublicationConflict("Publication dependencies exceed the supported shape")
    from .document_template_migration import template_enrollment_evidence

    enrollment = template_enrollment_evidence(document)
    if enrollment is not None and enrollment.library_placement_ids:
        library_source = Document.objects.get(tenant_id=document.tenant_id, pk=enrollment.source_document_id)
        if not DocumentAuthority.objects.filter(
            tenant_id=document.tenant_id, workspace_id=library_source.entity.workspace_id,
            content_id=library_source.id, authority="repository",
        ).exists():
            raise PublicationConflict("Template library source requires the complete authority handoff")
    live_ids = {p.block_id for p in placements if p.resolution_mode == "live"
                and p.block.organization_id == document.organization_id}
    retired_ids = set(DocumentAuthority.objects.filter(
        workspace=document.entity.workspace, content_id__in=live_ids, authority="repository",
    ).values_list("content_id", flat=True))
    if retired_ids != live_ids:
        raise PublicationConflict("Shared live content requires a complete authority handoff")
    node = ContentNode.objects.get(repository=repository, content_id=document.id)
    variant = node.composition_variants.get("msp_internal", {})
    markdown = variant.get("markdown")
    if not isinstance(markdown, str) or (
        variant.get("digest") != source["composition_digest"]
        or hashlib.sha256(markdown.encode()).hexdigest() != source["markdown_sha256"]
    ):
        raise PublicationConflict("Indexed composition does not match the pinned Git source")
    if document.review_state == "approved" and document.review_content_sha256 != source["markdown_sha256"]:
        raise PublicationConflict("Approved review does not match the pinned Git content")
    key_snapshot = None
    entities: list[RenderedEntityMention] = []
    if key_targets_in_markdown(markdown) or entity_ids_in_markdown(markdown):
        if actor is None:
            raise PublicationConflict("Record dependencies require an authorized reader")
        member = require_permission(actor, PermissionKey.DOCUMENTS_VIEW, organization=document.organization)
        try:
            key_snapshot = freeze_repository_key_snapshot(
                repository=repository, node=node, document=document, markdown=markdown,
                audience="msp_internal", actor=actor, signed_at=signed_at,
            )
            entities = freeze_repository_entity_cards(
                repository=repository, markdown=key_snapshot["markdown"] if key_snapshot is not None else markdown,
                audience="msp_internal", actor=actor, member=member,
            )
        except RepositoryPublicationDependencyError as exc:
            raise PublicationConflict("Record dependencies are unavailable or outside the reviewed scope") from exc
    frozen_markdown = key_snapshot["markdown"] if key_snapshot is not None else markdown
    try:
        files = prepare_publication_files(document=document, markdown=frozen_markdown)
    except (ValueError, OSError) as exc:
        raise PublicationConflict("Managed file custody is unavailable") from exc
    preflight = repository_publication_preflight(
        markdown=frozen_markdown, audience="msp_internal", topic_type=node.topic_type or "unstructured",
        frozen_attachment_ids={uuid.UUID(item.descriptor["id"]) for item in files},
        frozen_primary_file=any(item.descriptor["purpose"] == "primary_file" for item in files),
        frozen_entity_ids={uuid.UUID(item["id"]) for item in entities},
        frozen_key_targets=set(key_targets_in_markdown(markdown)) if key_snapshot is not None else None,
    )
    if preflight["blockers"] or len(markdown.encode()) > 2 * 1024 * 1024:
        raise PublicationConflict("Publication contains unsupported or unavailable dependencies")
    from .document_migration_publications import publication_migration_evidence

    if (
        DocumentPublication.objects.filter(document=document).exists()
        and publication_migration_evidence(workspace=document.entity.workspace, document=document) is None
    ):
        raise PublicationConflict("Retained publication history is unavailable or unsupported")
    return PreparedGitPublication(
        node=node, authored_markdown=markdown,
        markdown=key_snapshot["markdown"] if key_snapshot is not None else markdown,
        preflight=preflight, files=files, key_snapshot=key_snapshot, entities=tuple(entities),
    )


def preflight_internal_git_document(
    *, document: Document, audience: str, workspace: ResolvedWorkspace | None = None,
) -> dict[str, Any]:
    """Readiness only: callers authorize document visibility; publishing rechecks all gates."""
    findings = []
    digest = ""
    try:
        if audience != "msp_internal":
            raise PublicationConflict("Only internal snapshots are supported")
        repository = WorkspaceRepository.objects.get(workspace=document.entity.workspace, tenant_id=document.tenant_id)
        with pinned_git_document_dependencies(
            repository_id=repository.id, content_id=document.id, audience=audience
        ) as source:
            locked = (
                Document.objects.select_for_update(of=("self",))
                .select_related("entity")
                .get(pk=document.pk, tenant_id=document.tenant_id, organization=document.organization)
            )
            prepared = _validated_git_publication_content(
                document=locked, repository=repository, source=source,
                actor=workspace.member.user if workspace is not None else None,
                signed_at=_timestamp(timezone.now()),
            )
            digest = source["composition_digest"]
            for code in prepared.preflight["warnings"]:
                severity, summary, remediation = FINDING_CATALOG.get(
                    code,
                    (
                        "warning",
                        "The Git document has a topic warning.",
                        "Review the document's topic sections in the repository editor.",
                    ),
                )
                findings.append(
                    {
                        "code": code,
                        "severity": severity,
                        "summary": summary,
                        "remediation": remediation,
                        "target": "document",
                        "section_id": None,
                        "line": None,
                    }
                )
    except (ContentPublicationSourceError, PublicationConflict, ObjectDoesNotExist, OSError):
        severity, summary, remediation = FINDING_CATALOG["repository.publication.unavailable"]
        findings = [
            {
                "code": "repository.publication.unavailable",
                "severity": severity,
                "summary": summary,
                "remediation": remediation,
                "target": "document",
                "section_id": None,
                "line": None,
            }
        ]
    return {
        "version": "tekdocs-preflight/v1",
        "scope": "document",
        "scope_id": str(document.entity_id),
        "composition_digest": digest,
        "audience": audience,
        "valid": not any(item["severity"] == "blocker" for item in findings),
        "counts": {
            level: sum(item["severity"] == level for item in findings) for level in ("blocker", "warning", "info")
        },
        "findings": findings,
    }


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
            created_at = timezone.now()
            prepared = _validated_git_publication_content(
                document=locked, repository=repository, source=source, actor=actor,
                signed_at=_timestamp(created_at),
            )
            node, markdown, files = prepared.node, prepared.markdown, prepared.files
            predecessor = None
            if supersedes_entity_id is not None:
                # Snapshots are immutable. FOR UPDATE hides them under runtime
                # RLS; existing approval guards serialize successor controls.
                predecessor = DocumentPublication.objects.filter(
                    document=locked,
                    tenant_id=member.tenant.id,
                    organization=workspace.organization,
                    entity_id=supersedes_entity_id,
                ).first()
                if (
                    predecessor is None
                    or predecessor.lifecycle_state not in {"published", "review_due", "withdrawn"}
                    or not verify_publication(predecessor)["valid"]
                    or not verify_retained_publication_custody(predecessor)
                ):
                    raise PublicationConflict("The selected Git publication cannot be superseded")
            publication_id, entity_id = uuid.uuid4(), uuid.uuid4()
            rendered_files: dict[str, RenderedAttachment] = {f.descriptor["id"]: {
                "id": f.descriptor["id"], "filename": f.descriptor["filename"], "size": f.descriptor["size"],
            } for f in files}
            pdf = render_pdf(
                markdown, title=node.title, attachments=rendered_files,
                entity_mentions={item["id"]: item for item in prepared.entities},
                publication_id=str(entity_id) if files else "",
                published_at=_timestamp(created_at) if files else "",
                audience="msp_internal" if files else "", reason=reason if files else "",
            )
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
            template_source = None
            if locked.is_template:
                from .documents import ensure_template_revision

                version = ensure_template_revision(source=locked, actor_id=actor.id)
                template_source = {
                    "content_id": str(locked.id), "revision": str(version.id), "checksum": version.checksum,
                }
                source = {**source, "format": "tekdocs.git-dependencies/v2"}
            shared_composition = (source["format"] == "tekdocs.git-dependencies/v2"
                                  or len(source["sources"]) != 2
                                  or any(s["mode"] == "pinned" for s in source["sources"]))
            manifest = {
                "format": (CONTENT_KEY_GIT_STATIC_FORMAT if prepared.key_snapshot is not None
                           and any(item["kind"] == "content" for item in prepared.key_snapshot["records"])
                           else ADDRESSED_GIT_STATIC_FORMAT if prepared.addressed
                           else TEMPLATE_GIT_STATIC_FORMAT if source["format"] == "tekdocs.git-dependencies/v2"
                           else SHARED_GIT_STATIC_FORMAT if shared_composition
                           else FILE_GIT_STATIC_FORMAT if files else GIT_STATIC_FORMAT),
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
                **({"authored_markdown": prepared.authored_markdown,
                    "key_bindings": node.frontmatter.get("key_bindings", {}),
                    "key_snapshot": prepared.key_snapshot} if prepared.addressed else {}),
                **({"template_source": template_source} if template_source is not None else {}),
                "artifacts": [_artifact_descriptor(pending), *[_artifact_descriptor(f.artifact) for f in files]],
                **({"managed_files": [f.descriptor for f in files]}
                   if files or shared_composition or prepared.addressed else {}),
                "entities": list(prepared.entities),
                "attachments": [
                    {key: f.descriptor[key] for key in ("id", "filename", "media_type", "size", "checksum")}
                    for f in files
                ],
                "placements": [],
                "diagrams": [],
                "key_resolutions": prepared.key_snapshot["records"] if prepared.key_snapshot is not None else [],
            }
            html = render_markdown(
                markdown, attachments=rendered_files,
                entity_mentions={item["id"]: item for item in prepared.entities},
            )
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
            for retained in (pending, *(f.artifact for f in files)):
                artifact_entity = Entity.objects.create(
                    id=retained.entity_id,
                    tenant_id=locked.tenant_id,
                    organization=workspace.organization,
                    workspace=owner,
                    entity_type="document_publication_artifact",
                    display_name=retained.filename,
                    visibility="msp_private",
                )
                artifact = DocumentPublicationArtifact(
                    id=retained.id,
                    tenant_id=locked.tenant_id,
                    organization=workspace.organization,
                    publication=publication,
                    entity=artifact_entity,
                    kind=retained.kind,
                    original_filename=retained.filename,
                    media_type=retained.media_type,
                    size=len(retained.content),
                    checksum=retained.checksum,
                    source_attachment=retained.source_attachment,
                    created_at=created_at,
                )
                # Track the opaque UUID path before writing: filesystem storage
                # may create bytes and then raise without returning a name.
                storage = artifact.file.storage
                intended_name = artifact.file.field.generate_filename(artifact, "retained")
                if storage.exists(intended_name):
                    raise PublicationConflict("Retained artifact storage identity already exists")
                stored.append((storage, intended_name))
                artifact.file.save("retained", ContentFile(retained.content), save=False)
                if artifact.file.name != intended_name:
                    stored.append((storage, artifact.file.name))
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
