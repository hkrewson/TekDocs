from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import InventoryError, require_operational_owner
from .models import NetworkInterface, NetworkIPAddress, NetworkMACAddress
from .network_endpoints import (
    NetworkEndpointError,
    create_interface,
    create_ip_address,
    create_mac_address,
    interfaces_for_scope,
    ip_addresses_for_scope,
    mac_addresses_for_scope,
    update_interface,
    update_ip_address,
    update_mac_address,
)
from .network_inventory_views import StrictSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class InterfaceWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    device_id = serializers.UUIDField(source="device_entity_id")
    kind = serializers.ChoiceField(
        choices=("physical", "virtual", "lag", "loopback", "tunnel", "wireless", "other"),
        default="physical",
    )
    status = serializers.ChoiceField(choices=("planned", "active", "disabled", "retired"), default="active")
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class IPAddressWriteSerializer(StrictSerializer):
    address = serializers.CharField(max_length=45, trim_whitespace=True)
    subnet_id = serializers.UUIDField(source="subnet_entity_id")
    hardware_asset_id = serializers.UUIDField(
        source="hardware_asset_entity_id", required=False, allow_null=True, default=None
    )
    status = serializers.ChoiceField(choices=("active", "reserved", "dhcp", "deprecated"), default="active")
    dns_name = serializers.CharField(max_length=253, required=False, allow_blank=True, default="")
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class MACAddressWriteSerializer(StrictSerializer):
    address = serializers.CharField(max_length=32, trim_whitespace=True)
    hardware_asset_id = serializers.UUIDField(
        source="hardware_asset_entity_id", required=False, allow_null=True, default=None
    )
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class InterfaceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    device_id = serializers.UUIDField(source="device.entity_id")
    device_name = serializers.CharField(source="device.entity.display_name")
    kind = serializers.CharField()
    status = serializers.CharField()
    description = serializers.CharField()


class IPAddressSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    address = serializers.CharField()
    address_family = serializers.IntegerField()
    subnet_id = serializers.UUIDField(source="subnet.entity_id")
    subnet_cidr = serializers.CharField(source="subnet.cidr")
    vrf_id = serializers.UUIDField(source="subnet.vrf.entity_id", allow_null=True)
    vrf_name = serializers.CharField(source="subnet.vrf.entity.display_name", allow_null=True)
    interface_id = serializers.UUIDField(source="interface.entity_id", allow_null=True)
    interface_name = serializers.CharField(source="interface.entity.display_name", allow_null=True)
    hardware_asset_id = serializers.SerializerMethodField()
    hardware_asset_name = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    status = serializers.CharField()
    dns_name = serializers.CharField()
    description = serializers.CharField()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_hardware_asset_id(self, record: NetworkIPAddress) -> UUID | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        return asset.entity_id if self.context.get("can_view_assets") and asset is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_hardware_asset_name(self, record: NetworkIPAddress) -> str | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        return asset.entity.display_name if self.context.get("can_view_assets") and asset is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_device_name(self, record: NetworkIPAddress) -> str | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        if self.context.get("can_view_assets") and asset is not None:
            return asset.entity.display_name
        interface = record.interface if record.interface_id else None
        return interface.device.entity.display_name if interface is not None else None


class MACAddressSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    address = serializers.CharField()
    interface_id = serializers.UUIDField(source="interface.entity_id", allow_null=True)
    interface_name = serializers.CharField(source="interface.entity.display_name", allow_null=True)
    hardware_asset_id = serializers.SerializerMethodField()
    hardware_asset_name = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    description = serializers.CharField()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_hardware_asset_id(self, record: NetworkMACAddress) -> UUID | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        return asset.entity_id if self.context.get("can_view_assets") and asset is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_hardware_asset_name(self, record: NetworkMACAddress) -> str | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        return asset.entity.display_name if self.context.get("can_view_assets") and asset is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_device_name(self, record: NetworkMACAddress) -> str | None:
        asset = record.hardware_asset if record.hardware_asset_id else None
        if self.context.get("can_view_assets") and asset is not None:
            return asset.entity.display_name
        interface = record.interface if record.interface_id else None
        return interface.device.entity.display_name if interface is not None else None


class CollectionResultSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class InterfaceResultSerializer(CollectionResultSerializer):
    results = InterfaceSerializer(many=True)


class IPAddressResultSerializer(CollectionResultSerializer):
    results = IPAddressSerializer(many=True)


class MACAddressResultSerializer(CollectionResultSerializer):
    results = MACAddressSerializer(many=True)


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    try:
        require_operational_owner(workspace.organization)
    except InventoryError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _page(
    queryset: QuerySet[Any], request: Any, workspace: ResolvedWorkspace, serializer: type[serializers.Serializer]
) -> Response:
    query = BoundedCollectionQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = paginate(queryset, **query.validated_data)
    return Response(
        serializer(
            {
                "results": page.records,
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
                "can_manage": context_has_permission(
                    workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
                ),
            },
            context={
                "can_view_assets": context_has_permission(
                    workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
                )
            },
        ).data
    )


def _error(exc: Exception) -> serializers.ValidationError:
    if isinstance(exc, DjangoValidationError):
        detail = "; ".join(exc.messages)
    elif isinstance(exc, IntegrityError):
        detail = "That value conflicts with an existing network record in this Workspace."
    else:
        detail = str(exc)
    return serializers.ValidationError({"detail": detail})


class InterfaceListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: InterfaceResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(interfaces_for_scope(workspace.data_scope), request, workspace, InterfaceResultSerializer)

    @extend_schema(request=InterfaceWriteSerializer, responses={201: InterfaceSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = InterfaceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_interface(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(InterfaceSerializer(record).data, status=201)


class InterfaceDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkInterface:
        try:
            return interfaces_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkInterface.DoesNotExist as exc:
            raise PermissionDenied("The selected interface is unavailable.") from exc

    @extend_schema(responses={200: InterfaceSerializer})
    def get(self, request, interface_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(InterfaceSerializer(self._record(workspace, interface_entity_id)).data)

    @extend_schema(request=InterfaceWriteSerializer, responses={200: InterfaceSerializer})
    def patch(self, request, interface_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = InterfaceWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_interface(
                record=self._record(workspace, interface_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(InterfaceSerializer(record).data)


class IPAddressListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: IPAddressResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(ip_addresses_for_scope(workspace.data_scope), request, workspace, IPAddressResultSerializer)

    @extend_schema(request=IPAddressWriteSerializer, responses={201: IPAddressSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = IPAddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("hardware_asset_entity_id") is not None:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            record = create_ip_address(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                interface_entity_id=None,
                **serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(IPAddressSerializer(record, context={"can_view_assets": True}).data, status=201)


class IPAddressDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkIPAddress:
        try:
            return ip_addresses_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkIPAddress.DoesNotExist as exc:
            raise PermissionDenied("The selected IP address is unavailable.") from exc

    @extend_schema(responses={200: IPAddressSerializer})
    def get(self, request, ip_address_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        return Response(
            IPAddressSerializer(
                self._record(workspace, ip_address_entity_id), context={"can_view_assets": can_view_assets}
            ).data
        )

    @extend_schema(request=IPAddressWriteSerializer, responses={200: IPAddressSerializer})
    def patch(self, request, ip_address_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = IPAddressWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "hardware_asset_id" in request.data:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            record = update_ip_address(
                record=self._record(workspace, ip_address_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        return Response(IPAddressSerializer(record, context={"can_view_assets": can_view_assets}).data)


class MACAddressListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: MACAddressResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(mac_addresses_for_scope(workspace.data_scope), request, workspace, MACAddressResultSerializer)

    @extend_schema(request=MACAddressWriteSerializer, responses={201: MACAddressSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = MACAddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("hardware_asset_entity_id") is not None:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            record = create_mac_address(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                interface_entity_id=None,
                **serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(MACAddressSerializer(record, context={"can_view_assets": True}).data, status=201)


class MACAddressDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkMACAddress:
        try:
            return mac_addresses_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkMACAddress.DoesNotExist as exc:
            raise PermissionDenied("The selected MAC address is unavailable.") from exc

    @extend_schema(responses={200: MACAddressSerializer})
    def get(self, request, mac_address_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        return Response(
            MACAddressSerializer(
                self._record(workspace, mac_address_entity_id), context={"can_view_assets": can_view_assets}
            ).data
        )

    @extend_schema(request=MACAddressWriteSerializer, responses={200: MACAddressSerializer})
    def patch(self, request, mac_address_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = MACAddressWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "hardware_asset_id" in request.data:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            record = update_mac_address(
                record=self._record(workspace, mac_address_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkEndpointError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        return Response(MACAddressSerializer(record, context={"can_view_assets": can_view_assets}).data)
