"""Portable key bindings and content-source dependencies for guarded document copies."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import cast

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from .content_profile import MAX_KEY_BINDINGS
from .document_key_fields import RESOLVABLE_RECORDS, resolvable_field
from .document_key_freeze import MAXIMUM_CONTENT_KEY_DEPTH, MAXIMUM_FROZEN_MARKDOWN_BYTES
from .document_key_models import DocumentKeyBinding
from .document_keys import MAXIMUM_KEYS_PER_DOCUMENT, key_targets_in_markdown, keys_in_markdown
from .models import Block, Document, Workspace


class DocumentMigrationKeyError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def content_key_authority_edges(
    workspace: Workspace, document_ids: tuple[uuid.UUID, ...],
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """All configured block bindings remain live dependencies, including unused ones."""
    return list(DocumentKeyBinding.objects.filter(
        tenant_id=workspace.tenant_id, workspace=workspace,
        organization_id=cast(uuid.UUID, workspace.organization_id), archived_at__isnull=True,
        target_entity__entity_type="document_block",
    ).filter(
        Q(document_id__in=document_ids)
        | Q(target_entity__block_record__source_document_id__in=document_ids)
    ).values_list("document_id", "target_entity__block_record__source_document_id"))


def portable_content_key_sources(
    document: Document, markdown: str, *, source_markdown: Callable[[uuid.UUID], str] | None = None,
) -> tuple[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str], ...]:
    """Collect legacy revision identities; an accepted-body loader also validates Git edits."""
    root_keys, malformed = keys_in_markdown(markdown)
    if malformed or len(root_keys) > MAXIMUM_KEYS_PER_DOCUMENT:
        raise DocumentMigrationKeyError("key_binding_mapping_required")
    if not any(key.path == ("content",) for key in root_keys):
        return ()
    bindings = {
        binding.name: binding for binding in DocumentKeyBinding.objects.filter(
            document=document, archived_at__isnull=True,
        ).select_related("target_entity")
    }
    sources: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]] = {}
    expressions: set[str] = set()

    def visit(body: str, ancestry: tuple[uuid.UUID, ...] = ()) -> None:
        if len(ancestry) >= MAXIMUM_CONTENT_KEY_DEPTH or len(body.encode()) > MAXIMUM_FROZEN_MARKDOWN_BYTES:
            raise DocumentMigrationKeyError("content_key_limit_exceeded")
        keys, malformed = keys_in_markdown(body)
        targets = key_targets_in_markdown(body)
        expressions.update(key.expression for key in keys)
        if malformed or len(expressions) > MAXIMUM_KEYS_PER_DOCUMENT:
            raise DocumentMigrationKeyError("key_binding_mapping_required")
        for key in keys:
            binding = bindings.get(key.binding)
            if binding is None:
                raise DocumentMigrationKeyError("key_binding_mapping_required")
            if key.path != ("content",):
                if resolvable_field(binding.target_entity.entity_type, key.path) is None:
                    raise DocumentMigrationKeyError("key_binding_mapping_required")
                continue
            pattern = rf"(?m)^ {{0,3}}<{re.escape(key.target)}>[ \t]*(?:\n|$)"
            if len(re.findall(pattern, body)) != targets.count(key.target):
                raise DocumentMigrationKeyError("content_key_placement")
            block = Block.objects.select_related("current_revision").filter(
                entity=binding.target_entity, tenant_id=document.tenant_id,
                organization_id=cast(uuid.UUID, document.organization_id), archived_at__isnull=True,
            ).first()
            if block is None or block.current_revision is None:
                raise DocumentMigrationKeyError("content_key_source_unavailable")
            if block.id in ancestry:
                raise DocumentMigrationKeyError("content_key_cycle")
            revision = block.current_revision
            sources[block.id] = (binding.target_entity_id, block.id, revision.id, revision.checksum)
            visit(
                revision.markdown if source_markdown is None else source_markdown(block.id),
                (*ancestry, block.id),
            )

    visit(markdown)
    return tuple(sources[identity] for identity in sorted(sources))


def portable_document_keys(
    document: Document, markdown: str
) -> tuple[dict[str, str], tuple[tuple[str, uuid.UUID, uuid.UUID], ...]]:
    """Export identities, never resolved field values or access decisions."""

    records = list(
        DocumentKeyBinding.objects.filter(document=document, archived_at__isnull=True)
        .select_related("target_entity")
        .order_by("name", "id")
    )
    if len(records) > MAX_KEY_BINDINGS:
        raise DocumentMigrationKeyError("key_binding_limit_exceeded")
    names: dict[str, DocumentKeyBinding] = {}
    for binding in records:
        target = binding.target_entity
        if (
            binding.tenant_id != document.tenant_id
            or binding.workspace_id != document.entity.workspace_id
            or binding.organization_id != document.organization_id
            or target.tenant_id != document.tenant_id
            or target.workspace_id != document.entity.workspace_id
            or target.archived_at is not None
        ):
            raise DocumentMigrationKeyError("key_binding_scope_required")
        if target.entity_type == "document_block":
            if not Block.objects.filter(
                entity=target, tenant_id=document.tenant_id,
                organization_id=cast(uuid.UUID, document.organization_id), archived_at__isnull=True,
                source_document__entity__workspace_id=document.entity.workspace_id,
                source_document__archived_at__isnull=True,
            ).exists():
                raise DocumentMigrationKeyError("key_binding_mapping_required")
            names[binding.name] = binding
            continue
        specification = RESOLVABLE_RECORDS.get(target.entity_type)
        if specification is None:
            raise DocumentMigrationKeyError("key_binding_mapping_required")
        try:
            target_record = getattr(target, specification.record_accessor)
        except ObjectDoesNotExist as exc:
            raise DocumentMigrationKeyError("key_binding_mapping_required") from exc
        if getattr(target_record, "archived_at", None) is not None:
            raise DocumentMigrationKeyError("key_binding_mapping_required")
        if binding.name in names:
            raise DocumentMigrationKeyError("key_binding_mapping_required")
        names[binding.name] = binding

    keys, malformed = keys_in_markdown(markdown)
    if malformed or len(keys) > MAXIMUM_KEYS_PER_DOCUMENT:
        raise DocumentMigrationKeyError("key_binding_mapping_required")
    for key in keys:
        resolved_binding = names.get(key.binding)
        if resolved_binding is None:
            raise DocumentMigrationKeyError("key_binding_mapping_required")
        if key.path == ("content",):
            if resolved_binding.target_entity.entity_type != "document_block":
                raise DocumentMigrationKeyError("key_binding_mapping_required")
            continue
        if resolvable_field(resolved_binding.target_entity.entity_type, key.path) is None:
            raise DocumentMigrationKeyError("key_binding_mapping_required")

    frontmatter = {name: str(binding.target_entity_id) for name, binding in sorted(names.items())}
    identities = tuple((name, binding.id, binding.target_entity_id) for name, binding in sorted(names.items()))
    return frontmatter, identities
