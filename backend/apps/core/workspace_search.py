from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import CharField, Prefetch, Q, QuerySet
from django.db.models.functions import Cast

from .models import DocumentPlacement, Entity, EntityVisibility, PlacementAudienceProfile
from .relationships import visible_entities_for_workspace
from .workspaces import ResolvedWorkspace

MAX_MATCHES = 1_000
MAX_TERMS = 12
MAX_EXCERPT = 240

NETWORK_ENTITY_TYPES = (
    "network_rack",
    "network_device",
    "network_vrf",
    "network_vlan",
    "network_subnet",
    "network_interface",
    "network_ip_address",
    "network_mac_address",
    "wireless_network",
    "dns_zone",
    "dns_record",
    "network_circuit",
    "network_circuit_handoff",
)

RESULT_TYPE_ENTITY_TYPES: dict[str, tuple[str, ...]] = {
    "organization": ("organization",),
    "person": ("person",),
    "site": ("site",),
    "location": ("location",),
    "document": ("document",),
    "file": ("document_attachment",),
    "asset": ("client_asset",),
    "product": ("catalog_product",),
    "model": ("catalog_model",),
    "license": ("software_license",),
    "service": ("commercial_contract",),
    "credential_reference": ("credential_reference",),
    "domain": ("registered_domain",),
    "certificate": ("certificate_endpoint",),
    "network": NETWORK_ENTITY_TYPES,
    "data_flow": ("data_flow",),
}
ENTITY_TYPE_RESULT_TYPE = {
    entity_type: result_type
    for result_type, entity_types in RESULT_TYPE_ENTITY_TYPES.items()
    for entity_type in entity_types
}
RESULT_TYPE_LABELS = {
    "organization": "Organizations",
    "person": "People",
    "site": "Sites",
    "location": "Locations",
    "document": "Documents",
    "file": "Files",
    "asset": "Assets",
    "product": "Products",
    "model": "Models",
    "license": "Licenses",
    "service": "Services",
    "credential_reference": "Credential references",
    "domain": "Domains",
    "certificate": "Certificates",
    "network": "Networks",
    "data_flow": "Data flows",
}

# Only values already exposed by their normal read surfaces belong here. In
# particular, credential URLs, provider payloads, audit metadata, and custom
# fields are deliberately absent.
FIELD_LOOKUPS_BY_ENTITY_TYPE: dict[str, tuple[str, ...]] = {
    "organization": ("organization_record__legal_name__icontains", "organization_record__website__icontains"),
    "person": (
        "person_record__preferred_name__icontains",
        "person_record__phone__icontains",
        "person_record__email__icontains",
        "person_record__associations__role__icontains",
        "person_record__associations__responsibility__icontains",
        "person_record__associations__location__icontains",
        "person_record__associations__office__icontains",
    ),
    "site": (
        "site_record__code__icontains",
        "site_record__address_line_1__icontains",
        "site_record__address_line_2__icontains",
        "site_record__city__icontains",
        "site_record__region__icontains",
        "site_record__postal_code__icontains",
        "site_record__phone__icontains",
    ),
    "location": ("location_record__code__icontains",),
    "document": (
        "document_record__placements__block__current_revision__markdown__icontains",
        "document_record__placements__pinned_revision__markdown__icontains",
    ),
    "document_attachment": ("document_attachment_record__original_filename__icontains",),
    "client_asset": (
        "client_asset__hardware__serial_number__icontains",
        "client_asset__hardware__asset_tag__icontains",
        "client_asset__hardware__acquisition_reference__icontains",
        "client_asset__hardware__warranty_reference__icontains",
        "client_asset__product__entity__display_name__icontains",
        "client_asset__model__entity__display_name__icontains",
    ),
    "catalog_product": ("catalog_product__description__icontains",),
    "catalog_model": (
        "catalog_model__model_number__icontains",
        "catalog_model__product__entity__display_name__icontains",
    ),
    "software_license": (
        "software_license__reference__icontains",
        "software_license__product__entity__display_name__icontains",
        "software_license__model__entity__display_name__icontains",
    ),
    "commercial_contract": (
        "commercial_contract__reference__icontains",
        "commercial_contract__description__icontains",
        "commercial_contract__provider__entity__display_name__icontains",
    ),
    "registered_domain": ("registered_domain__ascii_name__icontains",),
    "certificate_endpoint": ("certificate_endpoint__hostname__ascii_name__icontains",),
    "network_vrf": ("network_vrf__route_distinguisher__icontains",),
    "network_subnet": ("network_subnet__primary_dns__icontains", "network_subnet__secondary_dns__icontains"),
    "network_ip_address": ("network_ip_address__dns_name__icontains",),
    "network_mac_address": ("network_mac_address__address__icontains",),
    "wireless_network": ("wireless_network__ssid__icontains",),
    "dns_zone": ("dns_zone__name__icontains",),
    "dns_record": ("dns_record__owner_name__icontains", "dns_record__value__icontains"),
    "network_circuit": ("network_circuit__service_identifier__icontains",),
    "network_circuit_handoff": ("network_circuit_handoff__provider_reference__icontains",),
}

SELECT_RELATED_BY_ENTITY_TYPE: dict[str, tuple[str, ...]] = {
    "person": ("person_record",),
    "site": ("site_record",),
    "location": ("location_record",),
    "document": ("document_record",),
    "document_attachment": ("document_attachment_record",),
    "client_asset": (
        "client_asset__hardware",
        "client_asset__product__entity",
        "client_asset__model__entity",
    ),
    "catalog_product": ("catalog_product",),
    "catalog_model": ("catalog_model__product__entity",),
    "software_license": ("software_license__product__entity", "software_license__model__entity"),
    "commercial_contract": ("commercial_contract__provider__entity",),
    "registered_domain": ("registered_domain",),
    "certificate_endpoint": ("certificate_endpoint__hostname",),
    **{entity_type: (entity_type,) for entity_type in NETWORK_ENTITY_TYPES},
}


@dataclass(frozen=True, slots=True)
class SearchField:
    label: str
    value: str
    kind: str = "identifier"


@dataclass(frozen=True, slots=True)
class RankedHit:
    entity: Entity
    result_type: str
    score: int
    excerpt: str


def _related(record: object, name: str) -> Any | None:
    try:
        return getattr(record, name)
    except ObjectDoesNotExist:
        return None


def _value(value: object | None) -> str:
    return "" if value is None else str(value).strip()


def _field(label: str, value: object | None, kind: str = "identifier") -> SearchField | None:
    normalized = _value(value)
    return SearchField(label, normalized, kind) if normalized else None


def _document_markdown(entity: Entity) -> str:
    document = _related(entity, "document_record")
    if document is None:
        return ""
    placements = getattr(document, "search_placements", ())
    markdown = []
    for placement in placements:
        revision = placement.pinned_revision if placement.pinned_revision_id else placement.block.current_revision
        if revision is not None and revision.markdown:
            markdown.append(revision.markdown)
    return "\n\n".join(markdown)


def _search_fields(entity: Entity) -> list[SearchField]:
    fields: list[SearchField | None] = [_field("Title", entity.display_name, "title")]
    entity_type = entity.entity_type
    if entity_type == "organization":
        record = _related(entity, "organization_record")
        fields.extend(
            (
                _field("Legal name", getattr(record, "legal_name", "")),
                _field("Website", getattr(record, "website", "")),
            )
        )
    elif entity_type == "person":
        record = _related(entity, "person_record")
        fields.extend(
            (
                _field("Preferred name", getattr(record, "preferred_name", "")),
                _field("Email", getattr(record, "email", "")),
                _field("Phone", getattr(record, "phone", "")),
            )
        )
        for association in getattr(record, "search_associations", ()):
            fields.extend(
                (
                    _field("Role", association.role),
                    _field("Responsibility", association.responsibility),
                    _field("Location", association.location),
                    _field("Office", association.office),
                )
            )
    elif entity_type == "site":
        record = _related(entity, "site_record")
        fields.extend(
            _field(label, getattr(record, name, ""))
            for label, name in (
                ("Site code", "code"),
                ("Address", "address_line_1"),
                ("Address", "address_line_2"),
                ("City", "city"),
                ("State or region", "region"),
                ("Postal code", "postal_code"),
                ("Phone", "phone"),
            )
        )
    elif entity_type == "location":
        record = _related(entity, "location_record")
        fields.append(_field("Location code", getattr(record, "code", "")))
    elif entity_type == "document":
        fields.append(_field("Document content", _document_markdown(entity), "body"))
    elif entity_type == "document_attachment":
        record = _related(entity, "document_attachment_record")
        fields.append(_field("Filename", getattr(record, "original_filename", "")))
    elif entity_type == "client_asset":
        record = _related(entity, "client_asset")
        hardware = _related(record, "hardware") if record is not None else None
        fields.extend(
            (
                _field("Serial number", getattr(hardware, "serial_number", "")),
                _field("Asset tag", getattr(hardware, "asset_tag", "")),
                _field("Acquisition reference", getattr(hardware, "acquisition_reference", "")),
                _field("Warranty reference", getattr(hardware, "warranty_reference", "")),
                _field("Product", getattr(getattr(record, "product", None), "entity", None)),
                _field("Model", getattr(getattr(record, "model", None), "entity", None)),
            )
        )
    elif entity_type == "catalog_product":
        record = _related(entity, "catalog_product")
        fields.append(_field("Description", getattr(record, "description", "")))
    elif entity_type == "catalog_model":
        record = _related(entity, "catalog_model")
        fields.extend(
            (
                _field("Model number", getattr(record, "model_number", "")),
                _field("Product", getattr(getattr(record, "product", None), "entity", None)),
            )
        )
    elif entity_type == "software_license":
        record = _related(entity, "software_license")
        fields.extend(
            (
                _field("Reference", getattr(record, "reference", "")),
                _field("Product", getattr(getattr(record, "product", None), "entity", None)),
                _field("Model", getattr(getattr(record, "model", None), "entity", None)),
            )
        )
    elif entity_type == "commercial_contract":
        record = _related(entity, "commercial_contract")
        fields.extend(
            (
                _field("Reference", getattr(record, "reference", "")),
                _field("Provider", getattr(getattr(record, "provider", None), "entity", None)),
                _field("Description", getattr(record, "description", ""), "body"),
            )
        )
    elif entity_type == "registered_domain":
        record = _related(entity, "registered_domain")
        fields.append(_field("Domain", getattr(record, "ascii_name", "")))
    elif entity_type == "certificate_endpoint":
        record = _related(entity, "certificate_endpoint")
        hostname = getattr(record, "hostname", None)
        fields.append(_field("Hostname", getattr(hostname, "ascii_name", "")))
    elif entity_type in NETWORK_ENTITY_TYPES:
        fields.extend(_network_fields(entity))
    return [field for field in fields if field is not None]


def _network_fields(entity: Entity) -> list[SearchField | None]:
    accessor_fields = {
        "network_vrf": (("Route distinguisher", "route_distinguisher"),),
        "network_vlan": (("VLAN", "vlan_id"),),
        "network_subnet": (("CIDR", "cidr"), ("Primary DNS", "primary_dns"), ("Secondary DNS", "secondary_dns")),
        "network_ip_address": (("IP address", "address"), ("DNS name", "dns_name")),
        "network_mac_address": (("MAC address", "address"),),
        "wireless_network": (("SSID", "ssid"),),
        "dns_zone": (("DNS zone", "name"),),
        "dns_record": (("DNS owner", "owner_name"), ("DNS value", "value")),
        "network_circuit": (("Service identifier", "service_identifier"),),
        "network_circuit_handoff": (("Provider reference", "provider_reference"),),
    }
    record = _related(entity, entity.entity_type)
    return [_field(label, getattr(record, name, "")) for label, name in accessor_fields.get(entity.entity_type, ())]


def _fold(value: str) -> str:
    return " ".join(value.casefold().split())


def _terms(query: str) -> tuple[str, ...]:
    terms = tuple(re.findall(r"[\w@.:/+-]+", query.casefold(), flags=re.UNICODE)[:MAX_TERMS])
    return terms or (query.casefold(),)


def _matching_excerpt(field: SearchField, query: str, terms: tuple[str, ...]) -> str:
    collapsed = " ".join(field.value.replace("\r", " ").replace("\n", " ").split())
    folded = collapsed.casefold()
    position = folded.find(query.casefold())
    if position < 0:
        position = min((folded.find(term) for term in terms if term in folded), default=0)
    start = max(0, position - 70)
    end = min(len(collapsed), position + len(query) + 130)
    excerpt = f"{'…' if start else ''}{collapsed[start:end]}{'…' if end < len(collapsed) else ''}"
    if field.kind == "body":
        return excerpt[:MAX_EXCERPT]
    return f"{field.label}: {excerpt}"[:MAX_EXCERPT]


def _rank(entity: Entity, query: str, terms: tuple[str, ...]) -> RankedHit:
    folded_query = _fold(query)
    best_score = 0
    best_field: SearchField | None = None
    for field in _search_fields(entity):
        folded = _fold(field.value)
        if not all(term in folded for term in terms):
            continue
        if field.kind == "title":
            score = 1_200 if folded == folded_query else 1_000 if folded.startswith(folded_query) else 900
        elif field.kind == "body":
            score = 350 if folded_query in folded else 250
            score += min(sum(folded.count(term) for term in terms), 20)
        else:
            score = 850 if folded == folded_query else 700 if folded.startswith(folded_query) else 550
        if score > best_score:
            best_score, best_field = score, field
    return RankedHit(
        entity=entity,
        result_type=ENTITY_TYPE_RESULT_TYPE[entity.entity_type],
        score=best_score,
        excerpt="" if best_field is None or best_field.kind == "title" else _matching_excerpt(best_field, query, terms),
    )


def _candidate_filter(term: str, lookups: tuple[str, ...]) -> Q:
    condition = Q()
    for lookup in lookups:
        condition |= Q(**{lookup: term})
    return condition


def _candidate_branch(
    entities: QuerySet[Entity], *, entity_types: tuple[str, ...], lookups: tuple[str, ...], terms: tuple[str, ...]
) -> Any:
    branch = entities.filter(entity_type__in=entity_types)
    if "network_ip_address" in entity_types:
        branch = branch.annotate(search_ip=Cast("network_ip_address__address", output_field=CharField()))
        lookups += ("search_ip__icontains",)
    if "network_subnet" in entity_types:
        branch = branch.annotate(search_cidr=Cast("network_subnet__cidr", output_field=CharField()))
        lookups += ("search_cidr__icontains",)
    if "network_vlan" in entity_types:
        branch = branch.annotate(search_vlan=Cast("network_vlan__vlan_id", output_field=CharField()))
        lookups += ("search_vlan__icontains",)
    for term in terms:
        branch = branch.filter(_candidate_filter(term, lookups))
    return branch.values("id", "entity_type")


def _candidate_queryset(workspace: ResolvedWorkspace, query: str) -> QuerySet[Entity]:
    entity_types = tuple(ENTITY_TYPE_RESULT_TYPE)
    candidates = visible_entities_for_workspace(workspace=workspace, include_reference_organizations=False).filter(
        entity_type__in=entity_types
    )
    if workspace.member.surface == "client_portal":
        candidates = candidates.filter(visibility=EntityVisibility.CLIENT_VISIBLE)
    terms = _terms(query)
    branches = [
        _candidate_branch(candidates, entity_types=entity_types, lookups=("display_name__icontains",), terms=terms)
    ]
    branches.extend(
        _candidate_branch(candidates, entity_types=(entity_type,), lookups=lookups, terms=terms)
        for entity_type, lookups in FIELD_LOOKUPS_BY_ENTITY_TYPE.items()
    )
    candidate_rows = list(branches[0].union(*branches[1:]).order_by("id")[: MAX_MATCHES + 1])
    candidate_ids = [row["id"] for row in candidate_rows]
    candidate_types = {row["entity_type"] for row in candidate_rows}
    candidates = candidates.filter(id__in=candidate_ids)
    placements = DocumentPlacement.objects.select_related("block__current_revision", "pinned_revision").order_by(
        "position", "id"
    )
    if workspace.member.surface == "client_portal":
        placements = placements.filter(
            audience_profile__in=(PlacementAudienceProfile.SHARED, PlacementAudienceProfile.CLIENT_VISIBLE)
        )
    associations = (
        _related_model(Entity, "person_record")
        ._meta.get_field("associations")
        .related_model.objects.filter(archived_at__isnull=True)
        .order_by("id")
    )
    select_related = tuple(
        lookup
        for entity_type in candidate_types
        for lookup in SELECT_RELATED_BY_ENTITY_TYPE.get(entity_type, ())
    )
    return (
        candidates.select_related(*select_related)
        .prefetch_related(
            Prefetch("person_record__associations", queryset=associations, to_attr="search_associations"),
            Prefetch("document_record__placements", queryset=placements, to_attr="search_placements"),
        )
        .order_by("display_name", "id")
        .distinct()
    )


def _related_model(model: type[Entity], relation: str):  # type: ignore[no-untyped-def]
    return model._meta.get_field(relation).related_model


def _workspace_label(entity: Entity, workspace: ResolvedWorkspace) -> str:
    organization = entity.organization
    if organization is not None:
        return organization.entity.display_name
    if workspace.organization is not None and entity.id == workspace.organization.entity_id:
        return workspace.organization.entity.display_name
    if entity.entity_type == "organization":
        return "MSP organization directory"
    return workspace.member.tenant.name


def _target(entity: Entity, workspace: ResolvedWorkspace) -> str:
    if entity.entity_type == "organization" and workspace.kind == "msp":
        return f"/workspaces/organizations/{entity.id}/overview"
    area = {
        "person": "people",
        "site": "sites",
        "location": "sites",
        "document": "documentation",
        "document_attachment": "files",
        "client_asset": "assets",
        "catalog_product": "products",
        "catalog_model": "products",
        "software_license": "licenses",
        "commercial_contract": "services",
        "credential_reference": "credentials",
        "registered_domain": "domains",
        "certificate_endpoint": "certificates",
        "data_flow": "compliance",
    }.get(entity.entity_type, "networks" if entity.entity_type in NETWORK_ENTITY_TYPES else "overview")
    prefix = "" if workspace.kind == "msp" else f"/workspaces/organizations/{workspace.id}"
    target = f"{prefix}/{area}"
    if entity.entity_type == "document":
        return f"{target}?{urlencode({'document': str(entity.id)})}"
    if entity.entity_type in {"document_attachment", "certificate_endpoint"}:
        return f"{target}?{urlencode({'q': entity.display_name})}"
    return target


def _projection(hit: RankedHit, workspace: ResolvedWorkspace) -> dict[str, object]:
    document = _related(hit.entity, "document_record") if hit.entity.entity_type == "document" else None
    updated_at = max(hit.entity.updated_at, getattr(document, "updated_at", hit.entity.updated_at))
    return {
        "id": hit.entity.id,
        "result_type": hit.result_type,
        "entity_type": hit.entity.entity_type,
        "title": hit.entity.display_name,
        "excerpt": hit.excerpt,
        "workspace_label": _workspace_label(hit.entity, workspace),
        "target": _target(hit.entity, workspace),
        "score": hit.score,
        "updated_at": updated_at,
        "review_state": getattr(document, "review_state", None),
    }


def search_workspace(
    *,
    workspace: ResolvedWorkspace,
    query: str,
    result_type: str,
    page: int,
    page_size: int,
) -> dict[str, object]:
    candidates = list(_candidate_queryset(workspace, query)[: MAX_MATCHES + 1])
    truncated = len(candidates) > MAX_MATCHES
    terms = _terms(query)
    ranked = [_rank(entity, query, terms) for entity in candidates[:MAX_MATCHES]]
    ranked = [hit for hit in ranked if hit.score > 0]
    ranked.sort(key=lambda hit: (-hit.score, hit.entity.display_name.casefold(), hit.result_type, str(hit.entity.id)))
    facet_counts = Counter(hit.result_type for hit in ranked)
    facets = [
        {"value": value, "label": RESULT_TYPE_LABELS[value], "count": facet_counts[value]}
        for value in RESULT_TYPE_ENTITY_TYPES
        if facet_counts[value]
    ]
    selected = [hit for hit in ranked if not result_type or hit.result_type == result_type]
    count = len(selected)
    offset = (page - 1) * page_size
    page_results = selected[offset : offset + page_size]
    return {
        "results": [_projection(hit, workspace) for hit in page_results],
        "facets": facets,
        "page": page,
        "page_size": page_size,
        "count": count,
        "has_more": offset + page_size < count,
        "truncated": truncated,
    }
