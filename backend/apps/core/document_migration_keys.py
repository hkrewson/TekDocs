"""Portable field-key binding metadata for a guarded legacy document copy."""

from __future__ import annotations

import uuid

from django.core.exceptions import ObjectDoesNotExist

from .content_profile import MAX_KEY_BINDINGS
from .document_key_fields import RESOLVABLE_RECORDS, resolvable_field
from .document_key_models import DocumentKeyBinding
from .document_keys import MAXIMUM_KEYS_PER_DOCUMENT, keys_in_markdown
from .models import Document


class DocumentMigrationKeyError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
            raise DocumentMigrationKeyError("content_key_parity_required")
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
            raise DocumentMigrationKeyError("content_key_parity_required")
        if resolvable_field(resolved_binding.target_entity.entity_type, key.path) is None:
            raise DocumentMigrationKeyError("key_binding_mapping_required")

    frontmatter = {name: str(binding.target_entity_id) for name, binding in sorted(names.items())}
    identities = tuple((name, binding.id, binding.target_entity_id) for name, binding in sorted(names.items()))
    return frontmatter, identities
