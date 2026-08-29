from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Prefetch, QuerySet

from .models import (
    AuditEvent,
    CatalogProduct,
    ContractCost,
    Entity,
    EntityVisibility,
    Invoice,
    InvoiceLine,
    Organization,
    ServiceRate,
    TaxRate,
    Tenant,
    workspace_for_owner,
)
from .money import InvoiceAmounts, LineAmounts, calculate_invoice, calculate_line
from .scoping import DataScope


class InvoiceError(ValueError):
    pass


def invoices_for_scope(scope: DataScope) -> QuerySet[Invoice]:
    return (
        Invoice.scoped.for_scope(scope)
        .select_related("entity", "organization")
        .prefetch_related(Prefetch("lines", queryset=InvoiceLine.objects.select_related("catalog_product__entity")))
        .order_by("-invoice_date", "-created_at", "id")
    )


def line_amounts(line: InvoiceLine) -> LineAmounts:
    return calculate_line(
        quantity=line.quantity,
        unit_amount=line.unit_amount,
        currency=line.currency,
        tax_rate=line.tax_rate_value,
        tax_inclusive=line.tax_inclusive,
    )


def invoice_amounts(invoice: Invoice) -> InvoiceAmounts:
    return calculate_invoice((line_amounts(line) for line in invoice.lines.all()), invoice.currency)


def _validate(instance) -> None:  # type: ignore[no-untyped-def]
    try:
        instance.full_clean()
    except ValidationError as exc:
        raise InvoiceError("; ".join(exc.messages)) from exc


@transaction.atomic
def create_invoice(
    *,
    tenant: Tenant,
    organization: Organization,
    actor_id: UUID,
    currency: str,
    invoice_date: date,
    due_date: date,
    reference: str = "",
    notes: str = "",
) -> Invoice:
    if organization.tenant_id != tenant.id:
        raise InvoiceError("Invoice organization must belong to the selected tenant")
    if not organization.classifications.filter(kind="client").exists():
        raise InvoiceError("Invoices can only be drafted in client Workspaces")
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="invoice",
        display_name=f"Draft invoice · {invoice_date.isoformat()}",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    invoice = Invoice(
        tenant=tenant,
        organization=organization,
        entity=entity,
        currency=currency,
        invoice_date=invoice_date,
        due_date=due_date,
        reference=reference,
        notes=notes,
    )
    _validate(invoice)
    invoice.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="invoice.draft_created", entity_id=entity.id, metadata={}
    )
    return invoice


@transaction.atomic
def update_invoice(*, invoice: Invoice, actor_id: UUID, values: dict[str, object]) -> Invoice:
    locked = Invoice.objects.select_for_update().select_related("entity", "organization").get(pk=invoice.pk)
    if locked.state != "draft":
        raise InvoiceError("Only draft invoices can be edited")
    next_currency = str(values.get("currency", locked.currency))
    if next_currency != locked.currency and InvoiceLine.objects.filter(invoice=locked).exists():
        raise InvoiceError("Remove draft lines before changing invoice currency")
    for field in ("currency", "invoice_date", "due_date", "reference", "notes"):
        if field in values:
            setattr(locked, field, values[field])
    _validate(locked)
    locked.save(update_fields=(*values.keys(), "updated_at"))
    if "invoice_date" in values:
        locked.entity.display_name = f"Draft invoice · {locked.invoice_date.isoformat()}"
        locked.entity.save(update_fields=("display_name", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="invoice.draft_updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return locked


@transaction.atomic
def delete_invoice(*, invoice: Invoice, actor_id: UUID) -> None:
    locked = Invoice.objects.select_for_update().select_related("entity").get(pk=invoice.pk)
    if locked.state != "draft":
        raise InvoiceError("Only draft invoices can be deleted")
    tenant = locked.tenant
    entity = locked.entity
    entity_id = entity.id
    locked.delete()
    entity.delete()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="invoice.draft_deleted", entity_id=entity_id, metadata={}
    )


def _origin_snapshot(
    *, invoice: Invoice, origin_type: str, origin_id: UUID | None
) -> tuple[dict[str, object], dict[str, object]]:
    if not origin_type:
        return {}, {}
    if origin_id is None:
        raise InvoiceError("An origin ID is required when an origin type is selected")
    if origin_type == "catalog_product":
        origin = (
            CatalogProduct.objects.select_related("entity")
            .filter(tenant=invoice.tenant, entity_id=origin_id, archived_at__isnull=True, unit_amount__isnull=False)
            .first()
        )
        if origin is None:
            raise InvoiceError("The priced catalog product is unavailable")
        return (
            {"catalog_product": origin},
            {
                "description": origin.entity.display_name,
                "quantity": Decimal("1"),
                "unit_amount": origin.unit_amount,
                "currency": origin.currency,
            },
        )
    if origin_type == "service_rate":
        service_rate = ServiceRate.objects.filter(
            tenant=invoice.tenant, id=origin_id, archived_at__isnull=True
        ).first()
        if service_rate is None:
            raise InvoiceError("The service rate is unavailable")
        return (
            {"service_rate": service_rate},
            {
                "description": service_rate.name,
                "quantity": Decimal("1"),
                "unit_amount": service_rate.unit_amount,
                "currency": service_rate.currency,
            },
        )
    if origin_type == "contract_cost":
        contract_cost = ContractCost.objects.filter(
            tenant=invoice.tenant, organization=invoice.organization, id=origin_id, archived_at__isnull=True
        ).first()
        if contract_cost is None:
            raise InvoiceError("The contract cost is unavailable in this Workspace")
        return (
            {"contract_cost": contract_cost},
            {
                "description": contract_cost.label,
                "quantity": contract_cost.quantity,
                "unit_amount": contract_cost.amount,
                "currency": contract_cost.currency,
            },
        )
    raise InvoiceError("Choose a supported invoice-line origin")


@transaction.atomic
def create_line(
    *,
    invoice: Invoice,
    actor_id: UUID,
    values: dict[str, object],
    origin_type: str = "",
    origin_id: UUID | None = None,
    tax_rate: TaxRate | None = None,
) -> InvoiceLine:
    locked = Invoice.objects.select_for_update().select_related("organization").get(pk=invoice.pk)
    if locked.state != "draft":
        raise InvoiceError("Only draft invoices can be edited")
    origin_fields, snapshot = _origin_snapshot(invoice=locked, origin_type=origin_type, origin_id=origin_id)
    snapshot.update({key: value for key, value in values.items() if value is not None})
    required = {"description", "quantity", "unit_amount"}
    if not required.issubset(snapshot):
        raise InvoiceError("Description, quantity, and unit amount are required for a manual line")
    if str(snapshot.get("currency", locked.currency)) != locked.currency:
        raise InvoiceError("Invoice-line origin currency must match the invoice currency")
    if tax_rate is not None:
        if tax_rate.tenant_id != locked.tenant_id:
            raise InvoiceError("Tax rate must belong to the invoice tenant")
        snapshot.update(tax_rate_name=tax_rate.name, tax_rate_value=tax_rate.rate, tax_inclusive=tax_rate.inclusive)
    next_position = (InvoiceLine.objects.filter(invoice=locked).aggregate(value=Max("position"))["value"] or 0) + 1
    line = InvoiceLine(
        tenant=locked.tenant,
        organization=locked.organization,
        invoice=locked,
        position=next_position,
        currency=locked.currency,
        tax_rate_name=str(snapshot.get("tax_rate_name", "")),
        tax_rate_value=cast(Decimal, snapshot.get("tax_rate_value", Decimal("0"))),
        tax_inclusive=bool(snapshot.get("tax_inclusive", False)),
        description=str(snapshot["description"]),
        quantity=cast(Decimal, snapshot["quantity"]),
        unit_amount=cast(Decimal, snapshot["unit_amount"]),
        **origin_fields,
    )
    _validate(line)
    line.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="invoice.draft_line_created",
        entity_id=locked.entity_id,
        metadata={},
    )
    return line


@transaction.atomic
def update_line(*, line: InvoiceLine, actor_id: UUID, values: dict[str, object]) -> InvoiceLine:
    locked = InvoiceLine.objects.select_for_update().select_related("invoice", "organization").get(pk=line.pk)
    if locked.invoice.state != "draft":
        raise InvoiceError("Only draft invoice lines can be edited")
    for field in ("description", "quantity", "unit_amount", "tax_rate_name", "tax_rate_value", "tax_inclusive"):
        if field in values:
            setattr(locked, field, values[field])
    _validate(locked)
    locked.save(update_fields=(*values.keys(), "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="invoice.draft_line_updated",
        entity_id=locked.invoice.entity_id,
        metadata={},
    )
    return locked


@transaction.atomic
def delete_line(*, line: InvoiceLine, actor_id: UUID) -> None:
    locked = InvoiceLine.objects.select_for_update().select_related("invoice").get(pk=line.pk)
    if locked.invoice.state != "draft":
        raise InvoiceError("Only draft invoice lines can be deleted")
    tenant = locked.tenant
    entity_id = locked.invoice.entity_id
    locked.delete()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="invoice.draft_line_deleted", entity_id=entity_id, metadata={}
    )
