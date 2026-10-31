"""Append-only provenance for a reused template section's client-owned fork."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .models import BlockRevision, DocumentPlacement


def template_fork_metadata(
    *,
    enrollment_id: UUID,
    placement: DocumentPlacement,
    revision: BlockRevision,
    source: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": "tekdocs.template-fork/v1",
        "enrollment": str(enrollment_id),
        "placement": str(placement.id),
        "source": dict(source),
        "destination": {
            "block": str(placement.block_id),
            "entity": str(placement.block.entity_id),
            "revision": str(revision.id),
            "checksum": revision.checksum,
        },
    }
