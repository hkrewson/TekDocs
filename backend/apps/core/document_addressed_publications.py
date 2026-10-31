"""Verify retained field-key and entity-card proof without live record reads."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from .content_profile import MAX_KEY_BINDINGS
from .document_key_freeze import verify_frozen_field_keys
from .document_keys import key_targets_in_markdown
from .document_shared_publications import verify_shared_publication_manifest, verify_template_publication_manifest
from .rendering import entity_ids_in_markdown

ADDRESSED_GIT_STATIC_FORMAT = "tekdocs-static-publication/v9"


def verify_addressed_publication_manifest(manifest: dict[str, Any], document_id: UUID, markdown: str) -> bool:
    """The signed authored source, binding map and frozen projection must agree."""
    try:
        authored = manifest["authored_markdown"]
        bindings = manifest["key_bindings"]
        snapshot = manifest["key_snapshot"]
        cards = manifest["entities"]
        if (
            not isinstance(authored, str)
            or len(authored.encode()) > 2 * 1024 * 1024
            or not isinstance(bindings, dict)
            or len(bindings) > MAX_KEY_BINDINGS
            or not isinstance(cards, list)
            or len(cards) > 200
            or (snapshot is None and not cards)
            or manifest["git_source"]["markdown_sha256"] != hashlib.sha256(authored.encode()).hexdigest()
        ):
            return False
        for name, target in bindings.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name):
                return False
            if not isinstance(target, str) or str(UUID(target)) != target:
                return False
        if snapshot is None:
            if key_targets_in_markdown(authored) or markdown != authored or manifest["key_resolutions"] != []:
                return False
        elif (
            not verify_frozen_field_keys(authored, snapshot)
            or markdown != snapshot["markdown"]
            or manifest["key_resolutions"] != snapshot["records"]
            or any(
                record["source_entity_id"] != bindings.get(record["expression"].split(".", 1)[0])
                or record["resolved_at"] != manifest["published_at"]
                for record in snapshot["records"]
            )
        ):
            return False
        identities = []
        for card in cards:
            if (
                not isinstance(card, dict)
                or set(card) != {"id", "display_name", "entity_type", "workspace_label"}
                or any(not isinstance(value, str) or not value for value in card.values())
            ):
                return False
            identities.append(UUID(card["id"]))
        if len(set(identities)) != len(identities) or set(identities) != entity_ids_in_markdown(markdown):
            return False
        if manifest["git_source"]["format"] == "tekdocs.git-dependencies/v2":
            return verify_template_publication_manifest(manifest, document_id)
        return bool(
            manifest["git_source"]["format"] == "tekdocs.git-dependencies/v1"
            and verify_shared_publication_manifest(manifest, document_id)
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
