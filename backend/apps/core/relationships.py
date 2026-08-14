from __future__ import annotations

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
    "client_asset",
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
    "client_asset": PermissionKey.ASSETS_VIEW,
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
    accessible_organization_ids = accessible_organizations(
        member,
        PermissionKey.ORGANIZATIONS_VIEW,
    ).values("id")
    if workspace.kind == "msp":
        visibility = Q(organization__isnull=True)
        visibility &= ~Q(entity_type="organization") | Q(organization_record__id__in=accessible_organization_ids)
        visibility &= ~Q(entity_type="person") | (
            Q(person_record__associations__organization__isnull=True)
            | Q(person_record__associations__organization_id__in=accessible_organization_ids)
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
