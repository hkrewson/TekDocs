"""Authorization-filtered read models for the accepted repository content graph."""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404

from .content_index_models import ContentEntityLink, ContentFinding, ContentNode, ContentProperty
from .models import ClientAsset, Entity, WorkspaceRepository, workspace_for_owner
from .relationships import entity_for_workspace, entity_projection, visible_entities_for_workspace
from .rendering import RenderedEntityMention, render_markdown
from .workspaces import ResolvedWorkspace


def repository_for_reader(workspace: ResolvedWorkspace) -> WorkspaceRepository:
    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    return WorkspaceRepository.objects.select_related("accepted_commit", "indexed_commit").get(workspace=owner)


def _visible_entity_context(workspace: ResolvedWorkspace, ids: set[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    if not ids:
        return {}
    entities = visible_entities_for_workspace(
        workspace=workspace,
        include_reference_organizations=True,
    ).filter(id__in=ids)
    return {entity.id: entity_projection(entity, workspace) for entity in entities}


def document_detail(*, workspace: ResolvedWorkspace, content_id: uuid.UUID, audience: str) -> dict[str, Any]:
    repository = repository_for_reader(workspace)
    node = get_object_or_404(ContentNode.objects.filter(repository=repository), content_id=content_id)
    links = list(node.entity_links.all())
    visible = _visible_entity_context(workspace, {link.target_entity_id for link in links})
    mentions: dict[str, RenderedEntityMention] = {
        str(entity_id): {
            "id": str(entity_id),
            "display_name": str(item["display_name"]),
            "entity_type": str(item["entity_type"]),
            "workspace_label": str(item["workspace_label"]),
        }
        for entity_id, item in visible.items()
    }
    composition = node.composition_variants.get(audience)
    markdown = str(composition.get("markdown", "")) if isinstance(composition, dict) else node.markdown
    return {
        "id": node.content_id,
        "kind": node.kind,
        "title": node.title,
        "path": node.source_path,
        "indexed_commit": node.indexed_commit.object_id,
        "markdown": markdown,
        "sanitized_html": render_markdown(markdown, entity_mentions=mentions),
        "entity_context": [
            {
                "id": link.target_entity_id,
                "relationship": link.relationship,
                "origin": link.origin,
                "display_name": visible[link.target_entity_id]["display_name"],
                "entity_type": visible[link.target_entity_id]["entity_type"],
            }
            for link in links
            if link.target_entity_id in visible
        ],
        "findings": [
            {"code": item.code, "severity": item.severity, "detail": item.detail} for item in node.findings.all()
        ],
    }


def document_collection(
    *,
    workspace: ResolvedWorkspace,
    q: str,
    kind: str,
    topic: str,
    property_key: str,
    property_value: str,
    has_findings: bool,
    unresolved_only: bool,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    repository = repository_for_reader(workspace)
    nodes = ContentNode.objects.filter(repository=repository)
    if q:
        nodes = nodes.filter(
            Q(title__icontains=q)
            | Q(markdown__icontains=q)
            | Q(composition_variants__msp_internal__markdown__icontains=q)
        )
    if kind:
        nodes = nodes.filter(kind=kind)
    if topic:
        nodes = nodes.filter(topic_type=topic)
    if property_key:
        properties = ContentProperty.objects.filter(key=property_key)
        if property_value:
            properties = properties.filter(value=property_value)
        nodes = nodes.filter(id__in=properties.values("node_id"))
    if unresolved_only:
        nodes = nodes.filter(findings__code__in=("wikilink.unresolved", "entity_link.unresolved"))
    elif has_findings:
        nodes = nodes.filter(findings__isnull=False)
    nodes = nodes.distinct().order_by("title", "content_id")
    count = nodes.count()
    offset = (page - 1) * page_size
    selected = list(nodes[offset : offset + page_size + 1])
    results = [
        {
            "id": node.content_id,
            "kind": node.kind,
            "title": node.title,
            "path": node.source_path,
            "topic": node.topic_type or None,
            "finding_count": ContentFinding.objects.filter(node=node).count(),
        }
        for node in selected[:page_size]
    ]
    return {
        "results": results,
        "page": page,
        "page_size": page_size,
        "count": count,
        "has_more": len(selected) > page_size,
        "accepted_commit": repository.accepted_commit.object_id if repository.accepted_commit else None,
        "indexed_commit": repository.indexed_commit.object_id if repository.indexed_commit else None,
    }


def entity_documentation(*, workspace: ResolvedWorkspace, entity_id: uuid.UUID) -> dict[str, Any]:
    try:
        entity = entity_for_workspace(workspace=workspace, entity_id=entity_id)
    except Entity.DoesNotExist as exc:
        raise Http404 from exc
    repository = repository_for_reader(workspace)
    target_scopes: dict[uuid.UUID, str] = {entity.id: "exact"}
    if entity.entity_type == "client_asset":
        asset = (
            ClientAsset.objects.filter(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                entity_id=entity.id,
                archived_at__isnull=True,
            )
            .select_related("model", "product")
            .first()
        )
        if asset is not None:
            target_scopes[asset.model.entity_id] = "model"
            target_scopes[asset.product.entity_id] = "class"
    links = (
        ContentEntityLink.objects.filter(source__repository=repository, target_entity_id__in=target_scopes)
        .select_related("source")
        .order_by("source__title", "source__content_id", "ordinal")
    )
    return {
        "entity_id": entity.id,
        "documents": [
            {
                "id": link.source.content_id,
                "title": link.source.title,
                "kind": link.source.kind,
                "relationship": link.relationship,
                "scope": target_scopes[link.target_entity_id],
            }
            for link in links
        ],
        "indexed_commit": repository.indexed_commit.object_id if repository.indexed_commit else None,
    }
