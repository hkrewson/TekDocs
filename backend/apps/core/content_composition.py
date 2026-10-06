"""Bounded deterministic expansion of repository-backed reusable fragments."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .content_index_models import ContentNodeKind
from .content_profile import ParsedContent, ParsedInclude

MAX_COMPOSITION_DEPTH = 12
MAX_COMPOSITION_NODES = 512
MAX_EXPANDED_BYTES = 4 * 1024 * 1024


class ContentCompositionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResolvedComposition:
    markdown: str
    digest: str
    manifest: tuple[dict[str, Any], ...]
    entity_links: tuple[dict[str, Any], ...]


SnapshotLoader = Callable[[str], dict[uuid.UUID, ParsedContent]]


class ContentCompositionResolver:
    def __init__(self, *, accepted_object_id: str, accepted: dict[uuid.UUID, ParsedContent], loader: SnapshotLoader):
        self.accepted_object_id = accepted_object_id
        self.accepted = accepted
        self.loader = loader

    def snapshot(self, object_id: str) -> dict[uuid.UUID, ParsedContent]:
        if object_id == self.accepted_object_id:
            return self.accepted
        return self.loader(object_id)

    def direct_target(self, *, context_object_id: str, include: ParsedInclude) -> tuple[str, ParsedContent]:
        object_id = include.pinned_object_id if include.mode == "pinned" else context_object_id
        target = self.snapshot(object_id).get(include.target_content_id)
        if target is None:
            raise ContentCompositionError("include.unresolved", "Include target is unavailable in its selected commit")
        if target.kind != ContentNodeKind.FRAGMENT:
            raise ContentCompositionError("include.kind", "Includes may target only reusable fragments")
        return object_id, target

    def resolve(self, *, content_id: uuid.UUID, audience: str | None) -> ResolvedComposition:
        root = self.accepted.get(content_id)
        if root is None:  # pragma: no cover - caller iterates the accepted snapshot
            raise ContentCompositionError("composition.root", "Composition root is unavailable")
        parts: list[str] = []
        manifest: list[dict[str, Any]] = []
        entity_links: list[dict[str, Any]] = []
        expanded_bytes = 0
        expanded_nodes = 0

        def visit(
            parsed: ParsedContent,
            *,
            object_id: str,
            depth: int,
            stack: tuple[tuple[str, uuid.UUID], ...],
            parent_audience: str | None,
            ordinal_path: tuple[int, ...],
        ) -> None:
            nonlocal expanded_bytes, expanded_nodes
            key = (object_id, parsed.content_id)
            if key in stack:
                raise ContentCompositionError("include.cycle", "Fragment composition contains a cycle")
            if depth > MAX_COMPOSITION_DEPTH:
                raise ContentCompositionError("include.depth", "Fragment composition exceeds its depth limit")
            expanded_nodes += 1
            if expanded_nodes > MAX_COMPOSITION_NODES:
                raise ContentCompositionError("include.limit", "Fragment composition exceeds its node limit")
            markdown = parsed.markdown.strip("\n")
            expanded_bytes += len(markdown.encode("utf-8"))
            if expanded_bytes > MAX_EXPANDED_BYTES:
                raise ContentCompositionError("include.size", "Fragment composition exceeds its expanded-size limit")
            if markdown:
                parts.append(markdown)
            for link in parsed.entity_links:
                entity_links.append(
                    {
                        "id": str(link.target_entity_id),
                        "relationship": link.relationship,
                        "origin": link.origin,
                        "source_id": str(parsed.content_id),
                        "commit": object_id,
                        "ordinal_path": list(ordinal_path) + [link.ordinal],
                    }
                )
            next_stack = stack + (key,)
            for include in parsed.includes:
                if parent_audience not in {None, "shared"} and include.audience != parent_audience:
                    raise ContentCompositionError(
                        "include.audience.widened", "A nested include cannot widen or change its parent audience"
                    )
                if audience is not None and include.audience not in {"shared", audience}:
                    continue
                target_object_id, target = self.direct_target(
                    context_object_id=object_id,
                    include=include,
                )
                target_path = ordinal_path + (include.ordinal,)
                manifest.append(
                    {
                        "audience": include.audience,
                        "commit": target_object_id,
                        "depth": depth + 1,
                        "digest": target.content_digest,
                        "id": str(target.content_id),
                        "mode": include.mode,
                        "ordinal_path": list(target_path),
                        "title": target.title,
                    }
                )
                visit(
                    target,
                    object_id=target_object_id,
                    depth=depth + 1,
                    stack=next_stack,
                    parent_audience=include.audience,
                    ordinal_path=target_path,
                )

        visit(
            root,
            object_id=self.accepted_object_id,
            depth=0,
            stack=(),
            parent_audience=None,
            ordinal_path=(),
        )
        markdown = "\n\n".join(parts)
        if markdown:
            markdown += "\n"
        if len(markdown.encode("utf-8")) > MAX_EXPANDED_BYTES:
            raise ContentCompositionError("include.size", "Fragment composition exceeds its expanded-size limit")
        payload = {"manifest": manifest, "markdown": markdown, "entity_links": entity_links}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ResolvedComposition(
            markdown=markdown,
            digest=digest,
            manifest=tuple(manifest),
            entity_links=tuple(entity_links),
        )
