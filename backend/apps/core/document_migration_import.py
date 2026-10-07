"""Guarded copy of one owned-placement legacy document into workspace Git."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace

from .content_index import ContentIndexError, index_repository_content, validate_candidate_snapshot
from .content_profile import parse_content
from .document_migration_export import (
    DocumentMigrationBindingError,
    DocumentMigrationExportError,
    DocumentMigrationFileError,
    DocumentMigrationReferenceError,
    DocumentMigrationTopicError,
    SimpleDocumentExport,
    build_simple_document_export,
)
from .document_migration_inventory import inventory_legacy_documents
from .document_migration_projection import portable_node_projection_matches, portable_root_entity_links_match
from .models import ContentInclude, ContentLink, ContentNode, Document, Workspace, WorkspaceRepository
from .repository_service import (
    RepositoryAuditAttribution,
    RepositoryConflictError,
    commit_repository_files,
    read_accepted_repository_markdown_files,
)


class DocumentMigrationBlocked(ValueError):
    def __init__(self, *codes: str) -> None:
        self.codes = tuple(sorted(set(codes)))
        super().__init__(", ".join(self.codes))


@dataclass(frozen=True, slots=True)
class PreparedDocumentImport:
    repository: WorkspaceRepository
    export: SimpleDocumentExport
    base_commit: str
    plan_sha256: str
    already_present: bool


@dataclass(frozen=True, slots=True)
class DocumentImportResult:
    status: str
    commit: str
    indexed: bool


def fingerprint_document_import(*, base_commit: str, export: SimpleDocumentExport) -> str:
    payload = {
        "base_commit": base_commit,
        "document_id": str(export.document_id),
        "blocks": [(str(block_id), str(revision_id)) for block_id, revision_id in export.blocks],
        "referenced_digests": [(str(content_id), digest) for content_id, digest in export.referenced_digests],
        "attachment_digests": [(str(entity_id), digest) for entity_id, digest in export.attachment_digests],
        "key_binding_ids": [
            (name, str(binding_id), str(target_id)) for name, binding_id, target_id in export.key_binding_ids
        ],
        "pinned_commits": [(str(content_id), commit) for content_id, commit in export.pinned_commits],
        "reference_commit": export.reference_commit,
        "files": [(path, hashlib.sha256(source).hexdigest()) for path, source in export.files],
        "resolved_entity_links": export.resolved_entity_links,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_document_import(*, workspace: Workspace, document_id: uuid.UUID) -> PreparedDocumentImport:
    inventory = inventory_legacy_documents(workspace)
    row = next((item for item in inventory["documents"] if item["document_id"] == str(document_id)), None)
    if row is None:
        raise DocumentMigrationBlocked("document_unavailable")
    reasons = set(row["reasons"])
    # A prior import is the only acceptable same-ID collision, verified by exact bytes below.
    reasons.discard("git_identity_collision")
    if reasons:
        raise DocumentMigrationBlocked(*reasons)
    repository = WorkspaceRepository.objects.filter(workspace=workspace).first()
    if repository is None:
        raise DocumentMigrationBlocked("repository_missing")
    document = Document.objects.select_related("entity").get(
        id=document_id, tenant_id=workspace.tenant_id, organization=workspace.organization
    )
    try:
        export = build_simple_document_export(document, verify_attachments=True)
    except (
        DocumentMigrationReferenceError,
        DocumentMigrationTopicError,
        DocumentMigrationFileError,
        DocumentMigrationBindingError,
    ) as exc:
        raise DocumentMigrationBlocked(exc.code) from exc
    if repository.accepted_commit_id is None:
        raise DocumentMigrationBlocked("repository_no_accepted_commit")
    accepted, current_files = read_accepted_repository_markdown_files(repository_id=repository.id)
    if export.reference_commit is not None and export.reference_commit != accepted.object_id:
        raise DocumentMigrationBlocked("repository_changed")
    current = dict(current_files)
    destinations = dict(export.files)
    existing = {path: current[path] for path in destinations if path in current}
    if existing and existing != destinations:
        raise DocumentMigrationBlocked("git_destination_conflict")
    if existing and set(existing) != set(destinations):
        raise DocumentMigrationBlocked("git_destination_conflict")
    already_present = bool(existing)
    if not already_present:
        blockers = inventory["repository_blockers"]
        if blockers:
            raise DocumentMigrationBlocked(*blockers)
        current.update(destinations)
        validate_candidate_snapshot(repository=repository, files=tuple(sorted(current.items())))
    return PreparedDocumentImport(
        repository=repository,
        export=export,
        base_commit=accepted.object_id,
        plan_sha256=fingerprint_document_import(base_commit=accepted.object_id, export=export),
        already_present=already_present,
    )


def _verify_projection(prepared: PreparedDocumentImport, commit: str) -> bool:
    repository = prepared.repository
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    if repository.accepted_commit is None or repository.accepted_commit.object_id != commit:
        return False
    if repository.indexed_commit_id != repository.accepted_commit_id:
        return False
    identities = (prepared.export.document_id, *(block_id for block_id, _revision_id in prepared.export.blocks))
    nodes = {
        node.content_id: node
        for node in ContentNode.objects.filter(repository=repository, content_id__in=identities).prefetch_related(
            "properties", "includes", "outgoing_links", "entity_links"
        )
    }
    if len(nodes) != len(identities):
        return False
    for path, source in prepared.export.files:
        parsed = parse_content(source)
        node = nodes.get(parsed.content_id)
        if not portable_node_projection_matches(
            node=node,
            parsed=parsed,
            path=path,
            indexed_commit_id=repository.indexed_commit_id,
            indexed_object_id=commit,
        ):
            return False
    root = nodes.get(prepared.export.document_id)
    if root is None or not portable_root_entity_links_match(root, prepared.export.resolved_entity_links):
        return False
    composition = root.composition_variants.get("all", {})
    if not isinstance(composition, dict):
        return False
    manifest = composition.get("manifest")
    if not isinstance(manifest, list):
        return False
    pinned = dict(prepared.export.pinned_commits)
    if any(
        not any(
            isinstance(item, dict)
            and item.get("id") == str(content_id)
            and item.get("digest") == digest
            and (content_id not in pinned or item.get("commit") == pinned[content_id])
            for item in manifest
        )
        for content_id, digest in prepared.export.referenced_digests
    ):
        return False
    return (
        hashlib.sha256(str(composition.get("markdown", "")).encode()).hexdigest()
        == prepared.export.resolved_markdown_sha256
    )


def apply_document_import(
    *, workspace: Workspace, document_id: uuid.UUID, expected_base: str, plan_sha256: str, actor_id: uuid.UUID
) -> DocumentImportResult:
    """Copy only; legacy remains authoritative until a later explicit cutover."""

    prepared = prepare_document_import(workspace=workspace, document_id=document_id)
    if prepared.already_present:
        commit = prepared.base_commit
        try:
            index_repository_content(repository_id=prepared.repository.id)
        except ContentIndexError:
            return DocumentImportResult("index_pending", commit, False)
        verified = _verify_projection(prepared, commit)
        return DocumentImportResult("already_present" if verified else "verification_pending", commit, verified)
    if expected_base != prepared.base_commit or plan_sha256 != prepared.plan_sha256:
        raise DocumentMigrationBlocked("preview_changed")
    try:
        committed = commit_repository_files(
            repository_id=prepared.repository.id,
            expected_base=expected_base,
            changes=dict(prepared.export.files),
            message=f"Import legacy document {document_id}",
            attribution=RepositoryAuditAttribution(actor_id=actor_id, action="content.migration_import"),
        )
    except RepositoryConflictError as exc:
        raise DocumentMigrationBlocked("repository_changed") from exc
    try:
        index_repository_content(repository_id=prepared.repository.id)
    except ContentIndexError:
        return DocumentImportResult("index_pending", committed.object_id, False)
    verified = _verify_projection(prepared, committed.object_id)
    current = Document.objects.select_related("entity").get(
        id=document_id, tenant_id=workspace.tenant_id, organization=workspace.organization
    )
    try:
        current_export = build_simple_document_export(current, verify_attachments=True)
    except DocumentMigrationExportError:
        return DocumentImportResult("source_changed", committed.object_id, verified)
    if current_export != replace(prepared.export, reference_commit=current_export.reference_commit):
        return DocumentImportResult("source_changed", committed.object_id, verified)
    return DocumentImportResult("imported" if verified else "verification_pending", committed.object_id, verified)


def rollback_document_import(
    *, workspace: Workspace, document_id: uuid.UUID, expected_commit: str, actor_id: uuid.UUID
) -> DocumentImportResult:
    """Remove only unchanged copied files, never a referenced source fragment."""

    prepared = prepare_document_import(workspace=workspace, document_id=document_id)
    if not prepared.already_present:
        raise DocumentMigrationBlocked("import_not_present")
    if prepared.base_commit != expected_commit:
        raise DocumentMigrationBlocked("repository_changed")
    repository = prepared.repository
    if repository.indexed_commit_id != repository.accepted_commit_id:
        raise DocumentMigrationBlocked("repository_index_not_current")
    identities = prepared.export.copied_content_ids
    if (
        ContentLink.objects.filter(workspace=workspace, target_content_id__in=identities)
        .exclude(source__content_id__in=identities)
        .exists()
        or ContentInclude.objects.filter(workspace=workspace, target_content_id__in=identities)
        .exclude(source__content_id__in=identities)
        .exists()
    ):
        raise DocumentMigrationBlocked("import_has_external_references")
    _accepted, current_files = read_accepted_repository_markdown_files(repository_id=repository.id)
    candidate = dict(current_files)
    for path, source in prepared.export.files:
        if candidate.get(path) != source:
            raise DocumentMigrationBlocked("git_destination_conflict")
        del candidate[path]
    validate_candidate_snapshot(repository=repository, files=tuple(sorted(candidate.items())))
    try:
        committed = commit_repository_files(
            repository_id=repository.id,
            expected_base=expected_commit,
            changes={path: None for path, _source in prepared.export.files},
            message=f"Rollback legacy document import {document_id}",
            attribution=RepositoryAuditAttribution(actor_id=actor_id, action="content.migration_rollback"),
        )
    except RepositoryConflictError as exc:
        raise DocumentMigrationBlocked("repository_changed") from exc
    try:
        index_repository_content(repository_id=repository.id)
    except ContentIndexError:
        return DocumentImportResult("index_pending", committed.object_id, False)
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    absent = not ContentNode.objects.filter(repository=repository, content_id__in=identities).exists()
    verified = repository.indexed_commit_id == repository.accepted_commit_id and absent
    return DocumentImportResult("rolled_back" if verified else "verification_pending", committed.object_id, verified)
