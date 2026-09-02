from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    AuditEvent,
    Document,
    DocumentTaxonomyTerm,
    Organization,
    OrganizationTaxonomyTerm,
    Taxonomy,
    TaxonomyBinding,
    TaxonomyTerm,
    TaxonomyTermStatus,
    TaxonomyVersion,
    Tenant,
)

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class TaxonomyError(ValueError):
    pass


def _plain(value: str, *, name: str, maximum: int, required: bool = True) -> str:
    cleaned = " ".join(value.split())
    if (required and not cleaned) or len(cleaned) > maximum or any(ord(character) < 32 for character in cleaned):
        requirement = "1 to " if required else "at most "
        raise TaxonomyError(f"{name} must be plain text of {requirement}{maximum} characters.")
    return cleaned


def _key(value: str, *, name: str = "Key") -> str:
    cleaned = value.strip().lower()
    if not KEY_PATTERN.fullmatch(cleaned):
        raise TaxonomyError(f"{name} must begin with a letter and use lowercase letters, numbers, and hyphens.")
    return cleaned


def _normalized_alias(value: str) -> str:
    return _plain(value, name="Alias", maximum=120).casefold()


def _validate_terms(raw_terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not raw_terms:
        raise TaxonomyError("A taxonomy requires at least one term.")
    if len(raw_terms) > 500:
        raise TaxonomyError("A taxonomy may contain at most 500 terms.")
    normalized: list[dict[str, Any]] = []
    keys: set[str] = set()
    names: dict[str, str] = {}
    for position, raw in enumerate(raw_terms):
        stable_key = _key(str(raw.get("stable_key", "")), name="Term key")
        if stable_key in keys:
            raise TaxonomyError(f"Term key '{stable_key}' appears more than once.")
        keys.add(stable_key)
        label = _plain(str(raw.get("label", "")), name="Term label", maximum=120)
        aliases: list[str] = []
        for candidate in raw.get("aliases", []):
            alias = _plain(str(candidate), name="Alias", maximum=120)
            folded = alias.casefold()
            if folded not in {item.casefold() for item in aliases}:
                aliases.append(alias)
        for candidate in [label, stable_key, *aliases]:
            folded = candidate.casefold()
            owner = names.get(folded)
            if owner is not None and owner != stable_key:
                raise TaxonomyError(f"'{candidate}' is already used by term '{owner}'.")
            names[folded] = stable_key
        status = str(raw.get("status", TaxonomyTermStatus.ACTIVE))
        if status not in TaxonomyTermStatus.values:
            raise TaxonomyError("Term status must be active or retired.")
        normalized.append(
            {
                "stable_key": stable_key,
                "label": label,
                "description": _plain(
                    str(raw.get("description", "")), name="Term description", maximum=500, required=False
                ),
                "parent_key": str(raw.get("parent_key", "")).strip().lower(),
                "aliases": aliases,
                "status": status,
                "replacement_key": str(raw.get("replacement_key", "")).strip().lower(),
                "sort_order": int(raw.get("sort_order", position)),
            }
        )
    by_key = {item["stable_key"]: item for item in normalized}
    for item in normalized:
        parent = item["parent_key"]
        replacement = item["replacement_key"]
        if parent and (parent not in by_key or parent == item["stable_key"]):
            raise TaxonomyError(f"Parent term '{parent}' is unavailable.")
        if replacement and (
            replacement not in by_key
            or replacement == item["stable_key"]
            or item["status"] != TaxonomyTermStatus.RETIRED
            or by_key[replacement]["status"] != TaxonomyTermStatus.ACTIVE
        ):
            raise TaxonomyError("A retired term replacement must identify another active term.")
    for item in normalized:
        seen = {item["stable_key"]}
        parent = item["parent_key"]
        while parent:
            if parent in seen:
                raise TaxonomyError("Term hierarchy contains a cycle.")
            seen.add(parent)
            parent = by_key[parent]["parent_key"]
    return normalized


@transaction.atomic
def create_taxonomy(
    *,
    tenant: Tenant,
    actor_id: UUID,
    key: str,
    binding: str,
    label: str,
    description: str,
    allow_local_terms: bool,
    terms: list[dict[str, Any]],
) -> Taxonomy:
    if binding not in TaxonomyBinding.values:
        raise TaxonomyError("Taxonomy binding is unavailable.")
    stable_key = _key(key, name="Taxonomy key")
    if Taxonomy.objects.filter(tenant=tenant, key=stable_key).exists():
        raise TaxonomyError("A taxonomy already uses this key.")
    taxonomy = Taxonomy.objects.create(tenant=tenant, key=stable_key, binding=binding)
    _create_version(
        taxonomy=taxonomy,
        actor_id=actor_id,
        label=label,
        description=description,
        allow_local_terms=allow_local_terms,
        raw_terms=terms,
    )
    AuditEvent.objects.create(tenant=tenant, actor_id=actor_id, action="taxonomy.created", metadata={})
    return taxonomy


def _create_version(
    *,
    taxonomy: Taxonomy,
    actor_id: UUID,
    label: str,
    description: str,
    allow_local_terms: bool,
    raw_terms: list[dict[str, Any]],
) -> TaxonomyVersion:
    terms = _validate_terms(raw_terms)
    version_number = (taxonomy.versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
    version = TaxonomyVersion.objects.create(
        tenant=taxonomy.tenant,
        taxonomy=taxonomy,
        version=version_number,
        label=_plain(label, name="Taxonomy label", maximum=120),
        description=_plain(description, name="Taxonomy description", maximum=500, required=False),
        allow_local_terms=allow_local_terms,
        created_by_id=actor_id,
    )
    created: dict[str, TaxonomyTerm] = {}
    pending = list(terms)
    while pending:
        ready = [item for item in pending if not item["parent_key"] or item["parent_key"] in created]
        for item in ready:
            created[item["stable_key"]] = TaxonomyTerm.objects.create(
                tenant=taxonomy.tenant,
                taxonomy=taxonomy,
                version=version,
                stable_key=item["stable_key"],
                label=item["label"],
                description=item["description"],
                parent=created.get(item["parent_key"]),
                aliases=item["aliases"],
                status=item["status"],
                replacement_key=item["replacement_key"],
                sort_order=item["sort_order"],
            )
            pending.remove(item)
    taxonomy.current_version = version
    taxonomy.save(update_fields=("current_version", "updated_at"))
    local_terms = OrganizationTaxonomyTerm.objects.filter(taxonomy=taxonomy, archived_at__isnull=True)
    if allow_local_terms:
        local_terms.update(taxonomy_version=version, updated_at=timezone.now())
    else:
        local_terms.update(archived_at=timezone.now(), updated_at=timezone.now())
    return version


@transaction.atomic
def revise_taxonomy(
    *,
    taxonomy: Taxonomy,
    actor_id: UUID,
    label: str,
    description: str,
    allow_local_terms: bool,
    terms: list[dict[str, Any]],
) -> Taxonomy:
    locked = Taxonomy.objects.select_for_update().get(id=taxonomy.id, tenant=taxonomy.tenant)
    if locked.archived_at is not None:
        raise TaxonomyError("Archived taxonomies cannot be revised.")
    previous_keys = (
        set(locked.current_version.terms.values_list("stable_key", flat=True)) if locked.current_version else set()
    )
    next_keys = {_key(str(item.get("stable_key", "")), name="Term key") for item in terms}
    missing_keys = sorted(previous_keys - next_keys)
    if missing_keys:
        raise TaxonomyError(
            f"Terms cannot be removed from a version. Retire these terms instead: {', '.join(missing_keys)}."
        )
    _create_version(
        taxonomy=locked,
        actor_id=actor_id,
        label=label,
        description=description,
        allow_local_terms=allow_local_terms,
        raw_terms=terms,
    )
    AuditEvent.objects.create(tenant=locked.tenant, actor_id=actor_id, action="taxonomy.revised", metadata={})
    return locked


@transaction.atomic
def archive_taxonomy(*, taxonomy: Taxonomy, actor_id: UUID) -> None:
    Taxonomy.objects.select_for_update().filter(id=taxonomy.id, archived_at__isnull=True).update(
        archived_at=timezone.now(), updated_at=timezone.now()
    )
    AuditEvent.objects.create(tenant=taxonomy.tenant, actor_id=actor_id, action="taxonomy.archived", metadata={})


def taxonomy_queryset(tenant: Tenant, *, include_archived: bool = False):  # type: ignore[no-untyped-def]
    queryset = (
        Taxonomy.objects.filter(tenant=tenant)
        .select_related("current_version")
        .prefetch_related("versions", "current_version__terms", "current_version__terms__parent")
    )
    if not include_archived:
        queryset = queryset.filter(archived_at__isnull=True)
    return queryset.order_by("current_version__label", "key")


def serialize_taxonomy(taxonomy: Taxonomy, *, organization: Organization | None = None) -> dict[str, Any]:
    version = taxonomy.current_version
    if version is None:
        raise TaxonomyError("Taxonomy has no current version.")
    global_term_impact = {
        row["term__stable_key"]: {"documents": row["documents"], "templates": row["templates"]}
        for row in DocumentTaxonomyTerm.objects.filter(taxonomy=taxonomy, term__isnull=False)
        .values("term__stable_key")
        .annotate(
            documents=Count("document", distinct=True),
            templates=Count("document", filter=Q(document__is_template=True), distinct=True),
        )
    }
    terms: list[dict[str, Any]] = [
        {
            "id": str(term.id),
            "stable_key": term.stable_key,
            "label": term.label,
            "description": term.description,
            "parent_key": term.parent.stable_key if term.parent is not None else "",
            "aliases": term.aliases,
            "status": term.status,
            "replacement_key": term.replacement_key,
            "sort_order": term.sort_order,
            "local": False,
            "impact": global_term_impact.get(term.stable_key, {"documents": 0, "templates": 0}),
        }
        for term in version.terms.all()
    ]
    if organization is not None and version.allow_local_terms:
        terms.extend(
            {
                "id": str(term.id),
                "stable_key": term.stable_key,
                "label": term.label,
                "description": term.description,
                "parent_key": "",
                "aliases": term.aliases,
                "status": TaxonomyTermStatus.ACTIVE,
                "replacement_key": "",
                "sort_order": len(terms) + position,
                "local": True,
                "impact": DocumentTaxonomyTerm.objects.filter(local_term=term).aggregate(
                    documents=Count("document", distinct=True),
                    templates=Count("document", filter=Q(document__is_template=True), distinct=True),
                ),
            }
            for position, term in enumerate(
                OrganizationTaxonomyTerm.objects.filter(
                    tenant=taxonomy.tenant,
                    organization=organization,
                    taxonomy=taxonomy,
                    archived_at__isnull=True,
                ).order_by("label", "stable_key")
            )
        )
    impact = DocumentTaxonomyTerm.objects.filter(taxonomy=taxonomy).aggregate(
        documents=Count("document", distinct=True),
        templates=Count("document", filter=Q(document__is_template=True), distinct=True),
    )
    return {
        "id": str(taxonomy.id),
        "key": taxonomy.key,
        "binding": taxonomy.binding,
        "archived": taxonomy.archived_at is not None,
        "current_version": {
            "id": str(version.id),
            "version": version.version,
            "label": version.label,
            "description": version.description,
            "allow_local_terms": version.allow_local_terms,
            "created_at": version.created_at,
            "terms": terms,
        },
        "versions": [
            {"id": str(item.id), "version": item.version, "label": item.label, "created_at": item.created_at}
            for item in taxonomy.versions.all()
        ],
        "impact": {"documents": impact["documents"], "templates": impact["templates"]},
    }


def document_term_records(document: Document) -> list[DocumentTaxonomyTerm]:
    return list(
        DocumentTaxonomyTerm.objects.filter(document=document)
        .select_related("taxonomy", "term", "term__version", "local_term", "local_term__taxonomy_version")
        .order_by("taxonomy__key", "term__sort_order", "term__label", "local_term__label")
    )


def document_taxonomy_manifest(document: Document) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    labels: dict[tuple[str, int], str] = {}
    for assignment in document_term_records(document):
        selected = assignment.term or assignment.local_term
        if selected is None:
            continue
        if assignment.term is not None:
            version = assignment.term.version
        elif assignment.local_term is not None:
            version = assignment.local_term.taxonomy_version
        else:
            continue
        key = (assignment.taxonomy.key, version.version)
        labels[key] = version.label
        grouped[key].append(
            {
                "key": selected.stable_key,
                "label": selected.label,
                **({"local": True} if assignment.local_term_id is not None else {}),
            }
        )
    return [
        {
            "taxonomy_key": key,
            "taxonomy_version": version,
            "label": labels[(key, version)],
            "terms": grouped[(key, version)],
        }
        for key, version in sorted(grouped)
    ]


def document_tag_labels(document: Document) -> list[str]:
    labels = [
        selected.label
        for assignment in document_term_records(document)
        if (selected := assignment.term or assignment.local_term) is not None
    ]
    return list(dict.fromkeys([*document.tags, *labels]))


@transaction.atomic
def assign_document_terms(*, document: Document, term_ids: list[UUID], actor_id: UUID) -> None:
    if len(term_ids) > 20 or len(set(term_ids)) != len(term_ids):
        raise TaxonomyError("Choose at most 20 distinct taxonomy terms.")
    requested_ids = set(term_ids)
    existing_assignments = list(DocumentTaxonomyTerm.objects.filter(document=document))
    existing_global_ids = {assignment.term_id for assignment in existing_assignments if assignment.term_id}
    existing_local_ids = {assignment.local_term_id for assignment in existing_assignments if assignment.local_term_id}
    terms = list(
        TaxonomyTerm.objects.filter(
            id__in=term_ids,
            tenant=document.tenant,
            taxonomy__binding=TaxonomyBinding.DOCUMENT_TAGS,
        ).select_related("taxonomy", "version")
    )
    global_ids = {term.id for term in terms}
    local_terms = list(
        OrganizationTaxonomyTerm.objects.filter(
            id__in=requested_ids - global_ids,
            tenant=document.tenant,
            organization=document.organization,
            taxonomy__binding=TaxonomyBinding.DOCUMENT_TAGS,
        ).select_related("taxonomy", "taxonomy_version")
    )
    global_available = all(
        term.id in existing_global_ids
        or (
            term.status == TaxonomyTermStatus.ACTIVE
            and term.taxonomy.archived_at is None
            and term.taxonomy.current_version_id == term.version_id
        )
        for term in terms
    )
    local_available = all(
        term.id in existing_local_ids
        or (
            term.archived_at is None
            and term.taxonomy.archived_at is None
            and term.taxonomy.current_version_id == term.taxonomy_version_id
            and term.taxonomy_version.allow_local_terms
        )
        for term in local_terms
    )
    if len(terms) + len(local_terms) != len(term_ids) or not global_available or not local_available:
        raise TaxonomyError("One or more selected terms are unavailable or retired.")
    stable_selections = [(term.taxonomy_id, term.stable_key) for term in terms] + [
        (term.taxonomy_id, term.stable_key) for term in local_terms
    ]
    if len(stable_selections) != len(set(stable_selections)):
        raise TaxonomyError("Choose only one version of each taxonomy term.")
    retained_assignment_ids = {
        assignment.id
        for assignment in existing_assignments
        if assignment.term_id in requested_ids or assignment.local_term_id in requested_ids
    }
    DocumentTaxonomyTerm.objects.filter(document=document).exclude(id__in=retained_assignment_ids).delete()
    DocumentTaxonomyTerm.objects.bulk_create(
        [
            DocumentTaxonomyTerm(
                tenant=document.tenant,
                organization=document.organization,
                document=document,
                taxonomy=term.taxonomy,
                term=term,
            )
            for term in terms
            if term.id not in existing_global_ids
        ]
        + [
            DocumentTaxonomyTerm(
                tenant=document.tenant,
                organization=document.organization,
                document=document,
                taxonomy=term.taxonomy,
                local_term=term,
            )
            for term in local_terms
            if term.id not in existing_local_ids
        ]
    )
    AuditEvent.objects.create(
        tenant=document.tenant,
        actor_id=actor_id,
        action="document.taxonomy_terms_updated",
        metadata={"term_count": len(terms) + len(local_terms)},
    )


@transaction.atomic
def copy_document_taxonomy_terms(*, source: Document, destination: Document, actor_id: UUID) -> None:
    assignments = document_term_records(source)
    if any(
        assignment.local_term_id is not None and source.organization_id != destination.organization_id
        for assignment in assignments
    ):
        raise TaxonomyError("Client-local taxonomy terms cannot be copied into another client workspace.")
    selected_ids: list[UUID] = []
    for assignment in assignments:
        if assignment.local_term_id is not None:
            selected_ids.append(assignment.local_term_id)
            continue
        if assignment.term is None:
            continue
        term = assignment.term
        if term.version_id != assignment.taxonomy.current_version_id or term.status != TaxonomyTermStatus.ACTIVE:
            target_key = term.replacement_key or term.stable_key
            replacement = TaxonomyTerm.objects.filter(
                taxonomy=assignment.taxonomy,
                version_id=assignment.taxonomy.current_version_id,
                stable_key=target_key,
                status=TaxonomyTermStatus.ACTIVE,
            ).first()
            if replacement is None:
                raise TaxonomyError(f"Template term '{term.label}' has no active current replacement.")
            term = replacement
        selected_ids.append(term.id)
    assign_document_terms(document=destination, term_ids=selected_ids, actor_id=actor_id)


@transaction.atomic
def create_local_term(
    *,
    tenant: Tenant,
    organization: Organization,
    taxonomy: Taxonomy,
    actor_id: UUID,
    stable_key: str,
    label: str,
    description: str,
    aliases: list[str],
) -> OrganizationTaxonomyTerm:
    locked = Taxonomy.objects.select_for_update().get(id=taxonomy.id, tenant=tenant)
    version = (
        TaxonomyVersion.objects.get(id=locked.current_version_id) if locked.current_version_id is not None else None
    )
    if locked.archived_at is not None or version is None or not version.allow_local_terms:
        raise TaxonomyError("This taxonomy does not allow client-local terms.")
    key = _key(stable_key, name="Term key")
    cleaned_label = _plain(label, name="Term label", maximum=120)
    cleaned_aliases = list(dict.fromkeys(_plain(value, name="Alias", maximum=120) for value in aliases))
    requested_names = {value.casefold() for value in [key, cleaned_label, *cleaned_aliases]}
    for msp_term in version.terms.all():
        if requested_names.intersection(
            value.casefold() for value in [msp_term.stable_key, msp_term.label, *msp_term.aliases]
        ):
            raise TaxonomyError("The local term key, label, or alias is already governed by the MSP taxonomy.")
    for existing_local_term in OrganizationTaxonomyTerm.objects.filter(
        tenant=tenant, organization=organization, taxonomy=locked, archived_at__isnull=True
    ):
        if requested_names.intersection(
            value.casefold()
            for value in [
                existing_local_term.stable_key,
                existing_local_term.label,
                *existing_local_term.aliases,
            ]
        ):
            raise TaxonomyError("The local term key, label, or alias is already in use.")
    created_term = OrganizationTaxonomyTerm.objects.create(
        tenant=tenant,
        organization=organization,
        taxonomy=locked,
        taxonomy_version=version,
        stable_key=key,
        label=cleaned_label,
        description=_plain(description, name="Term description", maximum=500, required=False),
        aliases=cleaned_aliases,
        created_by_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="taxonomy.local_term_created",
        entity_id=organization.entity_id,
        metadata={"taxonomy_key": locked.key, "term_key": key},
    )
    return created_term


def migration_preview(*, tenant: Tenant) -> dict[str, Any]:
    lookup: dict[str, list[TaxonomyTerm]] = defaultdict(list)
    terms = TaxonomyTerm.objects.filter(
        tenant=tenant,
        taxonomy__binding=TaxonomyBinding.DOCUMENT_TAGS,
        taxonomy__archived_at__isnull=True,
        status=TaxonomyTermStatus.ACTIVE,
        version__current_for__isnull=False,
    ).select_related("taxonomy", "version")
    for term in terms:
        for name in [term.stable_key, term.label, *term.aliases]:
            lookup[_normalized_alias(str(name))].append(term)
    rows = []
    counts = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    for document in Document.objects.filter(tenant=tenant, archived_at__isnull=True).select_related(
        "entity", "organization"
    ):
        for tag in document.tags:
            candidates = lookup.get(_normalized_alias(tag), [])
            status = "matched" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"
            counts[status] += 1
            rows.append(
                {
                    "document_id": str(document.entity_id),
                    "document_title": document.entity.display_name,
                    "tag": tag,
                    "status": status,
                    "term_id": str(candidates[0].id) if len(candidates) == 1 else None,
                    "term_label": candidates[0].label if len(candidates) == 1 else None,
                }
            )
    return {"counts": counts, "rows": rows}


@transaction.atomic
def apply_migration(*, tenant: Tenant, actor_id: UUID) -> dict[str, Any]:
    preview = migration_preview(tenant=tenant)
    matched = [row for row in preview["rows"] if row["status"] == "matched"]
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in matched:
        by_document[row["document_id"]].append(row)
    for entity_id, rows in by_document.items():
        document = Document.objects.select_for_update().get(tenant=tenant, entity_id=entity_id)
        existing = set(DocumentTaxonomyTerm.objects.filter(document=document).values_list("term_id", flat=True))
        term_ids = existing | {UUID(row["term_id"]) for row in rows}
        terms = TaxonomyTerm.objects.filter(id__in=term_ids).select_related("taxonomy")
        DocumentTaxonomyTerm.objects.bulk_create(
            [
                DocumentTaxonomyTerm(
                    tenant=tenant,
                    organization=document.organization,
                    document=document,
                    taxonomy=term.taxonomy,
                    term=term,
                )
                for term in terms
                if term.id not in existing
            ],
            ignore_conflicts=True,
        )
        matched_names = {row["tag"] for row in rows}
        document.tags = [tag for tag in document.tags if tag not in matched_names]
        document.save(update_fields=("tags", "updated_at"))
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="taxonomy.legacy_tags_migrated", metadata={"matched": len(matched)}
    )
    return migration_preview(tenant=tenant)
