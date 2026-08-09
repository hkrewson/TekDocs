from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.models import OrganizationAccessMode

from .models import (
    TENANT_ASSIGNABLE_ROLE_CHOICES,
    BuiltInRole,
    CustomRole,
    CustomRoleScope,
    ScopedRoleAssignment,
)


class PermissionDefinitionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    category = serializers.CharField()
    requires_mfa = serializers.BooleanField()


class RoleDefinitionSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=BuiltInRole.choices)
    label = serializers.CharField()
    description = serializers.CharField()
    assignable_scope = serializers.ChoiceField(choices=("installation", "tenant", "organization"))
    permissions = serializers.ListField(child=serializers.CharField())


class AccessControlCatalogSerializer(serializers.Serializer):
    permissions = PermissionDefinitionSerializer(many=True)
    roles = RoleDefinitionSerializer(many=True)
    custom_assignable_permissions = PermissionDefinitionSerializer(many=True)


class MemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=BuiltInRole.choices)
    is_owner = serializers.BooleanField()
    joined_at = serializers.DateTimeField(allow_null=True)


class MemberRoleWriteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=TENANT_ASSIGNABLE_ROLE_CHOICES)


class AssignedStaffSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="membership.user_id")
    display_name = serializers.CharField(source="membership.user.display_name")
    email = serializers.EmailField(source="membership.user.email")
    role = serializers.ChoiceField(source="membership.role", choices=TENANT_ASSIGNABLE_ROLE_CHOICES)


class OrganizationAccessSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)
    assigned_staff = AssignedStaffSerializer(source="access_assignments", many=True, read_only=True)


class OrganizationAccessWriteSerializer(serializers.Serializer):
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)


class OrganizationStaffWriteSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class CustomRoleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField()
    scope = serializers.ChoiceField(choices=CustomRoleScope.choices)
    permissions = serializers.SerializerMethodField()
    assignment_count = serializers.IntegerField()
    archived_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj: CustomRole) -> list[str]:
        return [row.permission for row in obj.permission_rows.all()]


class CustomRoleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, trim_whitespace=True)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    scope = serializers.ChoiceField(choices=CustomRoleScope.choices)
    permissions = serializers.ListField(child=serializers.CharField(max_length=80), allow_empty=False)


class CustomRoleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, trim_whitespace=True)
    description = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    permissions = serializers.ListField(child=serializers.CharField(max_length=80), allow_empty=False)


class ScopedRoleAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_id = serializers.UUIDField(source="membership.user_id")
    member_name = serializers.CharField(source="membership.user.display_name")
    member_email = serializers.EmailField(source="membership.user.email")
    role_id = serializers.UUIDField()
    role_name = serializers.CharField(source="role.name")
    role_scope = serializers.ChoiceField(source="role.scope", choices=CustomRoleScope.choices)
    organization_id = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_organization_id(self, obj: ScopedRoleAssignment) -> UUID | None:
        return obj.organization.entity_id if obj.organization is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_organization_name(self, obj: ScopedRoleAssignment) -> str | None:
        return obj.organization.entity.display_name if obj.organization is not None else None


class ScopedRoleAssignmentWriteSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role_id = serializers.UUIDField()
    organization_id = serializers.UUIDField(required=False, allow_null=True, default=None)
