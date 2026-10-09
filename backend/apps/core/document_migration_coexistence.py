"""Read-only dual-store status; never decides document authority."""

from __future__ import annotations

import hashlib

from django.http import Http404

from .content_profile import ContentProfileError, parse_content
from .content_read import document_detail
from .document_attachments import resolve_rendered_attachments
from .document_key_freeze import expand_rendered_content_keys
from .document_key_resolution import resolve_rendered_keys
from .document_migration_attachments import DocumentMigrationAttachmentError, portable_document_attachments
from .document_migration_export import (
    DocumentMigrationBindingError,
    DocumentMigrationExportError,
    DocumentMigrationFileError,
    DocumentMigrationReferenceError,
    build_simple_document_export,
)
from .document_migration_projection import portable_node_projection_matches, portable_root_entity_links_match
from .document_migration_relationships import (
    DocumentMigrationRelationshipError,
    portable_document_entity_references,
)
from .documents import PlacementConflict, resolve_document
from .entity_mentions import resolve_entity_mentions
from .models import ContentNode, Document, Workspace, WorkspaceRepository
from .relationships import visible_entities_for_workspace
from .rendering import render_markdown
from .repository_service import RepositoryServiceError, read_accepted_repository_file
from .workspaces import ResolvedWorkspace


def _visible_legacy_references(*, document: Document, reader_workspace: ResolvedWorkspace) -> set[tuple[str, str]]:
    references = portable_document_entity_references(document)
    ids = {item["id"] for item in references}
    if not ids:
        return set()
    visible_ids = {
        str(entity_id)
        for entity_id in visible_entities_for_workspace(
            workspace=reader_workspace, include_reference_organizations=True
        )
        .filter(id__in=ids)
        .values_list("id", flat=True)
    }
    return {(item["id"], item["relationship"]) for item in references if item["id"] in visible_ids}


def _render_legacy_document(*, document: Document, reader_workspace: ResolvedWorkspace, markdown: str) -> str:
    """Use the legacy reader's key, attachment, and entity rendering inputs."""

    expanded = expand_rendered_content_keys(workspace=reader_workspace, document=document, markdown=markdown)
    return render_markdown(
        expanded,
        entity_mentions=resolve_entity_mentions(workspace=reader_workspace, markdown=expanded),
        attachments=resolve_rendered_attachments(workspace=reader_workspace, document=document, markdown=expanded),
        key_resolutions=resolve_rendered_keys(workspace=reader_workspace, document=document, markdown=expanded),
    )


def document_coexistence_status(
    *, workspace: Workspace, document: Document, reader_workspace: ResolvedWorkspace
) -> dict[str, object]:
    """Report copy parity and the still-unmet authority handoff gates."""

    response = _document_copy_status(workspace=workspace, document=document)
    response["read_projection_state"] = "not_checked"
    if response["content_copy_state"] == "in_sync":
        try:
            repository_read = document_detail(
                workspace=reader_workspace, content_id=document.id, audience="msp_internal"
            )
            legacy_markdown = resolve_document(document).markdown
            legacy_references = _visible_legacy_references(document=document, reader_workspace=reader_workspace)
            legacy_html = _render_legacy_document(
                document=document, reader_workspace=reader_workspace, markdown=legacy_markdown
            )
        except (Http404, WorkspaceRepository.DoesNotExist, PlacementConflict, DocumentMigrationRelationshipError):
            response["read_projection_state"] = "unavailable"
        else:
            repository_references = {
                (str(item["id"]), str(item["relationship"]))
                for item in repository_read["entity_context"]
                if item["origin"] == "typed"
            }
            response["read_projection_state"] = (
                "matched"
                if repository_read["title"] == document.entity.display_name
                and repository_read["markdown"] == legacy_markdown
                and repository_read["sanitized_html"] == legacy_html
                and repository_references == legacy_references
                else "different"
            )
    blockers = []
    if response["content_copy_state"] != "in_sync":
        blockers.append("content_copy_not_in_sync")
    if response["read_projection_state"] in ("different", "unavailable"):
        blockers.append("repository_read_projection_not_matched")
    blockers.extend(
        (
            "repository_document_reads_not_authoritative",
            "repository_document_writes_not_authoritative",
            "publication_parity_not_verified",
        )
    )
    response["handoff_blockers"] = blockers
    return response


def _document_copy_status(*, workspace: Workspace, document: Document) -> dict[str, object]:
    """Compare a supported legacy shape to its indexed same-commit copy."""

    if document.tenant_id != workspace.tenant_id or document.organization_id != workspace.organization_id:
        raise ValueError("Document does not belong to the selected workspace")
    response: dict[str, object] = {
        "document_id": str(document.id),
        "legacy_authoritative": True,
        "cutover_ready": False,
        "content_copy_state": "legacy_only",
        "accepted_commit": None,
        "indexed_commit": None,
        "legacy_revision_id": None,
        "legacy_revision_ids": [],
    }
    repository = (
        WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit")
        .filter(workspace=workspace)
        .first()
    )
    if repository is None:
        response["content_copy_state"] = "repository_missing"
        return response
    response["accepted_commit"] = repository.accepted_commit.object_id if repository.accepted_commit else None
    response["indexed_commit"] = repository.indexed_commit.object_id if repository.indexed_commit else None
    if repository.accepted_commit_id != repository.indexed_commit_id:
        response["content_copy_state"] = "index_pending"
        return response
    try:
        export = build_simple_document_export(document)
        expected = {path: parse_content(source) for path, source in export.files}
    except DocumentMigrationReferenceError as exc:
        response["content_copy_state"] = (
            "diverged" if exc.code == "cross_document_source_drift" else "unsupported_legacy_shape"
        )
        return response
    except (DocumentMigrationBindingError, DocumentMigrationFileError):
        response["content_copy_state"] = (
            "diverged"
            if ContentNode.objects.filter(repository=repository, content_id=document.id).exists()
            else "unsupported_legacy_shape"
        )
        return response
    except (ContentProfileError, DocumentMigrationExportError, ValueError):
        response["content_copy_state"] = "unsupported_legacy_shape"
        return response
    if export.reference_commit is not None and export.reference_commit != response["accepted_commit"]:
        response["content_copy_state"] = "diverged"
        return response
    response["legacy_revision_id"] = str(export.revision_id)
    response["legacy_revision_ids"] = [str(revision_id) for _block_id, revision_id in export.blocks]
    identities = (export.document_id, *(block_id for block_id, _revision_id in export.blocks))
    nodes = {
        node.content_id: node
        for node in ContentNode.objects.filter(repository=repository, content_id__in=identities).prefetch_related(
            "properties", "includes", "outgoing_links", "entity_links"
        )
    }
    if not any(content_id in nodes for content_id in export.copied_content_ids):
        return response
    if len(nodes) != len(identities):
        response["content_copy_state"] = "partial_copy"
        return response
    for path, parsed in expected.items():
        node = nodes.get(parsed.content_id)
        if not portable_node_projection_matches(
            node=node,
            parsed=parsed,
            path=path,
            indexed_commit_id=repository.indexed_commit_id,
            indexed_object_id=str(response["indexed_commit"]),
        ):
            response["content_copy_state"] = "diverged"
            return response
    root = nodes[export.document_id]
    if not portable_root_entity_links_match(root, export.resolved_entity_links):
        response["content_copy_state"] = "diverged"
        return response
    composition = root.composition_variants.get("all")
    markdown = composition.get("markdown") if isinstance(composition, dict) else None
    manifest = composition.get("manifest") if isinstance(composition, dict) else None
    pinned = dict(export.pinned_commits)
    if not isinstance(manifest, list) or any(
        not any(
            isinstance(item, dict)
            and item.get("id") == str(content_id)
            and item.get("digest") == digest
            and (content_id not in pinned or item.get("commit") == pinned[content_id])
            for item in manifest
        )
        for content_id, digest in export.referenced_digests
    ):
        response["content_copy_state"] = "diverged"
        return response
    if (
        not isinstance(markdown, str)
        or hashlib.sha256(markdown.encode()).hexdigest() != export.resolved_markdown_sha256
    ):
        response["content_copy_state"] = "diverged"
        return response
    try:
        attachment_digests = portable_document_attachments(document, markdown, verify_content=True)
    except DocumentMigrationAttachmentError:
        response["content_copy_state"] = "diverged"
        return response
    if attachment_digests != export.attachment_digests:
        response["content_copy_state"] = "diverged"
        return response
    try:
        if any(
            read_accepted_repository_file(repository_id=repository.id, path=path) != source
            for path, source in export.files
        ):
            response["content_copy_state"] = "diverged"
            return response
    except RepositoryServiceError:
        response["content_copy_state"] = "diverged"
        return response
    response["content_copy_state"] = "in_sync"
    return response
