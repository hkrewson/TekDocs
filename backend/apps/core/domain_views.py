from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .domains import DomainError, DomainInput, create_domain, domains_for_scope
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class DomainWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=253)
    registrar_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    registration_date = serializers.DateField(required=False, allow_null=True, default=None)
    expiration_date = serializers.DateField(required=False, allow_null=True, default=None)
    renewal_mode = serializers.ChoiceField(choices=("manual", "auto", "external"))
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(choices=("active", "pending", "expired", "transferred"))
    notes = serializers.CharField(max_length=20_000, required=False, allow_blank=True, default="")


class DomainSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="ascii_name")
    registrar_id = serializers.UUIDField(source="registrar.entity_id", allow_null=True)
    registrar = serializers.CharField(source="registrar.name", allow_null=True)
    registration_date = serializers.DateField(allow_null=True)
    expiration_date = serializers.DateField(allow_null=True)
    renewal_mode = serializers.CharField()
    owner_id = serializers.UUIDField(allow_null=True)
    owner = serializers.CharField(source="owner.display_name", allow_null=True)
    status = serializers.CharField()
    notes = serializers.CharField()
    created_at = serializers.DateTimeField()


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    return (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )


class DomainListCreateView(APIView):
    @extend_schema(responses={200: DomainSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        return Response(DomainSerializer(domains_for_scope(workspace)[:500], many=True).data)

    @extend_schema(request=DomainWriteSerializer, responses={201: DomainSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        serializer = DomainWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            domain = create_domain(
                workspace=workspace, actor_id=request.user.pk, value=DomainInput(**serializer.validated_data)
            )
        except DomainError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(DomainSerializer(domain).data, status=201)


@extend_schema_view(
    get=extend_schema(operation_id="msp_domain_list"),
    post=extend_schema(operation_id="msp_domain_create"),
)
class MSPDomainListCreateView(DomainListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_domain_list"),
    post=extend_schema(operation_id="organization_domain_create"),
)
class OrganizationDomainListCreateView(DomainListCreateView):
    pass
