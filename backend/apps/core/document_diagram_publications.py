"""Offline diagram custody layered over existing Git content certificates."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from .diagram_exports import MAX_PNG_BYTES, MAX_SVG_BYTES, RENDERER_REPORT, diagram_sources

DIAGRAM_GIT_STATIC_FORMAT = "tekdocs-static-publication/v11"
CONTENT_FORMATS = frozenset(f"tekdocs-static-publication/v{version}" for version in range(5, 11))


def publication_content_manifest(manifest: dict[str, Any], markdown: str) -> dict[str, Any]:
    """Validate the diagram layer, then expose its unchanged content certificate.

    The returned view is only for structural validation. Signatures always cover
    the original manifest including every diagram descriptor and content format.
    No current renderer, database record or Git source is consulted here.
    """
    if manifest.get("format") != DIAGRAM_GIT_STATIC_FORMAT:
        return manifest
    if manifest.get("content_format") not in CONTENT_FORMATS:
        raise ValueError("Diagram publication content format is invalid")
    sources = diagram_sources(markdown)
    records = manifest.get("diagrams")
    artifacts = manifest.get("artifacts")
    if not sources or not isinstance(records, list) or len(records) != len(sources) or not isinstance(artifacts, list):
        raise ValueError("Diagram publication evidence is incomplete")
    by_id = {item["entity_id"]: item for item in artifacts}
    if len(by_id) != len(artifacts) or len({item["id"] for item in artifacts}) != len(artifacts):
        raise ValueError("Diagram publication artifact identities are duplicated")
    selected = set()
    for source, record in zip(sources, records, strict=True):
        expected = {
            "index": source.index, "title": source.title, "description": source.description,
            "family": source.family, "source_checksum": source.source_checksum, "state": "rendered",
        }
        if (set(record) != set(expected) | {
            "renderer_version", "svg_checksum", "png_checksum", "svg_artifact_id", "svg_filename",
            "png_artifact_id", "png_filename",
        } or any(record[key] != value for key, value in expected.items())
            or not RENDERER_REPORT.fullmatch(record["renderer_version"])):
            raise ValueError("Diagram publication source proof is invalid")
        for extension, media_type, limit in (
            ("svg", "image/svg+xml", MAX_SVG_BYTES), ("png", "image/png", MAX_PNG_BYTES),
        ):
            identity = record[f"{extension}_artifact_id"]
            if str(UUID(identity)) != identity or identity in selected:
                raise ValueError("Diagram publication artifact identity is invalid")
            selected.add(identity)
            item = by_id[identity]
            if (item["kind"] != f"diagram_{extension}" or item["media_type"] != media_type
                or type(item["size"]) is not int or not 0 < item["size"] <= limit
                or item["source_attachment_id"] is not None
                or item["checksum"] != record[f"{extension}_checksum"]
                or not re.fullmatch(r"[0-9a-f]{64}", item["checksum"])
                or item["filename"] != record[f"{extension}_filename"]
                or item["filename"] != f"diagram-{source.index:03d}.{extension}"):
                raise ValueError("Diagram publication artifact proof is invalid")
    if selected != {item["entity_id"] for item in artifacts if item["kind"] in {"diagram_svg", "diagram_png"}}:
        raise ValueError("Diagram publication has unclaimed artifacts")
    return {
        **manifest, "format": manifest["content_format"], "diagrams": [],
        "artifacts": [item for item in artifacts if item["entity_id"] not in selected],
    }
