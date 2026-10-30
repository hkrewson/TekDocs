"""Offline structural verification for signed shared-composition source proof."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from .content_composition import MAX_COMPOSITION_NODES
from .document_publication_files import verify_publication_file_manifest

SHARED_GIT_STATIC_FORMAT = "tekdocs-static-publication/v7"


def verify_shared_publication_manifest(manifest: dict[str, Any], document_id: UUID) -> bool:
    """Use only signed inputs: current placements, index and Git are not evidence."""
    try:
        source = manifest["git_source"]
        sources = source["sources"]
        object_pattern = r"[0-9a-f]{40}" if source["object_format"] == "sha1" else r"[0-9a-f]{64}"
        if source["object_format"] not in {"sha1", "sha256"} or not re.fullmatch(
            object_pattern,
            source["accepted_commit"],
        ):
            return False
        if not isinstance(sources, list) or not 2 <= len(sources) <= MAX_COMPOSITION_NODES:
            return False
        paths = []
        identities = set()
        for index, item in enumerate(sources):
            identity = UUID(item["id"])
            path = item["ordinal_path"]
            if (
                identity in identities
                or not isinstance(path, list)
                or any(type(value) is not int or value < 0 for value in path)
                or not re.fullmatch(object_pattern, item["commit"])
                or not re.fullmatch(object_pattern, item["blob"])
                or any(not re.fullmatch(r"[0-9a-f]{64}", item[key]) for key in ("source_sha256", "content_digest"))
            ):
                return False
            if index == 0:
                if (
                    identity != document_id
                    or path
                    or item["mode"] != "root"
                    or item["audience"] != "msp_internal"
                    or item["commit"] != source["accepted_commit"]
                    or item["path"] != f"docs/{document_id}.md"
                ):
                    return False
            elif (
                not path
                or item["mode"] not in {"live", "pinned"}
                or item["audience"] != "shared"
                or item["path"] != f"fragments/{identity}.md"
                or (item["mode"] == "live" and item["commit"] != source["accepted_commit"])
                or tuple(path[:-1]) not in paths
            ):
                return False
            identities.add(identity)
            paths.append(tuple(path))
        if paths != sorted(paths) or len(set(paths)) != len(paths):
            return False
        for parent in paths:
            ordinals = [path[-1] for path in paths if path and path[:-1] == parent]
            if ordinals != list(range(len(ordinals))):
                return False
        if manifest["managed_files"]:
            return verify_publication_file_manifest(manifest, document_id)
        return bool(
            manifest["managed_files"] == []
            and manifest["attachments"] == []
            and len(manifest["artifacts"]) == 1
            and manifest["artifacts"][0]["kind"] == "pdf"
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
