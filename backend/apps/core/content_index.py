"""Deterministic rebuildable projection of canonical repository content."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .content_index_models import (
    ContentFinding,
    ContentIndexAttempt,
    ContentIndexStatus,
    ContentLink,
    ContentNode,
    ContentProperty,
)
from .content_profile import ContentProfileError, ParsedContent, parse_content
from .models import OrganizationTaxonomyTerm, Taxonomy, TaxonomyTerm, WorkspaceRepository
from .repository_service import read_accepted_repository_markdown_files

logger = logging.getLogger(__name__)


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
    return parsed_by_path, tuple(sorted(diagnostics, key=lambda item: (item["path"], item["code"], item["message"])))


def _projection_payload(parsed_by_path: dict[str, ParsedContent]) -> list[dict[str, Any]]:
    return [
        {
            "content_digest": parsed.content_digest,
            "content_id": str(parsed.content_id),
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
            "path": path,
            "properties": parsed.properties,
            "taxonomies": parsed.taxonomies,
            "title": parsed.title,
            "topic_schema_version": parsed.topic_schema_version,
            "topic_type": parsed.topic_type,
        }
        for path, parsed in sorted(parsed_by_path.items())
    ]


def _digest(parsed_by_path: dict[str, ParsedContent]) -> str:
    encoded = json.dumps(_projection_payload(parsed_by_path), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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

    projection_digest = _digest(parsed_by_path)
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


def content_graph_projection(*, repository: WorkspaceRepository) -> dict[str, Any]:
    nodes = list(
        ContentNode.objects.filter(repository=repository)
        .prefetch_related("properties", "outgoing_links", "backlinks", "findings")
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
