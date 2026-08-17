from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.policy import PermissionKey, accessible_organizations, context_has_permission

from .models import AuditEvent, Entity, EntityLink, EntityLinkType, Organization
from .workspaces import ResolvedWorkspace

SEARCHABLE_ENTITY_TYPES = (
    "organization",
    "person",
    "site",
    "location",
    "document",
    "document_attachment",
    "client_asset",
    "catalog_product",
    "catalog_model",
    "software_license",
    "commercial_contract",
    "credential_reference",
    "registered_domain",
    "certificate_endpoint",
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

ENTITY_TYPE_VIEW_PERMISSION = {
    "organization": PermissionKey.ORGANIZATIONS_VIEW,
    "person": PermissionKey.PEOPLE_VIEW,
    "site": PermissionKey.SITES_VIEW,
    "location": PermissionKey.SITES_VIEW,
    "document": PermissionKey.DOCUMENTS_VIEW,
    "document_attachment": PermissionKey.DOCUMENTS_VIEW,
    "client_asset": PermissionKey.ASSETS_VIEW,
    "catalog_product": PermissionKey.ASSETS_VIEW,
    "catalog_model": PermissionKey.ASSETS_VIEW,
    "software_license": PermissionKey.ASSETS_VIEW,
    "commercial_contract": PermissionKey.COSTS_VIEW,
    "credential_reference": PermissionKey.CREDENTIAL_REFERENCES_VIEW,
    "registered_domain": PermissionKey.DOMAINS_VIEW,
    "certificate_endpoint": PermissionKey.DOMAINS_VIEW,
    "network_rack": PermissionKey.NETWORKS_VIEW,
    "network_device": PermissionKey.NETWORKS_VIEW,
    "network_vrf": PermissionKey.NETWORKS_VIEW,
    "network_vlan": PermissionKey.NETWORKS_VIEW,
    "network_subnet": PermissionKey.NETWORKS_VIEW,
    "network_interface": PermissionKey.NETWORKS_VIEW,
    "network_ip_address": PermissionKey.NETWORKS_VIEW,
    "network_mac_address": PermissionKey.NETWORKS_VIEW,
    "wireless_network": PermissionKey.NETWORKS_VIEW,
    "dns_zone": PermissionKey.NETWORKS_VIEW,
    "dns_record": PermissionKey.NETWORKS_VIEW,
    "network_circuit": PermissionKey.NETWORKS_VIEW,
    "network_circuit_handoff": PermissionKey.NETWORKS_VIEW,
}


class EntityRelationshipError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LinkTypeDefinition:
    value: str
    forward_label: str
    inverse_label: str
    symmetric: bool = False
    target_types: tuple[str, ...] = ()
    target_classification: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "forward_label": self.forward_label,
            "inverse_label": self.inverse_label,
            "symmetric": self.symmetric,
            "target_types": list(self.target_types),
        }


LINK_TYPES: tuple[LinkTypeDefinition, ...] = (
    LinkTypeDefinition(EntityLinkType.RELATED_TO, "Related to", "Related to", symmetric=True),
    LinkTypeDefinition(
        EntityLinkType.CONNECTED_TO,
        "Connected to",
        "Connected to",
        symmetric=True,
        target_types=("network_device",),
    ),
    LinkTypeDefinition(EntityLinkType.DEPENDS_ON, "Depends on", "Required by"),
    LinkTypeDefinition(EntityLinkType.MANAGED_BY, "Managed by", "Manages", target_types=("organization", "person")),
    LinkTypeDefinition(
        EntityLinkType.SUPPLIED_BY,
        "Supplied by",
        "Supplies",
        target_types=("organization",),
        target_classification="vendor",
    ),
    LinkTypeDefinition(
        EntityLinkType.MANUFACTURED_BY,
        "Manufactured by",
        "Manufactures",
        target_types=("organization",),
        target_classification="manufacturer",
    ),
    LinkTypeDefinition(
        EntityLinkType.PARTNERED_WITH,
        "Partnered with",
        "Partnered with",
        symmetric=True,
        target_types=("organization",),
    ),
    LinkTypeDefinition(EntityLinkType.LOCATED_AT, "Located at", "Contains", target_types=("site", "location")),
    LinkTypeDefinition(EntityLinkType.ASSIGNED_TO, "Assigned to", "Has assigned", target_types=("person",)),
    LinkTypeDefinition(EntityLinkType.REFERENCES, "References", "Referenced by"),
)
LINK_TYPE_BY_VALUE = {item.value: item for item in LINK_TYPES}

GRAPH_FAMILY_ENTITY_TYPES: dict[str, tuple[str, ...]] = {
    "network": (
        "client_asset",
        "site",
        "location",
        "network_rack",
        "network_device",
        "network_vlan",
        "network_subnet",
        "network_ip_address",
        "network_mac_address",
        "wireless_network",
        "dns_zone",
        "dns_record",
        "network_circuit",
        "network_circuit_handoff",
    ),
    "asset": ("client_asset", "catalog_product", "catalog_model"),
    "document": ("document",),
}


def link_type_catalog() -> list[dict[str, object]]:
    return [item.as_dict() for item in LINK_TYPES]


def _visible_entities(
    *,
    workspace: ResolvedWorkspace,
    include_reference_organizations: bool,
    include_archived: bool = False,
) -> QuerySet[Entity]:
    member = workspace.member
    allowed_entity_types = tuple(
        entity_type
        for entity_type, permission in ENTITY_TYPE_VIEW_PERMISSION.items()
        if context_has_permission(member, permission, organization=workspace.organization)
    )
    entities = Entity.scoped.for_tenant(workspace.member.tenant)
    if not allowed_entity_types:
        return entities.none()
    entities = entities.filter(entity_type__in=allowed_entity_types)
    accessible_organization_ids = accessible_organizations(member, PermissionKey.ORGANIZATIONS_VIEW).values("id")
    if workspace.kind == "msp":
        visibility = Q(organization__isnull=True)
        visibility &= ~Q(entity_type="organization") | Q(organization_record__id__in=accessible_organization_ids)
        visibility &= ~Q(entity_type="person") | (
            Q(person_record__associations__organization__isnull=True)
            & Q(person_record__associations__archived_at__isnull=True)
        )
        entities = entities.filter(visibility)
    else:
        organization = workspace.organization
        if organization is None:
            return entities.none()
        visibility = (
            Q(organization_id=organization.id)
            | Q(id=organization.entity_id)
            | Q(
                entity_type="person",
                person_record__associations__organization_id=organization.id,
                person_record__associations__archived_at__isnull=True,
            )
        )
        if include_reference_organizations:
            visibility |= Q(
                entity_type="organization",
                organization__isnull=True,
                organization_record__id__in=accessible_organization_ids,
            )
        entities = entities.filter(visibility)
    if not include_archived:
        entities = entities.filter(archived_at__isnull=True)
    return entities.distinct().select_related(
        "organization",
        "organization__entity",
        "organization_record",
    ).prefetch_related("organization_record__classifications")


def entity_for_workspace(*, workspace: ResolvedWorkspace, entity_id: UUID) -> Entity:
    return _visible_entities(
        workspace=workspace,
        include_reference_organizations=False,
    ).get(id=entity_id)


def eligible_target_for_workspace(*, workspace: ResolvedWorkspace, entity_id: UUID) -> Entity:
    return _visible_entities(
        workspace=workspace,
        include_reference_organizations=True,
    ).get(id=entity_id)


def _workspace_label(entity: Entity, workspace: ResolvedWorkspace) -> str:
    organization = entity.organization
    if organization is not None:
        return organization.entity.display_name
    if entity.entity_type == "organization":
        return "MSP organization directory"
    return workspace.member.tenant.name


def _eligible_link_types(entity: Entity) -> list[str]:
    classifications: set[str] = set()
    if entity.entity_type == "organization":
        organization = getattr(entity, "organization_record", None)
        if organization is not None:
            classifications = {item.kind for item in organization.classifications.all()}
    return [
        definition.value
        for definition in LINK_TYPES
        if (not definition.target_types or entity.entity_type in definition.target_types)
        and (definition.target_classification is None or definition.target_classification in classifications)
    ]


def entity_projection(entity: Entity, workspace: ResolvedWorkspace) -> dict[str, object]:
    return {
        "id": entity.id,
        "display_name": entity.display_name,
        "entity_type": entity.entity_type,
        "visibility": entity.visibility,
        "workspace_label": _workspace_label(entity, workspace),
        "eligible_link_types": _eligible_link_types(entity),
    }


def search_entities(
    *,
    workspace: ResolvedWorkspace,
    query: str,
    entity_type: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int, bool]:
    entities = _visible_entities(workspace=workspace, include_reference_organizations=True)
    if query:
        entities = entities.filter(display_name__icontains=query)
    if entity_type:
        entities = entities.filter(entity_type=entity_type)
    entities = entities.order_by("display_name", "id")
    count = entities.count()
    offset = (page - 1) * page_size
    selected = list(entities[offset : offset + page_size + 1])
    return (
        [entity_projection(entity, workspace) for entity in selected[:page_size]],
        count,
        len(selected) > page_size,
    )


def entities_for_mentions(*, workspace: ResolvedWorkspace, entity_ids: set[UUID]) -> list[Entity]:
    if not entity_ids:
        return []
    return list(
        _visible_entities(workspace=workspace, include_reference_organizations=True)
        .filter(id__in=entity_ids)
        .order_by("display_name", "id")[:200]
    )


def _validate_link_type_target(*, definition: LinkTypeDefinition, target: Entity) -> None:
    if definition.target_types and target.entity_type not in definition.target_types:
        raise EntityRelationshipError("The selected record type is not valid for this relationship.")
    if definition.target_classification is None:
        return
    if target.entity_type != "organization":
        raise EntityRelationshipError("The selected organization classification is not valid for this relationship.")
    organization = (
        Organization.scoped.for_tenant(target.tenant_id)
        .filter(entity_id=target.id, entity__archived_at__isnull=True)
        .prefetch_related("classifications")
        .first()
    )
    if organization is None or not any(
        classification.kind == definition.target_classification for classification in organization.classifications.all()
    ):
        raise EntityRelationshipError("The selected organization classification is not valid for this relationship.")


@transaction.atomic
def create_entity_link(
    *,
    workspace: ResolvedWorkspace,
    source_entity_id: UUID,
    target_entity_id: UUID,
    link_type: str,
    actor_id: UUID,
) -> EntityLink:
    definition = LINK_TYPE_BY_VALUE.get(link_type)
    if definition is None:
        raise EntityRelationshipError("Unsupported relationship type.")
    visible_source = entity_for_workspace(workspace=workspace, entity_id=source_entity_id)
    visible_target = eligible_target_for_workspace(workspace=workspace, entity_id=target_entity_id)
    source = Entity.scoped.for_tenant(workspace.member.tenant).select_for_update().get(id=visible_source.id)
    target = Entity.scoped.for_tenant(workspace.member.tenant).select_for_update().get(id=visible_target.id)
    if source.id == target.id:
        raise EntityRelationshipError("A record cannot be related to itself.")
    _validate_link_type_target(definition=definition, target=target)
    if definition.symmetric and source.id.int > target.id.int:
        source, target = target, source
    try:
        link = EntityLink.objects.create(
            tenant=workspace.member.tenant,
            source=source,
            target=target,
            link_type=link_type,
            metadata={},
        )
    except IntegrityError as exc:
        raise EntityRelationshipError("That relationship already exists.") from exc
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor_id=actor_id,
        action="entity_link.created",
        entity_id=visible_source.id,
        metadata={},
    )
    return link


def _active_links_for_entity(*, workspace: ResolvedWorkspace, entity: Entity) -> QuerySet[EntityLink]:
    candidate_ids = _visible_entities(
        workspace=workspace,
        include_reference_organizations=True,
    ).values("id")
    return (
        EntityLink.scoped.for_tenant(workspace.member.tenant)
        .filter(archived_at__isnull=True)
        .filter(Q(source=entity, target_id__in=candidate_ids) | Q(target=entity, source_id__in=candidate_ids))
        .select_related(
            "source",
            "source__organization",
            "source__organization__entity",
            "target",
            "target__organization",
            "target__organization__entity",
        )
        .order_by("link_type", "created_at", "id")
    )


def relationship_projection(*, link: EntityLink, perspective: Entity, workspace: ResolvedWorkspace) -> dict[str, Any]:
    definition = LINK_TYPE_BY_VALUE[link.link_type]
    outgoing = link.source_id == perspective.id
    related = link.target if outgoing else link.source
    return {
        "id": link.id,
        "link_type": link.link_type,
        "label": definition.forward_label if outgoing or definition.symmetric else definition.inverse_label,
        "direction": "outgoing" if outgoing else "incoming",
        "source_id": link.source_id,
        "target_id": link.target_id,
        "related_entity": entity_projection(related, workspace),
        "created_at": link.created_at,
    }


def relationships_for_entity(*, workspace: ResolvedWorkspace, entity_id: UUID) -> list[dict[str, Any]]:
    entity = entity_for_workspace(workspace=workspace, entity_id=entity_id)
    return [
        relationship_projection(link=link, perspective=entity, workspace=workspace)
        for link in _active_links_for_entity(workspace=workspace, entity=entity)
    ]


def _graph_node(entity: Entity, *, root_id: UUID | None) -> dict[str, object]:
    return {
        "id": str(entity.id),
        "label": entity.display_name,
        "entity_type": entity.entity_type,
        "visibility": entity.visibility,
        "root": entity.id == root_id,
    }


def _graph_edge(link: EntityLink) -> dict[str, object]:
    definition = LINK_TYPE_BY_VALUE[link.link_type]
    return {
        "id": str(link.id),
        "source": str(link.source_id),
        "target": str(link.target_id),
        "link_type": link.link_type,
        "label": definition.forward_label,
        "symmetric": definition.symmetric,
    }


def relationship_graph_projection(
    *,
    workspace: ResolvedWorkspace,
    family: str,
    root_entity_id: UUID | None,
    depth: int,
    edge_limit: int,
) -> dict[str, object]:
    """Return a bounded graph after authorizing every node and edge server-side."""

    family_types = GRAPH_FAMILY_ENTITY_TYPES[family]
    visible = _visible_entities(workspace=workspace, include_reference_organizations=False)
    visible_ids = visible.values("id")
    root: Entity | None = None
    if root_entity_id is not None:
        root = visible.get(id=root_entity_id, entity_type__in=family_types)

    links = (
        EntityLink.scoped.for_tenant(workspace.member.tenant)
        .filter(archived_at__isnull=True, source_id__in=visible_ids, target_id__in=visible_ids)
        .select_related("source", "target")
        .order_by("id")
    )
    selected: list[EntityLink] = []
    truncated = False
    if root is None:
        candidates = list(
            links.filter(Q(source__entity_type__in=family_types) | Q(target__entity_type__in=family_types))[
                : edge_limit + 1
            ]
        )
        truncated = len(candidates) > edge_limit
        selected = candidates[:edge_limit]
    else:
        frontier = {root.id}
        visited_nodes = {root.id}
        visited_links: set[UUID] = set()
        for _level in range(depth):
            if not frontier or len(selected) >= edge_limit:
                break
            remaining = edge_limit - len(selected)
            candidates = list(
                links.filter(Q(source_id__in=frontier) | Q(target_id__in=frontier))
                .exclude(id__in=visited_links)[: remaining + 1]
            )
            if len(candidates) > remaining:
                truncated = True
            candidates = candidates[:remaining]
            selected.extend(candidates)
            visited_links.update(item.id for item in candidates)
            next_frontier = {
                endpoint
                for item in candidates
                for endpoint in (item.source_id, item.target_id)
                if endpoint not in visited_nodes
            }
            visited_nodes.update(next_frontier)
            frontier = next_frontier

    entities: dict[UUID, Entity] = {}
    if root is not None:
        entities[root.id] = root
    for link in selected:
        entities[link.source_id] = link.source
        entities[link.target_id] = link.target
    nodes = [_graph_node(entities[key], root_id=root.id if root else None) for key in sorted(entities, key=str)]
    edges = [_graph_edge(link) for link in selected]
    digest_source = {
        "family": family,
        "root_entity_id": str(root.id) if root else None,
        "nodes": nodes,
        "edges": edges,
    }
    digest = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **digest_source,
        "workspace": {
            "kind": workspace.kind,
            "id": str(workspace.organization.entity_id) if workspace.organization is not None else str(workspace.member.tenant_id),
        },
        "depth": depth,
        "edge_limit": edge_limit,
        "truncated": truncated,
        "digest": digest,
    }


@transaction.atomic
def archive_entity_link(
    *,
    workspace: ResolvedWorkspace,
    entity_id: UUID,
    link_id: UUID,
    actor_id: UUID,
) -> None:
    entity = entity_for_workspace(workspace=workspace, entity_id=entity_id)
    link = _active_links_for_entity(workspace=workspace, entity=entity).select_for_update(of=("self",)).get(id=link_id)
    archived_at = timezone.now()
    EntityLink.scoped.for_tenant(workspace.member.tenant).filter(id=link.id).update(
        archived_at=archived_at,
        updated_at=archived_at,
    )
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor_id=actor_id,
        action="entity_link.archived",
        entity_id=entity.id,
        metadata={},
    )
