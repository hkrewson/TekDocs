from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .inventory import InventoryError, require_operational_owner
from .models import CatalogProductKind, ClientAsset, NetBoxObjectType, NetBoxReference
from .netbox_reconciliation import (
    NETBOX_ENTITY_TYPES,
    NetBoxReferenceError,
    archive_reference,
    eligible_entities,
    reconciliation_preview,
    references_for_scope,
    set_reference,
)
from .network_inventory_views import StrictSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class NetBoxReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    entity_id = serializers.UUIDField(source="entity.id")
    entity_name = serializers.CharField(source="entity.display_name")
    entity_type = serializers.CharField(source="entity.entity_type")
    object_type = serializers.CharField()
    object_id = serializers.IntegerField()
    observed_fingerprint = serializers.CharField()
    last_observed_at = serializers.DateTimeField(allow_null=True)


class NetBoxReferenceWriteSerializer(StrictSerializer):
    entity_id = serializers.UUIDField()
    object_type = serializers.ChoiceField(choices=NetBoxObjectType.choices)
    object_id = serializers.IntegerField(min_value=1, max_value=9_223_372_036_854_775_807)
    fingerprint = serializers.RegexField(regex=r"^[0-9a-f]{64}$", required=False, allow_blank=True, default="")


class NetBoxChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    entity_type = serializers.CharField()
    object_type = serializers.CharField()
    linked = serializers.BooleanField()


class NetBoxChoiceResultSerializer(serializers.Serializer):
    results = NetBoxChoiceSerializer(many=True)
    can_manage = serializers.BooleanField()


class NetBoxObservationSerializer(StrictSerializer):
    object_type = serializers.ChoiceField(choices=NetBoxObjectType.choices)
    object_id = serializers.IntegerField(min_value=1, max_value=9_223_372_036_854_775_807)
    fingerprint = serializers.RegexField(regex=r"^[0-9a-f]{64}$")


class NetBoxPreviewWriteSerializer(StrictSerializer):
    observations = NetBoxObservationSerializer(many=True, allow_empty=True, max_length=500)


class NetBoxPreviewItemSerializer(serializers.Serializer):
    object_type = serializers.CharField()
    object_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=("current", "changed", "unmatched", "missing_remote"))
    entity_id = serializers.UUIDField(allow_null=True)
    entity_name = serializers.CharField()
    entity_type = serializers.CharField()


class NetBoxPreviewResultSerializer(serializers.Serializer):
    results = NetBoxPreviewItemSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField(min_value=0))


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


def _error(exc: Exception) -> serializers.ValidationError:
    if isinstance(exc, DjangoValidationError):
        detail = "; ".join(exc.messages)
    elif isinstance(exc, IntegrityError):
        detail = "That NetBox identity conflicts with another record in this Workspace."
    else:
        detail = str(exc)
    return serializers.ValidationError({"detail": detail})


def _reference(workspace: ResolvedWorkspace, reference_id: UUID) -> NetBoxReference:
    try:
        return references_for_scope(workspace.data_scope).get(id=reference_id)
    except NetBoxReference.DoesNotExist as exc:
        raise PermissionDenied("The selected NetBox reference is unavailable.") from exc


class NetBoxReferenceCollectionView(APIView):
    @extend_schema(responses={200: NetBoxReferenceSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        return Response(NetBoxReferenceSerializer(references_for_scope(workspace.data_scope), many=True).data)

    @extend_schema(request=NetBoxReferenceWriteSerializer, responses={201: NetBoxReferenceSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = NetBoxReferenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reference = set_reference(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetBoxReferenceError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(NetBoxReferenceSerializer(reference).data, status=status.HTTP_201_CREATED)


class NetBoxReferenceDetailView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request, reference_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        archive_reference(reference=_reference(workspace, reference_id), actor_id=request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NetBoxReferenceChoiceView(APIView):
    @extend_schema(responses={200: NetBoxChoiceResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        linked = set(references_for_scope(workspace.data_scope).values_list("entity_id", flat=True))
        hardware_assets = set(
            ClientAsset.scoped.for_scope(workspace.data_scope)
            .filter(archived_at__isnull=True, product__kind=CatalogProductKind.HARDWARE)
            .values_list("entity_id", flat=True)
        )
        inverse = {entity_type: object_type for object_type, entity_type in NETBOX_ENTITY_TYPES.items()}
        choices = [
            {
                "id": entity.id,
                "name": entity.display_name,
                "entity_type": entity.entity_type,
                "object_type": inverse[entity.entity_type],
                "linked": entity.id in linked,
            }
            for entity in eligible_entities(workspace.data_scope)[:500]
            if entity.entity_type != "client_asset" or entity.id in hardware_assets
        ]
        return Response(
            NetBoxChoiceResultSerializer(
                {
                    "results": choices,
                    "can_manage": context_has_permission(
                        workspace.member,
                        PermissionKey.NETWORKS_EDIT,
                        organization=workspace.organization,
                    ),
                }
            ).data
        )


class NetBoxReconciliationPreviewView(APIView):
    @extend_schema(request=NetBoxPreviewWriteSerializer, responses={200: NetBoxPreviewResultSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        serializer = NetBoxPreviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = reconciliation_preview(workspace.data_scope, serializer.validated_data["observations"])
        except NetBoxReferenceError as exc:
            raise _error(exc) from exc
        return Response(NetBoxPreviewResultSerializer({"results": preview.results, "counts": preview.counts}).data)
