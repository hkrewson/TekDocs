"""Offline structural verification for signed shared-composition source proof."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from .content_composition import MAX_COMPOSITION_NODES
from .document_publication_files import verify_publication_file_manifest

SHARED_GIT_STATIC_FORMAT = "tekdocs-static-publication/v7"
TEMPLATE_GIT_STATIC_FORMAT = "tekdocs-static-publication/v8"


def verify_shared_publication_manifest(manifest: dict[str, Any], document_id: UUID) -> bool:
    """Use only signed inputs: current placements, index and Git are not evidence."""
    return _verify_shared_manifest(manifest, document_id, library=False)


def verify_template_publication_manifest(manifest: dict[str, Any], document_id: UUID) -> bool:
    return _verify_shared_manifest(manifest, document_id, library=True)


def _verify_shared_manifest(manifest: dict[str, Any], document_id: UUID, *, library: bool) -> bool:
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
        foreign_count = 0
        identities = set()
        for index, item in enumerate(sources):
            identity = UUID(item["id"])
            path = item["ordinal_path"]
            foreign = library and "library_workspace" in item
            source_pattern = object_pattern
            namespace = source["workspace_id"]
            if foreign:
                if index == 0:
                    return False
                namespace = str(UUID(item["library_workspace"]))
                UUID(item["repository_id"])
                revision_id = UUID(item["template_revision"])
                if namespace == source["workspace_id"] or item["object_format"] not in {"sha1", "sha256"}:
                    return False
                source_pattern = r"[0-9a-f]{40}" if item["object_format"] == "sha1" else r"[0-9a-f]{64}"
                if (not re.fullmatch(source_pattern, item["accepted_commit"])
                    or not re.fullmatch(r"[0-9a-f]{64}", item["template_checksum"])
                    or item["body_only"] is not True
                    or (item["mode"] == "live" and item["commit"] != item["accepted_commit"])):
                    return False
                foreign_count += 1
            key = (namespace, identity)
            if (
                key in identities
                or not isinstance(path, list)
                or any(type(value) is not int or value < 0 for value in path)
                or not re.fullmatch(source_pattern, item["commit"])
                or not re.fullmatch(source_pattern, item["blob"])
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
                or item["path"] not in (
                    {f"fragments/{identity}.md", f"template-snapshots/{revision_id}/fragments/{identity}.content"}
                    if foreign and item["mode"] == "pinned" else {f"fragments/{identity}.md"}
                )
                or (not foreign and item["mode"] == "live" and item["commit"] != source["accepted_commit"])
                or tuple(path[:-1]) not in paths
            ):
                return False
            identities.add(key)
            paths.append(tuple(path))
        if library:
            certificate = manifest.get("template_source")
            if certificate is not None:
                if (manifest["workspace"] != {"kind": "msp", "id": None}
                    or foreign_count or not isinstance(certificate, dict)
                    or set(certificate) != {"content_id", "revision", "checksum"}
                    or UUID(certificate["content_id"]) != document_id
                    or not re.fullmatch(r"[0-9a-f]{64}", certificate["checksum"])):
                    return False
                UUID(certificate["revision"])
            if (foreign_count == 0 and certificate is None) or source["format"] != "tekdocs.git-dependencies/v2":
                return False
        if library and any(
            child["ordinal_path"][:len(item["ordinal_path"])] == item["ordinal_path"]
            and len(child["ordinal_path"]) > len(item["ordinal_path"])
            for item in sources if "library_workspace" in item for child in sources
        ):
            return False
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
