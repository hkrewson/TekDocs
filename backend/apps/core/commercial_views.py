from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import (
    PermissionKey,
    SensitiveField,
    context_has_permission,
    project_authorized_fields,
    require_permission,
)

from .commercial import (
    CommercialError,
    archive_contract,
    archive_cost,
    contracts_for_scope,
    create_contract,
    create_cost,
    provider_choices,
    update_contract,
    update_cost,
)
from .inventory import InventoryError, require_operational_owner
from .models import (
    CommercialContract,
    CommercialContractKind,
    CommercialContractStatus,
    CostBillingInterval,
)
from .software_inventory_views import StrictSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class ContractWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, required=False)
    provider_id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=CommercialContractKind.values, required=False)
    status = serializers.ChoiceField(choices=CommercialContractStatus.values, required=False)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    reference = serializers.CharField(max_length=240, allow_blank=True, required=False)
    starts_on = serializers.DateField(allow_null=True, required=False)
    ends_on = serializers.DateField(allow_null=True, required=False)
    renews_on = serializers.DateField(allow_null=True, required=False)
    auto_renew = serializers.BooleanField(required=False)
    renewal_notice_days = serializers.IntegerField(min_value=0, max_value=3650, required=False)


class CostWriteSerializer(StrictSerializer):
    label = serializers.CharField(max_length=160, required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False)
    currency = serializers.RegexField(regex=r"^[A-Za-z]{3}$", required=False)
    billing_interval = serializers.ChoiceField(choices=CostBillingInterval.values, required=False)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False)
    starts_on = serializers.DateField(allow_null=True, required=False)
    ends_on = serializers.DateField(allow_null=True, required=False)
    reference = serializers.CharField(max_length=240, allow_blank=True, required=False)


class CostSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    billing_interval = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    starts_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    reference = serializers.CharField()


class ContractSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    provider_id = serializers.UUIDField(source="provider.entity_id")
    provider_name = serializers.CharField(source="provider.entity.display_name")
    kind = serializers.CharField()
    status = serializers.CharField()
    description = serializers.CharField()
    reference = serializers.CharField()
    starts_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    renews_on = serializers.DateField(allow_null=True)
    auto_renew = serializers.BooleanField()
    renewal_notice_days = serializers.IntegerField()
    costs = CostSerializer(many=True, required=False)

    def get_fields(self):  # type: ignore[no-untyped-def]
        fields = super().get_fields()
        member = self.context.get("member")
        organization = self.context.get("organization")
        if member is not None and not context_has_permission(
            member, PermissionKey.COSTS_VIEW, organization=organization
        ):
            fields.pop("costs", None)
        return fields

    def to_representation(self, instance):  # type: ignore[no-untyped-def]
        values = super().to_representation(instance)
        return project_authorized_fields(
            self.context["member"],
            values,
            {"costs": SensitiveField.COST},
            organization=self.context["organization"],
        )


class ContractResultSerializer(serializers.Serializer):
    results = ContractSerializer(many=True)
    count = serializers.IntegerField()
    can_manage = serializers.BooleanField()
    can_view_costs = serializers.BooleanField()


class ProviderChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ProviderChoiceResultSerializer(serializers.Serializer):
    results = ProviderChoiceSerializer(many=True)


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


def _record(workspace: ResolvedWorkspace, entity_id: UUID) -> CommercialContract:
    include_costs = context_has_permission(
        workspace.member, PermissionKey.COSTS_VIEW, organization=workspace.organization
    )
    return get_object_or_404(
        contracts_for_scope(workspace.data_scope, include_costs=include_costs), entity_id=entity_id
    )


def _serialized(record, workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    return ContractSerializer(record, context={"member": workspace.member, "organization": workspace.organization}).data


def _require_cost_access(workspace: ResolvedWorkspace) -> None:
    if not context_has_permission(workspace.member, PermissionKey.COSTS_VIEW, organization=workspace.organization):
        raise PermissionDenied("Cost access is required for this action.")


class CommercialContractListCreateView(APIView):
    @extend_schema(responses={200: ContractResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        can_manage = context_has_permission(
            workspace.member, PermissionKey.ASSETS_EDIT, organization=workspace.organization
        )
        can_view_costs = context_has_permission(
            workspace.member, PermissionKey.COSTS_VIEW, organization=workspace.organization
        )
        records = contracts_for_scope(
            workspace.data_scope,
            query=request.query_params.get("q", ""),
            include_costs=can_view_costs,
        )
        return Response(
            {
                "results": [_serialized(record, workspace) for record in records],
                "count": records.count(),
                "can_manage": can_manage,
                "can_view_costs": can_view_costs,
            }
        )

    @extend_schema(
        request=ContractWriteSerializer,
        responses={201: ContractSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ContractWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if not {"name", "provider_id", "kind"}.issubset(values):
            raise serializers.ValidationError({"detail": "Name, provider, and contract kind are required."})
        values.setdefault("status", CommercialContractStatus.DRAFT)
        values.setdefault("description", "")
        values.setdefault("reference", "")
        values.setdefault("auto_renew", False)
        values.setdefault("renewal_notice_days", 0)
        try:
            record = create_contract(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                values=values,
            )
        except CommercialError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialized(_record(workspace, record.entity_id), workspace), status=201)


class CommercialContractDetailView(APIView):
    @extend_schema(responses={200: ContractSerializer})
    def get(self, request, organization_entity_id, contract_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(_serialized(_record(workspace, contract_entity_id), workspace))

    @extend_schema(request=ContractWriteSerializer, responses={200: ContractSerializer})
    def patch(self, request, organization_entity_id, contract_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ContractWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_contract(
                record=_record(workspace, contract_entity_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except CommercialError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialized(_record(workspace, record.entity_id), workspace))

    @extend_schema(responses={204: None})
    def delete(self, request, organization_entity_id, contract_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        archive_contract(record=_record(workspace, contract_entity_id), actor_id=request.user.pk)
        return Response(status=204)


class CommercialProviderChoiceView(APIView):
    @extend_schema(responses={200: ProviderChoiceResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        records = provider_choices(workspace.member.tenant, query=request.query_params.get("q", ""))[:100]
        return Response({"results": [{"id": item.entity_id, "name": item.entity.display_name} for item in records]})


class ContractCostListCreateView(APIView):
    @extend_schema(request=CostWriteSerializer, responses={201: ContractSerializer})
    def post(self, request, organization_entity_id, contract_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        _require_cost_access(workspace)
        serializer = CostWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if not {"label", "amount", "currency", "billing_interval"}.issubset(values):
            raise serializers.ValidationError({"detail": "Label, amount, currency, and billing interval are required."})
        values.setdefault("quantity", 1)
        values.setdefault("reference", "")
        try:
            record = create_cost(
                contract=_record(workspace, contract_entity_id), actor_id=request.user.pk, values=values
            )
        except CommercialError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialized(_record(workspace, record.entity_id), workspace), status=201)


class ContractCostDetailView(APIView):
    @extend_schema(request=CostWriteSerializer, responses={200: ContractSerializer})
    def patch(self, request, organization_entity_id, contract_entity_id, cost_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        _require_cost_access(workspace)
        serializer = CostWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            record = update_cost(
                contract=_record(workspace, contract_entity_id),
                cost_id=cost_id,
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except CommercialError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialized(_record(workspace, record.entity_id), workspace))

    @extend_schema(responses={200: ContractSerializer})
    def delete(self, request, organization_entity_id, contract_entity_id, cost_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        _require_cost_access(workspace)
        try:
            record = archive_cost(
                contract=_record(workspace, contract_entity_id), cost_id=cost_id, actor_id=request.user.pk
            )
        except CommercialError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(_serialized(_record(workspace, record.entity_id), workspace))
