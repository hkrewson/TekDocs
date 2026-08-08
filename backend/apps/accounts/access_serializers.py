from rest_framework import serializers

from apps.core.models import OrganizationAccessMode

from .models import TENANT_ASSIGNABLE_ROLE_CHOICES, BuiltInRole


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


class MemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=BuiltInRole.choices)
    is_owner = serializers.BooleanField()
    joined_at = serializers.DateTimeField(allow_null=True)


class MemberRoleWriteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=TENANT_ASSIGNABLE_ROLE_CHOICES)


class OrganizationAccessSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)


class OrganizationAccessWriteSerializer(serializers.Serializer):
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)
