"""Deterministic owned-placement export plan; this module never commits Git."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import yaml

from .content_composition import ContentCompositionResolver
from .content_index_models import ContentNodeKind
from .content_profile import CONTENT_SCHEMA, ContentProfileError, ParsedContent, parse_content
from .document_migration_attachments import DocumentMigrationAttachmentError, portable_document_attachments
from .document_migration_keys import DocumentMigrationKeyError, portable_document_keys
from .document_migration_relationships import (
    DocumentMigrationRelationshipError,
    portable_document_entity_references,
)
from .document_migration_shape import DocumentMigrationShapeError, owned_placement_tree
from .document_migration_taxonomy import DocumentMigrationTaxonomyError, portable_document_taxonomies
from .documents import resolve_document
from .models import (
    ContentNode,
    Document,
    DocumentPlacement,
    PlacementResolutionMode,
    WorkspaceRepository,
)
from .repository_service import (
    RepositoryServiceError,
    list_accepted_repository_history,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)
from .topic_schemas import SCHEMA_VERSION, SCHEMAS, inspect_markdown


class DocumentMigrationExportError(ValueError):
    pass


class DocumentMigrationReferenceError(DocumentMigrationExportError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DocumentMigrationTopicError(DocumentMigrationExportError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DocumentMigrationFileError(DocumentMigrationExportError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DocumentMigrationBindingError(DocumentMigrationExportError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


MAX_MIGRATION_PIN_HISTORY_COMMITS = 32
MAX_MIGRATION_PIN_HISTORY_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SimpleDocumentExport:
    document_id: uuid.UUID
    blocks: tuple[tuple[uuid.UUID, uuid.UUID], ...]
    referenced_digests: tuple[tuple[uuid.UUID, str], ...]
    attachment_digests: tuple[tuple[uuid.UUID, str], ...]
    key_binding_ids: tuple[tuple[str, uuid.UUID, uuid.UUID], ...]
    pinned_commits: tuple[tuple[uuid.UUID, str], ...]
    reference_commit: str | None
    files: tuple[tuple[str, bytes], ...]
    resolved_markdown_sha256: str
    resolved_entity_links: tuple[tuple[str, str, str], ...]

    @property
    def block_id(self) -> uuid.UUID:
        return self.blocks[0][0]

    @property
    def revision_id(self) -> uuid.UUID:
        return self.blocks[0][1]

    @property
    def copied_content_ids(self) -> tuple[uuid.UUID, ...]:
        referenced_ids = {content_id for content_id, _digest in self.referenced_digests}
        return (
            self.document_id,
            *(block_id for block_id, _revision_id in self.blocks if block_id not in referenced_ids),
        )


def _source(frontmatter: dict[str, object], markdown: str) -> bytes:
    encoded = ("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + markdown).encode(
        "utf-8"
    )
    parse_content(encoded)
    return encoded


def _include_source(placement: DocumentPlacement, pinned_commits: dict[uuid.UUID, str]) -> dict[str, str]:
    source = {"id": str(placement.block_id), "mode": "live", "audience": "shared"}
    if placement.resolution_mode == PlacementResolutionMode.PINNED:
        source.update({"mode": "pinned", "commit": pinned_commits[placement.block_id]})
    return source


def _linked_historical_leaf(
    snapshot: dict[uuid.UUID, ParsedContent], *, source_document_id: uuid.UUID, block_id: uuid.UUID
) -> ParsedContent | None:
    """Require the selected old fragment to be reachable through live source includes."""

    root = snapshot.get(source_document_id)
    leaf = snapshot.get(block_id)
    if root is None or root.kind != ContentNodeKind.DOCUMENT or leaf is None:
        return None
    if leaf.kind != ContentNodeKind.FRAGMENT or leaf.includes:
        return None
    visited: set[uuid.UUID] = set()
    pending = [root]
    while pending:
        parent = pending.pop()
        if parent.content_id in visited:
            continue
        visited.add(parent.content_id)
        for include in parent.includes:
            if include.mode != "live":
                continue
            if include.target_content_id == block_id:
                return leaf
            child = snapshot.get(include.target_content_id)
            if child is not None and child.kind == ContentNodeKind.FRAGMENT:
                pending.append(child)
    return None


def _existing_references(
    document: Document, placements: tuple[DocumentPlacement, ...]
) -> tuple[str | None, dict[uuid.UUID, ParsedContent], dict[uuid.UUID, str]]:
    """Require exact, indexed, same-workspace leaf sources; never copy them."""

    references = tuple(placement for placement in placements if placement.block.source_document_id != document.id)
    if not references:
        return None, {}, {}
    repository = (
        WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit")
        .filter(workspace__tenant_id=document.tenant_id, workspace__organization=document.organization)
        .first()
    )
    if (
        repository is None
        or repository.accepted_commit_id is None
        or repository.accepted_commit_id != repository.indexed_commit_id
    ):
        raise DocumentMigrationReferenceError("cross_document_source_unavailable")
    _accepted, files = read_accepted_repository_markdown_files(repository_id=repository.id)
    current_files = dict(files)
    accepted_commit = repository.accepted_commit
    if accepted_commit is None:
        raise DocumentMigrationReferenceError("cross_document_source_unavailable")
    accepted_object_id = accepted_commit.object_id
    prior_root = current_files.get(f"docs/{document.id}.md")
    prior_files: dict[uuid.UUID, ParsedContent] = {}
    if prior_root is not None:
        for path in (f"docs/{document.id}.md", *(f"fragments/{item.block_id}.md" for item in placements)):
            source = current_files.get(path)
            if source is not None:
                parsed_owner = parse_content(source)
                prior_files[parsed_owner.content_id] = parsed_owner
    retained_snapshots: dict[str, dict[uuid.UUID, ParsedContent]] = {}
    history: tuple[str, ...] | None = None
    loaded_history_bytes = 0

    def load_retained(commit: str) -> dict[uuid.UUID, ParsedContent]:
        nonlocal loaded_history_bytes
        if commit in retained_snapshots:
            return retained_snapshots[commit]
        if len(retained_snapshots) >= MAX_MIGRATION_PIN_HISTORY_COMMITS:
            raise DocumentMigrationReferenceError("pinned_history_limit_exceeded")
        try:
            _commit, historical_files = read_repository_markdown_files_at_commit(
                repository_id=repository.id, object_id=commit
            )
        except RepositoryServiceError as exc:
            raise DocumentMigrationReferenceError("pinned_source_snapshot_required") from exc
        loaded_history_bytes += sum(len(body) for _path, body in historical_files)
        if loaded_history_bytes > MAX_MIGRATION_PIN_HISTORY_BYTES:
            raise DocumentMigrationReferenceError("pinned_history_limit_exceeded")
        snapshot: dict[uuid.UUID, ParsedContent] = {}
        try:
            for path, body in historical_files:
                item = parse_content(body)
                if item.content_id in snapshot or (item.kind == ContentNodeKind.FRAGMENT) != path.startswith(
                    "fragments/"
                ):
                    raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
                snapshot[item.content_id] = item
        except ContentProfileError as exc:
            raise DocumentMigrationReferenceError("pinned_source_snapshot_required") from exc
        retained_snapshots[commit] = snapshot
        return snapshot

    ids = {placement.block_id for placement in references}
    roots = {placement.block.source_document_id for placement in references}
    if None in roots:
        raise DocumentMigrationReferenceError("cross_document_source_unavailable")
    root_ids = {source_id for source_id in roots if source_id is not None}
    nodes = {
        node.content_id: node
        for node in ContentNode.objects.filter(repository=repository, content_id__in=ids | root_ids)
    }
    if any(nodes.get(root_id) is None or nodes[root_id].kind != ContentNodeKind.DOCUMENT for root_id in root_ids):
        raise DocumentMigrationReferenceError("cross_document_source_unavailable")
    parsed_references: dict[uuid.UUID, ParsedContent] = {}
    pinned_commits: dict[uuid.UUID, str] = {}
    for placement in references:
        source_document_id = placement.block.source_document_id
        if source_document_id is None:
            raise DocumentMigrationReferenceError("cross_document_source_unavailable")
        node = nodes.get(placement.block_id)
        if node is None or node.kind != ContentNodeKind.FRAGMENT:
            raise DocumentMigrationReferenceError("cross_document_source_unavailable")
        root = nodes[source_document_id]
        composition = root.composition_variants.get("all")
        manifest = composition.get("manifest") if isinstance(composition, dict) else None
        if not isinstance(manifest, list) or not any(
            isinstance(item, dict) and item.get("id") == str(placement.block_id) for item in manifest
        ):
            raise DocumentMigrationReferenceError("cross_document_source_unlinked")
        source = current_files.get(node.source_path)
        if source is None:
            raise DocumentMigrationReferenceError("cross_document_source_unavailable")
        current = parse_content(source)
        revision = (
            placement.block.current_revision
            if placement.resolution_mode == PlacementResolutionMode.LIVE
            else placement.pinned_revision
        )
        pinned_commit = ""
        parsed = current
        if placement.resolution_mode == PlacementResolutionMode.PINNED:
            parent = placement.parent
            if placement.parent_id is not None and parent is None:
                raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
            parent_id = document.id if parent is None else parent.block_id
            prior_parent = prior_files.get(parent_id)
            if prior_root is not None:
                prior = (
                    next(
                        (item for item in prior_parent.includes if item.target_content_id == placement.block_id),
                        None,
                    )
                    if prior_parent is not None
                    else None
                )
                if prior is None or prior.mode != "pinned":
                    raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
                pinned_commit = prior.pinned_object_id
            else:
                if revision is None:
                    raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
                if current.markdown == revision.markdown and not current.includes:
                    pinned_commit = accepted_object_id
                else:
                    if history is None:
                        try:
                            history = list_accepted_repository_history(
                                repository_id=repository.id, limit=MAX_MIGRATION_PIN_HISTORY_COMMITS
                            )
                        except RepositoryServiceError as exc:
                            raise DocumentMigrationReferenceError("pinned_source_snapshot_required") from exc
                        if history[0] != accepted_object_id:
                            raise DocumentMigrationReferenceError("repository_changed")
                    for candidate_commit in history[1:]:
                        candidate = _linked_historical_leaf(
                            load_retained(candidate_commit),
                            source_document_id=source_document_id,
                            block_id=placement.block_id,
                        )
                        if candidate is not None and candidate.markdown == revision.markdown:
                            pinned_commit = candidate_commit
                            break
                    if not pinned_commit:
                        raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
            if pinned_commit != accepted_object_id:
                historical = _linked_historical_leaf(
                    load_retained(pinned_commit),
                    source_document_id=source_document_id,
                    block_id=placement.block_id,
                )
                if historical is None:
                    raise DocumentMigrationReferenceError("pinned_source_snapshot_required")
                parsed = historical
            pinned_commits[placement.block_id] = pinned_commit
        if (
            parsed.content_id != placement.block_id
            or parsed.kind != ContentNodeKind.FRAGMENT
            or parsed.includes
            or (pinned_commit == accepted_object_id or not pinned_commit)
            and parsed.content_digest != node.content_digest
            or revision is None
            or parsed.markdown != revision.markdown
        ):
            raise DocumentMigrationReferenceError(
                "pinned_source_snapshot_required" if pinned_commit else "cross_document_source_drift"
            )
        parsed_references[placement.block_id] = parsed
    return accepted_object_id, parsed_references, pinned_commits


def build_simple_document_export(document: Document, *, verify_attachments: bool = False) -> SimpleDocumentExport:
    """Produce stable source bytes while proving exact legacy/rendered parity."""

    placements = list(
        DocumentPlacement.objects.filter(document=document).select_related(
            "block__entity", "block__current_revision", "pinned_revision"
        )
    )
    if (
        document.archived_at is not None
        or document.is_template
        or document.topic_type not in SCHEMAS
        or document.topic_schema_version != SCHEMA_VERSION
    ):
        raise DocumentMigrationExportError("Document is not a supported first-wave candidate")
    try:
        tree = owned_placement_tree(document, placements)
    except DocumentMigrationShapeError as exc:
        raise DocumentMigrationExportError(exc.reason) from exc
    reference_commit, referenced, pinned_commits = _existing_references(document, tree.ordered)
    try:
        taxonomies = portable_document_taxonomies(document)
    except DocumentMigrationTaxonomyError as exc:
        raise DocumentMigrationExportError("taxonomy_mapping_required") from exc
    try:
        entity_links = portable_document_entity_references(document)
    except DocumentMigrationRelationshipError as exc:
        raise DocumentMigrationExportError("relationship_mapping_required") from exc
    legacy = resolve_document(document).markdown
    try:
        key_bindings, key_binding_ids = portable_document_keys(document, legacy)
    except DocumentMigrationKeyError as exc:
        raise DocumentMigrationBindingError(exc.code) from exc
    title = document.entity.display_name
    properties = {
        "category": str(document.category),
        "collection": document.collection,
        "tags": document.tags,
    }
    fragments: list[tuple[str, bytes]] = []
    blocks: list[tuple[uuid.UUID, uuid.UUID]] = []
    for index, placement in enumerate(tree.ordered):
        block = placement.block
        revision = (
            block.current_revision
            if placement.resolution_mode == PlacementResolutionMode.LIVE
            else placement.pinned_revision
        )
        if revision is None:  # pragma: no cover - shape validation already checked this
            raise DocumentMigrationExportError("Document has an unsupported placement")
        blocks.append((block.id, revision.id))
        if block.source_document_id != document.id:
            continue
        frontmatter: dict[str, object] = {
            "schema": CONTENT_SCHEMA,
            "id": str(block.id),
            "kind": "fragment",
            "title": title if index == 0 else block.entity.display_name,
        }
        child_placements = tree.children.get(placement.id, ())
        if child_placements:
            frontmatter["includes"] = [_include_source(child, pinned_commits) for child in child_placements]
        fragment = _source(
            frontmatter,
            revision.markdown,
        )
        fragments.append((f"fragments/{block.id}.md", fragment))
    root = _source(
        {
            "schema": CONTENT_SCHEMA,
            "id": str(document.id),
            "kind": "document",
            "title": title,
            "topic": {"type": str(document.topic_type), "version": document.topic_schema_version},
            "properties": properties,
            **({"taxonomies": taxonomies} if taxonomies else {}),
            **({"entity_links": entity_links} if entity_links else {}),
            **({"key_bindings": key_bindings} if key_bindings else {}),
            "includes": [_include_source(placement, pinned_commits) for placement in tree.children[None]],
        },
        "",
    )
    files = ((f"docs/{document.id}.md", root), *fragments)
    parsed = dict(referenced)
    for _path, source in files:
        content = parse_content(source)
        parsed[content.content_id] = content
    resolved = ContentCompositionResolver(
        accepted_object_id="migration:preview",
        accepted=parsed,
        loader=lambda object_id: (
            {
                content_id: content
                for content_id, content in referenced.items()
                if pinned_commits.get(content_id) == object_id
            }
        ),
    ).resolve(content_id=document.id, audience=None)
    if resolved.markdown != legacy:
        raise DocumentMigrationExportError("Legacy and repository composition do not match")
    try:
        attachment_digests = portable_document_attachments(document, legacy, verify_content=verify_attachments)
    except DocumentMigrationAttachmentError as exc:
        raise DocumentMigrationFileError(exc.code) from exc
    if any(finding["severity"] == "blocker" for finding in inspect_markdown(document.topic_type, resolved.markdown)):
        raise DocumentMigrationTopicError("structured_topic_sections_required")
    return SimpleDocumentExport(
        document_id=document.id,
        blocks=tuple(blocks),
        referenced_digests=tuple(
            (content_id, parsed.content_digest) for content_id, parsed in sorted(referenced.items())
        ),
        attachment_digests=attachment_digests,
        key_binding_ids=key_binding_ids,
        pinned_commits=tuple(sorted(pinned_commits.items())),
        reference_commit=reference_commit,
        files=tuple(files),
        resolved_markdown_sha256=hashlib.sha256(legacy.encode("utf-8")).hexdigest(),
        resolved_entity_links=tuple(
            (str(link["id"]), str(link["relationship"]), str(link["origin"])) for link in resolved.entity_links
        ),
    )
