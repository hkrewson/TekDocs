from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Max, Prefetch, QuerySet
from django.utils import timezone
from django.utils.text import slugify

from .document_keys import keys_in_markdown
from .email import send_invoice_email
from .invoice_pdf import render_invoice_pdf
from .models import (
    AuditEvent,
    CatalogProduct,
    ContractCost,
    Entity,
    EntityVisibility,
    Invoice,
    InvoiceArtifact,
    InvoiceLine,
    InvoiceNumberSeries,
    InvoiceState,
    Organization,
    ServiceRate,
    TaxRate,
    Tenant,
    TenantBillingProfile,
    workspace_for_owner,
)
from .money import InvoiceAmounts, LineAmounts, calculate_invoice, calculate_line, render_amount
from .publications import _encoded_public_key, publication_signing_key
from .scoping import DataScope


class InvoiceError(ValueError):
    pass


ISSUED_SIGNATURE_FORMAT = "tekdocs-issued-invoice/v1"


def _issued_invoice(invoice: Invoice) -> Invoice:
    if invoice.state != InvoiceState.ISSUED:
        raise InvoiceError("Only issued invoices can be delivered or downloaded")
    return invoice


def invoice_pdf_bytes(invoice: Invoice) -> bytes:
    issued = _issued_invoice(invoice)
    try:
        artifact = issued.artifact
    except InvoiceArtifact.DoesNotExist as exc:
        raise InvoiceError("The retained invoice PDF is unavailable") from exc
    artifact.file.open("rb")
    try:
        content = cast(bytes, artifact.file.read())
    finally:
        artifact.file.close()
    if len(content) != artifact.size or hashlib.sha256(content).hexdigest() != artifact.checksum:
        raise InvoiceError("The retained invoice PDF failed its integrity check")
    return content


def _safe_csv_cell(value: object) -> str:
    rendered = str(value)
    return f"'{rendered}" if rendered.startswith(("=", "+", "-", "@")) else rendered


def invoice_csv_bytes(invoice: Invoice) -> bytes:
    issued = _issued_invoice(invoice)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "invoice_number",
            "invoice_date",
            "due_date",
            "reference",
            "currency",
            "line_position",
            "description",
            "quantity",
            "unit_amount",
            "tax_rate_name",
            "tax_rate_value",
            "tax_inclusive",
            "net",
            "tax",
            "line_total",
            "invoice_subtotal",
            "invoice_tax",
            "invoice_total",
        ]
    )
    amounts = invoice_amounts(issued)
    for line in issued.lines.all():
        line_totals = line_amounts(line)
        writer.writerow(
            [
                issued.number,
                issued.invoice_date.isoformat(),
                issued.due_date.isoformat(),
                _safe_csv_cell(issued.reference),
                issued.currency,
                line.position,
                _safe_csv_cell(line.description),
                str(line.quantity),
                render_amount(line.unit_amount, issued.currency),
                _safe_csv_cell(line.tax_rate_name),
                str(line.tax_rate_value),
                "true" if line.tax_inclusive else "false",
                render_amount(line_totals.net, issued.currency),
                render_amount(line_totals.tax, issued.currency),
                render_amount(line_totals.total, issued.currency),
                render_amount(amounts.subtotal, issued.currency),
                render_amount(amounts.tax_total, issued.currency),
                render_amount(amounts.total, issued.currency),
            ]
        )
    return output.getvalue().encode("utf-8")


@transaction.atomic
def deliver_invoice(*, invoice: Invoice, recipient: str, actor_id: UUID) -> Invoice:
    locked = (
        Invoice.objects.select_for_update()
        .select_related("tenant")
        .prefetch_related("lines")
        .get(pk=invoice.pk)
    )
    _issued_invoice(locked)
    pdf = invoice_pdf_bytes(locked)
    csv_export = invoice_csv_bytes(locked)
    issuer_name = str(locked.issuer_snapshot.get("legal_name", "")).strip()
    if not issuer_name:
        raise InvoiceError("The snapshotted invoice issuer is unavailable")
    total = render_amount(invoice_amounts(locked).total, locked.currency)
    send_invoice_email(
        recipient=recipient,
        invoice_number=locked.number,
        issuer_name=issuer_name,
        total=total,
        currency=locked.currency,
        due_date=locked.due_date.isoformat(),
        pdf=pdf,
        csv_export=csv_export,
        message_id=f"<tekdocs-invoice-{locked.entity_id}-{uuid4()}@invoice.tekdocs.invalid>",
    )
    delivered_at = timezone.now()
    Invoice.objects.filter(pk=locked.pk).update(
        delivered_at=delivered_at,
        delivered_by_id=actor_id,
        delivery_recipient=recipient,
        delivery_count=F("delivery_count") + 1,
        updated_at=delivered_at,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="invoice.delivered",
        entity_id=locked.entity_id,
        metadata={"delivery_count": locked.delivery_count + 1},
    )
    return invoices_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)


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
    if invoice.state == InvoiceState.ISSUED:
        if invoice.subtotal_amount is None or invoice.tax_amount is None or invoice.total_amount is None:
            raise InvoiceError("Issued invoice totals are unavailable")
        return InvoiceAmounts(
            subtotal=invoice.subtotal_amount,
            tax_total=invoice.tax_amount,
            total=invoice.total_amount,
        )
    return calculate_invoice((line_amounts(line) for line in invoice.lines.all()), invoice.currency)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _profile_snapshot(profile: TenantBillingProfile) -> dict[str, object]:
    return {
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
    }


def _customer_snapshot(invoice: Invoice) -> dict[str, object]:
    return {
        "display_name": invoice.organization.entity.display_name,
        "legal_name": invoice.organization.legal_name,
        "website": invoice.organization.website,
    }


@transaction.atomic
def configure_issue_settings(
    *, tenant: Tenant, actor_id: UUID, values: dict[str, object], yearly_reset: bool
) -> tuple[TenantBillingProfile, InvoiceNumberSeries]:
    profile, _created = TenantBillingProfile.objects.select_for_update().get_or_create(tenant=tenant)
    for field in (
        "legal_name",
        "address_line_1",
        "address_line_2",
        "city",
        "region",
        "postal_code",
        "country_code",
        "billing_email",
        "phone",
        "tax_registration",
        "default_currency",
        "payment_terms_days",
        "invoice_prefix",
    ):
        if field in values:
            setattr(profile, field, values[field])
    _validate(profile)
    profile.save()
    series = (
        InvoiceNumberSeries.objects.select_for_update().filter(tenant=tenant, prefix=profile.invoice_prefix).first()
    )
    if series is None:
        series = InvoiceNumberSeries(tenant=tenant, prefix=profile.invoice_prefix, yearly_reset=yearly_reset)
    elif series.yearly_reset != yearly_reset:
        if series.invoices.exists():
            raise InvoiceError("A numbering series cannot change its yearly-reset rule after use")
        series.yearly_reset = yearly_reset
        series.current_year = None
    _validate(series)
    series.save()
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="invoice.issue_settings_updated",
        metadata={},
    )
    return profile, series


@transaction.atomic
def issue_invoice(*, invoice: Invoice, actor_id: UUID) -> Invoice:
    locked = (
        Invoice.objects.select_for_update()
        .select_related("entity", "organization__entity", "tenant")
        .prefetch_related("lines")
        .get(pk=invoice.pk)
    )
    if locked.state != InvoiceState.DRAFT:
        raise InvoiceError("Only a draft invoice can be issued")
    lines = list(locked.lines.all())
    if not lines:
        raise InvoiceError("Add at least one line before issuing the invoice")
    for line in lines:
        keys, malformed = keys_in_markdown(line.description)
        if keys or malformed:
            raise InvoiceError("Resolve invoice-line key expressions before issuing the invoice")
    try:
        profile = TenantBillingProfile.objects.select_for_update().get(tenant=locked.tenant)
    except TenantBillingProfile.DoesNotExist as exc:
        raise InvoiceError("Configure the invoice issuer before issuing") from exc
    if not profile.is_issue_ready:
        raise InvoiceError("Complete the invoice issuer identity before issuing")
    try:
        series = InvoiceNumberSeries.objects.select_for_update().get(
            tenant=locked.tenant, prefix=profile.invoice_prefix
        )
    except InvoiceNumberSeries.DoesNotExist as exc:
        raise InvoiceError("Configure the invoice numbering series before issuing") from exc

    issue_year = locked.invoice_date.year
    if series.yearly_reset:
        if series.current_year is not None and issue_year < series.current_year:
            raise InvoiceError("A prior-year invoice cannot use a numbering series that has advanced")
        if series.current_year != issue_year:
            series.current_year = issue_year
            series.next_number = 1
            series.save(update_fields=("current_year", "next_number", "updated_at"))
    sequence = series.next_number
    number = (
        f"{series.prefix}-{issue_year}-{sequence:06d}" if series.yearly_reset else f"{series.prefix}-{sequence:06d}"
    )
    amounts = calculate_invoice((line_amounts(line) for line in lines), locked.currency)
    issued_at = timezone.now()
    issuer = _profile_snapshot(profile)
    customer = _customer_snapshot(locked)
    line_records = []
    for line in lines:
        values = line_amounts(line)
        line_records.append(
            {
                "id": str(line.id),
                "position": line.position,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_amount": render_amount(line.unit_amount, locked.currency),
                "currency": line.currency,
                "tax_rate_name": line.tax_rate_name,
                "tax_rate_value": str(line.tax_rate_value),
                "tax_inclusive": line.tax_inclusive,
                "net": render_amount(values.net, locked.currency),
                "tax": render_amount(values.tax, locked.currency),
                "total": render_amount(values.total, locked.currency),
            }
        )
    pdf = render_invoice_pdf(
        number=number,
        invoice_date=locked.invoice_date.isoformat(),
        due_date=locked.due_date.isoformat(),
        currency=locked.currency,
        reference=locked.reference,
        notes=locked.notes,
        issuer=issuer,
        customer=customer,
        lines=line_records,
        subtotal=render_amount(amounts.subtotal, locked.currency),
        tax_total=render_amount(amounts.tax_total, locked.currency),
        total=render_amount(amounts.total, locked.currency),
    )
    artifact_checksum = hashlib.sha256(pdf).hexdigest()
    manifest = {
        "format": ISSUED_SIGNATURE_FORMAT,
        "invoice_id": str(locked.entity_id),
        "number": number,
        "series_id": str(series.id),
        "series_sequence": sequence,
        "series_year": issue_year if series.yearly_reset else None,
        "invoice_date": locked.invoice_date.isoformat(),
        "due_date": locked.due_date.isoformat(),
        "currency": locked.currency,
        "reference": locked.reference,
        "notes": locked.notes,
        "issuer": issuer,
        "customer": customer,
        "lines": line_records,
        "subtotal": render_amount(amounts.subtotal, locked.currency),
        "tax_total": render_amount(amounts.tax_total, locked.currency),
        "total": render_amount(amounts.total, locked.currency),
        "issued_by": str(actor_id),
        "issued_at": issued_at.isoformat(),
        "pdf_checksum": artifact_checksum,
    }
    digest = hashlib.sha256(_canonical_json(manifest)).digest()
    signing_key = publication_signing_key()
    public_key, fingerprint = _encoded_public_key(signing_key)

    locked.state = InvoiceState.ISSUED
    locked.number_series = series
    locked.number = number
    locked.series_year = issue_year if series.yearly_reset else None
    locked.series_sequence = sequence
    locked.issuer_snapshot = issuer
    locked.customer_snapshot = customer
    locked.key_resolutions = []
    locked.subtotal_amount = amounts.subtotal
    locked.tax_amount = amounts.tax_total
    locked.total_amount = amounts.total
    locked.content_digest = digest.hex()
    locked.signature = base64.urlsafe_b64encode(signing_key.sign(digest)).decode("ascii")
    locked.signature_algorithm = "Ed25519"
    locked.public_key = public_key
    locked.key_fingerprint = fingerprint
    locked.issued_by_id = actor_id
    locked.issued_at = issued_at
    _validate(locked)
    locked.save()

    artifact = InvoiceArtifact(
        tenant=locked.tenant,
        organization=locked.organization,
        invoice=locked,
        original_filename=f"{slugify(number) or 'invoice'}.pdf",
        size=len(pdf),
        checksum=artifact_checksum,
        created_at=issued_at,
    )
    artifact.file.save(artifact.original_filename, ContentFile(pdf), save=False)
    _validate(artifact)
    artifact.save()  # type: ignore[no-untyped-call]

    series.next_number = sequence + 1
    series.save(update_fields=("current_year", "next_number", "updated_at"))
    locked.entity.display_name = f"Invoice {number}"
    locked.entity.save(update_fields=("display_name", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="invoice.issued",
        entity_id=locked.entity_id,
        metadata={},
    )
    return locked


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
        service_rate = ServiceRate.objects.filter(tenant=invoice.tenant, id=origin_id, archived_at__isnull=True).first()
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
