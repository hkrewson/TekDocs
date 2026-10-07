"""Read-only first-wave placement shape shared by inventory and export."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .content_composition import MAX_COMPOSITION_DEPTH, MAX_COMPOSITION_NODES
from .models import Document, DocumentPlacement, PlacementAudienceProfile, PlacementResolutionMode


class DocumentMigrationShapeError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class OwnedPlacementTree:
    ordered: tuple[DocumentPlacement, ...]
    children: dict[uuid.UUID | None, tuple[DocumentPlacement, ...]]


def owned_placement_tree(document: Document, placements: list[DocumentPlacement]) -> OwnedPlacementTree:
    """Return bounded legacy pre-order without reading any Markdown bodies."""

    if not placements:
        raise DocumentMigrationShapeError("composed_or_missing_placements")
    if len(placements) + 1 > MAX_COMPOSITION_NODES:
        raise DocumentMigrationShapeError("composition_node_limit_exceeded")
    placement_ids = {placement.id for placement in placements}
    if len(placement_ids) != len(placements) or len({placement.block_id for placement in placements}) != len(
        placements
    ):
        raise DocumentMigrationShapeError("unsupported_placement_graph")
    children: dict[uuid.UUID | None, list[DocumentPlacement]] = {}
    for placement in placements:
        if (
            placement.document_id != document.id
            or placement.tenant_id != document.tenant_id
            or placement.organization_id != document.organization_id
            or placement.audience_profile != PlacementAudienceProfile.SHARED
        ):
            raise DocumentMigrationShapeError("non_primary_or_pinned_placement")
        if placement.resolution_mode == PlacementResolutionMode.LIVE:
            if placement.block.current_revision_id is None or placement.pinned_revision_id is not None:
                raise DocumentMigrationShapeError("non_primary_or_pinned_placement")
        elif placement.resolution_mode == PlacementResolutionMode.PINNED:
            pinned_revision = placement.pinned_revision
            if (
                placement.block.source_document_id == document.id
                or pinned_revision is None
                or pinned_revision.block_id != placement.block_id
            ):
                raise DocumentMigrationShapeError("pinned_source_snapshot_required")
        else:
            raise DocumentMigrationShapeError("non_primary_or_pinned_placement")
        if (
            placement.block.tenant_id != document.tenant_id
            or placement.block.organization_id != document.organization_id
        ):
            raise DocumentMigrationShapeError("cross_workspace_reference")
        if placement.parent_id is not None and placement.parent_id not in placement_ids:
            raise DocumentMigrationShapeError("unsupported_placement_graph")
        children.setdefault(placement.parent_id, []).append(placement)
    ordered_children: dict[uuid.UUID | None, tuple[DocumentPlacement, ...]] = {}
    for parent_id, siblings in children.items():
        sorted_siblings = tuple(sorted(siblings, key=lambda item: (item.position, item.id.int)))
        if any(placement.position != index for index, placement in enumerate(sorted_siblings)):
            raise DocumentMigrationShapeError("unsupported_placement_graph")
        ordered_children[parent_id] = sorted_siblings
    if any(
        placement.block.source_document_id != document.id and ordered_children.get(placement.id)
        for placement in placements
    ):
        raise DocumentMigrationShapeError("cross_document_nested_reference")
    if not ordered_children.get(None):
        raise DocumentMigrationShapeError("unsupported_placement_graph")

    ordered: list[DocumentPlacement] = []
    visited: set[uuid.UUID] = set()

    def visit(placement: DocumentPlacement, depth: int) -> None:
        if depth >= MAX_COMPOSITION_DEPTH:
            raise DocumentMigrationShapeError("composition_depth_exceeded")
        if placement.id in visited:
            raise DocumentMigrationShapeError("unsupported_placement_graph")
        visited.add(placement.id)
        ordered.append(placement)
        for child in ordered_children.get(placement.id, ()):
            visit(child, depth + 1)

    for root in ordered_children[None]:
        visit(root, 0)
    if len(ordered) != len(placements):
        raise DocumentMigrationShapeError("unsupported_placement_graph")
    return OwnedPlacementTree(ordered=tuple(ordered), children=ordered_children)
