from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .domain_hierarchy import (
    HostnameInput,
    create_hostname,
    domain_for_workspace,
    hostnames_for_domain,
    record_dns_observation,
)
from .domains import DomainError
from .models import ManagedHostname
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class HostnameWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=253)
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    provenance = serializers.ChoiceField(choices=("entered", "discovered"))
    source = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class ObservationWriteSerializer(serializers.Serializer):
    record_type = serializers.ChoiceField(choices=("A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA", "SRV"))
    value = serializers.CharField(max_length=1_024)
    ttl = serializers.IntegerField(min_value=0, max_value=2_147_483_647, required=False, allow_null=True, default=None)
    provenance = serializers.ChoiceField(choices=("entered", "discovered"))
    source = serializers.CharField(max_length=120)
    observed_at = serializers.DateTimeField()


class HostnameSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="ascii_name")
    parent_id = serializers.UUIDField(source="parent.entity_id", allow_null=True)
    provenance = serializers.CharField()
    source = serializers.CharField()


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    return (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )


class HostnameListCreateView(APIView):
    @extend_schema(responses={200: HostnameSerializer(many=True)})
    def get(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        records = hostnames_for_domain(domain_for_workspace(workspace, domain_entity_id))[:500]
        return Response(HostnameSerializer(records, many=True).data)

    @extend_schema(request=HostnameWriteSerializer, responses={201: HostnameSerializer})
    def post(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        serializer = HostnameWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hostname = create_hostname(
                workspace=workspace,
                domain=domain_for_workspace(workspace, domain_entity_id),
                actor_id=request.user.pk,
                value=HostnameInput(**serializer.validated_data),
            )
        except DomainError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(HostnameSerializer(hostname).data, status=201)


class ObservationCreateView(APIView):
    @extend_schema(request=ObservationWriteSerializer, responses={201: dict})
    def post(self, request, hostname_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        try:
            hostname = ManagedHostname.scoped.for_scope(workspace.data_scope).get(
                entity_id=hostname_entity_id, archived_at__isnull=True
            )
        except ManagedHostname.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "The selected hostname is unavailable."}) from exc
        serializer = ObservationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            observation = record_dns_observation(
                hostname=hostname, actor_id=request.user.pk, **serializer.validated_data
            )
        except DomainError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response({"id": str(observation.id), "content_digest": observation.content_digest}, status=201)


@extend_schema_view(
    get=extend_schema(operation_id="msp_hostname_list"),
    post=extend_schema(operation_id="msp_hostname_create"),
)
class MSPHostnameListCreateView(HostnameListCreateView):
    pass


class OrganizationHostnameListCreateView(HostnameListCreateView):
    pass


class MSPObservationCreateView(ObservationCreateView):
    pass


class OrganizationObservationCreateView(ObservationCreateView):
    pass
