from __future__ import annotations

from typing import cast
from uuid import UUID

from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import InventoryError, assets_for_scope, require_operational_owner
from .models import NetworkDevice, NetworkDeviceRole, NetworkDeviceStatus, NetworkRack, NetworkRackStatus
from .network_inventory import (
    NetworkInventoryError,
    create_device,
    create_rack,
    devices_for_scope,
    racks_for_scope,
    update_device,
    update_rack,
)
from .sites import locations_for_scope, sites_for_scope
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class NetworkRackWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    site_id = serializers.UUIDField(source="site_entity_id")
    location_id = serializers.UUIDField(source="location_entity_id", allow_null=True, required=False, default=None)
    unit_count = serializers.IntegerField(min_value=1, max_value=100, required=False, default=42)
    status = serializers.ChoiceField(choices=NetworkRackStatus.values, required=False, default=NetworkRackStatus.ACTIVE)


class NetworkDeviceWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    role = serializers.ChoiceField(choices=NetworkDeviceRole.values)
    status = serializers.ChoiceField(
        choices=NetworkDeviceStatus.values, required=False, default=NetworkDeviceStatus.ACTIVE
    )
    hardware_asset_id = serializers.UUIDField(
        source="hardware_asset_entity_id", allow_null=True, required=False, default=None
    )
    site_id = serializers.UUIDField(source="site_entity_id", allow_null=True, required=False, default=None)
    location_id = serializers.UUIDField(source="location_entity_id", allow_null=True, required=False, default=None)
    rack_id = serializers.UUIDField(source="rack_entity_id", allow_null=True, required=False, default=None)
    rack_unit = serializers.IntegerField(min_value=1, max_value=100, allow_null=True, required=False, default=None)
    rack_units = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)


class NetworkRackSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    site_id = serializers.UUIDField(source="site.entity_id")
    site_name = serializers.CharField(source="site.entity.display_name")
    location_id = serializers.UUIDField(source="location.entity_id", allow_null=True)
    location_name = serializers.CharField(source="location.entity.display_name", allow_null=True)
    unit_count = serializers.IntegerField()
    status = serializers.CharField()
    device_count = serializers.SerializerMethodField()

    @extend_schema_field(serializers.IntegerField())
    def get_device_count(self, rack: NetworkRack) -> int:
        return len(rack.network_devices.all())


class NetworkDeviceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    role = serializers.CharField()
    status = serializers.CharField()
    hardware_asset_id = serializers.SerializerMethodField()
    hardware_asset_name = serializers.SerializerMethodField()
    site_id = serializers.UUIDField(source="site.entity.id", allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)
    location_id = serializers.UUIDField(source="location.entity.id", allow_null=True)
    location_name = serializers.CharField(source="location.entity.display_name", allow_null=True)
    rack_id = serializers.UUIDField(source="rack.entity.id", allow_null=True)
    rack_name = serializers.CharField(source="rack.entity.display_name", allow_null=True)
    rack_unit = serializers.IntegerField(allow_null=True)
    rack_units = serializers.IntegerField()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_hardware_asset_id(self, device: NetworkDevice) -> UUID | None:
        asset = device.hardware_asset if device.hardware_asset_id else None
        return asset.entity_id if self.context.get("can_view_assets") and asset is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_hardware_asset_name(self, device: NetworkDevice) -> str | None:
        asset = device.hardware_asset if device.hardware_asset_id else None
        return (
            asset.entity.display_name if self.context.get("can_view_assets") and asset is not None else None
        )


class NetworkRackResultSerializer(serializers.Serializer):
    results = NetworkRackSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class NetworkDeviceResultSerializer(serializers.Serializer):
    results = NetworkDeviceSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()
    can_view_relationships = serializers.BooleanField()
    can_create_relationships = serializers.BooleanField()
    can_archive_relationships = serializers.BooleanField()


class NetworkChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    site_id = serializers.UUIDField(allow_null=True, required=False)


class NetworkChoicesSerializer(serializers.Serializer):
    sites = NetworkChoiceSerializer(many=True)
    locations = NetworkChoiceSerializer(many=True)
    racks = NetworkChoiceSerializer(many=True)
    hardware_assets = NetworkChoiceSerializer(many=True)


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


def _rack(workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkRack:
    try:
        return racks_for_scope(workspace.data_scope).get(entity_id=entity_id)
    except NetworkRack.DoesNotExist as exc:
        raise PermissionDenied("The selected rack is unavailable.") from exc


def _device(workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkDevice:
    try:
        return devices_for_scope(workspace.data_scope).get(entity_id=entity_id)
    except NetworkDevice.DoesNotExist as exc:
        raise PermissionDenied("The selected network device is unavailable.") from exc


def _service_error(exc: NetworkInventoryError) -> serializers.ValidationError:
    return serializers.ValidationError({"detail": str(exc)})


def _device_data(device: NetworkDevice, workspace: ResolvedWorkspace) -> dict[str, object]:
    can_view_assets = context_has_permission(
        workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
    )
    return cast(dict[str, object], NetworkDeviceSerializer(device, context={"can_view_assets": can_view_assets}).data)


class NetworkRackListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: NetworkRackResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(racks_for_scope(workspace.data_scope), **query.validated_data)
        return Response(NetworkRackResultSerializer({
            "results": page.records,
            "page": page.page,
            "page_size": page.page_size,
            "count": page.count,
            "has_more": page.has_more,
            "can_manage": context_has_permission(
                workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
            ),
        }).data)

    @extend_schema(request=NetworkRackWriteSerializer, responses={201: NetworkRackSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkRackWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rack = create_rack(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except NetworkInventoryError as exc:
            raise _service_error(exc) from exc
        return Response(NetworkRackSerializer(rack).data, status=201)


class NetworkRackDetailView(APIView):
    @extend_schema(responses={200: NetworkRackSerializer})
    def get(self, request, rack_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(NetworkRackSerializer(_rack(workspace, rack_entity_id)).data)

    @extend_schema(request=NetworkRackWriteSerializer, responses={200: NetworkRackSerializer})
    def patch(self, request, rack_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkRackWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            rack = update_rack(
                rack=_rack(workspace, rack_entity_id), actor_id=request.user.pk, values=serializer.validated_data
            )
        except NetworkInventoryError as exc:
            raise _service_error(exc) from exc
        return Response(NetworkRackSerializer(rack).data)


class NetworkDeviceListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: NetworkDeviceResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(devices_for_scope(workspace.data_scope), **query.validated_data)
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        response = NetworkDeviceResultSerializer({
            "results": page.records,
            "page": page.page,
            "page_size": page.page_size,
            "count": page.count,
            "has_more": page.has_more,
            "can_manage": context_has_permission(
                workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
            ),
            "can_view_relationships": context_has_permission(
                workspace.member, PermissionKey.RELATIONSHIPS_VIEW, organization=workspace.organization
            ),
            "can_create_relationships": context_has_permission(
                workspace.member, PermissionKey.RELATIONSHIPS_CREATE, organization=workspace.organization
            ),
            "can_archive_relationships": context_has_permission(
                workspace.member, PermissionKey.RELATIONSHIPS_ARCHIVE, organization=workspace.organization
            ),
        }, context={"can_view_assets": can_view_assets}).data
        return Response(response)

    @extend_schema(request=NetworkDeviceWriteSerializer, responses={201: NetworkDeviceSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkDeviceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("hardware_asset_entity_id") is not None:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            device = create_device(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except NetworkInventoryError as exc:
            raise _service_error(exc) from exc
        return Response(_device_data(device, workspace), status=201)


class NetworkDeviceDetailView(APIView):
    @extend_schema(responses={200: NetworkDeviceSerializer})
    def get(self, request, device_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(_device_data(_device(workspace, device_entity_id), workspace))

    @extend_schema(request=NetworkDeviceWriteSerializer, responses={200: NetworkDeviceSerializer})
    def patch(self, request, device_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkDeviceWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "hardware_asset_id" in request.data:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            device = update_device(
                device=_device(workspace, device_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except NetworkInventoryError as exc:
            raise _service_error(exc) from exc
        return Response(_device_data(device, workspace))


class NetworkChoiceListView(APIView):
    @extend_schema(responses={200: NetworkChoicesSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        sites = sites_for_scope(workspace.data_scope)
        locations = locations_for_scope(workspace.data_scope)
        racks = racks_for_scope(workspace.data_scope)
        can_view_assets = context_has_permission(
            workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization
        )
        assets = (
            assets_for_scope(workspace.data_scope).filter(product__kind="hardware")
            if can_view_assets
            else []
        )
        return Response(NetworkChoicesSerializer({
            "sites": [{"id": item.entity_id, "name": item.entity.display_name} for item in sites],
            "locations": [
                {"id": item.entity_id, "name": item.entity.display_name, "site_id": item.site.entity_id}
                for item in locations
            ],
            "racks": [
                {"id": item.entity_id, "name": item.entity.display_name, "site_id": item.site.entity_id}
                for item in racks
            ],
            "hardware_assets": [{"id": item.entity_id, "name": item.entity.display_name} for item in assets],
        }).data)
