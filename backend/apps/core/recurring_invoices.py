"""Approved recurring enrollment and atomic period claims (issue #75)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .invoice_recurrence import RecurrenceError, recurring_periods_due
from .invoicing import create_invoice, create_line
from .models import (
    AuditEvent,
    CommercialContract,
    ContractCost,
    Organization,
    RecurringInvoicePeriod,
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
    TaxRate,
)
from .money import calculate_line, normalize_currency, validate_amount
from .scoping import DataScope


def _scope(user: User, organization: Organization) -> DataScope:
    member = require_permission(user, PermissionKey.INVOICES_EDIT, organization=organization)
    require_permission(user, PermissionKey.INVOICES_VIEW, organization=organization)
    require_permission(user, PermissionKey.COSTS_VIEW, organization=organization)
    if not organization.classifications.filter(kind="client").exists():
        raise RecurrenceError("Recurring invoices require a client Workspace")
    return DataScope.organization(member.tenant, organization)


def _source(scope: DataScope, cost_id: UUID, *, lock: bool = False) -> ContractCost:
    cost = ContractCost.scoped.for_scope(scope).filter(pk=cost_id).first()
    if cost is None:
        raise RecurrenceError("The contract cost is unavailable in this Workspace")
    contracts = CommercialContract.scoped.for_scope(scope)
    if lock:
        contracts = contracts.select_for_update()
    contract = contracts.get(pk=cost.contract_id)
    costs = ContractCost.scoped.for_scope(scope)
    if lock:
        costs = costs.select_for_update()
    cost = costs.get(pk=cost_id, contract=contract)
    cost.contract = contract
    if cost.archived_at or contract.archived_at or contract.entity.archived_at or contract.status != "active":
        raise RecurrenceError("Recurring invoices require an active, unarchived contract and cost")
    if cost.billing_interval not in {"monthly", "quarterly", "annual"}:
        raise RecurrenceError("One-time costs cannot be enrolled for recurring invoices")
    return cost


def _snapshot(cost: ContractCost) -> dict[str, object]:
    return {
        "cost_id": str(cost.pk),
        "contract_id": str(cost.contract_id),
        "label": cost.label,
        "amount": str(cost.amount),
        "quantity": str(cost.quantity),
        "currency": cost.currency,
        "interval": cost.billing_interval,
        "cost_starts_on": cost.starts_on.isoformat() if cost.starts_on else None,
        "cost_ends_on": cost.ends_on.isoformat() if cost.ends_on else None,
        "contract_starts_on": cost.contract.starts_on.isoformat() if cost.contract.starts_on else None,
        "contract_ends_on": cost.contract.ends_on.isoformat() if cost.contract.ends_on else None,
    }


def _digest(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recurring_source_digest(*, user: User, organization: Organization, cost_id: UUID) -> str:
    """Bind an enrollment decision to the exact currently reviewed source values."""
    return _digest(_snapshot(_source(_scope(user, organization), cost_id)))


def _save(record: models.Model) -> None:
    try:
        record.full_clean()
    except ValidationError as exc:
        raise RecurrenceError(" ".join(exc.messages)) from exc
    record.save()


@transaction.atomic
def enroll_recurring_schedule(
    *,
    user: User,
    organization: Organization,
    cost_id: UUID,
    expected_source_digest: str,
    anchor: date,
    ends_on: date | None,
    description: str,
    unit_amount: Decimal,
    quantity: Decimal,
    currency: str,
    due_days: int,
    tax_rate_id: UUID | None = None,
) -> RecurringInvoiceSchedule:
    scope = _scope(user, organization)
    cost = _source(scope, cost_id, lock=True)
    snapshot = _snapshot(cost)
    if _digest(snapshot) != expected_source_digest:
        raise RecurrenceError("The source terms changed; review them before enrollment")
    if RecurringInvoiceSchedule.scoped.for_scope(scope).filter(contract_cost=cost).exists():
        raise RecurrenceError("This cost already has a retained recurring schedule")
    starts = [value for value in (cost.starts_on, cost.contract.starts_on) if value is not None]
    ends = [value for value in (cost.ends_on, cost.contract.ends_on) if value is not None]
    recurring_periods_due(anchor=anchor, interval=cost.billing_interval, as_of=anchor, ends_on=ends_on)
    if starts and anchor < max(starts):
        raise RecurrenceError("The billing anchor precedes the source effective dates")
    if ends and (ends_on is None or ends_on > min(ends)):
        raise RecurrenceError("The billing end must stay within the source effective dates")
    currency = normalize_currency(currency)
    if currency != cost.currency:
        raise RecurrenceError("Approved sell terms must use the contract-cost currency")
    validate_amount(unit_amount, currency)
    calculate_line(quantity=quantity, unit_amount=unit_amount, currency=currency)
    tax_rate = None
    if tax_rate_id is not None:
        tax_rate = TaxRate.objects.filter(tenant_id=scope.tenant_id, pk=tax_rate_id).first()
        if tax_rate is None:
            raise RecurrenceError("The selected tax rate is unavailable")
        _tax_date(tax_rate, anchor)
    schedule = RecurringInvoiceSchedule(
        tenant_id=scope.tenant_id,
        organization=organization,
        contract_cost=cost,
        anchor=anchor,
        ends_on=ends_on,
        interval=cost.billing_interval,
        created_by=user,
    )
    _save(schedule)
    terms = RecurringInvoiceTerms(
        tenant_id=scope.tenant_id,
        organization=organization,
        schedule=schedule,
        description=description,
        unit_amount=unit_amount,
        quantity=quantity,
        currency=currency,
        due_days=due_days,
        tax_rate=tax_rate,
        source_snapshot=snapshot,
        source_digest=expected_source_digest,
        approved_by=user,
    )
    _save(terms)
    AuditEvent.objects.create(
        tenant_id=scope.tenant_id,
        actor=user,
        action="invoice.recurring_enrolled",
        entity_id=cost.contract.entity_id,
        metadata={"schedule_id": str(schedule.pk)},
    )
    return schedule


def _tax_date(tax_rate: TaxRate, starts_on: date) -> None:
    if starts_on < tax_rate.effective_from or (tax_rate.effective_to and starts_on > tax_rate.effective_to):
        raise RecurrenceError("The approved tax version does not cover this period; review the schedule")


@transaction.atomic
def generate_recurring_draft(
    *,
    user: User,
    organization: Organization,
    schedule_id: UUID,
    starts_on: date,
    as_of: date,
) -> RecurringInvoicePeriod:
    if type(starts_on) is not date or type(as_of) is not date:
        raise RecurrenceError("Generation requires explicit business dates")
    if starts_on > as_of:
        raise RecurrenceError("Future billing periods are not yet due")
    scope = _scope(user, organization)
    found = RecurringInvoiceSchedule.scoped.for_scope(scope).filter(pk=schedule_id).first()
    if found is None:
        raise RecurrenceError("The recurring schedule is unavailable in this Workspace")
    # All source writers lock contract before cost; keep that order before locking the schedule.
    cost = _source(scope, found.contract_cost_id, lock=True)
    schedule = RecurringInvoiceSchedule.scoped.for_scope(scope).select_for_update().get(pk=schedule_id)
    existing = RecurringInvoicePeriod.scoped.for_scope(scope).filter(schedule=schedule, starts_on=starts_on).first()
    if existing is not None:
        return existing
    if not schedule.enabled:
        raise RecurrenceError("This recurring schedule is disabled")
    terms = RecurringInvoiceTerms.scoped.for_scope(scope).select_related("tax_rate").get(schedule=schedule, version=1)
    if _digest(_snapshot(cost)) != terms.source_digest:
        raise RecurrenceError("The source terms changed; review the schedule before generating more drafts")
    periods = recurring_periods_due(
        anchor=schedule.anchor,
        interval=schedule.interval,
        due_from=starts_on,
        as_of=starts_on,
        ends_on=schedule.ends_on,
    )
    if not periods or periods[0].starts_on != starts_on:
        raise RecurrenceError("Choose a due billing-period start from this schedule")
    period = periods[0]
    if period.requires_proration_review:
        raise RecurrenceError("Partial periods require an explicit proration decision and cannot yet be generated")
    if terms.tax_rate is not None:
        _tax_date(terms.tax_rate, starts_on)
    try:
        due_date = starts_on + timedelta(days=terms.due_days)
    except OverflowError as exc:
        raise RecurrenceError("The invoice due date is outside the supported date range") from exc
    invoice = create_invoice(
        tenant=organization.tenant,
        organization=organization,
        actor_id=user.pk,
        currency=terms.currency,
        invoice_date=starts_on,
        due_date=due_date,
        reference=f"Service period {starts_on.isoformat()} to {(period.ends_before - timedelta(days=1)).isoformat()}",
    )
    line = create_line(
        invoice=invoice,
        actor_id=user.pk,
        origin_type="contract_cost",
        origin_id=cost.pk,
        tax_rate=terms.tax_rate,
        values={
            "description": terms.description,
            "quantity": terms.quantity,
            "unit_amount": terms.unit_amount,
            "currency": terms.currency,
        },
    )
    claim = RecurringInvoicePeriod(
        tenant_id=scope.tenant_id,
        organization=organization,
        schedule=schedule,
        terms=terms,
        starts_on=starts_on,
        ends_before=period.ends_before,
        invoice=invoice,
        line=line,
        generated_by=user,
    )
    _save(claim)
    AuditEvent.objects.create(
        tenant_id=scope.tenant_id,
        actor=user,
        action="invoice.recurring_generated",
        entity_id=invoice.entity_id,
        metadata={"schedule_id": str(schedule.pk), "period_id": str(claim.pk)},
    )
    return claim
