"""Offline occurrence and diagram envelopes over existing Git content certificates."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from .content_composition import MAX_COMPOSITION_NODES
from .diagram_exports import MAX_PNG_BYTES, MAX_SVG_BYTES, RENDERER_REPORT, diagram_sources

DIAGRAM_GIT_STATIC_FORMAT = "tekdocs-static-publication/v11"
OCCURRENCE_GIT_STATIC_FORMAT = "tekdocs-static-publication/v12"
LIBRARY_GIT_STATIC_FORMAT = "tekdocs-static-publication/v13"
CONTENT_FORMATS = frozenset(f"tekdocs-static-publication/v{version}" for version in range(5, 11))


def has_repeated_source_envelope(manifest: dict[str, Any]) -> bool:
    selected = manifest.get("library_format") if manifest.get("format") == LIBRARY_GIT_STATIC_FORMAT else (
        manifest.get("format")
    )
    return selected == OCCURRENCE_GIT_STATIC_FORMAT


def publication_content_manifest(manifest: dict[str, Any], markdown: str) -> dict[str, Any]:
    """Validate envelope layers, then expose their unchanged content certificate.

    The returned view is only for structural validation. Signatures always cover
    the original manifest including occurrence/diagram descriptors and formats.
    No current renderer, database record or Git source is consulted here.
    """
    if "ordinary_library" in manifest:
        raise ValueError("Reserved library validation marker")
    if manifest.get("format") == LIBRARY_GIT_STATIC_FORMAT:
        source = manifest["git_source"]
        if (manifest.get("library_format") not in {
            f"tekdocs-static-publication/v{version}" for version in range(7, 13)
        } or source.get("format") != "tekdocs.git-dependencies/v3"
            or not any("library_source" in item for item in source["sources"])):
            raise ValueError("Ordinary library publication envelope is invalid")
        manifest = {**manifest, "format": manifest["library_format"], "ordinary_library": True,
                    "git_source": {**source, "format": "tekdocs.git-dependencies/v2"}}
    elif any("library_source" in item for item in manifest.get("git_source", {}).get("sources", [])):
        raise ValueError("Historical formats cannot admit ordinary library proof")
    if manifest.get("format") == OCCURRENCE_GIT_STATIC_FORMAT:
        if manifest.get("occurrence_format") not in {
            f"tekdocs-static-publication/v{version}" for version in range(7, 12)
        }:
            raise ValueError("Occurrence publication content format is invalid")
        sources = manifest["git_source"]["sources"]
        if not isinstance(sources, list) or not 3 <= len(sources) <= MAX_COMPOSITION_NODES:
            raise ValueError("Occurrence publication source count is invalid")
        identities = {(item.get("library_workspace", manifest["git_source"]["workspace_id"]), item["id"])
                      for item in sources}
        if len(identities) == len(sources):
            raise ValueError("Occurrence publication requires repeated source identities")
        manifest = {**manifest, "format": manifest["occurrence_format"]}
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
