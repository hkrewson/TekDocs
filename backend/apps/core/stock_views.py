from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .models import Organization, StockItem, StockMovement, StockMovementType, Tenant
from .money import render_amount
from .stock import StockError, archive_stock_item, change_stock, create_stock_item, update_stock_item
from .workspaces import ResolvedWorkspace, resolve_msp_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class StockItemWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")
    vendor_id = serializers.UUIDField(allow_null=True, required=False, default=None)
    vendor_part_number = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    unit = serializers.CharField(max_length=32)
    initial_quantity = serializers.DecimalField(max_digits=15, decimal_places=3, required=False, default=0)
    reorder_level = serializers.DecimalField(
        max_digits=15, decimal_places=3, allow_null=True, required=False, default=None
    )
    currency = serializers.CharField(max_length=3)
    cost_per_unit = serializers.DecimalField(max_digits=18, decimal_places=6)
    client_price_per_unit = serializers.DecimalField(max_digits=18, decimal_places=4)
    purchase_quantity = serializers.DecimalField(
        max_digits=15, decimal_places=3, allow_null=True, required=False, default=None
    )
    purchase_price = serializers.DecimalField(
        max_digits=18, decimal_places=4, allow_null=True, required=False, default=None
    )
    order_total = serializers.DecimalField(
        max_digits=18, decimal_places=4, allow_null=True, required=False, default=None
    )
    order_number = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    order_url = serializers.URLField(max_length=1000, allow_blank=True, required=False, default="")
    ordered_on = serializers.DateField(allow_null=True, required=False, default=None)
    tracking_number = serializers.CharField(max_length=160, allow_blank=True, required=False, default="")
    tracking_url = serializers.URLField(max_length=1000, allow_blank=True, required=False, default="")


class StockItemUpdateSerializer(StockItemWriteSerializer):
    initial_quantity = None

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class StockMovementWriteSerializer(StrictSerializer):
    movement_type = serializers.ChoiceField(choices=StockMovementType.values)
    quantity_change = serializers.DecimalField(max_digits=15, decimal_places=3)
    client_id = serializers.UUIDField(allow_null=True, required=False, default=None)
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    occurred_at = serializers.DateTimeField(required=False)


class StockMovementSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    client_id = serializers.UUIDField(source="client.entity_id", allow_null=True)
    client_name = serializers.CharField(source="client.entity.display_name", allow_null=True)

    class Meta:
        model = StockMovement
        fields = (
            "id", "movement_type", "quantity_change", "quantity_after", "client_id", "client_name", "note",
            "occurred_at", "recorded_at", "actor",
        )

    @extend_schema_field(serializers.CharField())
    def get_actor(self, item):  # type: ignore[no-untyped-def]
        return item.actor.get_full_name() or item.actor.get_username()


class StockItemSerializer(serializers.ModelSerializer):
    vendor_id = serializers.UUIDField(source="vendor.entity_id", allow_null=True)
    vendor_name = serializers.CharField(source="vendor.entity.display_name", allow_null=True)
    cost_per_unit = serializers.SerializerMethodField()
    client_price_per_unit = serializers.SerializerMethodField()
    purchase_price = serializers.SerializerMethodField()
    order_total = serializers.SerializerMethodField()
    movements = StockMovementSerializer(many=True)

    class Meta:
        model = StockItem
        fields = (
            "id", "name", "description", "vendor_id", "vendor_name", "vendor_part_number", "unit",
            "quantity_on_hand", "reorder_level", "currency", "cost_per_unit", "client_price_per_unit",
            "purchase_quantity", "purchase_price", "order_total", "order_number", "order_url", "ordered_on",
            "tracking_number", "tracking_url", "movements", "created_at", "updated_at",
        )

    @extend_schema_field(serializers.CharField())
    def get_cost_per_unit(self, item):  # type: ignore[no-untyped-def]
        return format(item.cost_per_unit, "f")

    @extend_schema_field(serializers.CharField())
    def get_client_price_per_unit(self, item):  # type: ignore[no-untyped-def]
        return render_amount(item.client_price_per_unit, item.currency)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_purchase_price(self, item):  # type: ignore[no-untyped-def]
        return None if item.purchase_price is None else render_amount(item.purchase_price, item.currency)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_order_total(self, item):  # type: ignore[no-untyped-def]
        return None if item.order_total is None else render_amount(item.order_total, item.currency)


class StockResultSerializer(serializers.Serializer):
    results = StockItemSerializer(many=True)
    can_manage = serializers.BooleanField()
    vendors = serializers.ListField(child=serializers.DictField())
    clients = serializers.ListField(child=serializers.DictField())


def _query(workspace: ResolvedWorkspace) -> QuerySet[StockItem]:
    return (
        StockItem.scoped.for_tenant(workspace.member.tenant)
        .filter(archived_at__isnull=True)
        .select_related("vendor__entity")
        .prefetch_related("movements__actor", "movements__client__entity")
    )


def _organization_choice(tenant: Tenant, entity_id: UUID | None, kind: str) -> Organization | None:
    if entity_id is None:
        return None
    return get_object_or_404(
        Organization.objects.filter(tenant=tenant, entity_id=entity_id, classifications__kind=kind).distinct()
    )


def _choices(tenant: Tenant, kind: str) -> list[dict[str, str]]:
    return [
        {"id": str(record.entity_id), "name": record.entity.display_name}
        for record in Organization.objects.filter(
            tenant=tenant, entity__archived_at__isnull=True, classifications__kind=kind
        ).select_related("entity").order_by("entity__display_name")[:500]
    ]


class StockItemListCreateView(APIView):
    @extend_schema(responses={200: StockResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, PermissionKey.INVOICES_VIEW)
        return Response(
            StockResultSerializer(
                {
                    "results": _query(workspace),
                    "can_manage": context_has_permission(workspace.member, PermissionKey.INVOICES_EDIT),
                    "vendors": _choices(workspace.member.tenant, "vendor"),
                    "clients": _choices(workspace.member.tenant, "client"),
                }
            ).data
        )

    @extend_schema(request=StockItemWriteSerializer, responses={201: StockItemSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, PermissionKey.INVOICES_EDIT)
        serializer = StockItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        initial_quantity = values.pop("initial_quantity", Decimal("0"))
        values["vendor"] = _organization_choice(workspace.member.tenant, values.pop("vendor_id", None), "vendor")
        try:
            record = create_stock_item(
                tenant=workspace.member.tenant,
                actor_id=request.user.pk,
                values=values,
                initial_quantity=initial_quantity,
            )
        except (StockError, DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(StockItemSerializer(record).data, status=201)


class StockItemDetailView(APIView):
    def _record(self, workspace, item_id: UUID) -> StockItem:  # type: ignore[no-untyped-def]
        return get_object_or_404(_query(workspace), id=item_id)

    @extend_schema(request=StockItemUpdateSerializer, responses={200: StockItemSerializer})
    def patch(self, request, item_id):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, PermissionKey.INVOICES_EDIT)
        serializer = StockItemUpdateSerializer(data=request.data, partial=True)  # type: ignore[no-untyped-call]
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "vendor_id" in values:
            values["vendor"] = _organization_choice(workspace.member.tenant, values.pop("vendor_id"), "vendor")
        try:
            record = update_stock_item(
                item=self._record(workspace, item_id), actor_id=request.user.pk, values=values
            )
        except (StockError, DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(StockItemSerializer(_query(workspace).get(pk=record.pk)).data)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, item_id):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, PermissionKey.INVOICES_EDIT)
        archive_stock_item(item=self._record(workspace, item_id), actor_id=request.user.pk)
        return Response(status=204)


class StockMovementCreateView(APIView):
    @extend_schema(request=StockMovementWriteSerializer, responses={201: StockItemSerializer})
    def post(self, request, item_id):  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, PermissionKey.INVOICES_EDIT)
        serializer = StockMovementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        client = _organization_choice(workspace.member.tenant, values.pop("client_id", None), "client")
        try:
            change_stock(
                item=get_object_or_404(_query(workspace), id=item_id),
                actor_id=request.user.pk,
                client=client,
                **values,
            )
        except (StockError, DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(StockItemSerializer(_query(workspace).get(id=item_id)).data, status=201)
