from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import InventoryError, require_operational_owner
from .models import (
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkCircuitKind,
    NetworkCircuitStatus,
    NetworkHandoffMedia,
    NetworkHandoffSide,
)
from .network_circuits import (
    NetworkCircuitError,
    circuit_choices,
    circuits_for_scope,
    create_circuit,
    create_handoff,
    handoffs_for_scope,
    lifecycle_events,
    update_circuit,
    update_handoff,
)
from .network_inventory_views import StrictSerializer
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class CircuitWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    provider_id = serializers.UUIDField(source="provider_entity_id")
    contract_id = serializers.UUIDField(source="contract_entity_id", allow_null=True, required=False, default=None)
    service_identifier = serializers.CharField(max_length=240, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=NetworkCircuitKind.values, default=NetworkCircuitKind.INTERNET)
    status = serializers.ChoiceField(choices=NetworkCircuitStatus.values, default=NetworkCircuitStatus.ACTIVE)
    bandwidth_down_mbps = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"), allow_null=True, required=False, default=None
    )
    bandwidth_up_mbps = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"), allow_null=True, required=False, default=None
    )
    installed_on = serializers.DateField(allow_null=True, required=False, default=None)
    service_starts_on = serializers.DateField(allow_null=True, required=False, default=None)
    review_on = serializers.DateField(allow_null=True, required=False, default=None)
    planned_disconnect_on = serializers.DateField(allow_null=True, required=False, default=None)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")


class HandoffWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    side = serializers.ChoiceField(choices=NetworkHandoffSide.values)
    media = serializers.ChoiceField(choices=NetworkHandoffMedia.values)
    connector = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    provider_reference = serializers.CharField(max_length=240, allow_blank=True, required=False, default="")
    site_id = serializers.UUIDField(source="site_entity_id", allow_null=True, required=False, default=None)
    location_id = serializers.UUIDField(source="location_entity_id", allow_null=True, required=False, default=None)
    device_id = serializers.UUIDField(source="device_entity_id", allow_null=True, required=False, default=None)
    interface_id = serializers.UUIDField(source="interface_entity_id", allow_null=True, required=False, default=None)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")


class HandoffSerializer(serializers.Serializer):
    circuit_id = serializers.UUIDField(source="circuit.entity_id")
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    side = serializers.CharField()
    media = serializers.CharField()
    connector = serializers.CharField()
    provider_reference = serializers.CharField()
    site_id = serializers.UUIDField(source="site.entity_id", allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)
    location_id = serializers.UUIDField(source="location.entity_id", allow_null=True)
    location_name = serializers.CharField(source="location.entity.display_name", allow_null=True)
    device_id = serializers.UUIDField(source="device.entity_id", allow_null=True)
    device_name = serializers.CharField(source="device.entity.display_name", allow_null=True)
    interface_id = serializers.UUIDField(source="interface.entity_id", allow_null=True)
    interface_name = serializers.CharField(source="interface.entity.display_name", allow_null=True)
    description = serializers.CharField()


class CircuitContractSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    status = serializers.CharField()
    renews_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    auto_renew = serializers.BooleanField()
    renewal_notice_days = serializers.IntegerField()


class LifecycleEventSerializer(serializers.Serializer):
    kind = serializers.CharField()
    date = serializers.DateField()
    label = serializers.CharField()
    state = serializers.ChoiceField(choices=("overdue", "today", "upcoming"))


class CircuitSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    provider_id = serializers.UUIDField(source="provider.entity_id")
    provider_name = serializers.CharField(source="provider.entity.display_name")
    contract = CircuitContractSerializer(allow_null=True, required=False)
    service_identifier = serializers.CharField()
    kind = serializers.CharField()
    status = serializers.CharField()
    bandwidth_down_mbps = serializers.DecimalField(max_digits=12, decimal_places=3, allow_null=True)
    bandwidth_up_mbps = serializers.DecimalField(max_digits=12, decimal_places=3, allow_null=True)
    installed_on = serializers.DateField(allow_null=True, required=False)
    service_starts_on = serializers.DateField(allow_null=True, required=False)
    review_on = serializers.DateField(allow_null=True, required=False)
    planned_disconnect_on = serializers.DateField(allow_null=True, required=False)
    description = serializers.CharField(required=False)
    handoffs = HandoffSerializer(many=True, required=False)
    lifecycle_events = serializers.SerializerMethodField(required=False)

    def get_fields(self):  # type: ignore[no-untyped-def]
        fields = super().get_fields()
        if self.context.get("omit_handoffs"):
            fields.pop("handoffs", None)
        if self.context.get("summary"):
            for name in (
                "description",
                "contract",
                "lifecycle_events",
                "installed_on",
                "service_starts_on",
                "review_on",
                "planned_disconnect_on",
            ):
                fields.pop(name, None)
        if not self.context.get("can_view_contracts"):
            fields.pop("contract", None)
        return fields

    @extend_schema_field(LifecycleEventSerializer(many=True))
    def get_lifecycle_events(self, record: NetworkCircuit) -> list[dict[str, object]]:
        return lifecycle_events(
            record,
            include_contract=bool(self.context.get("can_view_contracts")),
            today=self.context.get("today", timezone.localdate()),
        )


class CircuitResultSerializer(serializers.Serializer):
    results = CircuitSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()
    can_view_contracts = serializers.BooleanField()


class ChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    provider_id = serializers.UUIDField(required=False)
    site_id = serializers.UUIDField(required=False, allow_null=True)
    device_id = serializers.UUIDField(required=False)


class CircuitChoicesSerializer(serializers.Serializer):
    providers = ChoiceSerializer(many=True)
    contracts = ChoiceSerializer(many=True)
    sites = ChoiceSerializer(many=True)
    locations = ChoiceSerializer(many=True)
    devices = ChoiceSerializer(many=True)
    interfaces = ChoiceSerializer(many=True)
    can_view_contracts = serializers.BooleanField()


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


def _can_view_contracts(workspace: ResolvedWorkspace) -> bool:
    return context_has_permission(workspace.member, PermissionKey.ASSETS_VIEW, organization=workspace.organization)


def _circuit(workspace: ResolvedWorkspace, entity_id: UUID, *, include_handoffs: bool = True) -> NetworkCircuit:
    records = circuits_for_scope(workspace.data_scope)
    if not include_handoffs:
        records = records.prefetch_related(None)
    try:
        return records.get(entity_id=entity_id)
    except NetworkCircuit.DoesNotExist as exc:
        raise PermissionDenied("The selected circuit is unavailable.") from exc


def _handoff(workspace: ResolvedWorkspace, circuit: NetworkCircuit, entity_id: UUID) -> NetworkCircuitHandoff:
    try:
        return handoffs_for_scope(workspace.data_scope).get(circuit=circuit, entity_id=entity_id)
    except NetworkCircuitHandoff.DoesNotExist as exc:
        raise PermissionDenied("The selected circuit handoff is unavailable.") from exc


def _data(record: NetworkCircuit, workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    return CircuitSerializer(record, context={"can_view_contracts": _can_view_contracts(workspace)}).data


def _error(exc: Exception) -> serializers.ValidationError:
    if isinstance(exc, DjangoValidationError):
        detail = "; ".join(exc.messages)
    elif isinstance(exc, IntegrityError):
        detail = "That circuit or handoff conflicts with an existing record in this Workspace."
    else:
        detail = str(exc)
    return serializers.ValidationError({"detail": detail})


def _require_contract_access(request: Any, workspace: ResolvedWorkspace, values: dict[str, object]) -> None:
    if values.get("contract_entity_id") is not None:
        require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)


CIRCUIT_ORDERING = {
    "name": "entity__display_name",
    "provider_name": "provider__entity__display_name",
    "service_identifier": "service_identifier",
    "kind": "kind",
    "status": "status",
    "bandwidth_down_mbps": "bandwidth_down_mbps",
}
HANDOFF_ORDERING = {
    "name": "entity__display_name",
    "side": "side",
    "media": "media",
    "site_name": "site__entity__display_name",
}


class CircuitQuerySerializer(BoundedCollectionQuerySerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=253, default="")
    status = serializers.ChoiceField(choices=NetworkCircuitStatus.values, required=False)
    kind = serializers.ChoiceField(choices=NetworkCircuitKind.values, required=False)
    ordering = serializers.ChoiceField(
        choices=[key for field in CIRCUIT_ORDERING for key in (field, f"-{field}")], required=False
    )
    summary = serializers.BooleanField(default=False)


class CircuitDetailQuerySerializer(serializers.Serializer):
    include_handoffs = serializers.BooleanField(default=True)


class HandoffQuerySerializer(BoundedCollectionQuerySerializer):
    paginated = serializers.BooleanField(default=False)
    q = serializers.CharField(required=False, allow_blank=True, max_length=253, default="")
    side = serializers.ChoiceField(choices=NetworkHandoffSide.values, required=False)
    ordering = serializers.ChoiceField(
        choices=[key for field in HANDOFF_ORDERING for key in (field, f"-{field}")], required=False
    )


class HandoffResultSerializer(serializers.Serializer):
    results = HandoffSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class CircuitListCreateView(APIView):
    @extend_schema(parameters=[CircuitQuerySerializer], responses={200: CircuitResultSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        query = CircuitQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records = circuits_for_scope(workspace.data_scope)
        if values["summary"]:
            records = records.prefetch_related(None)
        if values["q"]:
            records = records.filter(
                Q(entity__display_name__icontains=values["q"])
                | Q(service_identifier__icontains=values["q"])
                | Q(provider__entity__display_name__icontains=values["q"])
            )
        for field in ("status", "kind"):
            if field in values:
                records = records.filter(**{field: values[field]})
        if "ordering" in values:
            order = values["ordering"]
            records = records.order_by(
                ("-" if order.startswith("-") else "") + CIRCUIT_ORDERING[order.lstrip("-")], "entity_id"
            )
        page = paginate(records, page=values["page"], page_size=values["page_size"])
        can_view_contracts = _can_view_contracts(workspace)
        return Response(
            CircuitResultSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
                    ),
                    "can_view_contracts": can_view_contracts,
                },
                context={
                    "can_view_contracts": can_view_contracts,
                    "summary": values["summary"],
                    "omit_handoffs": values["summary"],
                },
            ).data
        )

    @extend_schema(request=CircuitWriteSerializer, responses={201: CircuitSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = CircuitWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        _require_contract_access(request, workspace, values)
        try:
            record = create_circuit(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                **values,
            )
        except (NetworkCircuitError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(_data(record, workspace), status=201)


class CircuitDetailView(APIView):
    @extend_schema(parameters=[CircuitDetailQuerySerializer], responses={200: CircuitSerializer})
    def get(self, request, circuit_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        query = CircuitDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        if query.validated_data["include_handoffs"]:
            return Response(_data(_circuit(workspace, circuit_entity_id), workspace))
        try:
            record = circuits_for_scope(workspace.data_scope).prefetch_related(None).get(entity_id=circuit_entity_id)
        except NetworkCircuit.DoesNotExist as exc:
            raise PermissionDenied("The selected circuit is unavailable.") from exc
        return Response(
            CircuitSerializer(
                record, context={"can_view_contracts": _can_view_contracts(workspace), "omit_handoffs": True}
            ).data
        )

    @extend_schema(request=CircuitWriteSerializer, responses={200: CircuitSerializer})
    def patch(self, request, circuit_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        record = _circuit(workspace, circuit_entity_id)
        serializer = CircuitWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        _require_contract_access(request, workspace, values)
        if "provider_entity_id" in values and record.contract_id:
            require_permission(request.user, PermissionKey.ASSETS_VIEW, organization=workspace.organization)
        try:
            updated = update_circuit(record=record, actor_id=request.user.pk, values=values)
        except (NetworkCircuitError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(_data(updated, workspace))


class CircuitChoiceView(APIView):
    @extend_schema(responses={200: CircuitChoicesSerializer})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        can_view_contracts = _can_view_contracts(workspace)
        choices = circuit_choices(workspace.data_scope, include_contracts=can_view_contracts)
        payload = {
            "providers": [
                {"id": item.entity_id, "name": item.entity.display_name} for item in choices["providers"][:100]
            ],
            "contracts": [
                {"id": item.entity_id, "name": item.entity.display_name, "provider_id": item.provider.entity_id}
                for item in choices["contracts"][:100]
            ],
            "sites": [{"id": item.entity_id, "name": item.entity.display_name} for item in choices["sites"][:100]],
            "locations": [
                {"id": item.entity_id, "name": item.entity.display_name, "site_id": item.site.entity_id}
                for item in choices["locations"][:200]
            ],
            "devices": [{"id": item.entity_id, "name": item.entity.display_name} for item in choices["devices"][:200]],
            "interfaces": [
                {"id": item.entity_id, "name": item.entity.display_name, "device_id": item.device.entity_id}
                for item in choices["interfaces"][:500]
            ],
            "can_view_contracts": can_view_contracts,
        }
        return Response(CircuitChoicesSerializer(payload).data)


class HandoffListCreateView(APIView):
    @extend_schema(
        parameters=[HandoffQuerySerializer],
        responses={
            200: PolymorphicProxySerializer(
                component_name="HandoffCollectionResponse",
                serializers=[HandoffResultSerializer, HandoffSerializer(many=True)],
                resource_type_field_name=None,
                many=False,
            )
        },
    )
    def get(self, request, circuit_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        circuit = _circuit(workspace, circuit_entity_id, include_handoffs=False)
        query = HandoffQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records = handoffs_for_scope(workspace.data_scope).filter(circuit=circuit)
        if not values["paginated"]:
            return Response(HandoffSerializer(records, many=True).data)
        if values["q"]:
            records = records.filter(
                Q(entity__display_name__icontains=values["q"])
                | Q(provider_reference__icontains=values["q"])
                | Q(connector__icontains=values["q"])
            )
        if "side" in values:
            records = records.filter(side=values["side"])
        order = values.get("ordering", "name")
        records = records.order_by(
            ("-" if order.startswith("-") else "") + HANDOFF_ORDERING[order.lstrip("-")], "entity_id"
        )
        page = paginate(records, page=values["page"], page_size=values["page_size"])
        return Response(
            HandoffResultSerializer(
                {
                    "results": page.records,
                    "count": page.count,
                    "page": page.page,
                    "page_size": page.page_size,
                    "has_more": page.has_more,
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.NETWORKS_EDIT, organization=workspace.organization
                    ),
                }
            ).data
        )

    @extend_schema(request=HandoffWriteSerializer, responses={201: HandoffSerializer})
    def post(self, request, circuit_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        serializer = HandoffWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            handoff = create_handoff(
                circuit=_circuit(workspace, circuit_entity_id, include_handoffs=False),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (NetworkCircuitError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(HandoffSerializer(handoff).data, status=201)


class HandoffDetailView(APIView):
    @extend_schema(responses={200: HandoffSerializer})
    def get(self, request, circuit_entity_id, handoff_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_VIEW)
        circuit = _circuit(workspace, circuit_entity_id, include_handoffs=False)
        return Response(HandoffSerializer(_handoff(workspace, circuit, handoff_entity_id)).data)

    @extend_schema(request=HandoffWriteSerializer, responses={200: HandoffSerializer})
    def patch(self, request, circuit_entity_id, handoff_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.NETWORKS_EDIT)
        circuit = _circuit(workspace, circuit_entity_id, include_handoffs=False)
        serializer = HandoffWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            handoff = update_handoff(
                handoff=_handoff(workspace, circuit, handoff_entity_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except (NetworkCircuitError, DjangoValidationError, IntegrityError) as exc:
            raise _error(exc) from exc
        return Response(HandoffSerializer(handoff).data)
