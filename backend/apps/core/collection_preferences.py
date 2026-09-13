"""Personal presentation choices; never record values or workspace filters."""

from dataclasses import dataclass
from uuid import UUID

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission

from .inventory_views import StrictSerializer, _workspace
from .models import CollectionPreference


@dataclass(frozen=True)
class CollectionDefinition:
    permission: PermissionKey
    columns: tuple[tuple[str, PermissionKey], ...]
    defaults: tuple[str, ...]


COLLECTIONS = {
    "wireless-register": CollectionDefinition(
        PermissionKey.NETWORKS_VIEW,
        tuple((column, PermissionKey.NETWORKS_VIEW) for column in ("name", "network", "status", "purpose", "security")),
        ("name", "network", "status", "security"),
    ),
    "network-wireless": CollectionDefinition(
        PermissionKey.NETWORKS_VIEW,
        tuple((column, PermissionKey.NETWORKS_VIEW) for column in ("name", "status", "purpose", "security")),
        ("name", "status", "purpose", "security"),
    ),
    "network-addresses": CollectionDefinition(
        PermissionKey.NETWORKS_VIEW,
        tuple((column, PermissionKey.NETWORKS_VIEW) for column in ("name", "status", "dns_name")),
        ("name", "status", "dns_name"),
    ),
    "networks": CollectionDefinition(
        PermissionKey.NETWORKS_VIEW,
        tuple((column, PermissionKey.NETWORKS_VIEW) for column in ("name", "location", "vlan", "cidr")),
        ("name", "location", "vlan", "cidr"),
    ),
    "contracts": CollectionDefinition(
        PermissionKey.ASSETS_VIEW,
        tuple(
            (column, PermissionKey.ASSETS_VIEW)
            for column in ("name", "provider", "kind", "status", "renews_on", "ends_on")
        ),
        ("name", "provider", "kind", "status", "renews_on", "ends_on"),
    ),
    "assets": CollectionDefinition(
        PermissionKey.ASSETS_VIEW,
        tuple(
            (column, PermissionKey.ASSETS_VIEW)
            for column in ("name", "model", "status", "assignment", "site", "warranty")
        ),
        ("name", "model", "status", "assignment", "site", "warranty"),
    ),
}


class CollectionPreferenceWriteSerializer(StrictSerializer):
    columns = serializers.ListField(child=serializers.CharField(max_length=64), max_length=32, allow_empty=False)
    page_size = serializers.ChoiceField(choices=(25, 50, 100))

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Provide a preference object."]})
        return super().to_internal_value(data)  # type: ignore[no-untyped-call]


class CollectionPreferenceSerializer(CollectionPreferenceWriteSerializer):
    available_columns = serializers.ListField(child=serializers.CharField())
    default_columns = serializers.ListField(child=serializers.CharField())


class CollectionPreferenceView(APIView):
    @extend_schema(responses={200: CollectionPreferenceSerializer})
    def get(self, request: Request, feature: str, organization_entity_id: UUID | None = None) -> Response:
        return self.respond(request, feature, organization_entity_id)

    @extend_schema(request=CollectionPreferenceWriteSerializer, responses={200: CollectionPreferenceSerializer})
    def put(self, request: Request, feature: str, organization_entity_id: UUID | None = None) -> Response:
        return self.respond(request, feature, organization_entity_id)

    @extend_schema(request=None, responses={200: CollectionPreferenceSerializer})
    def delete(self, request: Request, feature: str, organization_entity_id: UUID | None = None) -> Response:
        return self.respond(request, feature, organization_entity_id)

    def respond(self, request: Request, feature: str, organization_entity_id: UUID | None) -> Response:
        definition = COLLECTIONS.get(feature)
        if definition is None:
            raise Http404
        workspace = _workspace(request, organization_entity_id, definition.permission)
        if request.query_params:
            raise serializers.ValidationError("Query parameters are not accepted.")
        allowed = [
            key
            for key, permission in definition.columns
            if context_has_permission(workspace.member, permission, organization=workspace.organization)
        ]
        defaults = [key for key in definition.defaults if key in allowed]
        owner = {"tenant": workspace.member.tenant, "user": request.user, "feature": feature}
        preferences = CollectionPreference.scoped.for_tenant(workspace.member.tenant)
        if request.method == "PUT":
            serializer = CollectionPreferenceWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            selected = values["columns"]
            if "name" not in selected or len(set(selected)) != len(selected) or set(selected) - set(allowed):
                raise serializers.ValidationError({"columns": "Choose available columns once and retain name."})
            preferences.update_or_create(
                **owner,
                defaults={"columns": [key for key in allowed if key in selected], "page_size": values["page_size"]},
            )
        elif request.method == "DELETE":
            if request.data:
                raise serializers.ValidationError("Reset does not accept a body.")
            preferences.filter(**owner).delete()
        preference = preferences.filter(**owner).first()
        selected = preference.columns if preference else defaults
        # Reapply current policy and curated order, even for old preferences.
        columns = [key for key in allowed if key == "name" or key in selected]
        response = Response(
            CollectionPreferenceSerializer(
                {
                    "columns": columns,
                    "page_size": preference.page_size if preference else 25,
                    "available_columns": allowed,
                    "default_columns": defaults,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response
