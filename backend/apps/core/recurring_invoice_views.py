"""Operator-initiated enrollment and reviewed recurring drafts; never automatic issue."""

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .collection_pagination import (
    BoundedCollectionQuerySerializer,
    OffsetPageSerializer,
    StrictQuerySerializer,
    paginate,
)
from .invoice_recurrence import RecurrenceError
from .invoice_views import StrictSerializer, _workspace
from .invoicing import InvoiceError
from .models import ContractCost, RecurringInvoiceSchedule
from .money import MoneyError
from .recurring_invoice_preview import (
    apply_recurring_preview,
    discover_recurring_periods,
    preview_recurring_drafts,
    review_recurring_source,
)
from .recurring_invoices import enroll_recurring_schedule
from .workspaces import ResolvedWorkspace

Result = TypeVar("Result")


class RecurringConflict(APIException):
    status_code = 409
    default_code = "recurring_conflict"


class RecurringErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class RecurringWriteSerializer(StrictSerializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        return super().to_internal_value(data)  # type: ignore[no-untyped-call]


class RecurringEnrollmentSerializer(RecurringWriteSerializer):
    cost_id = serializers.UUIDField()
    expected_source_digest = serializers.RegexField(r"^[0-9a-f]{64}$")
    anchor = serializers.DateField()
    ends_on = serializers.DateField(allow_null=True)
    description = serializers.CharField(max_length=1000)
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    currency = serializers.CharField(min_length=3, max_length=3)
    due_days = serializers.IntegerField(min_value=0, max_value=3650)
    tax_rate_id = serializers.UUIDField(allow_null=True, required=False)


class RecurringTermsSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    currency = serializers.CharField()
    due_days = serializers.IntegerField()
    tax_rate_id = serializers.UUIDField(allow_null=True)
    source_digest = serializers.CharField()


class RecurringScheduleSerializer(serializers.Serializer):
    source_label = serializers.CharField(source="contract_cost.label")
    contract_name = serializers.CharField(source="contract_cost.contract.entity.display_name")
    id = serializers.UUIDField()
    contract_cost_id = serializers.UUIDField()
    anchor = serializers.DateField()
    ends_on = serializers.DateField(allow_null=True)
    interval = serializers.CharField()
    enabled = serializers.BooleanField()
    terms = RecurringTermsSerializer(many=True)


class RecurringSchedulePageSerializer(OffsetPageSerializer):
    results = RecurringScheduleSerializer(many=True)
    business_date = serializers.DateField()


class RecurringDueQuerySerializer(StrictQuerySerializer):
    due_from = serializers.DateField()
    as_of = serializers.DateField()

    def validate_as_of(self, value):  # type: ignore[no-untyped-def]
        if value > timezone.localdate():
            raise serializers.ValidationError("The planning date cannot be later than today.")
        return value


class RecurringDuePeriodSerializer(serializers.Serializer):
    starts_on = serializers.DateField()
    ends_before = serializers.DateField()
    invoice_entity_id = serializers.UUIDField(allow_null=True)
    can_generate = serializers.BooleanField()
    blocked_reason = serializers.ChoiceField(
        choices=["", "disabled", "source_changed", "source_unavailable", "partial", "tax"]
    )


class RecurringDueSerializer(serializers.Serializer):
    periods = RecurringDuePeriodSerializer(many=True)
    due_from = serializers.DateField()
    as_of = serializers.DateField()


class RecurringSourceSnapshotSerializer(serializers.Serializer):
    cost_id = serializers.UUIDField()
    contract_id = serializers.UUIDField()
    label = serializers.CharField()
    amount = serializers.CharField()
    quantity = serializers.CharField()
    currency = serializers.CharField()
    interval = serializers.ChoiceField(choices=["monthly", "quarterly", "annual"])
    cost_starts_on = serializers.DateField(allow_null=True)
    cost_ends_on = serializers.DateField(allow_null=True)
    contract_starts_on = serializers.DateField(allow_null=True)
    contract_ends_on = serializers.DateField(allow_null=True)


class RecurringSourceSerializer(serializers.Serializer):
    source = RecurringSourceSnapshotSerializer()
    source_digest = serializers.CharField()
    earliest_anchor = serializers.DateField(allow_null=True)
    latest_end = serializers.DateField(allow_null=True)
    business_date = serializers.DateField()


class RecurringSourceChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    contract_name = serializers.CharField(source="contract.entity.display_name")
    currency = serializers.CharField()
    billing_interval = serializers.CharField()


class RecurringSourcePageSerializer(OffsetPageSerializer):
    results = RecurringSourceChoiceSerializer(many=True)


class RecurringSourceQuerySerializer(BoundedCollectionQuerySerializer):
    q = serializers.CharField(max_length=200, required=False, default="", allow_blank=True)


class RecurringPreviewWriteSerializer(RecurringWriteSerializer):
    starts_on = serializers.ListField(child=serializers.DateField(), min_length=1, max_length=120)
    as_of = serializers.DateField()

    def validate_as_of(self, value):  # type: ignore[no-untyped-def]
        if value > timezone.localdate():
            raise serializers.ValidationError(
                "The planning date cannot be later than today in the installation timezone."
            )
        return value


class RecurringApplySerializer(RecurringWriteSerializer):
    preview_token = serializers.CharField(max_length=65536)


class RecurringPeriodPreviewSerializer(serializers.Serializer):
    starts_on = serializers.DateField()
    ends_before = serializers.DateField()
    due_date = serializers.DateField()
    net = serializers.CharField()
    tax = serializers.CharField()
    total = serializers.CharField()


class RecurringExistingInvoiceSerializer(serializers.Serializer):
    starts_on = serializers.DateField()
    invoice_entity_id = serializers.UUIDField()


class RecurringPreviewSerializer(serializers.Serializer):
    preview_id = serializers.CharField()
    preview_token = serializers.CharField()
    expires_in_seconds = serializers.IntegerField()
    schedule_id = serializers.UUIDField()
    terms_id = serializers.UUIDField()
    source_digest = serializers.CharField()
    as_of = serializers.DateField()
    currency = serializers.CharField()
    description = serializers.CharField()
    quantity = serializers.CharField()
    unit_amount = serializers.CharField()
    periods = RecurringPeriodPreviewSerializer(many=True)
    existing_invoices = RecurringExistingInvoiceSerializer(many=True)


class RecurringClaimSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    starts_on = serializers.DateField()
    ends_before = serializers.DateField()
    invoice_entity_id = serializers.UUIDField(source="invoice.entity_id")
    line_id = serializers.UUIDField()


def _authorized_workspace(request: Any, organization_entity_id: UUID) -> ResolvedWorkspace:
    workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
    require_permission(request.user, PermissionKey.INVOICES_VIEW, organization=workspace.organization)
    require_permission(request.user, PermissionKey.COSTS_VIEW, organization=workspace.organization)
    return workspace


def _schedule(workspace: ResolvedWorkspace, schedule_id: UUID) -> RecurringInvoiceSchedule:
    return get_object_or_404(RecurringInvoiceSchedule.scoped.for_scope(workspace.data_scope), pk=schedule_id)


def _call(operation: Callable[..., Result], **kwargs: Any) -> Result:
    try:
        return operation(**kwargs)
    except (RecurrenceError, InvoiceError) as exc:
        raise RecurringConflict(str(exc)) from exc
    except MoneyError as exc:
        raise serializers.ValidationError({"detail": str(exc)}) from exc
    except IntegrityError as exc:
        # Never expose SQL or source identifiers from a failed persistence guard.
        raise RecurringConflict("The recurring records changed; review the schedule again.") from exc


class RecurringSourceView(APIView):
    @extend_schema(
        responses={
            200: RecurringSourceSerializer,
            403: RecurringErrorSerializer,
            404: RecurringErrorSerializer,
            409: RecurringErrorSerializer,
        }
    )
    def get(self, request, organization_entity_id, cost_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        get_object_or_404(ContractCost.scoped.for_scope(workspace.data_scope), pk=cost_id)
        result = _call(review_recurring_source, user=request.user, organization=workspace.organization, cost_id=cost_id)
        return Response(RecurringSourceSerializer(result).data)


class RecurringEnrollmentView(APIView):
    @extend_schema(
        operation_id="organization_recurring_invoices_list",
        parameters=[BoundedCollectionQuerySerializer],
        responses={200: RecurringSchedulePageSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        records = (
            RecurringInvoiceSchedule.scoped.for_scope(workspace.data_scope)
            .select_related("contract_cost__contract__entity")
            .prefetch_related("terms")
            .order_by("created_at", "pk")
        )
        page = paginate(records, **query.validated_data)
        return Response(
            RecurringSchedulePageSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    "business_date": timezone.localdate(),
                }
            ).data
        )

    @extend_schema(
        request=RecurringEnrollmentSerializer,
        responses={
            201: RecurringScheduleSerializer,
            400: RecurringErrorSerializer,
            403: RecurringErrorSerializer,
            404: RecurringErrorSerializer,
            409: RecurringErrorSerializer,
        },
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        data = RecurringEnrollmentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        get_object_or_404(ContractCost.scoped.for_scope(workspace.data_scope), pk=data.validated_data["cost_id"])
        schedule = _call(
            enroll_recurring_schedule, user=request.user, organization=workspace.organization, **data.validated_data
        )
        return Response(RecurringScheduleSerializer(schedule).data, status=201)


class RecurringScheduleView(APIView):
    @extend_schema(
        responses={200: RecurringScheduleSerializer, 403: RecurringErrorSerializer, 404: RecurringErrorSerializer}
    )
    def get(self, request, organization_entity_id, schedule_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        return Response(RecurringScheduleSerializer(_schedule(workspace, schedule_id)).data)


class RecurringPreviewView(APIView):
    @extend_schema(
        request=RecurringPreviewWriteSerializer,
        responses={
            200: RecurringPreviewSerializer,
            400: RecurringErrorSerializer,
            403: RecurringErrorSerializer,
            404: RecurringErrorSerializer,
            409: RecurringErrorSerializer,
        },
    )
    def post(self, request, organization_entity_id, schedule_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        _schedule(workspace, schedule_id)
        data = RecurringPreviewWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = _call(
            preview_recurring_drafts,
            user=request.user,
            organization=workspace.organization,
            schedule_id=schedule_id,
            **data.validated_data,
        )
        return Response(RecurringPreviewSerializer(result).data)


class RecurringApplyView(APIView):
    @extend_schema(
        request=RecurringApplySerializer,
        responses={
            200: RecurringClaimSerializer(many=True),
            400: RecurringErrorSerializer,
            403: RecurringErrorSerializer,
            404: RecurringErrorSerializer,
            409: RecurringErrorSerializer,
        },
    )
    def post(self, request, organization_entity_id, schedule_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        _schedule(workspace, schedule_id)
        data = RecurringApplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = _call(
            apply_recurring_preview,
            user=request.user,
            organization=workspace.organization,
            schedule_id=schedule_id,
            **data.validated_data,
        )
        return Response(RecurringClaimSerializer(result, many=True).data)


class RecurringDueView(APIView):
    @extend_schema(
        parameters=[RecurringDueQuerySerializer],
        responses={
            200: RecurringDueSerializer,
            400: RecurringErrorSerializer,
            403: RecurringErrorSerializer,
            404: RecurringErrorSerializer,
            409: RecurringErrorSerializer,
        },
    )
    def get(self, request, organization_entity_id, schedule_id):  # type: ignore[no-untyped-def]
        workspace = _authorized_workspace(request, organization_entity_id)
        _schedule(workspace, schedule_id)
        query = RecurringDueQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = _call(
            discover_recurring_periods,
            user=request.user,
            organization=workspace.organization,
            schedule_id=schedule_id,
            **query.validated_data,
        )
        return Response(RecurringDueSerializer(result).data)


class RecurringSourceListView(APIView):
    @extend_schema(
        operation_id="organization_recurring_sources_list",
        parameters=[RecurringSourceQuerySerializer],
        responses={200: RecurringSourcePageSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        from django.db.models import Q

        workspace = _authorized_workspace(request, organization_entity_id)
        query = RecurringSourceQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records = (
            ContractCost.scoped.for_scope(workspace.data_scope)
            .filter(
                billing_interval__in=["monthly", "quarterly", "annual"],
                archived_at__isnull=True,
                contract__archived_at__isnull=True,
                contract__entity__archived_at__isnull=True,
                contract__status="active",
                recurring_schedule__isnull=True,
            )
            .select_related("contract__entity")
            .order_by("label", "pk")
        )
        if values["q"]:
            records = records.filter(
                Q(label__icontains=values["q"]) | Q(contract__entity__display_name__icontains=values["q"])
            )
        page = paginate(records, page=values["page"], page_size=values["page_size"])
        return Response(
            RecurringSourcePageSerializer(
                {
                    "results": page.records,
                    "count": page.count,
                    "page": page.page,
                    "page_size": page.page_size,
                    "has_more": page.has_more,
                }
            ).data
        )
