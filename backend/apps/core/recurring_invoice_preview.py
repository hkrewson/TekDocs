"""Short-lived, actor-bound review of exact recurring periods before atomic apply."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .invoice_recurrence import MAX_RECURRING_PERIODS, RecurrenceError, recurring_periods_due
from .models import Organization, RecurringInvoicePeriod, RecurringInvoiceSchedule, RecurringInvoiceTerms
from .money import calculate_line, render_amount
from .recurring_invoices import _digest, _scope, _snapshot, _source, _tax_date, generate_recurring_draft

PREVIEW_SALT = "tekdocs.recurring-invoices.preview.v1"
PREVIEW_MAX_AGE = 15 * 60


def review_recurring_source(*, user: User, organization: Organization, cost_id: UUID) -> dict[str, object]:
    cost = _source(_scope(user, organization), cost_id)
    snapshot = _snapshot(cost)
    starts = [value for value in (cost.starts_on, cost.contract.starts_on) if value is not None]
    ends = [value for value in (cost.ends_on, cost.contract.ends_on) if value is not None]
    return {
        "source": snapshot,
        "source_digest": _digest(snapshot),
        "earliest_anchor": max(starts) if starts else None,
        "latest_end": min(ends) if ends else None,
        "business_date": timezone.localdate(),
    }


def _plan(
    *, user: User, organization: Organization, schedule_id: UUID, starts_on: list[date], as_of: date
) -> dict[str, object]:
    scope = _scope(user, organization)
    if type(as_of) is not date or any(type(value) is not date for value in starts_on):
        raise RecurrenceError("Preview requires explicit business dates")
    if not starts_on or len(starts_on) > MAX_RECURRING_PERIODS or len(set(starts_on)) != len(starts_on):
        raise RecurrenceError("Select between 1 and 120 distinct billing periods")
    found = RecurringInvoiceSchedule.scoped.for_scope(scope).filter(pk=schedule_id).first()
    if found is None:
        raise RecurrenceError("The recurring schedule is unavailable in this Workspace")
    cost = _source(scope, found.contract_cost_id, lock=True)
    schedule = RecurringInvoiceSchedule.scoped.for_scope(scope).select_for_update().get(pk=schedule_id)
    if not schedule.enabled:
        raise RecurrenceError("This recurring schedule is disabled")
    terms = RecurringInvoiceTerms.scoped.for_scope(scope).select_related("tax_rate").get(schedule=schedule, version=1)
    if _digest(_snapshot(cost)) != terms.source_digest:
        raise RecurrenceError("The source terms changed; review the schedule before generating more drafts")
    amounts = calculate_line(
        quantity=terms.quantity,
        unit_amount=terms.unit_amount,
        currency=terms.currency,
        tax_rate=terms.tax_rate.rate if terms.tax_rate else Decimal("0"),
        tax_inclusive=terms.tax_rate.inclusive if terms.tax_rate else False,
    )
    periods = []
    for start in sorted(starts_on):
        if start > as_of:
            raise RecurrenceError("Future billing periods are not yet due")
        due = recurring_periods_due(
            anchor=schedule.anchor,
            interval=schedule.interval,
            due_from=start,
            as_of=start,
            ends_on=schedule.ends_on,
        )
        if not due or due[0].starts_on != start:
            raise RecurrenceError("Choose a due billing-period start from this schedule")
        if due[0].requires_proration_review:
            raise RecurrenceError("Partial periods require an explicit proration decision and cannot yet be generated")
        if terms.tax_rate:
            _tax_date(terms.tax_rate, start)
        try:
            due_date = start + timedelta(days=terms.due_days)
        except OverflowError as exc:
            raise RecurrenceError("The invoice due date is outside the supported date range") from exc
        periods.append(
            {
                "starts_on": start.isoformat(),
                "ends_before": due[0].ends_before.isoformat(),
                "due_date": due_date.isoformat(),
                "net": render_amount(amounts.net, terms.currency),
                "tax": render_amount(amounts.tax, terms.currency),
                "total": render_amount(amounts.total, terms.currency),
            }
        )
    # Claims deliberately stay outside the signed identity: successful apply must remain retryable.
    return {
        "version": 1,
        "actor_id": str(user.pk),
        "tenant_id": str(scope.tenant_id),
        "organization_id": str(organization.pk),
        "schedule_id": str(schedule.pk),
        "terms_id": str(terms.pk),
        "source_digest": terms.source_digest,
        "as_of": as_of.isoformat(),
        "currency": terms.currency,
        "description": terms.description,
        "quantity": str(terms.quantity),
        "unit_amount": str(terms.unit_amount),
        "periods": periods,
    }


@transaction.atomic
def preview_recurring_drafts(
    *, user: User, organization: Organization, schedule_id: UUID, starts_on: list[date], as_of: date
) -> dict[str, object]:
    plan = _plan(user=user, organization=organization, schedule_id=schedule_id, starts_on=starts_on, as_of=as_of)
    claims = (
        RecurringInvoicePeriod.scoped.for_scope(_scope(user, organization))
        .filter(
            schedule_id=schedule_id,
            starts_on__in=starts_on,
        )
        .select_related("invoice")
    )
    return {
        **plan,
        "preview_id": _digest(plan),
        "preview_token": signing.dumps(plan, salt=PREVIEW_SALT, compress=True),
        "expires_in_seconds": PREVIEW_MAX_AGE,
        "existing_invoices": [
            {"starts_on": claim.starts_on.isoformat(), "invoice_entity_id": str(claim.invoice.entity_id)}
            for claim in claims
        ],
    }


@transaction.atomic
def apply_recurring_preview(
    *, user: User, organization: Organization, schedule_id: UUID, preview_token: str
) -> list[RecurringInvoicePeriod]:
    scope = _scope(user, organization)
    try:
        plan = signing.loads(preview_token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except signing.BadSignature as exc:
        raise RecurrenceError("The preview is invalid or expired; review the periods again") from exc
    if not isinstance(plan, dict) or any(
        plan.get(key) != value
        for key, value in {
            "version": 1,
            "actor_id": str(user.pk),
            "tenant_id": str(scope.tenant_id),
            "organization_id": str(organization.pk),
            "schedule_id": str(schedule_id),
        }.items()
    ):
        raise RecurrenceError("The preview does not belong to this operator and schedule")
    try:
        starts = [date.fromisoformat(period["starts_on"]) for period in plan["periods"]]
        as_of = date.fromisoformat(plan["as_of"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RecurrenceError("The preview is invalid; review the periods again") from exc
    current = _plan(user=user, organization=organization, schedule_id=schedule_id, starts_on=starts, as_of=as_of)
    if current != plan:
        raise RecurrenceError("The preview changed; review the periods again")
    return [
        generate_recurring_draft(
            user=user,
            organization=organization,
            schedule_id=schedule_id,
            starts_on=start,
            as_of=as_of,
        )
        for start in starts
    ]


def discover_recurring_periods(
    *, user: User, organization: Organization, schedule_id: UUID, due_from: date, as_of: date
) -> dict[str, object]:
    """Read-only discovery; apply independently rechecks every condition under locks."""
    scope = _scope(user, organization)
    schedule = RecurringInvoiceSchedule.scoped.for_scope(scope).get(pk=schedule_id)
    terms = RecurringInvoiceTerms.scoped.for_scope(scope).select_related("tax_rate").get(schedule=schedule, version=1)
    reason = ""
    if not schedule.enabled:
        reason = "disabled"
    else:
        try:
            cost = _source(scope, schedule.contract_cost_id)
            if _digest(_snapshot(cost)) != terms.source_digest:
                reason = "source_changed"
        except RecurrenceError:
            reason = "source_unavailable"
    periods = recurring_periods_due(
        anchor=schedule.anchor,
        interval=schedule.interval,
        ends_on=schedule.ends_on,
        due_from=due_from,
        as_of=as_of,
    )
    claims = {
        claim.starts_on: str(claim.invoice.entity_id)
        for claim in RecurringInvoicePeriod.scoped.for_scope(scope)
        .filter(schedule=schedule, starts_on__gte=due_from, starts_on__lte=as_of)
        .select_related("invoice")
    }
    results = []
    for period in periods:
        blocked = reason
        if period.requires_proration_review:
            blocked = "partial"
        if terms.tax_rate and not blocked:
            try:
                _tax_date(terms.tax_rate, period.starts_on)
            except RecurrenceError:
                blocked = "tax"
        results.append(
            {
                "starts_on": period.starts_on,
                "ends_before": period.ends_before,
                "invoice_entity_id": claims.get(period.starts_on),
                "blocked_reason": blocked,
                "can_generate": not blocked and period.starts_on not in claims,
            }
        )
    return {"periods": results, "as_of": as_of, "due_from": due_from}
