from __future__ import annotations

from uuid import UUID

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .invoicing import (
    InvoiceError,
    configure_issue_settings,
    create_invoice,
    create_line,
    delete_invoice,
    delete_line,
    invoice_amounts,
    invoices_for_scope,
    issue_invoice,
    line_amounts,
    update_invoice,
    update_line,
)
from .models import (
    CatalogProduct,
    ContractCost,
    Invoice,
    InvoiceLine,
    InvoiceNumberSeries,
    ServiceRate,
    TaxRate,
    TenantBillingProfile,
)
from .money import render_amount
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class InvoiceWriteSerializer(StrictSerializer):
    currency = serializers.CharField(max_length=3)
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    reference = serializers.CharField(max_length=240, allow_blank=True, required=False, default="")
    notes = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")


class InvoiceUpdateSerializer(StrictSerializer):
    currency = serializers.CharField(max_length=3, required=False)
    invoice_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=240, allow_blank=True, required=False)
    notes = serializers.CharField(max_length=4000, allow_blank=True, required=False)


class InvoiceLineWriteSerializer(StrictSerializer):
    origin_type = serializers.ChoiceField(
        choices=("catalog_product", "service_rate", "contract_cost"), allow_blank=True, required=False, default=""
    )
    origin_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=1000, required=False)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    tax_rate_id = serializers.UUIDField(required=False, allow_null=True)


class InvoiceLineUpdateSerializer(StrictSerializer):
    description = serializers.CharField(max_length=1000, required=False)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    tax_rate_name = serializers.CharField(max_length=120, allow_blank=True, required=False)
    tax_rate_value = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    tax_inclusive = serializers.BooleanField(required=False)


class InvoiceLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    position = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_amount = serializers.SerializerMethodField()
    currency = serializers.CharField()
    tax_rate_name = serializers.CharField()
    tax_rate_value = serializers.DecimalField(max_digits=9, decimal_places=6)
    tax_inclusive = serializers.BooleanField()
    net = serializers.SerializerMethodField()
    tax = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    origin_type = serializers.SerializerMethodField()
    origin_id = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_unit_amount(self, item):  # type: ignore[no-untyped-def]
        return render_amount(item.unit_amount, item.currency)

    def _amount(self, item, field: str) -> str:  # type: ignore[no-untyped-def]
        return render_amount(getattr(line_amounts(item), field), item.currency)

    @extend_schema_field(serializers.CharField())
    def get_net(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "net")

    @extend_schema_field(serializers.CharField())
    def get_tax(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "tax")

    @extend_schema_field(serializers.CharField())
    def get_total(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "total")

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_origin_type(self, item):  # type: ignore[no-untyped-def]
        if item.catalog_product_id:
            return "catalog_product"
        if item.service_rate_id:
            return "service_rate"
        if item.contract_cost_id:
            return "contract_cost"
        return ""

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_origin_id(self, item):  # type: ignore[no-untyped-def]
        if item.catalog_product_id:
            return item.catalog_product.entity_id
        return item.service_rate_id or item.contract_cost_id


class InvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    state = serializers.CharField()
    number = serializers.CharField(allow_blank=True)
    currency = serializers.CharField()
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    reference = serializers.CharField()
    notes = serializers.CharField()
    subtotal = serializers.SerializerMethodField()
    tax_total = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    lines = InvoiceLineSerializer(many=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    issued_at = serializers.DateTimeField(allow_null=True)
    content_digest = serializers.CharField(allow_blank=True)
    signature_algorithm = serializers.CharField(allow_blank=True)
    key_fingerprint = serializers.CharField(allow_blank=True)

    def to_representation(self, instance):  # type: ignore[no-untyped-def]
        rendered = super().to_representation(instance)
        if instance.state == "draft":
            for field in ("number", "issued_at", "content_digest", "signature_algorithm", "key_fingerprint"):
                rendered.pop(field, None)
        return rendered

    def _amount(self, item, field: str) -> str:  # type: ignore[no-untyped-def]
        return render_amount(getattr(invoice_amounts(item), field), item.currency)

    @extend_schema_field(serializers.CharField())
    def get_subtotal(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "subtotal")

    @extend_schema_field(serializers.CharField())
    def get_tax_total(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "tax_total")

    @extend_schema_field(serializers.CharField())
    def get_total(self, item):  # type: ignore[no-untyped-def]
        return self._amount(item, "total")


class InvoiceResultSerializer(serializers.Serializer):
    results = InvoiceSerializer(many=True)
    can_manage = serializers.BooleanField()
    can_issue = serializers.BooleanField()


class InvoiceIssueSettingsSerializer(StrictSerializer):
    legal_name = serializers.CharField(max_length=240)
    address_line_1 = serializers.CharField(max_length=240)
    address_line_2 = serializers.CharField(max_length=240, allow_blank=True, required=False, default="")
    city = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    postal_code = serializers.CharField(max_length=32)
    country_code = serializers.CharField(max_length=2)
    billing_email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=64, allow_blank=True, required=False, default="")
    tax_registration = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    default_currency = serializers.CharField(max_length=3)
    payment_terms_days = serializers.IntegerField(min_value=0, max_value=365)
    invoice_prefix = serializers.CharField(max_length=16)
    yearly_reset = serializers.BooleanField(default=False)


class InvoiceIssueSettingsResultSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    issue_ready = serializers.BooleanField()
    legal_name = serializers.CharField(allow_blank=True)
    address_line_1 = serializers.CharField(allow_blank=True)
    address_line_2 = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    region = serializers.CharField(allow_blank=True)
    postal_code = serializers.CharField(allow_blank=True)
    country_code = serializers.CharField(allow_blank=True)
    billing_email = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    tax_registration = serializers.CharField(allow_blank=True)
    default_currency = serializers.CharField()
    payment_terms_days = serializers.IntegerField()
    invoice_prefix = serializers.CharField()
    yearly_reset = serializers.BooleanField()


class OriginChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    origin_type = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    unit_amount = serializers.CharField()
    currency = serializers.CharField()
    quantity = serializers.CharField()


class OriginChoiceResultSerializer(serializers.Serializer):
    origins = OriginChoiceSerializer(many=True)
    tax_rates = serializers.ListField(child=serializers.DictField())


class ServiceRateWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    currency = serializers.CharField(max_length=3)


class ServiceRateSerializer(serializers.ModelSerializer):
    unit_amount = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRate
        fields = ("id", "name", "description", "unit_amount", "currency", "updated_at")

    @extend_schema_field(serializers.CharField())
    def get_unit_amount(self, item):  # type: ignore[no-untyped-def]
        return render_amount(item.unit_amount, item.currency)


def _workspace(request, organization_entity_id: UUID, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    if workspace.organization is None or "client" not in workspace.classifications:
        raise PermissionDenied("Invoice drafts require a client organization Workspace.")
    return workspace


def _invoice(workspace: ResolvedWorkspace, invoice_entity_id: UUID) -> Invoice:
    return get_object_or_404(invoices_for_scope(workspace.data_scope), entity_id=invoice_entity_id)


def _line(workspace: ResolvedWorkspace, invoice: Invoice, line_id: UUID) -> InvoiceLine:
    return get_object_or_404(InvoiceLine.scoped.for_scope(workspace.data_scope), invoice=invoice, id=line_id)


def _tax_rate(workspace: ResolvedWorkspace, value: UUID | None) -> TaxRate | None:
    if value is None:
        return None
    return get_object_or_404(TaxRate.scoped.for_tenant(workspace.member.tenant), id=value)


def _require_recent_session(request) -> None:  # type: ignore[no-untyped-def]
    if getattr(request, "auth", None) is not None or getattr(request, "api_token", None) is not None:
        raise PermissionDenied("API tokens cannot issue invoices or configure invoice issuance.")
    if not did_recently_authenticate(request._request):
        raise PermissionDenied("Recent password or MFA reauthentication is required.")


def _issue_settings_payload(tenant) -> dict[str, object]:  # type: ignore[no-untyped-def]
    try:
        profile = TenantBillingProfile.objects.get(tenant=tenant)
        configured = True
    except TenantBillingProfile.DoesNotExist:
        profile = TenantBillingProfile(tenant=tenant)
        configured = False
    series = InvoiceNumberSeries.objects.filter(tenant=tenant, prefix=profile.invoice_prefix).first()
    return {
        "configured": configured and series is not None,
        "issue_ready": configured and series is not None and profile.is_issue_ready,
        "legal_name": profile.legal_name,
        "address_line_1": profile.address_line_1,
        "address_line_2": profile.address_line_2,
        "city": profile.city,
        "region": profile.region,
        "postal_code": profile.postal_code,
        "country_code": profile.country_code,
        "billing_email": profile.billing_email,
        "phone": profile.phone,
        "tax_registration": profile.tax_registration,
        "default_currency": profile.default_currency,
        "payment_terms_days": profile.payment_terms_days,
        "invoice_prefix": profile.invoice_prefix,
        "yearly_reset": series.yearly_reset if series is not None else False,
    }


class InvoiceListCreateView(APIView):
    @extend_schema(operation_id="organization_invoices_list", responses={200: InvoiceResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_VIEW)
        return Response(
            InvoiceResultSerializer(
                {
                    "results": invoices_for_scope(workspace.data_scope),
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.INVOICES_EDIT, organization=workspace.organization
                    ),
                    "can_issue": context_has_permission(
                        workspace.member, PermissionKey.INVOICES_ISSUE, organization=workspace.organization
                    ),
                }
            ).data
        )

    @extend_schema(request=InvoiceWriteSerializer, responses={201: InvoiceSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        serializer = InvoiceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = workspace.organization
        if organization is None:  # pragma: no cover - guarded by _workspace
            raise PermissionDenied("Invoice drafts require a client organization Workspace.")
        try:
            record = create_invoice(
                tenant=workspace.member.tenant,
                organization=organization,
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (InvoiceError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, record.entity_id)).data, status=201)


class InvoiceIssueSettingsView(APIView):
    @extend_schema(responses={200: InvoiceIssueSettingsResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_ISSUE)
        return Response(InvoiceIssueSettingsResultSerializer(_issue_settings_payload(workspace.member.tenant)).data)

    @extend_schema(request=InvoiceIssueSettingsSerializer, responses={200: InvoiceIssueSettingsResultSerializer})
    def put(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_ISSUE)
        _require_recent_session(request)
        serializer = InvoiceIssueSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        yearly_reset = bool(values.pop("yearly_reset"))
        try:
            configure_issue_settings(
                tenant=workspace.member.tenant,
                actor_id=request.user.pk,
                values=values,
                yearly_reset=yearly_reset,
            )
        except (InvoiceError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceIssueSettingsResultSerializer(_issue_settings_payload(workspace.member.tenant)).data)


class InvoiceIssueView(APIView):
    @extend_schema(request=None, responses={200: InvoiceSerializer})
    def post(self, request, organization_entity_id, invoice_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_ISSUE)
        _require_recent_session(request)
        try:
            record = issue_invoice(invoice=_invoice(workspace, invoice_entity_id), actor_id=request.user.pk)
        except (InvoiceError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, record.entity_id)).data)


class InvoiceDetailView(APIView):
    @extend_schema(operation_id="organization_invoices_retrieve", responses={200: InvoiceSerializer})
    def get(self, request, organization_entity_id, invoice_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_VIEW)
        return Response(InvoiceSerializer(_invoice(workspace, invoice_entity_id)).data)

    @extend_schema(request=InvoiceUpdateSerializer, responses={200: InvoiceSerializer})
    def patch(self, request, organization_entity_id, invoice_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        serializer = InvoiceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise serializers.ValidationError({"detail": "At least one invoice field is required."})
        try:
            record = update_invoice(
                invoice=_invoice(workspace, invoice_entity_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except InvoiceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, record.entity_id)).data)

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Draft deleted")})
    def delete(self, request, organization_entity_id, invoice_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        try:
            delete_invoice(invoice=_invoice(workspace, invoice_entity_id), actor_id=request.user.pk)
        except InvoiceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(status=204)


class InvoiceLineListCreateView(APIView):
    @extend_schema(request=InvoiceLineWriteSerializer, responses={201: InvoiceSerializer})
    def post(self, request, organization_entity_id, invoice_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        serializer = InvoiceLineWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        origin_type = str(values.pop("origin_type", ""))
        origin_id = values.pop("origin_id", None)
        tax_rate = _tax_rate(workspace, values.pop("tax_rate_id", None))
        if origin_type == "contract_cost" and not context_has_permission(
            workspace.member, PermissionKey.COSTS_VIEW, organization=workspace.organization
        ):
            raise PermissionDenied("Cost visibility is required to use a contract-cost origin.")
        try:
            create_line(
                invoice=_invoice(workspace, invoice_entity_id),
                actor_id=request.user.pk,
                values=values,
                origin_type=origin_type,
                origin_id=origin_id,
                tax_rate=tax_rate,
            )
        except (InvoiceError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, invoice_entity_id)).data, status=201)


class InvoiceLineDetailView(APIView):
    @extend_schema(request=InvoiceLineUpdateSerializer, responses={200: InvoiceSerializer})
    def patch(self, request, organization_entity_id, invoice_entity_id, line_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        invoice = _invoice(workspace, invoice_entity_id)
        serializer = InvoiceLineUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise serializers.ValidationError({"detail": "At least one invoice-line field is required."})
        try:
            update_line(
                line=_line(workspace, invoice, line_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except InvoiceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, invoice_entity_id)).data)

    @extend_schema(request=None, responses={200: InvoiceSerializer})
    def delete(self, request, organization_entity_id, invoice_entity_id, line_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        invoice = _invoice(workspace, invoice_entity_id)
        try:
            delete_line(line=_line(workspace, invoice, line_id), actor_id=request.user.pk)
        except InvoiceError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(InvoiceSerializer(_invoice(workspace, invoice_entity_id)).data)


class InvoiceOriginChoiceView(APIView):
    @extend_schema(responses={200: OriginChoiceResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.INVOICES_EDIT)
        origins: list[dict[str, str]] = []
        for product in CatalogProduct.objects.filter(
            tenant=workspace.member.tenant, archived_at__isnull=True, unit_amount__isnull=False
        ).select_related("entity")[:200]:
            if product.unit_amount is None:  # pragma: no cover - narrowed by the query
                continue
            origins.append(
                {
                    "id": str(product.entity_id),
                    "origin_type": "catalog_product",
                    "name": product.entity.display_name,
                    "description": product.description,
                    "unit_amount": render_amount(product.unit_amount, product.currency),
                    "currency": product.currency,
                    "quantity": "1.000",
                }
            )
        for rate in ServiceRate.objects.filter(tenant=workspace.member.tenant, archived_at__isnull=True)[:200]:
            origins.append(
                {
                    "id": str(rate.id),
                    "origin_type": "service_rate",
                    "name": rate.name,
                    "description": rate.description,
                    "unit_amount": render_amount(rate.unit_amount, rate.currency),
                    "currency": rate.currency,
                    "quantity": "1.000",
                }
            )
        if context_has_permission(workspace.member, PermissionKey.COSTS_VIEW, organization=workspace.organization):
            for cost in ContractCost.scoped.for_scope(workspace.data_scope).filter(archived_at__isnull=True)[:200]:
                origins.append(
                    {
                        "id": str(cost.id),
                        "origin_type": "contract_cost",
                        "name": cost.label,
                        "description": cost.reference,
                        "unit_amount": render_amount(cost.amount, cost.currency),
                        "currency": cost.currency,
                        "quantity": str(cost.quantity),
                    }
                )
        today = timezone.localdate()
        rates = (
            TaxRate.scoped.for_tenant(workspace.member.tenant)
            .filter(effective_from__lte=today)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        )
        return Response(
            {
                "origins": origins,
                "tax_rates": [
                    {
                        "id": str(rate.id),
                        "name": rate.name,
                        "rate": str(rate.rate),
                        "inclusive": rate.inclusive,
                    }
                    for rate in rates
                ],
            }
        )


class ServiceRateListCreateView(APIView):
    def _workspace(self, request, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, permission)
        return workspace

    @extend_schema(responses={200: ServiceRateSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        workspace = self._workspace(request, PermissionKey.INVOICES_VIEW)
        records = ServiceRate.scoped.for_tenant(workspace.member.tenant).filter(archived_at__isnull=True)
        return Response(ServiceRateSerializer(records, many=True).data)

    @extend_schema(request=ServiceRateWriteSerializer, responses={201: ServiceRateSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        workspace = self._workspace(request, PermissionKey.INVOICES_EDIT)
        serializer = ServiceRateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = ServiceRate(tenant=workspace.member.tenant, **serializer.validated_data)
        try:
            record.full_clean()
            record.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ServiceRateSerializer(record).data, status=201)


class ServiceRateDetailView(APIView):
    def _workspace(self, request, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
        workspace = resolve_msp_workspace(request.user)
        require_permission(request.user, permission)
        return workspace

    def _record(self, workspace: ResolvedWorkspace, rate_id: UUID) -> ServiceRate:
        return get_object_or_404(
            ServiceRate.scoped.for_tenant(workspace.member.tenant), id=rate_id, archived_at__isnull=True
        )

    @extend_schema(request=ServiceRateWriteSerializer, responses={200: ServiceRateSerializer})
    def patch(self, request, rate_id):  # type: ignore[no-untyped-def]
        workspace = self._workspace(request, PermissionKey.INVOICES_EDIT)
        serializer = ServiceRateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = self._record(workspace, rate_id)
        for field, value in serializer.validated_data.items():
            setattr(record, field, value)
        try:
            record.full_clean()
            record.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ServiceRateSerializer(record).data)

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Service rate archived")})
    def delete(self, request, rate_id):  # type: ignore[no-untyped-def]
        workspace = self._workspace(request, PermissionKey.INVOICES_EDIT)
        record = self._record(workspace, rate_id)
        record.archived_at = timezone.now()
        record.save(update_fields=("archived_at", "updated_at"))
        return Response(status=204)
