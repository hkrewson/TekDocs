from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import AuditEvent, Organization, OrganizationAccessMode

from .models import TENANT_ASSIGNABLE_ROLES, BuiltInRole, TenantMembership, User
from .policy import InstallationMemberContext, PermissionKey, require_permission


@dataclass(frozen=True, slots=True)
class MemberProjection:
    id: UUID
    display_name: str
    email: str
    role: str
    is_owner: bool
    joined_at: datetime | None


def members_for_context(context: InstallationMemberContext) -> list[MemberProjection]:
    memberships = TenantMembership.scoped.for_tenant(context.tenant)
    if context.state.owner_id is not None:
        memberships = memberships.exclude(user_id=context.state.owner_id)
    memberships = memberships.select_related("user").order_by("user__display_name", "user__email", "user_id")
    owner = context.state.owner
    records = []
    if owner is not None:
        records.append(
            MemberProjection(
                id=owner.id,
                display_name=owner.display_name,
                email=owner.email,
                role=BuiltInRole.OWNER,
                is_owner=True,
                joined_at=context.state.bootstrapped_at,
            )
        )
    records.extend(
        MemberProjection(
            id=membership.user_id,
            display_name=membership.user.display_name,
            email=membership.user.email,
            role=membership.role,
            is_owner=False,
            joined_at=membership.created_at,
        )
        for membership in memberships
    )
    return records


@transaction.atomic
def assign_membership_role(
    *,
    actor: User,
    member_user_id: UUID,
    role: BuiltInRole,
) -> TenantMembership:
    context = require_permission(actor, PermissionKey.MEMBERSHIPS_ASSIGN_ROLE)
    if role not in TENANT_ASSIGNABLE_ROLES:
        raise ValidationError({"role": "Select a tenant-assignable built-in role."})
    if member_user_id == actor.id:
        raise ValidationError({"role": "You cannot change your own role."})
    try:
        membership = (
            TenantMembership.scoped.for_tenant(context.tenant)
            .select_for_update()
            .select_related("user")
            .get(user_id=member_user_id)
        )
    except TenantMembership.DoesNotExist as exc:
        raise NotFound("The tenant member is not available.") from exc
    if membership.role == role:
        return membership
    membership.role = role
    membership.save(update_fields=("role",))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="membership.role_assigned",
        entity_id=membership.user_id,
        metadata={},
    )
    return membership


def access_mode_organizations(context: InstallationMemberContext):  # type: ignore[no-untyped-def]
    return (
        Organization.scoped.for_tenant(context.tenant)
        .filter(entity__archived_at__isnull=True)
        .select_related("entity")
        .order_by("entity__display_name", "entity_id")
    )


@transaction.atomic
def change_organization_access_mode(
    *,
    actor: User,
    organization_entity_id: UUID,
    access_mode: OrganizationAccessMode,
) -> Organization:
    context = require_permission(actor, PermissionKey.ORGANIZATIONS_MANAGE_ACCESS)
    try:
        organization = (
            Organization.scoped.for_tenant(context.tenant)
            .select_for_update()
            .select_related("entity")
            .get(entity_id=organization_entity_id, entity__archived_at__isnull=True)
        )
    except Organization.DoesNotExist as exc:
        raise NotFound("The organization is not available.") from exc
    if organization.access_mode == access_mode:
        return organization
    organization.access_mode = access_mode
    organization.updated_at = timezone.now()
    organization.save(update_fields=("access_mode", "updated_at"))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="organization.access_mode_changed",
        entity_id=organization.entity_id,
        metadata={},
    )
    return organization
