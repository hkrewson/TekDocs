"""Deterministic rebuildable projection of canonical repository content."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any

from django.db import transaction

from .content_composition import ContentCompositionError, ContentCompositionResolver
from .content_index_models import (
    ContentEntityLink,
    ContentFinding,
    ContentInclude,
    ContentIndexAttempt,
    ContentIndexStatus,
    ContentLink,
    ContentNode,
    ContentProperty,
    ContentTemplateSource,
    ContentTemplateSourceState,
)
from .content_profile import ContentProfileError, ParsedContent, parse_content
from .models import OrganizationTaxonomyTerm, Taxonomy, TaxonomyTerm, WorkspaceRepository
from .repository_service import (
    RepositoryServiceError,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)

logger = logging.getLogger(__name__)
MAX_PINNED_SNAPSHOTS = 32
MAX_PINNED_HISTORY_BYTES = 64 * 1024 * 1024
MAX_TEMPLATE_PREVIEW_INPUT_BYTES = 64 * 1024
MAX_TEMPLATE_PREVIEW_OUTPUT_CHARS = 12 * 1024


class ContentIndexError(RuntimeError):
    pass


class ContentIndexValidationError(ContentIndexError):
    def __init__(self, diagnostics: tuple[dict[str, str], ...]) -> None:
        super().__init__("Accepted repository commit failed content validation")
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class ContentIndexResult:
    repository_id: uuid.UUID
    commit_id: uuid.UUID
    object_id: str
    node_count: int
    link_count: int
    projection_digest: str
    changed: bool


@dataclass(frozen=True, slots=True)
class ResolvedDirectInclude:
    object_id: str
    target: ParsedContent


@dataclass(frozen=True, slots=True)
class ResolvedTemplateSource:
    object_id: str
    pinned: ParsedContent
    current: ParsedContent | None
    state: str
    change_preview: str


def _current_template_digest(source: ResolvedTemplateSource) -> str | None:
    current = source.current
    return current.content_digest if current is not None else None


def _diagnostic(*, path: str, code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def _validate_taxonomies(*, repository: WorkspaceRepository, path: str, parsed: ParsedContent) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    for taxonomy_key, stable_keys in parsed.taxonomies.items():
        taxonomy = (
            Taxonomy.objects.filter(
                tenant_id=repository.tenant_id,
                key=taxonomy_key,
                archived_at__isnull=True,
            )
            .select_related("current_version")
            .first()
        )
        if taxonomy is None or taxonomy.current_version_id is None:
            diagnostics.append(
                _diagnostic(path=path, code="taxonomy.unknown", message=f"Unknown taxonomy: {taxonomy_key}")
            )
            continue
        global_keys = set(
            TaxonomyTerm.objects.filter(
                tenant_id=repository.tenant_id,
                taxonomy=taxonomy,
                version_id=taxonomy.current_version_id,
                status="active",
                stable_key__in=stable_keys,
            ).values_list("stable_key", flat=True)
        )
        local_keys: set[str] = set()
        if repository.workspace.organization_id is not None:
            local_keys = set(
                OrganizationTaxonomyTerm.objects.filter(
                    tenant_id=repository.tenant_id,
                    organization_id=repository.workspace.organization_id,
                    taxonomy=taxonomy,
                    taxonomy_version_id=taxonomy.current_version_id,
                    archived_at__isnull=True,
                    stable_key__in=stable_keys,
                ).values_list("stable_key", flat=True)
            )
        for stable_key in sorted(set(stable_keys) - global_keys - local_keys):
            diagnostics.append(
                _diagnostic(
                    path=path,
                    code="taxonomy.term.unknown",
                    message=f"Unknown stable taxonomy key: {taxonomy_key}:{stable_key}",
                )
            )
    return diagnostics


def _parse_snapshot(
    *, repository: WorkspaceRepository, files: tuple[tuple[str, bytes], ...]
) -> tuple[dict[str, ParsedContent], tuple[dict[str, str], ...]]:
    parsed_by_path: dict[str, ParsedContent] = {}
    diagnostics: list[dict[str, str]] = []
    identities: dict[uuid.UUID, str] = {}
    for path, source in files:
        try:
            parsed = parse_content(source)
        except ContentProfileError as exc:
            diagnostics.append(_diagnostic(path=path, code=exc.code, message=str(exc)))
            continue
        if parsed.kind == "fragment" and not path.startswith("fragments/"):
            diagnostics.append(
                _diagnostic(
                    path=path,
                    code="content.path.fragment",
                    message="Reusable fragments must be stored under fragments/",
                )
            )
        if parsed.kind == "document" and path.startswith("fragments/"):
            diagnostics.append(
                _diagnostic(
                    path=path,
                    code="content.path.document",
                    message="Documents cannot be stored under fragments/",
                )
            )
        if previous := identities.get(parsed.content_id):
            diagnostics.append(
                _diagnostic(
                    path=path,
                    code="content.id.duplicate",
                    message=f"Content id duplicates another file: {previous}",
                )
            )
        else:
            identities[parsed.content_id] = path
        diagnostics.extend(_validate_taxonomies(repository=repository, path=path, parsed=parsed))
        parsed_by_path[path] = parsed
    claimed_paths = set(parsed_by_path)
    for path, parsed in sorted(parsed_by_path.items()):
        for alias in parsed.frontmatter.get("aliases", []):
            if alias in claimed_paths:
                diagnostics.append(
                    _diagnostic(path=path, code="alias.collision", message="Alias collides with another content path")
                )
            claimed_paths.add(alias)
    return parsed_by_path, tuple(sorted(diagnostics, key=lambda item: (item["path"], item["code"], item["message"])))


def _identity_map(parsed_by_path: dict[str, ParsedContent]) -> dict[uuid.UUID, ParsedContent]:
    return {parsed.content_id: parsed for parsed in parsed_by_path.values()}


def _template_change_preview(pinned: ParsedContent, current: ParsedContent | None) -> str:
    if current is None:
        return "Source is absent from the accepted commit."
    if pinned.content_digest == current.content_digest:
        return ""
    before = f"{pinned.title}\n{pinned.markdown}"
    after = f"{current.title}\n{current.markdown}"
    if max(len(before.encode("utf-8")), len(after.encode("utf-8"))) > MAX_TEMPLATE_PREVIEW_INPUT_BYTES:
        return "Source changed; open the exact source versions to review the full diff."
    result = "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="pinned",
            tofile="current",
        )
    )
    if not result:
        return "Source metadata changed; open the exact source versions to review it."
    return result[:MAX_TEMPLATE_PREVIEW_OUTPUT_CHARS]


class _HistoricalSnapshots:
    def __init__(self, *, repository: WorkspaceRepository, accepted_object_id: str) -> None:
        self.repository = repository
        self.accepted_object_id = accepted_object_id
        self.cache: dict[str, dict[uuid.UUID, ParsedContent]] = {}
        self.loaded_bytes = 0

    def load(self, object_id: str) -> dict[uuid.UUID, ParsedContent]:
        if object_id in self.cache:
            return self.cache[object_id]
        if len(self.cache) >= MAX_PINNED_SNAPSHOTS + 1:
            raise ContentCompositionError("include.commit.limit", "Content uses too many distinct pinned commits")
        try:
            _commit, files = read_repository_markdown_files_at_commit(
                repository_id=self.repository.id,
                object_id=object_id,
            )
        except RepositoryServiceError as exc:
            raise ContentCompositionError(
                "include.commit.unavailable", "Pinned content commit is unavailable in this repository"
            ) from exc
        self.loaded_bytes += sum(len(source) for _path, source in files)
        if self.loaded_bytes > MAX_PINNED_HISTORY_BYTES:
            raise ContentCompositionError("include.commit.limit", "Pinned content history exceeds its size limit")
        parsed_by_id: dict[uuid.UUID, ParsedContent] = {}
        try:
            for path, source in files:
                parsed = parse_content(source)
                if (parsed.kind == "fragment") != path.startswith("fragments/"):
                    raise ContentCompositionError(
                        "include.commit.invalid", "Pinned content commit has invalid content placement"
                    )
                if parsed.content_id in parsed_by_id:
                    raise ContentCompositionError(
                        "include.commit.ambiguous", "Pinned content identity is ambiguous in its selected commit"
                    )
                parsed_by_id[parsed.content_id] = parsed
        except ContentProfileError as exc:
            raise ContentCompositionError(
                "include.commit.invalid", "Pinned content commit does not satisfy the content profile"
            ) from exc
        self.cache[object_id] = parsed_by_id
        return parsed_by_id


def _resolve_compositions(
    *,
    repository: WorkspaceRepository,
    accepted_object_id: str,
    parsed_by_path: dict[str, ParsedContent],
) -> tuple[
    dict[uuid.UUID, dict[str, dict[str, Any]]],
    dict[tuple[uuid.UUID, int], ResolvedDirectInclude],
    dict[tuple[uuid.UUID, int], ResolvedTemplateSource],
    tuple[dict[str, str], ...],
]:
    accepted = _identity_map(parsed_by_path)
    snapshots = _HistoricalSnapshots(repository=repository, accepted_object_id=accepted_object_id)
    snapshots.cache[accepted_object_id] = accepted
    resolver = ContentCompositionResolver(
        accepted_object_id=accepted_object_id,
        accepted=accepted,
        loader=snapshots.load,
    )
    compositions: dict[uuid.UUID, dict[str, dict[str, Any]]] = {}
    direct: dict[tuple[uuid.UUID, int], ResolvedDirectInclude] = {}
    template_sources: dict[tuple[uuid.UUID, int], ResolvedTemplateSource] = {}
    diagnostics: list[dict[str, str]] = []
    paths = {parsed.content_id: path for path, parsed in parsed_by_path.items()}

    for content_id, parsed in sorted(accepted.items(), key=lambda item: str(item[0])):
        path = paths[content_id]
        try:
            for include in parsed.includes:
                object_id, target = resolver.direct_target(
                    context_object_id=accepted_object_id,
                    include=include,
                )
                direct[(content_id, include.ordinal)] = ResolvedDirectInclude(object_id, target)

            if parsed.derived_from is not None:
                if parsed.derived_from.content_id == content_id:
                    raise ContentCompositionError(
                        "derived_from.identity", "An independent copy must use a new content identity"
                    )
                origin = snapshots.load(parsed.derived_from.object_id).get(parsed.derived_from.content_id)
                if origin is None or origin.kind != "fragment":
                    raise ContentCompositionError(
                        "derived_from.unresolved", "Independent-copy provenance does not identify a fragment"
                    )

            for source in parsed.template_sources:
                pinned = snapshots.load(source.object_id).get(source.content_id)
                if pinned is None:
                    raise ContentCompositionError(
                        "template_source.unresolved", "Template source is unavailable in its selected commit"
                    )
                current = accepted.get(source.content_id)
                state = (
                    ContentTemplateSourceState.MISSING
                    if current is None
                    else (
                        ContentTemplateSourceState.CURRENT
                        if current.content_digest == pinned.content_digest
                        else ContentTemplateSourceState.CHANGED
                    )
                )
                template_sources[(content_id, source.ordinal)] = ResolvedTemplateSource(
                    source.object_id,
                    pinned,
                    current,
                    state,
                    _template_change_preview(pinned, current),
                )

            variants: dict[str, dict[str, Any]] = {}
            for key, audience in (
                ("all", None),
                ("msp_internal", "msp_internal"),
                ("client_visible", "client_visible"),
            ):
                resolved = resolver.resolve(content_id=content_id, audience=audience)
                variants[key] = {
                    "digest": resolved.digest,
                    "manifest": list(resolved.manifest),
                    "markdown": resolved.markdown,
                    "entity_links": list(resolved.entity_links),
                }
            compositions[content_id] = variants
        except ContentCompositionError as exc:
            diagnostics.append(_diagnostic(path=path, code=exc.code, message=str(exc)))

    return (
        compositions,
        direct,
        template_sources,
        tuple(sorted(diagnostics, key=lambda item: (item["path"], item["code"], item["message"]))),
    )


def _projection_payload(
    parsed_by_path: dict[str, ParsedContent],
    compositions: dict[uuid.UUID, dict[str, dict[str, Any]]],
    template_sources: dict[tuple[uuid.UUID, int], ResolvedTemplateSource],
) -> list[dict[str, Any]]:
    return [
        {
            "content_digest": parsed.content_digest,
            "content_id": str(parsed.content_id),
            "composition": compositions[parsed.content_id],
            "derived_from": (
                {"commit": parsed.derived_from.object_id, "id": str(parsed.derived_from.content_id)}
                if parsed.derived_from is not None
                else None
            ),
            "findings": list(parsed.findings),
            "kind": parsed.kind,
            "links": [
                {
                    "fragment": link.fragment,
                    "label": link.label,
                    "ordinal": link.ordinal,
                    "target_content_id": str(link.target_content_id),
                }
                for link in parsed.links
            ],
            "includes": [
                {
                    "audience": include.audience,
                    "commit": include.pinned_object_id or None,
                    "id": str(include.target_content_id),
                    "mode": include.mode,
                    "ordinal": include.ordinal,
                }
                for include in parsed.includes
            ],
            "entity_links": [
                {
                    "id": str(link.target_entity_id),
                    "relationship": link.relationship,
                    "origin": link.origin,
                    "ordinal": link.ordinal,
                }
                for link in parsed.entity_links
            ],
            "path": path,
            "properties": parsed.properties,
            "taxonomies": parsed.taxonomies,
            "title": parsed.title,
            "template_sources": [
                {
                    "commit": source.object_id,
                    "id": str(source.content_id),
                    "ordinal": source.ordinal,
                    "pinned_digest": template_sources[(parsed.content_id, source.ordinal)].pinned.content_digest,
                    "current_digest": _current_template_digest(template_sources[(parsed.content_id, source.ordinal)]),
                    "state": template_sources[(parsed.content_id, source.ordinal)].state,
                    "change_preview": template_sources[(parsed.content_id, source.ordinal)].change_preview,
                }
                for source in parsed.template_sources
            ],
            "topic_schema_version": parsed.topic_schema_version,
            "topic_type": parsed.topic_type,
        }
        for path, parsed in sorted(parsed_by_path.items())
    ]


def _digest(
    parsed_by_path: dict[str, ParsedContent],
    compositions: dict[uuid.UUID, dict[str, dict[str, Any]]],
    template_sources: dict[tuple[uuid.UUID, int], ResolvedTemplateSource],
) -> str:
    encoded = json.dumps(
        _projection_payload(parsed_by_path, compositions, template_sources),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_candidate_snapshot(*, repository: WorkspaceRepository, files: tuple[tuple[str, bytes], ...]) -> None:
    """Reject an authoring candidate before Git advances its accepted ref.

    The synthetic identity cannot occur in versioned frontmatter, so pinned
    references always resolve from retained commits rather than candidate files.
    The final commit is indexed normally after the repository CAS succeeds.
    """

    parsed_by_path, diagnostics = _parse_snapshot(repository=repository, files=files)
    if not diagnostics:
        _compositions, _includes, _templates, diagnostics = _resolve_compositions(
            repository=repository,
            accepted_object_id="candidate:uncommitted",
            parsed_by_path=parsed_by_path,
        )
    if diagnostics:
        raise ContentIndexValidationError(diagnostics)


def index_repository_content(*, repository_id: uuid.UUID, force: bool = False) -> ContentIndexResult:
    repository = WorkspaceRepository.objects.select_related(
        "workspace", "workspace__organization", "accepted_commit", "indexed_commit"
    ).get(pk=repository_id)
    if repository.accepted_commit_id is None:
        raise ContentIndexError("Repository has no accepted commit")
    if not force and repository.indexed_commit_id == repository.accepted_commit_id:
        accepted_commit = repository.accepted_commit
        if accepted_commit is None:  # pragma: no cover - guarded by accepted_commit_id
            raise ContentIndexError("Repository has no accepted commit")
        attempt = ContentIndexAttempt.objects.get(repository=repository, commit=accepted_commit)
        return ContentIndexResult(
            repository.id,
            repository.accepted_commit_id,
            accepted_commit.object_id,
            ContentNode.objects.filter(repository=repository).count(),
            ContentLink.objects.filter(source__repository=repository).count(),
            attempt.projection_digest,
            False,
        )

    commit, files = read_accepted_repository_markdown_files(repository_id=repository.id)
    parsed_by_path, diagnostics = _parse_snapshot(repository=repository, files=files)
    compositions: dict[uuid.UUID, dict[str, dict[str, Any]]] = {}
    direct_includes: dict[tuple[uuid.UUID, int], ResolvedDirectInclude] = {}
    resolved_template_sources: dict[tuple[uuid.UUID, int], ResolvedTemplateSource] = {}
    if not diagnostics:
        compositions, direct_includes, resolved_template_sources, composition_diagnostics = _resolve_compositions(
            repository=repository,
            accepted_object_id=commit.object_id,
            parsed_by_path=parsed_by_path,
        )
        diagnostics = composition_diagnostics
    scope = {
        "tenant_id": repository.tenant_id,
        "organization_id": repository.workspace.organization_id,
        "workspace_id": repository.workspace_id,
    }
    if diagnostics:
        ContentIndexAttempt.objects.update_or_create(
            repository=repository,
            commit=commit,
            defaults={
                **scope,
                "status": ContentIndexStatus.REJECTED,
                "diagnostics": list(diagnostics),
                "projection_digest": "",
            },
        )
        logger.warning(
            "content_index_rejected repository=%s commit=%s diagnostics=%s",
            repository.id,
            commit.object_id,
            len(diagnostics),
        )
        raise ContentIndexValidationError(diagnostics)

    projection_digest = _digest(parsed_by_path, compositions, resolved_template_sources)
    with transaction.atomic():
        locked = WorkspaceRepository.objects.select_for_update().select_related("workspace").get(pk=repository.id)
        if locked.accepted_commit_id != commit.id:
            raise ContentIndexError("Repository accepted commit changed during indexing")
        ContentNode.objects.filter(repository=locked).delete()
        nodes: dict[uuid.UUID, ContentNode] = {}
        for path, parsed in sorted(parsed_by_path.items()):
            node = ContentNode.objects.create(
                **scope,
                repository=locked,
                indexed_commit=commit,
                content_id=parsed.content_id,
                source_path=path,
                kind=parsed.kind,
                title=parsed.title,
                markdown=parsed.markdown,
                frontmatter=parsed.frontmatter,
                taxonomy_keys=parsed.taxonomies,
                topic_type=parsed.topic_type,
                topic_schema_version=parsed.topic_schema_version,
                content_digest=parsed.content_digest,
                composition_variants=compositions[parsed.content_id],
                derived_from_content_id=(parsed.derived_from.content_id if parsed.derived_from is not None else None),
                derived_from_object_id=(parsed.derived_from.object_id if parsed.derived_from is not None else ""),
            )
            nodes[parsed.content_id] = node
            ContentProperty.objects.bulk_create(
                [ContentProperty(**scope, node=node, key=key, value=value) for key, value in parsed.properties.items()]
            )
            ContentFinding.objects.bulk_create(
                [
                    ContentFinding(
                        **scope,
                        node=node,
                        code=str(finding["code"]),
                        severity=str(finding["severity"]),
                        detail={key: value for key, value in finding.items() if key not in {"code", "severity"}},
                    )
                    for finding in parsed.findings
                ]
            )

        links: list[ContentLink] = []
        findings: list[ContentFinding] = []
        for path, parsed in sorted(parsed_by_path.items()):
            source = nodes[parsed.content_id]
            for link in parsed.links:
                target = nodes.get(link.target_content_id)
                links.append(
                    ContentLink(
                        **scope,
                        source=source,
                        target=target,
                        target_content_id=link.target_content_id,
                        fragment=link.fragment,
                        label=link.label,
                        ordinal=link.ordinal,
                    )
                )
                if target is None:
                    findings.append(
                        ContentFinding(
                            **scope,
                            node=source,
                            code="wikilink.unresolved",
                            severity="warning",
                            detail={"ordinal": link.ordinal, "path": path},
                        )
                    )
        ContentLink.objects.bulk_create(links)
        ContentFinding.objects.bulk_create(findings)
        includes: list[ContentInclude] = []
        template_source_rows: list[ContentTemplateSource] = []
        template_findings: list[ContentFinding] = []
        for _path, parsed in sorted(parsed_by_path.items()):
            source = nodes[parsed.content_id]
            for include in parsed.includes:
                resolved = direct_includes[(parsed.content_id, include.ordinal)]
                includes.append(
                    ContentInclude(
                        **scope,
                        source=source,
                        target=nodes.get(include.target_content_id),
                        target_content_id=include.target_content_id,
                        ordinal=include.ordinal,
                        resolution_mode=include.mode,
                        audience_profile=include.audience,
                        pinned_object_id=include.pinned_object_id,
                        resolved_object_id=resolved.object_id,
                        resolved_content_digest=resolved.target.content_digest,
                    )
                )
            for template_source in parsed.template_sources:
                resolved_source = resolved_template_sources[(parsed.content_id, template_source.ordinal)]
                template_source_rows.append(
                    ContentTemplateSource(
                        **scope,
                        template=source,
                        current_target=nodes.get(template_source.content_id),
                        source_content_id=template_source.content_id,
                        ordinal=template_source.ordinal,
                        pinned_object_id=template_source.object_id,
                        pinned_content_digest=resolved_source.pinned.content_digest,
                        pinned_title=resolved_source.pinned.title,
                        current_content_digest=(
                            resolved_source.current.content_digest if resolved_source.current is not None else ""
                        ),
                        state=resolved_source.state,
                        change_preview=resolved_source.change_preview,
                    )
                )
                if resolved_source.state != ContentTemplateSourceState.CURRENT:
                    template_findings.append(
                        ContentFinding(
                            **scope,
                            node=source,
                            code=f"template_source.{resolved_source.state}",
                            severity="warning",
                            detail={"ordinal": template_source.ordinal},
                        )
                    )
        ContentInclude.objects.bulk_create(includes)
        ContentTemplateSource.objects.bulk_create(template_source_rows)
        ContentFinding.objects.bulk_create(template_findings)
        ContentEntityLink.objects.bulk_create(
            [
                ContentEntityLink(
                    **scope,
                    source=nodes[parsed.content_id],
                    target_entity_id=uuid.UUID(link["id"]),
                    relationship=link["relationship"],
                    origin=link["origin"],
                    ordinal=ordinal,
                )
                for _path, parsed in sorted(parsed_by_path.items())
                for ordinal, link in enumerate(compositions[parsed.content_id]["msp_internal"]["entity_links"])
            ]
        )
        ContentIndexAttempt.objects.update_or_create(
            repository=locked,
            commit=commit,
            defaults={
                **scope,
                "status": ContentIndexStatus.ACCEPTED,
                "diagnostics": [],
                "projection_digest": projection_digest,
            },
        )
        locked.indexed_commit = commit
        locked.save(update_fields=("indexed_commit", "updated_at"))

    logger.info(
        "content_index_accepted repository=%s commit=%s nodes=%s links=%s",
        repository.id,
        commit.object_id,
        len(nodes),
        len(links),
    )
    return ContentIndexResult(
        repository.id,
        commit.id,
        commit.object_id,
        len(nodes),
        len(links),
        projection_digest,
        True,
    )


def content_graph_projection(*, repository: WorkspaceRepository, audience: str | None = None) -> dict[str, Any]:
    nodes = list(
        ContentNode.objects.filter(repository=repository)
        .prefetch_related(
            "properties",
            "outgoing_links",
            "backlinks__source",
            "findings",
            "includes",
            "included_by__source",
            "template_sources",
            "entity_links",
        )
        .order_by("source_path", "content_id")
    )
    accepted_object = repository.accepted_commit.object_id if repository.accepted_commit is not None else None
    indexed_object = repository.indexed_commit.object_id if repository.indexed_commit is not None else None
    return {
        "accepted_commit": accepted_object,
        "indexed_commit": indexed_object,
        "nodes": [
            {
                "id": str(node.content_id),
                "kind": node.kind,
                "title": node.title,
                "path": node.source_path,
                "markdown": node.markdown,
                "properties": {item.key: item.value for item in node.properties.all()},
                "taxonomies": node.taxonomy_keys,
                "topic": ({"type": node.topic_type, "version": node.topic_schema_version} if node.topic_type else None),
                "composition": node.composition_variants.get(audience or "all"),
                "derived_from": (
                    {"id": str(node.derived_from_content_id), "commit": node.derived_from_object_id}
                    if node.derived_from_content_id is not None
                    else None
                ),
                "includes": [
                    {
                        "target_id": str(include.target_content_id),
                        "mode": include.resolution_mode,
                        "audience": include.audience_profile,
                        "pinned_commit": include.pinned_object_id or None,
                        "resolved_commit": include.resolved_object_id,
                        "resolved_digest": include.resolved_content_digest,
                    }
                    for include in node.includes.all()
                ],
                "included_by": [str(include.source.content_id) for include in node.included_by.all()],
                "template_sources": [
                    {
                        "id": str(source.source_content_id),
                        "commit": source.pinned_object_id,
                        "pinned_digest": source.pinned_content_digest,
                        "current_digest": source.current_content_digest or None,
                        "title": source.pinned_title,
                        "state": source.state,
                        "change_preview": source.change_preview,
                    }
                    for source in node.template_sources.all()
                ],
                "entity_links": [
                    {
                        "id": str(link.target_entity_id),
                        "relationship": link.relationship,
                        "origin": link.origin,
                        "ordinal": link.ordinal,
                    }
                    for link in node.entity_links.all()
                ],
                "outgoing_links": [
                    {
                        "target_id": str(link.target_content_id),
                        "fragment": link.fragment or None,
                        "label": link.label or None,
                        "resolved": link.target_id is not None,
                    }
                    for link in node.outgoing_links.all()
                ],
                "backlinks": [str(link.source.content_id) for link in node.backlinks.all()],
                "findings": [
                    {"code": finding.code, "severity": finding.severity, "detail": finding.detail}
                    for finding in node.findings.all()
                ],
            }
            for node in nodes
        ],
        "latest_attempt": (
            {
                "commit": attempt.commit.object_id,
                "status": attempt.status,
                "diagnostics": attempt.diagnostics,
                "projection_digest": attempt.projection_digest or None,
            }
            if (attempt := repository.content_index_attempts.select_related("commit").first())
            else None
        ),
    }
