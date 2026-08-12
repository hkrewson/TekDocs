from __future__ import annotations

from collections.abc import Callable
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

from .collection_pagination import BoundedCollectionQuerySerializer, OffsetPageSerializer, paginate
from .inventory import InventoryError, require_operational_owner
from .models import NetworkSubnet, NetworkVLAN, NetworkVRF
from .network_addressing import (
    NetworkAddressingError,
    create_subnet,
    create_vlan,
    create_vrf,
    subnets_for_scope,
    update_subnet,
    update_vlan,
    update_vrf,
    vlans_for_scope,
    vrfs_for_scope,
)
from .network_inventory_views import StrictSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class VRFWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    route_distinguisher = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class VLANWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    vlan_id = serializers.IntegerField(min_value=1, max_value=4094)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class SubnetWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    cidr = serializers.CharField(max_length=49, trim_whitespace=True)
    vrf_id = serializers.UUIDField(source="vrf_entity_id", required=False, allow_null=True, default=None)
    vlan_id = serializers.UUIDField(source="vlan_entity_id", required=False, allow_null=True, default=None)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class VRFSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    route_distinguisher = serializers.CharField()
    description = serializers.CharField()


class VLANSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    vlan_id = serializers.IntegerField()
    description = serializers.CharField()


class SubnetSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    cidr = serializers.CharField()
    address_family = serializers.IntegerField()
    vrf_id = serializers.UUIDField(source="vrf.entity_id", allow_null=True)
    vrf_name = serializers.CharField(source="vrf.entity.display_name", allow_null=True)
    vlan_id = serializers.UUIDField(source="vlan.entity_id", allow_null=True)
    vlan_name = serializers.CharField(source="vlan.entity.display_name", allow_null=True)
    vlan_number = serializers.IntegerField(source="vlan.vlan_id", allow_null=True)
    description = serializers.CharField()


class CollectionResultSerializer(OffsetPageSerializer):
    pass
    can_manage = serializers.BooleanField()


class VRFResultSerializer(CollectionResultSerializer):
    results = VRFSerializer(many=True)


class VLANResultSerializer(CollectionResultSerializer):
    results = VLANSerializer(many=True)


class SubnetResultSerializer(CollectionResultSerializer):
    results = SubnetSerializer(many=True)


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
    queryset: QuerySet[Any],
    request: Any,
    workspace: ResolvedWorkspace,
    serializer: type[serializers.Serializer],
    transform: Callable[[Any], object] | None = None,
) -> Response:
    query = BoundedCollectionQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = paginate(queryset, **query.validated_data)
    return Response(
        serializer(
            {
                "results": [transform(item) for item in page.records] if transform else page.records,
                "page": page.page,
                "page_size": page.page_size,
                "count": page.count,
                "has_more": page.has_more,
                "can_manage": context_has_permission(
                    workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
                ),
            }
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


class VRFListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: VRFResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(vrfs_for_scope(workspace.data_scope), request, workspace, VRFResultSerializer)

    @extend_schema(request=VRFWriteSerializer, responses={201: VRFSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = VRFWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_vrf(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(VRFSerializer(record).data, status=201)


class VRFDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkVRF:
        try:
            return vrfs_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkVRF.DoesNotExist as exc:
            raise PermissionDenied("The selected VRF is unavailable.") from exc

    @extend_schema(responses={200: VRFSerializer})
    def get(self, request, vrf_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(VRFSerializer(self._record(workspace, vrf_entity_id)).data)

    @extend_schema(request=VRFWriteSerializer, responses={200: VRFSerializer})
    def patch(self, request, vrf_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = VRFWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_vrf(
                record=self._record(workspace, vrf_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(VRFSerializer(record).data)


class VLANListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: VLANResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(vlans_for_scope(workspace.data_scope), request, workspace, VLANResultSerializer)

    @extend_schema(request=VLANWriteSerializer, responses={201: VLANSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = VLANWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_vlan(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(VLANSerializer(record).data, status=201)


class VLANDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkVLAN:
        try:
            return vlans_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkVLAN.DoesNotExist as exc:
            raise PermissionDenied("The selected VLAN is unavailable.") from exc

    @extend_schema(responses={200: VLANSerializer})
    def get(self, request, vlan_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(VLANSerializer(self._record(workspace, vlan_entity_id)).data)

    @extend_schema(request=VLANWriteSerializer, responses={200: VLANSerializer})
    def patch(self, request, vlan_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = VLANWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_vlan(
                record=self._record(workspace, vlan_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(VLANSerializer(record).data)


class SubnetListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: SubnetResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(subnets_for_scope(workspace.data_scope), request, workspace, SubnetResultSerializer)

    @extend_schema(request=SubnetWriteSerializer, responses={201: SubnetSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = SubnetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_subnet(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(SubnetSerializer(record).data, status=201)


class SubnetDetailView(APIView):
    def _record(self, workspace: ResolvedWorkspace, entity_id: UUID) -> NetworkSubnet:
        try:
            return subnets_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkSubnet.DoesNotExist as exc:
            raise PermissionDenied("The selected subnet is unavailable.") from exc

    @extend_schema(responses={200: SubnetSerializer})
    def get(self, request, subnet_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(SubnetSerializer(self._record(workspace, subnet_entity_id)).data)

    @extend_schema(request=SubnetWriteSerializer, responses={200: SubnetSerializer})
    def patch(self, request, subnet_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = SubnetWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_subnet(
                record=self._record(workspace, subnet_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(SubnetSerializer(record).data)
