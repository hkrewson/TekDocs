from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import AuditEvent, InstallationState, Organization

from .models import (
    CustomRole,
    CustomRolePermission,
    CustomRoleScope,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)
from .policy import (
    CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS,
    InstallationMemberContext,
    PermissionKey,
    require_permission,
)


def custom_roles_for_context(context: InstallationMemberContext) -> QuerySet[CustomRole]:
    return (
        CustomRole.scoped.for_tenant(context.tenant)
        .prefetch_related("permission_rows")
        .annotate(assignment_count=Count("assignments"))
        .order_by("archived_at", "name_key", "id")
    )


def scoped_assignments_for_context(context: InstallationMemberContext) -> QuerySet[ScopedRoleAssignment]:
    return (
        ScopedRoleAssignment.scoped.for_tenant(context.tenant)
        .select_related("membership__user", "role", "organization__entity")
        .prefetch_related(
            Prefetch("role__permission_rows", queryset=CustomRolePermission.objects.order_by("permission"))
        )
        .order_by("membership__user__display_name", "role__name_key", "organization__entity__display_name")
    )


def _validated_permissions(permission_values: list[str]) -> list[PermissionKey]:
    values = set(permission_values)
    allowed = {permission.value: permission for permission in CUSTOM_ROLE_ASSIGNABLE_PERMISSIONS}
    invalid = sorted(values - allowed.keys())
    if invalid:
        raise ValidationError({"permissions": "One or more permissions cannot be delegated through custom roles."})
    if not values:
        raise ValidationError({"permissions": "Select at least one permission."})
    return sorted((allowed[value] for value in values), key=lambda permission: permission.value)


@transaction.atomic
def create_custom_role(
    *,
    actor: User,
    name: str,
    description: str,
    scope: CustomRoleScope,
    permissions: list[str],
) -> CustomRole:
    context = require_permission(actor, PermissionKey.CUSTOM_ROLES_MANAGE)
    validated = _validated_permissions(permissions)
    role = CustomRole(
        tenant=context.tenant,
        name=name,
        description=description,
        scope=scope,
        created_by=actor,
    )
    role.full_clean(exclude=("name_key",))
    try:
        role.save()
    except IntegrityError as exc:
        raise ValidationError({"name": "A role with this name and scope already exists."}) from exc
    CustomRolePermission.objects.bulk_create(
        [CustomRolePermission(tenant=context.tenant, role=role, permission=item.value) for item in validated]
    )
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="custom_role.created",
        entity_id=role.id,
        metadata={},
    )
    return custom_roles_for_context(context).get(pk=role.pk)


def _active_role_for_update(context: InstallationMemberContext, role_id: UUID) -> CustomRole:
    try:
        return (
            CustomRole.scoped.for_tenant(context.tenant)
            .select_for_update()
            .get(pk=role_id, archived_at__isnull=True)
        )
    except CustomRole.DoesNotExist as exc:
        raise NotFound("The custom role is not available.") from exc


@transaction.atomic
def update_custom_role(
    *,
    actor: User,
    role_id: UUID,
    name: str,
    description: str,
    permissions: list[str],
) -> CustomRole:
    context = require_permission(actor, PermissionKey.CUSTOM_ROLES_MANAGE)
    validated = _validated_permissions(permissions)
    role = _active_role_for_update(context, role_id)
    role.name = name
    role.description = description
    role.full_clean(exclude=("name_key",))
    try:
        role.save(update_fields=("name", "name_key", "description", "updated_at"))
    except IntegrityError as exc:
        raise ValidationError({"name": "A role with this name and scope already exists."}) from exc
    CustomRolePermission.scoped.for_tenant(context.tenant).filter(role=role).delete()
    CustomRolePermission.objects.bulk_create(
        [CustomRolePermission(tenant=context.tenant, role=role, permission=item.value) for item in validated]
    )
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="custom_role.updated",
        entity_id=role.id,
        metadata={},
    )
    return custom_roles_for_context(context).get(pk=role.pk)


@transaction.atomic
def archive_custom_role(*, actor: User, role_id: UUID) -> CustomRole:
    context = require_permission(actor, PermissionKey.CUSTOM_ROLES_MANAGE)
    role = _active_role_for_update(context, role_id)
    role.archived_at = timezone.now()
    role.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="custom_role.archived",
        entity_id=role.id,
        metadata={},
    )
    return custom_roles_for_context(context).get(pk=role.pk)


@transaction.atomic
def create_scoped_assignment(
    *,
    actor: User,
    member_user_id: UUID,
    role_id: UUID,
    organization_entity_id: UUID | None,
) -> tuple[ScopedRoleAssignment, bool]:
    context = require_permission(actor, PermissionKey.CUSTOM_ROLES_ASSIGN)
    try:
        membership = TenantMembership.scoped.for_tenant(context.tenant).get(user_id=member_user_id)
    except TenantMembership.DoesNotExist as exc:
        raise NotFound("The tenant member is not available.") from exc
    if InstallationState.objects.filter(
        tenant=context.tenant,
        owner_id=membership.user_id,
    ).exists():
        raise ValidationError({"user_id": "The installation owner cannot receive a custom role assignment."})
    try:
        role = CustomRole.scoped.for_tenant(context.tenant).get(pk=role_id, archived_at__isnull=True)
    except CustomRole.DoesNotExist as exc:
        raise NotFound("The custom role is not available.") from exc
    organization = None
    if role.scope == CustomRoleScope.ORGANIZATION:
        if organization_entity_id is None:
            raise ValidationError({"organization_id": "Select an organization for this role."})
        try:
            organization = Organization.scoped.for_tenant(context.tenant).get(
                entity_id=organization_entity_id,
                entity__archived_at__isnull=True,
            )
        except Organization.DoesNotExist as exc:
            raise NotFound("The organization is not available.") from exc
    elif organization_entity_id is not None:
        raise ValidationError({"organization_id": "Tenant-scoped roles cannot target an organization."})
    assignment, created = ScopedRoleAssignment.objects.get_or_create(
        tenant=context.tenant,
        membership=membership,
        role=role,
        organization=organization,
        defaults={"created_by": actor},
    )
    if created:
        AuditEvent.objects.create(
            tenant=context.tenant,
            actor=actor,
            action="custom_role.assigned",
            entity_id=assignment.id,
            metadata={},
        )
    return scoped_assignments_for_context(context).get(pk=assignment.pk), created


@transaction.atomic
def remove_scoped_assignment(*, actor: User, assignment_id: UUID) -> None:
    context = require_permission(actor, PermissionKey.CUSTOM_ROLES_ASSIGN)
    assignment = (
        ScopedRoleAssignment.scoped.for_tenant(context.tenant)
        .select_for_update()
        .filter(pk=assignment_id)
        .first()
    )
    if assignment is None:
        raise NotFound("The scoped role assignment is not available.")
    assignment.delete()
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="custom_role.unassigned",
        entity_id=assignment_id,
        metadata={},
    )
