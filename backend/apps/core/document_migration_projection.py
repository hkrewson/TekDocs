"""Shared parity check for parsed migration files and their derived index rows."""

from __future__ import annotations

import uuid

from .content_profile import ParsedContent
from .models import ContentNode


def _composed_entity_links(node: ContentNode) -> tuple[tuple[str, str, str], ...] | None:
    composition = node.composition_variants.get("msp_internal")
    links = composition.get("entity_links") if isinstance(composition, dict) else None
    if not isinstance(links, list):
        return None
    result: list[tuple[str, str, str]] = []
    for link in links:
        if not isinstance(link, dict) or any(
            not isinstance(link.get(key), str) for key in ("id", "relationship", "origin")
        ):
            return None
        result.append((link["id"], link["relationship"], link["origin"]))
    return tuple(result)


def portable_root_entity_links_match(node: ContentNode, expected: tuple[tuple[str, str, str], ...]) -> bool:
    return _composed_entity_links(node) == expected


def portable_node_projection_matches(
    *,
    node: ContentNode | None,
    parsed: ParsedContent,
    path: str,
    indexed_commit_id: uuid.UUID | None,
    indexed_object_id: str,
) -> bool:
    if node is None:
        return False
    metadata_matches = (
        node.indexed_commit_id == indexed_commit_id
        and node.source_path == path
        and node.kind == parsed.kind
        and node.content_digest == parsed.content_digest
        and node.title == parsed.title
        and node.markdown == parsed.markdown
        and node.frontmatter == parsed.frontmatter
        and node.taxonomy_keys == parsed.taxonomies
        and node.topic_type == parsed.topic_type
        and node.topic_schema_version == parsed.topic_schema_version
        and {property_row.key: property_row.value for property_row in node.properties.all()} == parsed.properties
    )
    if not metadata_matches:
        return False
    composed_entity_links = _composed_entity_links(node)
    if composed_entity_links is None or composed_entity_links != tuple(
        (str(link.target_entity_id), link.relationship, link.origin) for link in node.entity_links.all()
    ):
        return False
    includes = list(node.includes.all())
    links = list(node.outgoing_links.all())
    if len(includes) != len(parsed.includes) or len(links) != len(parsed.links):
        return False
    if not includes and not links:
        return True
    target_content_ids = {include.target_content_id for include in parsed.includes}
    target_content_ids.update(link.target_content_id for link in parsed.links)
    targets = {
        content_id: (target_id, digest)
        for content_id, target_id, digest in ContentNode.objects.filter(
            repository_id=node.repository_id,
            content_id__in=target_content_ids,
        ).values_list("content_id", "id", "content_digest")
    }
    for linked, expected_link in zip(links, parsed.links, strict=True):
        target = targets.get(expected_link.target_content_id)
        if (
            linked.ordinal != expected_link.ordinal
            or linked.target_content_id != expected_link.target_content_id
            or linked.target_id != (target[0] if target is not None else None)
            or linked.fragment != expected_link.fragment
            or linked.label != expected_link.label
        ):
            return False
    for included, expected_include in zip(includes, parsed.includes, strict=True):
        target = targets.get(expected_include.target_content_id)
        resolved_object_id = (
            indexed_object_id if expected_include.mode == "live" else expected_include.pinned_object_id
        )
        if (
            target is None
            or included.ordinal != expected_include.ordinal
            or included.target_content_id != expected_include.target_content_id
            or included.target_id != target[0]
            or included.resolution_mode != expected_include.mode
            or included.audience_profile != expected_include.audience
            or included.pinned_object_id != expected_include.pinned_object_id
            or included.resolved_object_id != resolved_object_id
            or (expected_include.mode == "live" and included.resolved_content_digest != target[1])
        ):
            return False
    return True
