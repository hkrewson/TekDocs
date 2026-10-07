"""Value-free readiness gate for retained repository publication evidence.

This intentionally blocks dependencies that the repository STATIC path does
not yet freeze. It is not the legacy database-document preflight.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from markdown_it import MarkdownIt

from .diagram_exports import DiagramRenderError, diagram_sources
from .topic_schemas import inspect_markdown

PREFLIGHT_FORMAT = "tekdocs-repository-publication-preflight/v1"
_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})


def repository_publication_preflight(
    *,
    markdown: str,
    audience: str,
    topic_type: str,
    frozen_attachment_ids: set[UUID] | None = None,
    frozen_entity_ids: set[UUID] | None = None,
    frozen_key_targets: set[str] | None = None,
) -> dict[str, Any]:
    """Return deterministic, content-free blocker and warning codes."""

    blockers: set[str] = set()
    warnings: set[str] = set()
    if not markdown.strip():
        blockers.add("document.empty")
    if topic_type:
        for item in inspect_markdown(topic_type, markdown):
            code = str(item["code"])
            (blockers if item["severity"] == "blocker" else warnings).add(code)

    for token in _MARKDOWN.parse(markdown):
        for child in token.children or ():
            if child.type == "image":
                blockers.add("repository.image.unfrozen")
            if child.type not in {"link_open", "image"}:
                continue
            target = child.attrGet("href" if child.type == "link_open" else "src")
            if not isinstance(target, str) or not target.casefold().startswith("tekdocs://"):
                continue
            kind = target[len("tekdocs://") :].split("/", 1)[0].casefold()
            if kind == "attachment" and frozen_attachment_ids is not None:
                try:
                    attachment_id = UUID(target[len("tekdocs://attachment/") :])
                except ValueError:
                    pass
                else:
                    if target == f"tekdocs://attachment/{attachment_id}" and attachment_id in frozen_attachment_ids:
                        continue
            if kind == "entity" and frozen_entity_ids is not None:
                try:
                    entity_id = UUID(target[len("tekdocs://entity/") :])
                except ValueError:
                    pass
                else:
                    if target == f"tekdocs://entity/{entity_id}" and entity_id in frozen_entity_ids:
                        continue
            if kind == "key" and frozen_key_targets is not None and target in frozen_key_targets:
                continue
            blockers.add(
                {
                    "attachment": "repository.attachment.unfrozen",
                    "key": "repository.key.unfrozen",
                    "entity": "repository.entity.unfrozen",
                }.get(kind, "repository.reference.unsupported")
            )

    try:
        if diagram_sources(markdown):
            blockers.add("repository.diagram.unfrozen")
    except DiagramRenderError:
        blockers.add("repository.diagram.unfrozen")

    return {
        "format": PREFLIGHT_FORMAT,
        "audience": audience,
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
    }
