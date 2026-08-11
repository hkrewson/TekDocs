from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import InventoryError, require_operational_owner
from .models import (
    DNSRecord,
    DNSRecordType,
    DNSZone,
    WirelessNetwork,
    WirelessNetworkPurpose,
    WirelessNetworkSecurity,
    WirelessNetworkStatus,
)
from .network_inventory_views import StrictSerializer
from .network_services import (
    NetworkServiceError,
    create_dns_record,
    create_dns_zone,
    create_wireless_network,
    dns_records_for_scope,
    dns_zones_for_scope,
    update_dns_record,
    update_dns_zone,
    update_wireless_network,
    wireless_networks_for_scope,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class WirelessWriteSerializer(StrictSerializer):
    ssid = serializers.CharField(max_length=128, trim_whitespace=False)
    purpose = serializers.ChoiceField(choices=WirelessNetworkPurpose.values, default=WirelessNetworkPurpose.CORPORATE)
    security = serializers.ChoiceField(
        choices=WirelessNetworkSecurity.values, default=WirelessNetworkSecurity.WPA3_PERSONAL
    )
    status = serializers.ChoiceField(choices=WirelessNetworkStatus.values, default=WirelessNetworkStatus.ACTIVE)
    hidden = serializers.BooleanField(default=False)
    client_isolation = serializers.BooleanField(default=False)
    site_id = serializers.UUIDField(source="site_entity_id", required=False, allow_null=True, default=None)
    vlan_id = serializers.UUIDField(source="vlan_entity_id", required=False, allow_null=True, default=None)
    subnet_id = serializers.UUIDField(source="subnet_entity_id", required=False, allow_null=True, default=None)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class WirelessSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    ssid = serializers.CharField()
    purpose = serializers.CharField()
    security = serializers.CharField()
    status = serializers.CharField()
    hidden = serializers.BooleanField()
    client_isolation = serializers.BooleanField()
    site_id = serializers.UUIDField(source="site.entity_id", allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)
    vlan_id = serializers.UUIDField(source="vlan.entity_id", allow_null=True)
    vlan_name = serializers.CharField(source="vlan.entity.display_name", allow_null=True)
    vlan_number = serializers.IntegerField(source="vlan.vlan_id", allow_null=True)
    subnet_id = serializers.UUIDField(source="subnet.entity_id", allow_null=True)
    subnet_cidr = serializers.CharField(source="subnet.cidr", allow_null=True)
    description = serializers.CharField()


class ZoneWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=253, trim_whitespace=True)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class ZoneSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField()
    description = serializers.CharField()
    record_count = serializers.IntegerField(read_only=True)


class RecordWriteSerializer(StrictSerializer):
    zone_id = serializers.UUIDField(source="zone_entity_id")
    owner_name = serializers.CharField(max_length=253, trim_whitespace=True)
    record_type = serializers.ChoiceField(choices=DNSRecordType.values)
    value = serializers.CharField(max_length=4096, trim_whitespace=False)
    ttl = serializers.IntegerField(min_value=0, max_value=2147483647, default=3600)
    priority = serializers.IntegerField(min_value=0, max_value=65535, required=False, allow_null=True, default=None)
    weight = serializers.IntegerField(min_value=0, max_value=65535, required=False, allow_null=True, default=None)
    port = serializers.IntegerField(min_value=0, max_value=65535, required=False, allow_null=True, default=None)
    ip_address_id = serializers.UUIDField(source="ip_address_entity_id", required=False, allow_null=True, default=None)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class RecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    zone_id = serializers.UUIDField(source="zone.entity_id")
    zone_name = serializers.CharField(source="zone.name")
    owner_name = serializers.CharField()
    record_type = serializers.CharField()
    value = serializers.CharField()
    ttl = serializers.IntegerField()
    priority = serializers.IntegerField(allow_null=True)
    weight = serializers.IntegerField(allow_null=True)
    port = serializers.IntegerField(allow_null=True)
    ip_address_id = serializers.UUIDField(source="ip_address.entity_id", allow_null=True)
    description = serializers.CharField()


class CollectionSerializer(serializers.Serializer):
    results = serializers.ListField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    try:
        require_operational_owner(workspace.organization)
    except InventoryError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _page(
    queryset: QuerySet[Any], request: Any, workspace: ResolvedWorkspace, item_serializer: type[serializers.Serializer]
) -> Response:
    query = BoundedCollectionQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = paginate(queryset, **query.validated_data)
    return Response(
        {
            "results": item_serializer(page.records, many=True).data,
            "page": page.page,
            "page_size": page.page_size,
            "count": page.count,
            "has_more": page.has_more,
            "can_manage": context_has_permission(
                workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
            ),
        }
    )


def _error(exc: Exception) -> serializers.ValidationError:
    detail = (
        "; ".join(exc.messages)
        if isinstance(exc, DjangoValidationError)
        else (
            "That value conflicts with an existing record in this Workspace."
            if isinstance(exc, IntegrityError)
            else str(exc)
        )
    )
    return serializers.ValidationError({"detail": detail})


class WirelessListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: CollectionSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(wireless_networks_for_scope(workspace.data_scope), request, workspace, WirelessSerializer)

    @extend_schema(request=WirelessWriteSerializer, responses={201: WirelessSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = WirelessWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_wireless_network(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(WirelessSerializer(record).data, status=201)


class WirelessDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> WirelessNetwork:
        try:
            return wireless_networks_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except WirelessNetwork.DoesNotExist as exc:
            raise PermissionDenied("The selected wireless network is unavailable.") from exc

    @extend_schema(responses={200: WirelessSerializer})
    def get(self, request, wireless_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(WirelessSerializer(self._record(workspace, wireless_entity_id)).data)

    @extend_schema(request=WirelessWriteSerializer, responses={200: WirelessSerializer})
    def patch(self, request, wireless_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = WirelessWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_wireless_network(
                record=self._record(workspace, wireless_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(WirelessSerializer(record).data)


class DNSZoneListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: CollectionSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(dns_zones_for_scope(workspace.data_scope), request, workspace, ZoneSerializer)

    @extend_schema(request=ZoneWriteSerializer, responses={201: ZoneSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = ZoneWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            zone = create_dns_zone(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(ZoneSerializer(zone).data, status=201)


class DNSZoneDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> DNSZone:
        try:
            return dns_zones_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except DNSZone.DoesNotExist as exc:
            raise PermissionDenied("The selected DNS zone is unavailable.") from exc

    @extend_schema(responses={200: ZoneSerializer})
    def get(self, request, zone_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(ZoneSerializer(self._record(workspace, zone_entity_id)).data)

    @extend_schema(request=ZoneWriteSerializer, responses={200: ZoneSerializer})
    def patch(self, request, zone_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = ZoneWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            zone = update_dns_zone(
                zone=self._record(workspace, zone_entity_id), actor_id=request.user.pk, values=serializer.validated_data
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(ZoneSerializer(zone).data)


class DNSRecordListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: CollectionSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(dns_records_for_scope(workspace.data_scope), request, workspace, RecordSerializer)

    @extend_schema(request=RecordWriteSerializer, responses={201: RecordSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = RecordWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_dns_record(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(RecordSerializer(record).data, status=201)


class DNSRecordDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> DNSRecord:
        try:
            return dns_records_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except DNSRecord.DoesNotExist as exc:
            raise PermissionDenied("The selected DNS record is unavailable.") from exc

    @extend_schema(responses={200: RecordSerializer})
    def get(self, request, record_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(RecordSerializer(self._record(workspace, record_entity_id)).data)

    @extend_schema(request=RecordWriteSerializer, responses={200: RecordSerializer})
    def patch(self, request, record_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = RecordWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_dns_record(
                record=self._record(workspace, record_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkServiceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(RecordSerializer(record).data)
