from __future__ import annotations

from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from .models import AuditEvent, Entity, Location, Organization, Site, Tenant, workspace_for_owner
from .scoping import DataScope


class SiteHierarchyError(ValueError):
    pass


def _validate_timezone(value: str) -> None:
    if not value:
        return
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError({"timezone": "Use a valid IANA timezone name."}) from exc


def locations_for_scope(scope: DataScope) -> QuerySet[Location]:
    return (
        Location.scoped.for_scope(scope)
        .filter(archived_at__isnull=True)
        .select_related("entity", "site", "site__entity", "parent", "parent__entity")
    )


def sites_for_scope(scope: DataScope) -> QuerySet[Site]:
    active_locations = locations_for_scope(scope).order_by("entity__display_name", "entity_id")
    return (
        Site.scoped.for_scope(scope)
        .filter(archived_at__isnull=True)
        .select_related("entity", "organization", "organization__entity")
        .prefetch_related(Prefetch("locations", queryset=active_locations, to_attr="active_locations"))
    )


def query_sites(*, scope: DataScope, q: str) -> list[Site]:
    records = sites_for_scope(scope)
    if q:
        records = records.filter(
            Q(entity__display_name__icontains=q)
            | Q(code__icontains=q)
            | Q(address_line_1__icontains=q)
            | Q(address_line_2__icontains=q)
            | Q(city__icontains=q)
            | Q(region__icontains=q)
            | Q(postal_code__icontains=q)
            | Q(locations__archived_at__isnull=True, locations__entity__display_name__icontains=q)
        ).distinct()
    return list(records.order_by("entity__display_name", "entity_id")[:200])


@transaction.atomic
def create_site(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    code: str,
    address_line_1: str,
    address_line_2: str,
    city: str,
    region: str,
    postal_code: str,
    country_code: str,
    timezone: str,
    phone: str,
) -> Site:
    _validate_timezone(timezone)
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="site",
        display_name=name,
    )
    site = Site.objects.create(
        tenant=tenant,
        organization=organization,
        entity=entity,
        code=code,
        address_line_1=address_line_1,
        address_line_2=address_line_2,
        city=city,
        region=region,
        postal_code=postal_code,
        country_code=country_code,
        timezone=timezone,
        phone=phone,
    )
    AuditEvent.objects.create(tenant=tenant, actor_id=actor_id, action="site.created", entity_id=entity.id, metadata={})
    return site


@transaction.atomic
def update_site(*, site: Site, actor_id: UUID, **values: str) -> Site:
    if "timezone" in values:
        _validate_timezone(values["timezone"])
    site.entity.display_name = values.pop("name")
    site.entity.save(update_fields=("display_name", "updated_at"))
    for field, value in values.items():
        setattr(site, field, value)
    site.save(update_fields=(*values.keys(), "updated_at"))
    AuditEvent.objects.create(
        tenant=site.tenant,
        actor_id=actor_id,
        action="site.updated",
        entity_id=site.entity_id,
        metadata={},
    )
    return site


@transaction.atomic
def archive_site(*, site: Site, actor_id: UUID) -> None:
    archived_at = timezone.now()
    scope = DataScope.owner(site.tenant, site.organization)
    locations = Location.scoped.for_scope(scope).filter(site=site, archived_at__isnull=True)
    Entity.scoped.for_scope(scope).filter(id__in=locations.values("entity_id")).update(
        archived_at=archived_at,
        updated_at=archived_at,
    )
    locations.update(archived_at=archived_at, updated_at=archived_at)
    site.entity.archived_at = archived_at
    site.entity.save(update_fields=("archived_at", "updated_at"))
    site.archived_at = archived_at
    site.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=site.tenant,
        actor_id=actor_id,
        action="site.archived",
        entity_id=site.entity_id,
        metadata={},
    )


def _parent_for_site(*, scope: DataScope, site: Site, parent_entity_id: UUID | None) -> Location | None:
    if parent_entity_id is None:
        return None
    try:
        return locations_for_scope(scope).get(site=site, entity_id=parent_entity_id)
    except Location.DoesNotExist as exc:
        raise SiteHierarchyError("The selected parent location is unavailable in this site.") from exc


@transaction.atomic
def create_location(
    *,
    scope: DataScope,
    site: Site,
    actor_id: UUID,
    name: str,
    kind: str,
    code: str,
    parent_id: UUID | None,
) -> Location:
    parent = _parent_for_site(scope=scope, site=site, parent_entity_id=parent_id)
    entity = Entity.objects.create(
        tenant=site.tenant,
        workspace=workspace_for_owner(tenant=site.tenant, organization=site.organization),
        organization=site.organization,
        entity_type="location",
        display_name=name,
    )
    location = Location.objects.create(
        tenant=site.tenant,
        organization=site.organization,
        entity=entity,
        site=site,
        parent=parent,
        kind=kind,
        code=code,
    )
    AuditEvent.objects.create(
        tenant=site.tenant,
        actor_id=actor_id,
        action="location.created",
        entity_id=entity.id,
        metadata={},
    )
    return location


def _validate_parent_change(*, location: Location, parent: Location | None) -> None:
    cursor = parent
    while cursor is not None:
        if cursor.pk == location.pk:
            raise SiteHierarchyError("A location cannot be moved beneath itself or one of its descendants.")
        cursor = cursor.parent


@transaction.atomic
def update_location(
    *,
    scope: DataScope,
    location: Location,
    actor_id: UUID,
    name: str,
    kind: str,
    code: str,
    parent_id: UUID | None,
) -> Location:
    parent = _parent_for_site(scope=scope, site=location.site, parent_entity_id=parent_id)
    _validate_parent_change(location=location, parent=parent)
    location.entity.display_name = name
    location.entity.save(update_fields=("display_name", "updated_at"))
    location.kind = kind
    location.code = code
    location.parent = parent
    location.save(update_fields=("kind", "code", "parent", "updated_at"))
    AuditEvent.objects.create(
        tenant=location.tenant,
        actor_id=actor_id,
        action="location.updated",
        entity_id=location.entity_id,
        metadata={},
    )
    return location


@transaction.atomic
def archive_location(*, location: Location, actor_id: UUID) -> None:
    scope = DataScope.owner(location.tenant, location.organization)
    all_locations = list(
        Location.scoped.for_scope(scope)
        .filter(site=location.site, archived_at__isnull=True)
        .values("id", "parent_id", "entity_id")
    )
    selected_ids = {location.id}
    changed = True
    while changed:
        changed = False
        for item in all_locations:
            if item["parent_id"] in selected_ids and item["id"] not in selected_ids:
                selected_ids.add(item["id"])
                changed = True
    archived_at = timezone.now()
    entity_ids = [item["entity_id"] for item in all_locations if item["id"] in selected_ids]
    Entity.scoped.for_scope(scope).filter(id__in=entity_ids).update(
        archived_at=archived_at,
        updated_at=archived_at,
    )
    Location.scoped.for_scope(scope).filter(id__in=selected_ids).update(
        archived_at=archived_at,
        updated_at=archived_at,
    )
    AuditEvent.objects.create(
        tenant=location.tenant,
        actor_id=actor_id,
        action="location.archived",
        entity_id=location.entity_id,
        metadata={},
    )
