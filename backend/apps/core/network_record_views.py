from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey

from .collection_pagination import BoundedCollectionQuerySerializer
from .models import NetworkSubnet
from .network_addressing import NetworkAddressingError
from .network_addressing_views import CollectionResultSerializer, _error, _page, _workspace
from .network_inventory_views import StrictSerializer
from .network_records import create_network_record, network_projection, network_records_for_scope, update_network_record


class NetworkRecordWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    location_id = serializers.UUIDField(source="location_entity_id", required=False, allow_null=True, default=None)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    vlan = serializers.IntegerField(
        source="vlan_number", min_value=1, max_value=4094, required=False, allow_null=True, default=None
    )
    cidr = serializers.CharField(max_length=49, trim_whitespace=True)
    use_full_range = serializers.BooleanField(required=False, default=True)
    range_start = serializers.CharField(max_length=45, required=False, allow_blank=True, allow_null=True, default=None)
    range_end = serializers.CharField(max_length=45, required=False, allow_blank=True, allow_null=True, default=None)
    primary_dns = serializers.CharField(max_length=45, required=False, allow_blank=True, allow_null=True, default=None)
    secondary_dns = serializers.CharField(
        max_length=45, required=False, allow_blank=True, allow_null=True, default=None
    )
    notes = serializers.CharField(max_length=8000, required=False, allow_blank=True, default="")


class NetworkRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    location_id = serializers.UUIDField(allow_null=True)
    location_name = serializers.CharField(allow_null=True)
    site_name = serializers.CharField(allow_null=True)
    description = serializers.CharField()
    vlan = serializers.IntegerField(allow_null=True)
    cidr = serializers.CharField()
    gateway = serializers.CharField()
    use_full_range = serializers.BooleanField()
    range_start = serializers.CharField()
    range_end = serializers.CharField()
    primary_dns = serializers.CharField(allow_null=True)
    secondary_dns = serializers.CharField(allow_null=True)
    notes = serializers.CharField()


class NetworkRecordResultSerializer(CollectionResultSerializer):
    results = NetworkRecordSerializer(many=True)


class NetworkRecordListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: NetworkRecordResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return _page(
            network_records_for_scope(workspace.data_scope),
            request,
            workspace,
            NetworkRecordResultSerializer,
            transform=network_projection,
        )

    @extend_schema(request=NetworkRecordWriteSerializer, responses={201: NetworkRecordSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkRecordWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_network_record(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(NetworkRecordSerializer(network_projection(record)).data, status=201)


class NetworkRecordDetailView(APIView):
    def _record(self, workspace, entity_id: UUID) -> NetworkSubnet:  # type: ignore[no-untyped-def]
        try:
            return network_records_for_scope(workspace.data_scope).get(entity_id=entity_id)
        except NetworkSubnet.DoesNotExist as exc:
            raise PermissionDenied("The selected network is unavailable.") from exc

    @extend_schema(request=NetworkRecordWriteSerializer, responses={200: NetworkRecordSerializer})
    def patch(self, request, network_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetworkRecordWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_network_record(
                record=self._record(workspace, network_entity_id),
                actor_id=request.user.pk,
                values=serializer.validated_data,
            )
        except (NetworkAddressingError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(NetworkRecordSerializer(network_projection(record)).data)
