"""Offline custody checks for native template leaves in signed publications."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from .content_profile import ContentProfileError, parse_content
from .document_keys import key_targets_in_markdown
from .publications import canonical_json
from .rendering import attachment_ids_in_markdown, entity_ids_in_markdown

NATIVE_TEMPLATE_EVIDENCE_FORMAT = 'tekdocs-repository-publication-evidence/v4'
NATIVE_TEMPLATE_DEPENDENCY_FORMAT = 'tekdocs.git-dependencies/v4'


def _uuid(value: str) -> bool:
    return str(UUID(value)) == value


def verify_native_template_evidence(manifest: dict[str, Any]) -> bool:
    """Verify retained source selection without current Git or enrollment reads.

    The enclosing signature supplies authenticity; this check proves the selected
    bytes, immutable template definition, and destination include agree.
    """
    try:
        source = manifest['source']
        if source['format'] != NATIVE_TEMPLATE_DEPENDENCY_FORMAT:
            return False
        root = parse_content(manifest['key_source']['source'].encode())
        foreign = [item for item in source['sources'] if 'library_workspace' in item]
        if not foreign or len(foreign) > 200:
            return False
        seen: set[tuple[int, ...]] = set()
        total = 0
        for record in foreign:
            definition = record['template_manifest']
            raw = record['selected_source'].encode()
            total += len(raw) + len(canonical_json(definition))
            if total > 8 * 1024 * 1024:
                return False
            path = tuple(record['ordinal_path'])
            if len(path) != 1 or type(path[0]) is not int or path in seen or path[0] < 0:
                return False
            seen.add(path)
            include = root.includes[path[0]]
            parsed = parse_content(raw)
            section = next(item for item in definition['sections'] if item['id'] == record['id'])
            template_root = parse_content(definition['root']['source'].encode())
            algorithm = record['object_format']
            digest = (hashlib.sha1(usedforsecurity=False) if algorithm == 'sha1' else hashlib.sha256())  # noqa: S324 -- Git identity
            digest.update(f'blob {len(raw)}\0'.encode())
            digest.update(raw)
            if (
                record.get('native_template') is not True or record.get('body_only') is not True
                or record['mode'] not in {'live', 'pinned'} or algorithm not in {'sha1', 'sha256'}
                or not all(_uuid(record[key]) for key in (
                    'id', 'library_workspace', 'repository_id', 'template_revision',
                ))
                or record['library_workspace'] == source['workspace_id']
                or record['repository_id'] == source['repository_id']
                or definition['format'] != 'tekdocs.native-template/v1'
                or definition['workspace_id'] != record['library_workspace']
                or definition['repository_id'] != record['repository_id']
                or (record['mode'] == 'pinned' and definition['commit'] != record['commit'])
                or hashlib.sha256(canonical_json(definition)).hexdigest() != record['template_checksum']
                or not re.fullmatch(r'[0-9a-f]{40}' if algorithm == 'sha1' else r'[0-9a-f]{64}', record['commit'])
                or (record['mode'] == 'live' and record['commit'] != record['accepted_commit'])
                or parsed.kind != 'fragment' or str(parsed.content_id) != record['id']
                or parsed.includes or parsed.template_sources or parsed.frontmatter.get('key_bindings')
                or parsed.entity_links or key_targets_in_markdown(parsed.markdown)
                or attachment_ids_in_markdown(parsed.markdown) or entity_ids_in_markdown(parsed.markdown)
                or record['source_sha256'] != hashlib.sha256(raw).hexdigest()
                or record['blob'] != digest.hexdigest() or record['content_digest'] != parsed.content_digest
                or section['source'] != record['selected_source'] or section['path'] != record['path']
                or section['body_sha256'] != hashlib.sha256(parsed.markdown.encode()).hexdigest()
                or template_root.kind != 'document'
                or str(template_root.content_id) != definition['content_id']
                or definition['root']['id'] != definition['content_id']
                or definition['root']['body_sha256'] != hashlib.sha256(template_root.markdown.encode()).hexdigest()
                or str(include.target_content_id) != record['id'] or include.mode != record['mode']
                or include.audience != record['audience']
                or str(include.library_workspace_id) != record['library_workspace']
                or str(include.library_revision_id) != record.get('enrollment_revision', record['template_revision'])
                or (include.mode == 'pinned' and include.pinned_object_id != record['commit'])
            ):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, StopIteration, ContentProfileError):
        return False
