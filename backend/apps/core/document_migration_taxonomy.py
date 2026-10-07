"""Read-only conversion of exact legacy document taxonomy selections."""

from __future__ import annotations

from .models import Document, DocumentTaxonomyTerm, TaxonomyTermStatus


class DocumentMigrationTaxonomyError(ValueError):
    pass


def portable_document_taxonomies(document: Document) -> dict[str, list[str]]:
    """Return stable keys only when every selected term is current and in scope."""

    selections = DocumentTaxonomyTerm.objects.filter(document=document).select_related(
        "taxonomy__current_version",
        "term__version",
        "local_term__taxonomy_version",
    )
    grouped: dict[str, set[str]] = {}
    for selection in selections:
        taxonomy = selection.taxonomy
        current = taxonomy.current_version
        if (
            selection.tenant_id != document.tenant_id
            or selection.organization_id != document.organization_id
            or taxonomy.tenant_id != document.tenant_id
            or taxonomy.archived_at is not None
            or current is None
            or current.tenant_id != document.tenant_id
            or current.taxonomy_id != taxonomy.id
        ):
            raise DocumentMigrationTaxonomyError("taxonomy_mapping_required")
        if selection.term_id is not None and selection.local_term_id is None:
            term = selection.term
            if (
                term is None
                or term.tenant_id != document.tenant_id
                or term.taxonomy_id != taxonomy.id
                or term.version_id != current.id
                or term.status != TaxonomyTermStatus.ACTIVE
            ):
                raise DocumentMigrationTaxonomyError("taxonomy_mapping_required")
            stable_key = term.stable_key
        elif selection.local_term_id is not None and selection.term_id is None:
            local = selection.local_term
            if (
                local is None
                or document.organization_id is None
                or local.tenant_id != document.tenant_id
                or local.organization_id != document.organization_id
                or local.taxonomy_id != taxonomy.id
                or local.taxonomy_version_id != current.id
                or local.archived_at is not None
                or not current.allow_local_terms
            ):
                raise DocumentMigrationTaxonomyError("taxonomy_mapping_required")
            stable_key = local.stable_key
        else:
            raise DocumentMigrationTaxonomyError("taxonomy_mapping_required")
        keys = grouped.setdefault(taxonomy.key, set())
        if stable_key in keys or len(keys) >= 64:
            raise DocumentMigrationTaxonomyError("taxonomy_mapping_required")
        keys.add(stable_key)
    return {taxonomy_key: sorted(keys) for taxonomy_key, keys in sorted(grouped.items())}
