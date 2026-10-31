"""Exact Git-object dependencies for a future repository-backed STATIC publication.

This is an internal, value-free proof. It does not authorize a reader or change
the database-authored publication path; callers must perform workspace policy
checks and recheck the accepted head when a publication is retained.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from .content_index import (
    MAX_PINNED_HISTORY_BYTES,
    _parse_snapshot,
    _resolve_compositions,
)
from .content_index_models import ContentNode, ContentNodeKind
from .content_profile import ContentProfileError, ParsedContent, parse_content
from .models import RepositoryObjectFormat, WorkspaceRepository
from .repository_service import (
    MAX_PINNED_SNAPSHOT_BYTES,
    RepositoryServiceError,
    pin_accepted_repository_for_publication,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)


class ContentPublicationSourceError(RuntimeError):
    """A repository document cannot be frozen into exact source evidence."""


def _blob_id(source: bytes, object_format: str) -> str:
    header = f"blob {len(source)}\0".encode("ascii")
    if object_format == RepositoryObjectFormat.SHA1:
        return hashlib.sha1(header + source, usedforsecurity=False).hexdigest()  # noqa: S324 -- Git blob identity
    if object_format == RepositoryObjectFormat.SHA256:
        return hashlib.sha256(header + source).hexdigest()
    raise ContentPublicationSourceError("Repository object format is unsupported")


def _sources_by_id(
    files: tuple[tuple[str, bytes], ...], *, historical: bool
) -> dict[uuid.UUID, tuple[str, bytes, ParsedContent]]:
    sources: dict[uuid.UUID, tuple[str, bytes, ParsedContent]] = {}
    for path, source in files:
        try:
            parsed = parse_content(source)
        except ContentProfileError as exc:
            raise ContentPublicationSourceError("Repository source does not satisfy the content profile") from exc
        if (parsed.kind == ContentNodeKind.FRAGMENT) != path.startswith("fragments/"):
            raise ContentPublicationSourceError("Repository source has invalid content placement")
        if parsed.content_id in sources:
            raise ContentPublicationSourceError("Repository source identity is ambiguous")
        sources[parsed.content_id] = (path, source, parsed)
    if historical and sum(len(source) for _path, source in files) > MAX_PINNED_SNAPSHOT_BYTES:
        raise ContentPublicationSourceError("Pinned repository snapshot exceeds its size limit")
    return sources


def _source_record(
    *,
    content_id: uuid.UUID,
    commit: str,
    source: tuple[str, bytes, ParsedContent],
    object_format: str,
    audience: str,
    mode: str,
    ordinal_path: list[int],
) -> dict[str, Any]:
    path, content, parsed = source
    return {
        "id": str(content_id),
        "commit": commit,
        "path": path,
        "blob": _blob_id(content, object_format),
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "content_digest": parsed.content_digest,
        "audience": audience,
        "mode": mode,
        "ordinal_path": ordinal_path,
    }


def freeze_git_document_dependencies(
    *, repository_id: uuid.UUID, content_id: uuid.UUID, audience: str
) -> dict[str, Any]:
    """Return deterministic root-and-include evidence at one accepted head.

    The caller must already be authorized for this workspace and audience. The
    accepted/indexed identity is checked before and after Git reads; publication
    retention must perform its own atomic accepted-head comparison.
    """

    if audience not in {"msp_internal", "client_visible"}:
        raise ContentPublicationSourceError("Publication audience is unsupported")
    repository = WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").get(
        pk=repository_id
    )
    if repository.accepted_commit_id is None or repository.indexed_commit_id != repository.accepted_commit_id:
        raise ContentPublicationSourceError("Repository index is not current with its accepted commit")
    accepted = repository.accepted_commit
    if accepted is None:  # pragma: no cover - guarded above
        raise ContentPublicationSourceError("Repository has no accepted commit")
    node = ContentNode.objects.filter(repository=repository, content_id=content_id).first()
    if node is None or node.kind != ContentNodeKind.DOCUMENT or node.indexed_commit_id != accepted.id:
        raise ContentPublicationSourceError("Indexed repository document is unavailable")
    try:
        read_commit, files = read_accepted_repository_markdown_files(repository_id=repository.id)
        if read_commit.id != accepted.id or sum(len(source) for _path, source in files) > MAX_PINNED_SNAPSHOT_BYTES:
            raise ContentPublicationSourceError("Accepted repository snapshot changed or exceeds its size limit")
        parsed_by_path, diagnostics = _parse_snapshot(repository=repository, files=files)
        if diagnostics:
            raise ContentPublicationSourceError("Accepted repository content failed validation")
        variants, _direct, _templates, diagnostics = _resolve_compositions(
            repository=repository,
            accepted_object_id=accepted.object_id,
            parsed_by_path=parsed_by_path,
        )
        if diagnostics:
            raise ContentPublicationSourceError("Accepted repository composition failed validation")
        accepted_sources = _sources_by_id(files, historical=False)
        root = accepted_sources.get(content_id)
        if root is None or root[2].kind != ContentNodeKind.DOCUMENT:
            raise ContentPublicationSourceError("Accepted repository document is unavailable")
        if (node.source_path, node.content_digest) != (root[0], root[2].content_digest):
            raise ContentPublicationSourceError("Indexed repository document differs from its accepted source")
        if (
            node.title != root[2].title
            or node.topic_type != root[2].topic_type
            or node.frontmatter != root[2].frontmatter
        ):
            raise ContentPublicationSourceError("Indexed repository metadata differs from its accepted source")
        variant = variants[content_id][audience]
        if node.composition_variants.get(audience) != variant:
            raise ContentPublicationSourceError("Indexed repository composition differs from its accepted source")

        evidence = [
            _source_record(
                content_id=content_id,
                commit=accepted.object_id,
                source=root,
                object_format=accepted.object_format,
                audience=audience,
                mode="root",
                ordinal_path=[],
            )
        ]
        historical_sources: dict[str, dict[uuid.UUID, tuple[str, bytes, ParsedContent]]] = {}
        history_bytes = 0
        for include in variant["manifest"]:
            include_commit = str(include["commit"])
            include_id = uuid.UUID(str(include["id"]))
            if "workspace" in include:
                evidence.append(_library_source_record(
                    repository=repository, document_id=content_id, include=include,
                ))
                continue
            if include_commit == accepted.object_id:
                sources = accepted_sources
            else:
                if include_commit not in historical_sources:
                    pinned_commit, pinned_files = read_repository_markdown_files_at_commit(
                        repository_id=repository.id, object_id=include_commit
                    )
                    if pinned_commit.object_format != accepted.object_format:
                        raise ContentPublicationSourceError("Pinned source object format differs from its repository")
                    history_bytes += sum(len(source) for _path, source in pinned_files)
                    if history_bytes > MAX_PINNED_HISTORY_BYTES:
                        raise ContentPublicationSourceError("Pinned content history exceeds its size limit")
                    historical_sources[include_commit] = _sources_by_id(pinned_files, historical=True)
                sources = historical_sources[include_commit]
            source = sources.get(include_id)
            if (
                source is None
                or source[2].kind != ContentNodeKind.FRAGMENT
                or source[2].content_digest != include["digest"]
            ):
                raise ContentPublicationSourceError("Included repository source differs from its accepted composition")
            evidence.append(
                _source_record(
                    content_id=include_id,
                    commit=include_commit,
                    source=source,
                    object_format=accepted.object_format,
                    audience=str(include["audience"]),
                    mode=str(include["mode"]),
                    ordinal_path=list(include["ordinal_path"]),
                )
            )
        repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
        if repository.accepted_commit_id != accepted.id or repository.indexed_commit_id != accepted.id:
            raise ContentPublicationSourceError("Repository accepted head changed during source freeze")
    except RepositoryServiceError as exc:
        raise ContentPublicationSourceError("Repository source objects are unavailable") from exc
    return {
        "format": ("tekdocs.git-dependencies/v2" if any(s.get("library_workspace") for s in evidence)
                   else "tekdocs.git-dependencies/v1"),
        "repository_id": str(repository.id),
        "workspace_id": str(repository.workspace_id),
        "content_id": str(content_id),
        "root_title": root[2].title,
        "audience": audience,
        "object_format": accepted.object_format,
        "accepted_commit": accepted.object_id,
        "composition_digest": variant["digest"],
        "markdown_sha256": hashlib.sha256(str(variant["markdown"]).encode("utf-8")).hexdigest(),
        "sources": evidence,
    }


@contextmanager
def pinned_git_document_dependencies(
    *, repository_id: uuid.UUID, content_id: uuid.UUID, audience: str
) -> Iterator[dict[str, Any]]:
    """Yield source proof while the accepted Git head and DB row are pinned.

    A repository-backed publisher must sign and insert its append-only record
    before this context exits. This does not authorize the caller or create a
    publication by itself.
    """

    try:
        # Foreign source heads and the client head remain fixed until signing.
        # Discover only the actual approved enrollment, never arbitrary includes.
        with ExitStack() as pins:
            locked_repositories = {
                identity: pins.enter_context(pin_accepted_repository_for_publication(identity))
                for identity in _publication_repository_ids(repository_id=repository_id, content_id=content_id)
            }
            locked = locked_repositories[repository_id]
            proof = freeze_git_document_dependencies(
                repository_id=repository_id, content_id=content_id, audience=audience
            )
            if locked.accepted_commit is None or proof["accepted_commit"] != locked.accepted_commit.object_id:
                raise ContentPublicationSourceError("Repository accepted head changed during publication")
            yield proof
    except RepositoryServiceError as exc:
        raise ContentPublicationSourceError("Repository source cannot be pinned for publication") from exc



def _publication_repository_ids(*, repository_id: uuid.UUID, content_id: uuid.UUID) -> tuple[uuid.UUID, ...]:
    from .document_template_migration import TemplateMigrationError, template_enrollment_evidence
    from .models import Document

    repository = WorkspaceRepository.objects.get(pk=repository_id)
    document = Document.objects.filter(
        tenant_id=repository.tenant_id, entity__workspace_id=repository.workspace_id,
        organization=repository.workspace.organization, pk=content_id,
    ).first()
    identities = {repository_id}
    if document is not None:
        try:
            enrollment = template_enrollment_evidence(document)
        except TemplateMigrationError as exc:
            raise ContentPublicationSourceError("Template enrollment source proof is unavailable") from exc
        if enrollment is not None and enrollment.library_placement_ids:
            source = Document.objects.get(tenant_id=document.tenant_id, pk=enrollment.source_document_id)
            identities.add(WorkspaceRepository.objects.get(
                tenant_id=repository.tenant_id, workspace_id=source.entity.workspace_id,
            ).id)
    return tuple(sorted(identities))


def _library_source_record(*, repository: WorkspaceRepository, document_id: uuid.UUID,
                           include: dict[str, Any]) -> dict[str, Any]:
    from django.db import transaction

    from .content_profile import ParsedInclude
    from .document_template_models import DocumentTemplateRevision
    from .models import DocumentPlacement
    from .repository_service import read_template_library_fragment
    from .template_library_content import template_library_loader

    workspace_id, revision_id = uuid.UUID(include["workspace"]), uuid.UUID(include["template_revision"])
    source_repository = WorkspaceRepository.objects.select_related("accepted_commit").get(
        tenant_id=repository.tenant_id, workspace_id=workspace_id,
    )
    selected_include = ParsedInclude(
        target_content_id=uuid.UUID(include["id"]), mode=include["mode"], audience=include["audience"],
        pinned_object_id=include["commit"] if include["mode"] == "pinned" else "",
        ordinal=include["ordinal_path"][-1], library_workspace_id=workspace_id, library_revision_id=revision_id,
    )
    with transaction.atomic():
        selected = read_template_library_fragment(
            destination_document_id=document_id, library_workspace_id=workspace_id,
            source_block_id=selected_include.target_content_id, mode=selected_include.mode,
            pinned_object_id=selected_include.pinned_object_id, template_revision_id=revision_id,
            audience=selected_include.audience,
        )
        placement = DocumentPlacement.objects.select_related("parent").get(
            tenant_id=repository.tenant_id, document_id=document_id,
            block_id=selected_include.target_content_id, resolution_mode=selected_include.mode,
            audience_profile=selected_include.audience,
        )
        parent_content_id = placement.parent.block_id if placement.parent is not None else document_id
        object_id, parsed = template_library_loader(repository)(parent_content_id, selected_include)
    if object_id != include["commit"] or parsed.content_digest != include["digest"]:
        raise ContentPublicationSourceError("Template library source changed during publication")
    if source_repository.accepted_commit is None:
        raise ContentPublicationSourceError("Template library repository is unavailable")
    record = _source_record(
        content_id=parsed.content_id, commit=selected.object_id,
        source=(selected.source_path, selected.source, parsed),
        object_format=source_repository.accepted_commit.object_format, audience=include["audience"],
        mode=include["mode"], ordinal_path=include["ordinal_path"],
    )
    record.update({
        "library_workspace": str(workspace_id), "repository_id": str(source_repository.id),
        "object_format": source_repository.accepted_commit.object_format,
        "accepted_commit": source_repository.accepted_commit.object_id,
        "template_revision": str(revision_id),
        "template_checksum": DocumentTemplateRevision.objects.get(
            tenant_id=repository.tenant_id, pk=revision_id,
        ).checksum,
        "body_only": True,
    })
    return record
