from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import APIToken, APITokenKind, APITokenWorkspaceScope


class APITokenWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=100, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=APITokenKind.choices)
    workspace_scope = serializers.ChoiceField(choices=APITokenWorkspaceScope.choices)
    organization_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=80), min_length=1, max_length=50, allow_empty=False
    )
    expires_in_days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class APITokenRotationSerializer(serializers.Serializer):
    expires_in_days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class APITokenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=APITokenKind.choices)
    name = serializers.CharField()
    display_prefix = serializers.SerializerMethodField()
    workspace_scope = serializers.ChoiceField(choices=APITokenWorkspaceScope.choices)
    organization = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    generation = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)
    rotated_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)

    def get_display_prefix(self, record: APIToken) -> str:
        marker = "tdp" if record.kind == APITokenKind.PERSONAL else "tds"
        return f"{marker}_{record.prefix}…"

    def get_organization(self, record: APIToken) -> dict[str, str] | None:
        if record.organization is None:
            return None
        return {"id": str(record.organization.entity_id), "name": record.organization.entity.display_name}

    def get_permissions(self, record: APIToken) -> list[str]:
        return sorted(row.permission for row in record.permission_rows.all())

    def get_status(self, record: APIToken) -> str:
        if record.revoked_at is not None:
            return "revoked"
        if record.expires_at <= timezone.now():
            return "expired"
        return "active"


class IssuedAPITokenSerializer(APITokenSerializer):
    token = serializers.CharField(write_only=False)


class APITokenCatalogSerializer(serializers.Serializer):
    tokens = APITokenSerializer(many=True)
    permissions = serializers.ListField(child=serializers.DictField())
