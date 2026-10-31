"""Offline reconstruction of signed Git content substitutions, without live reads."""

from __future__ import annotations

import hashlib
import re
from functools import partial
from typing import Any
from uuid import UUID

from .content_profile import ContentProfileError, parse_content
from .document_key_freeze import (
    MAXIMUM_CONTENT_KEY_DEPTH,
    MAXIMUM_FROZEN_MARKDOWN_BYTES,
    _literal_replacement,
    _replace_key_autolinks,
    _safe_inline_value,
)
from .document_keys import MAXIMUM_KEYS_PER_DOCUMENT, key_targets_in_markdown, keys_in_markdown

CONTENT_KEY_GIT_STATIC_FORMAT = "tekdocs-static-publication/v10"


def verify_frozen_content_keys(markdown: str, snapshot: Any) -> bool:
    """Require an exact, bounded reconstruction using every retained resolution."""
    try:
        if not isinstance(snapshot, dict) or set(snapshot) != {"markdown", "sha256", "records"}:
            return False
        records = snapshot["records"]
        if not isinstance(records, list) or not 1 <= len(records) <= MAXIMUM_KEYS_PER_DOCUMENT:
            return False
        by_expression = {item["expression"]: item for item in records}
        if len(by_expression) != len(records) or list(by_expression) != sorted(by_expression):
            return False
        used: set[str] = set()
        content_seen = False

        def expand(body: str, ancestry: tuple[str, ...] = ()) -> str:
            nonlocal content_seen
            if len(ancestry) >= MAXIMUM_CONTENT_KEY_DEPTH:
                raise ValueError("content depth")
            keys, malformed = keys_in_markdown(body)
            if malformed:
                raise ValueError("invalid key")
            replacements = {}
            expanded = body
            for key in keys:
                record = by_expression[key.expression]
                used.add(key.expression)
                if key.path != ("content",):
                    if record["kind"] != "field" or "git_source" in record:
                        raise ValueError("field proof")
                    replacements[key.target] = _safe_inline_value(record["value"])
                    continue
                content_seen = True
                entity = str(UUID(record["source_entity_id"]))
                chain = (*ancestry, entity)
                proof = record["git_source"]
                if (
                    record["kind"] != "content" or record["source_entity_type"] != "document_block"
                    or entity in ancestry or record["dependency_chain"] != list(chain)
                    or record["source_revision_id"] is not None or record["source_revision_number"] is not None
                    or set(proof) != {
                        "content_id", "workspace_id", "repository_id", "commit", "object_format",
                        "blob", "path", "source",
                    }
                ):
                    raise ValueError("content proof")
                for identity in ("content_id", "workspace_id", "repository_id"):
                    if str(UUID(proof[identity])) != proof[identity]:
                        raise ValueError("identity")
                pattern = {"sha1": r"[0-9a-f]{40}", "sha256": r"[0-9a-f]{64}"}[proof["object_format"]]
                if not re.fullmatch(pattern, proof["commit"]) or not re.fullmatch(pattern, proof["blob"]):
                    raise ValueError("object")
                raw = proof["source"].encode("utf-8")
                if len(raw) > MAXIMUM_FROZEN_MARKDOWN_BYTES:
                    raise ValueError("source size")
                digest = (
                    hashlib.sha1(usedforsecurity=False)  # noqa: S324  # nosec B324 -- Git object identity
                    if proof["object_format"] == "sha1" else hashlib.sha256()
                )
                digest.update(f"blob {len(raw)}\0".encode())
                digest.update(raw)
                parsed = parse_content(raw)
                if (
                    digest.hexdigest() != proof["blob"] or parsed.kind != "fragment"
                    or str(parsed.content_id) != proof["content_id"]
                    or proof["path"] != f"fragments/{parsed.content_id}.md"
                    or record["value"] != parsed.markdown
                    or record["source_fingerprint"] != hashlib.sha256(parsed.markdown.encode()).hexdigest()
                ):
                    raise ValueError("source mismatch")
                child = expand(parsed.markdown, chain)
                pattern = rf"(?m)^ {{0,3}}<{re.escape(key.target)}>[ \t]*(?:\n|$)"
                expanded, count = re.subn(
                    pattern, partial(_literal_replacement, value=child.rstrip("\n") + "\n"), expanded,
                )
                if count != key_targets_in_markdown(body).count(key.target):
                    raise ValueError("content placement")
            expanded = _replace_key_autolinks(expanded, replacements)
            if len(expanded.encode()) > MAXIMUM_FROZEN_MARKDOWN_BYTES:
                raise ValueError("expanded size")
            return expanded

        frozen = expand(markdown)
        return bool(
            content_seen and used == set(by_expression) and frozen == snapshot["markdown"]
            and hashlib.sha256(frozen.encode()).hexdigest() == snapshot["sha256"]
            and not key_targets_in_markdown(frozen)
        )
    except (KeyError, TypeError, ValueError, AttributeError, ContentProfileError):
        return False
