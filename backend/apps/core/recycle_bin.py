from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import (
    InstallationMemberContext,
    PermissionKey,
    context_has_archived_organization_permission,
    context_has_permission,
    require_archived_organization_permission,
    require_permission,
)

from .custom_fields import latest_version
from .models import (
    AuditEvent,
    CommercialContract,
    ContractCost,
    CustomFieldDefinition,
    Entity,
    Location,
    Organization,
    PersonAssociation,
    Site,
)
from .workspaces import ResolvedWorkspace


class RecoverableRecordType(StrEnum):
    ORGANIZATION = "organization"
    PERSON_ASSOCIATION = "person_association"
    SITE = "site"
    LOCATION = "location"
    CUSTOM_FIELD_DEFINITION = "custom_field_definition"
    COMMERCIAL_CONTRACT = "commercial_contract"


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    view: PermissionKey
    restore: PermissionKey


RECOVERY_POLICIES = {
    RecoverableRecordType.ORGANIZATION: RecoveryPolicy(
        PermissionKey.ORGANIZATIONS_VIEW,
        PermissionKey.ORGANIZATIONS_ARCHIVE,
    ),
    RecoverableRecordType.PERSON_ASSOCIATION: RecoveryPolicy(
        PermissionKey.PEOPLE_VIEW,
        PermissionKey.PEOPLE_ARCHIVE,
    ),
    RecoverableRecordType.SITE: RecoveryPolicy(PermissionKey.SITES_VIEW, PermissionKey.SITES_ARCHIVE),
    RecoverableRecordType.LOCATION: RecoveryPolicy(PermissionKey.SITES_VIEW, PermissionKey.SITES_ARCHIVE),
    RecoverableRecordType.CUSTOM_FIELD_DEFINITION: RecoveryPolicy(
        PermissionKey.CUSTOM_FIELDS_VIEW,
        PermissionKey.CUSTOM_FIELDS_MANAGE,
    ),
    RecoverableRecordType.COMMERCIAL_CONTRACT: RecoveryPolicy(
        PermissionKey.ASSETS_VIEW,
        PermissionKey.ASSETS_EDIT,
    ),
}


@dataclass(frozen=True, slots=True)
class RecycleBinItem:
    id: UUID
    record_type: RecoverableRecordType
    label: str
    archived_at: datetime
    workspace_kind: str
    workspace_id: UUID
    workspace_name: str
    cascade_count: int
    can_restore: bool


class RecoveryConflict(ValueError):
    pass


def _has_permissions(
    context: InstallationMemberContext,
    record_type: RecoverableRecordType,
    *,
    organization: Organization | None,
) -> tuple[bool, bool]:
    policy = RECOVERY_POLICIES[record_type]
    can_view = context_has_permission(context, policy.view, organization=organization)
    can_restore = (
        can_view
        and context_has_permission(context, PermissionKey.RECYCLE_BIN_RESTORE, organization=organization)
        and context_has_permission(context, policy.restore, organization=organization)
    )
    return can_view, can_restore


def _item(
    *,
    workspace: ResolvedWorkspace,
    record_id: UUID,
    record_type: RecoverableRecordType,
    label: str,
    archived_at: datetime,
    cascade_count: int,
    can_restore: bool,
) -> RecycleBinItem:
    return RecycleBinItem(
        id=record_id,
        record_type=record_type,
        label=label,
        archived_at=archived_at,
        workspace_kind=workspace.kind,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        cascade_count=cascade_count,
        can_restore=can_restore,
    )


def _scope_records(queryset: QuerySet, workspace: ResolvedWorkspace) -> QuerySet:  # type: ignore[type-arg]
    if workspace.organization is None:
        return queryset.filter(organization__isnull=True)
    return queryset.filter(organization=workspace.organization)


def _location_cascade_count(root: Location, records: list[Location]) -> int:
    selected = {root.id}
    changed = True
    while changed:
        changed = False
        for record in records:
            if record.archived_at == root.archived_at and record.parent_id in selected and record.id not in selected:
                selected.add(record.id)
                changed = True
    return len(selected)


def recycle_bin_items(workspace: ResolvedWorkspace) -> list[RecycleBinItem]:
    context = workspace.member
    items: list[RecycleBinItem] = []

    if workspace.kind == "msp":
        organizations = (
            Organization.scoped.for_tenant(context.tenant)
            .filter(entity__archived_at__isnull=False)
            .select_related("entity")
        )
        for organization in organizations:
            if not context_has_archived_organization_permission(
                context,
                PermissionKey.RECYCLE_BIN_VIEW,
                organization=organization,
            ) or not context_has_archived_organization_permission(
                context,
                PermissionKey.ORGANIZATIONS_VIEW,
                organization=organization,
            ):
                continue
            archived_at = organization.entity.archived_at
            if archived_at is None:
                continue
            can_restore = context_has_archived_organization_permission(
                context,
                PermissionKey.RECYCLE_BIN_RESTORE,
                organization=organization,
            ) and context_has_archived_organization_permission(
                context,
                PermissionKey.ORGANIZATIONS_ARCHIVE,
                organization=organization,
            )
            items.append(
                _item(
                    workspace=workspace,
                    record_id=organization.entity_id,
                    record_type=RecoverableRecordType.ORGANIZATION,
                    label=organization.entity.display_name,
                    archived_at=archived_at,
                    cascade_count=1,
                    can_restore=can_restore,
                )
            )

    can_view_people, can_restore_people = _has_permissions(
        context,
        RecoverableRecordType.PERSON_ASSOCIATION,
        organization=workspace.organization,
    )
    if can_view_people:
        associations = (
            _scope_records(
                PersonAssociation.scoped.for_tenant(context.tenant),
                workspace,
            )
            .filter(archived_at__isnull=False)
            .select_related("person__entity")
        )
        for association in associations:
            if association.archived_at is not None:
                items.append(
                    _item(
                        workspace=workspace,
                        record_id=association.person.entity_id,
                        record_type=RecoverableRecordType.PERSON_ASSOCIATION,
                        label=association.person.entity.display_name,
                        archived_at=association.archived_at,
                        cascade_count=1,
                        can_restore=can_restore_people,
                    )
                )

    can_view_sites, can_restore_sites = _has_permissions(
        context,
        RecoverableRecordType.SITE,
        organization=workspace.organization,
    )
    if can_view_sites:
        sites = list(
            _scope_records(Site.scoped.for_tenant(context.tenant), workspace)
            .filter(archived_at__isnull=False)
            .select_related("entity")
        )
        locations = list(
            _scope_records(Location.scoped.for_tenant(context.tenant), workspace)
            .filter(archived_at__isnull=False)
            .select_related("entity", "site", "parent")
        )
        for site in sites:
            if site.archived_at is None:
                continue
            cascade_count = 1 + sum(
                1 for location in locations if location.site_id == site.id and location.archived_at == site.archived_at
            )
            items.append(
                _item(
                    workspace=workspace,
                    record_id=site.entity_id,
                    record_type=RecoverableRecordType.SITE,
                    label=site.entity.display_name,
                    archived_at=site.archived_at,
                    cascade_count=cascade_count,
                    can_restore=can_restore_sites,
                )
            )
        active_site_ids = set(
            _scope_records(Site.scoped.for_tenant(context.tenant), workspace)
            .filter(archived_at__isnull=True)
            .values_list("id", flat=True)
        )
        for location in locations:
            if location.site_id not in active_site_ids or location.archived_at is None:
                continue
            if location.parent is not None and location.parent.archived_at is not None:
                continue
            items.append(
                _item(
                    workspace=workspace,
                    record_id=location.entity_id,
                    record_type=RecoverableRecordType.LOCATION,
                    label=location.entity.display_name,
                    archived_at=location.archived_at,
                    cascade_count=_location_cascade_count(location, locations),
                    can_restore=can_restore_sites,
                )
            )

    can_view_fields, can_restore_fields = _has_permissions(
        context,
        RecoverableRecordType.CUSTOM_FIELD_DEFINITION,
        organization=workspace.organization,
    )
    if can_view_fields:
        definitions = (
            _scope_records(CustomFieldDefinition.scoped.for_tenant(context.tenant), workspace)
            .filter(archived_at__isnull=False)
            .prefetch_related("versions")
        )
        for definition in definitions:
            if definition.archived_at is not None:
                items.append(
                    _item(
                        workspace=workspace,
                        record_id=definition.id,
                        record_type=RecoverableRecordType.CUSTOM_FIELD_DEFINITION,
                        label=latest_version(definition).label,
                        archived_at=definition.archived_at,
                        cascade_count=1,
                        can_restore=can_restore_fields,
                    )
                )

    can_view_contracts, can_restore_contracts = _has_permissions(
        context,
        RecoverableRecordType.COMMERCIAL_CONTRACT,
        organization=workspace.organization,
    )
    if can_view_contracts and workspace.organization is not None:
        contracts = (
            _scope_records(CommercialContract.scoped.for_tenant(context.tenant), workspace)
            .filter(archived_at__isnull=False)
            .select_related("entity")
        )
        for contract in contracts:
            if contract.archived_at is not None:
                items.append(
                    _item(
                        workspace=workspace,
                        record_id=contract.entity_id,
                        record_type=RecoverableRecordType.COMMERCIAL_CONTRACT,
                        label=contract.entity.display_name,
                        archived_at=contract.archived_at,
                        cascade_count=1 + contract.costs.filter(archived_at=contract.archived_at).count(),
                        can_restore=can_restore_contracts,
                    )
                )

    return sorted(items, key=lambda item: (item.archived_at, str(item.id)), reverse=True)


def _require_recovery_permissions(
    *,
    workspace: ResolvedWorkspace,
    user: User,
    record_type: RecoverableRecordType,
) -> None:
    policy = RECOVERY_POLICIES[record_type]
    require_permission(user, PermissionKey.RECYCLE_BIN_RESTORE, organization=workspace.organization)
    require_permission(user, policy.restore, organization=workspace.organization)


def _restore_organization(*, workspace: ResolvedWorkspace, user: User, record_id: UUID) -> UUID:
    if workspace.kind != "msp":
        raise Organization.DoesNotExist
    organization = (
        Organization.scoped.for_tenant(workspace.member.tenant)
        .select_related("entity")
        .select_for_update(of=("self",))
        .get(entity_id=record_id, entity__archived_at__isnull=False)
    )
    require_archived_organization_permission(
        user,
        PermissionKey.RECYCLE_BIN_RESTORE,
        organization=organization,
    )
    require_archived_organization_permission(
        user,
        PermissionKey.ORGANIZATIONS_ARCHIVE,
        organization=organization,
    )
    Entity.scoped.for_tenant(workspace.member.tenant).filter(id=organization.entity_id).update(
        archived_at=None,
        updated_at=timezone.now(),
    )
    return organization.entity_id


def _restore_person(*, workspace: ResolvedWorkspace, record_id: UUID) -> UUID:
    association = (
        _scope_records(
            PersonAssociation.scoped.for_tenant(workspace.member.tenant),
            workspace,
        )
        .select_related("person__entity", "site", "structured_location")
        .select_for_update(of=("self",))
        .get(person__entity_id=record_id, archived_at__isnull=False)
    )
    if association.site is not None and association.site.archived_at is not None:
        raise RecoveryConflict("Restore the person's structured site before restoring this record.")
    if association.structured_location is not None and association.structured_location.archived_at is not None:
        raise RecoveryConflict("Restore the person's structured location before restoring this record.")
    PersonAssociation.scoped.for_tenant(workspace.member.tenant).filter(id=association.id).update(
        archived_at=None,
        updated_at=timezone.now(),
    )
    return cast(UUID, association.person.entity_id)


def _restore_site(*, workspace: ResolvedWorkspace, record_id: UUID) -> UUID:
    site = (
        _scope_records(Site.scoped.for_tenant(workspace.member.tenant), workspace)
        .select_related("entity")
        .select_for_update()
        .get(entity_id=record_id, archived_at__isnull=False)
    )
    archived_at = site.archived_at
    locations = _scope_records(Location.scoped.for_tenant(workspace.member.tenant), workspace).filter(
        site=site,
        archived_at=archived_at,
    )
    entity_ids = list(locations.values_list("entity_id", flat=True))
    restored_at = timezone.now()
    Entity.scoped.for_tenant(workspace.member.tenant).filter(id__in=entity_ids).update(
        archived_at=None,
        updated_at=restored_at,
    )
    locations.update(archived_at=None, updated_at=restored_at)
    Entity.scoped.for_tenant(workspace.member.tenant).filter(id=site.entity_id).update(
        archived_at=None,
        updated_at=restored_at,
    )
    Site.scoped.for_tenant(workspace.member.tenant).filter(id=site.id).update(
        archived_at=None,
        updated_at=restored_at,
    )
    return cast(UUID, site.entity_id)


def _restore_location(*, workspace: ResolvedWorkspace, record_id: UUID) -> UUID:
    location = (
        _scope_records(Location.scoped.for_tenant(workspace.member.tenant), workspace)
        .select_related("site", "parent")
        .select_for_update(of=("self",))
        .get(entity_id=record_id, archived_at__isnull=False)
    )
    if location.site.archived_at is not None:
        raise RecoveryConflict("Restore the site before restoring this location.")
    if location.parent is not None and location.parent.archived_at is not None:
        raise RecoveryConflict("Restore the parent location before restoring this location.")
    all_locations = list(
        _scope_records(Location.scoped.for_tenant(workspace.member.tenant), workspace)
        .filter(site=location.site)
        .values("id", "parent_id", "entity_id", "archived_at")
    )
    selected_ids = {location.id}
    changed = True
    while changed:
        changed = False
        for item in all_locations:
            if (
                item["archived_at"] == location.archived_at
                and item["parent_id"] in selected_ids
                and item["id"] not in selected_ids
            ):
                selected_ids.add(item["id"])
                changed = True
    entity_ids = [item["entity_id"] for item in all_locations if item["id"] in selected_ids]
    restored_at = timezone.now()
    Entity.scoped.for_tenant(workspace.member.tenant).filter(id__in=entity_ids).update(
        archived_at=None,
        updated_at=restored_at,
    )
    Location.scoped.for_tenant(workspace.member.tenant).filter(id__in=selected_ids).update(
        archived_at=None,
        updated_at=restored_at,
    )
    return cast(UUID, location.entity_id)


def _restore_custom_field(*, workspace: ResolvedWorkspace, record_id: UUID) -> UUID:
    definition = (
        _scope_records(CustomFieldDefinition.scoped.for_tenant(workspace.member.tenant), workspace)
        .select_for_update()
        .get(id=record_id, archived_at__isnull=False)
    )
    CustomFieldDefinition.scoped.for_tenant(workspace.member.tenant).filter(id=definition.id).update(
        archived_at=None,
        updated_at=timezone.now(),
    )
    return cast(UUID, definition.id)


def _restore_commercial_contract(*, workspace: ResolvedWorkspace, record_id: UUID) -> UUID:
    contract = (
        _scope_records(CommercialContract.scoped.for_tenant(workspace.member.tenant), workspace)
        .select_related("entity", "provider__entity")
        .select_for_update()
        .get(entity_id=record_id, archived_at__isnull=False)
    )
    if contract.provider.entity.archived_at is not None:
        raise RecoveryConflict("Restore the provider organization before restoring this contract.")
    archived_at = contract.archived_at
    restored_at = timezone.now()
    CommercialContract.scoped.for_tenant(workspace.member.tenant).filter(id=contract.id).update(
        archived_at=None, updated_at=restored_at
    )
    ContractCost.scoped.for_tenant(workspace.member.tenant).filter(contract=contract, archived_at=archived_at).update(
        archived_at=None, updated_at=restored_at
    )
    Entity.scoped.for_tenant(workspace.member.tenant).filter(id=contract.entity_id).update(
        archived_at=None, updated_at=restored_at
    )
    return cast(UUID, contract.entity_id)


@transaction.atomic
def restore_recycle_bin_item(
    *,
    workspace: ResolvedWorkspace,
    user: User,
    record_type: RecoverableRecordType,
    record_id: UUID,
) -> None:
    if record_type == RecoverableRecordType.ORGANIZATION:
        entity_id = _restore_organization(workspace=workspace, user=user, record_id=record_id)
    else:
        _require_recovery_permissions(workspace=workspace, user=user, record_type=record_type)
        restorers = {
            RecoverableRecordType.PERSON_ASSOCIATION: _restore_person,
            RecoverableRecordType.SITE: _restore_site,
            RecoverableRecordType.LOCATION: _restore_location,
            RecoverableRecordType.CUSTOM_FIELD_DEFINITION: _restore_custom_field,
            RecoverableRecordType.COMMERCIAL_CONTRACT: _restore_commercial_contract,
        }
        entity_id = restorers[record_type](workspace=workspace, record_id=record_id)
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=user,
        action=f"{record_type.value}.restored",
        entity_id=entity_id,
        metadata={},
    )
