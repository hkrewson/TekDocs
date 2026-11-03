"""Offline verification of native binding inputs and frozen Git content keys."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from .content_profile import ContentProfileError, parse_content
from .document_content_key_publications import verify_frozen_content_keys
from .document_key_freeze import verify_frozen_field_keys
from .document_keys import key_targets_in_markdown
from .repository_key_context import canonical_key_bindings

NATIVE_KEY_EVIDENCE_FORMAT = 'tekdocs-repository-publication-evidence/v3'
MAX_NATIVE_KEY_SOURCE_BYTES = 8 * 1024 * 1024


def verify_native_key_evidence(markdown: str, manifest: dict[str, Any]) -> bool:
    """Bind declarations to retained root bytes and every used resolution, without live reads."""
    try:
        source = manifest['source']
        retained = manifest['key_source']
        if set(retained) != {'source', 'path', 'blob'}:
            return False
        raw = retained['source'].encode('utf-8')
        if len(raw) > 2 * 1024 * 1024:
            return False
        parsed = parse_content(raw)
        root = source['sources'][0]
        algorithm = source['object_format']
        digest = (hashlib.sha1(usedforsecurity=False) if algorithm == 'sha1' else hashlib.sha256())  # noqa: S324 -- Git identity
        digest.update(f'blob {len(raw)}\0'.encode())
        digest.update(raw)
        if (
            algorithm not in {'sha1', 'sha256'} or parsed.kind != 'document'
            or str(parsed.content_id) != manifest['content_id']
            or root['id'] != manifest['content_id'] or root['ordinal_path'] != []
            or root['commit'] != manifest['source_commit']
            or retained['path'] != root['path'] or retained['blob'] != root['blob']
            or retained['blob'] != digest.hexdigest()
            or root['source_sha256'] != hashlib.sha256(raw).hexdigest()
            or root['content_digest'] != parsed.content_digest
            or manifest['key_bindings'] != canonical_key_bindings(parsed.frontmatter.get('key_bindings', {}))
        ):
            return False
        snapshot = manifest.get('key_snapshot')
        if snapshot is None:
            return not key_targets_in_markdown(markdown)
        if not (
            verify_frozen_field_keys(markdown, snapshot)
            or verify_frozen_content_keys(markdown, snapshot, allow_native_fragments=True)
        ):
            return False
        source_bytes = len(raw)
        for record in snapshot['records']:
            identity = record['source_entity_id']
            name = record['expression'].split('.', 1)[0]
            if (
                manifest['key_bindings'].get(name) != identity
                or str(UUID(identity)) != identity
                or not re.fullmatch(r'[0-9a-f]{64}', record['source_fingerprint'])
                or record['resolved_at'] != manifest['signed_at']
                or record['provenance'] not in {'local', 'observed'}
            ):
                return False
            if record['kind'] == 'content':
                if record['source_entity_type'] != 'repository_fragment':
                    return False
                proof = record['git_source']
                source_bytes += len(proof['source'].encode('utf-8'))
                if source_bytes > MAX_NATIVE_KEY_SOURCE_BYTES:
                    return False
                if (
                    proof['repository_id'] != manifest['repository_id']
                    or proof['workspace_id'] != manifest['workspace_id']
                    or proof['commit'] != manifest['source_commit']
                    or proof['object_format'] != algorithm
                    or (record['source_entity_type'] == 'repository_fragment' and proof['content_id'] != identity)
                ):
                    return False
            elif record['kind'] != 'field' or record['dependency_chain'] != []:
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, ContentProfileError):
        return False
