"""Short-lived, actor-bound review of future recurring sell terms."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .invoice_recurrence import RecurrenceError
from .models import Organization, RecurringInvoiceTerms
from .money import calculate_line, render_amount
from .recurring_invoice_preview import PREVIEW_MAX_AGE
from .recurring_invoices import _digest, _scope, _validate_terms_amendment, amend_recurring_terms

TERMS_PREVIEW_SALT = "tekdocs.recurring-invoices.terms-preview.v1"


def _amounts(*, quantity: Decimal, unit_amount: Decimal, currency: str, tax_rate: object | None) -> dict[str, str]:
    rate = getattr(tax_rate, "rate", Decimal("0"))
    inclusive = getattr(tax_rate, "inclusive", False)
    result = calculate_line(
        quantity=quantity,
        unit_amount=unit_amount,
        currency=currency,
        tax_rate=rate,
        tax_inclusive=inclusive,
    )
    return {
        "net": render_amount(result.net, currency),
        "tax": render_amount(result.tax, currency),
        "total": render_amount(result.total, currency),
    }


@transaction.atomic
def preview_recurring_terms_amendment(
    *,
    user: User,
    organization: Organization,
    schedule_id: UUID,
    expected_terms_id: UUID,
    expected_source_digest: str,
    effective_from: date,
    description: str,
    unit_amount: Decimal,
    quantity: Decimal,
    currency: str,
    due_days: int,
    tax_rate_id: UUID | None = None,
) -> dict[str, object]:
    business_date = timezone.localdate()
    context = _validate_terms_amendment(
        user=user,
        organization=organization,
        schedule_id=schedule_id,
        expected_terms_id=expected_terms_id,
        expected_source_digest=expected_source_digest,
        effective_from=effective_from,
        business_date=business_date,
        unit_amount=unit_amount,
        quantity=quantity,
        currency=currency,
        tax_rate_id=tax_rate_id,
    )
    current = {
        "terms_id": str(context.latest.pk),
        "version": context.latest.version,
        "effective_from": context.latest.effective_from.isoformat(),
        "description": context.latest.description,
        "quantity": str(context.latest.quantity),
        "unit_amount": str(context.latest.unit_amount),
        "currency": context.latest.currency,
        "due_days": context.latest.due_days,
        "tax_rate_id": str(context.latest.tax_rate_id) if context.latest.tax_rate_id else None,
        **_amounts(
            quantity=context.latest.quantity,
            unit_amount=context.latest.unit_amount,
            currency=context.latest.currency,
            tax_rate=context.latest.tax_rate,
        ),
    }
    proposed = {
        "version": context.latest.version + 1,
        "effective_from": effective_from.isoformat(),
        "description": description,
        "quantity": str(quantity),
        "unit_amount": str(unit_amount),
        "currency": currency.upper(),
        "due_days": due_days,
        "tax_rate_id": str(tax_rate_id) if tax_rate_id else None,
        **_amounts(
            quantity=quantity,
            unit_amount=unit_amount,
            currency=currency.upper(),
            tax_rate=context.tax_rate,
        ),
    }
    plan = {
        "version": 1,
        "actor_id": str(user.pk),
        "tenant_id": str(context.scope.tenant_id),
        "organization_id": str(organization.pk),
        "schedule_id": str(schedule_id),
        "expected_terms_id": str(expected_terms_id),
        "expected_terms_version": context.latest.version,
        "expected_source_digest": expected_source_digest,
        "reviewed_on": business_date.isoformat(),
        "proposed": proposed,
    }
    return {
        **plan,
        "current": current,
        "source_changed": context.latest.source_digest != expected_source_digest,
        "preview_id": _digest(plan),
        "preview_token": signing.dumps(plan, salt=TERMS_PREVIEW_SALT, compress=True),
        "expires_in_seconds": PREVIEW_MAX_AGE,
    }


def _matching_applied_terms(
    *, user: User, organization: Organization, schedule_id: UUID, plan: dict[str, object]
) -> RecurringInvoiceTerms | None:
    scope = _scope(user, organization)
    proposed = plan.get("proposed")
    if not isinstance(proposed, dict):
        return None
    try:
        effective_from = date.fromisoformat(str(proposed["effective_from"]))
        quantity = Decimal(str(proposed["quantity"]))
        unit_amount = Decimal(str(proposed["unit_amount"]))
        tax_rate_id = UUID(str(proposed["tax_rate_id"])) if proposed.get("tax_rate_id") else None
        expected_version = int(str(plan["expected_terms_version"])) + 1
        due_days = int(proposed["due_days"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    terms = (
        RecurringInvoiceTerms.scoped.for_scope(scope)
        .filter(
            schedule_id=schedule_id,
            version=expected_version,
            effective_from=effective_from,
            approved_by=user,
        )
        .first()
    )
    if terms is None:
        return None
    expected = (
        str(proposed.get("description")),
        quantity,
        unit_amount,
        str(proposed.get("currency")),
        due_days,
        tax_rate_id,
        str(plan.get("expected_source_digest")),
    )
    actual = (
        terms.description,
        terms.quantity,
        terms.unit_amount,
        terms.currency,
        terms.due_days,
        terms.tax_rate_id,
        terms.source_digest,
    )
    return terms if actual == expected else None


@transaction.atomic
def apply_recurring_terms_preview(
    *, user: User, organization: Organization, schedule_id: UUID, preview_token: str
) -> RecurringInvoiceTerms:
    scope = _scope(user, organization)
    try:
        plan = signing.loads(preview_token, salt=TERMS_PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except signing.BadSignature as exc:
        raise RecurrenceError("The terms preview is invalid or expired; review the amendment again") from exc
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
        raise RecurrenceError("The terms preview does not belong to this operator and schedule")
    existing = _matching_applied_terms(user=user, organization=organization, schedule_id=schedule_id, plan=plan)
    if existing is not None:
        return existing
    proposed = plan.get("proposed")
    if not isinstance(proposed, dict):
        raise RecurrenceError("The terms preview is invalid; review the amendment again")
    try:
        expected_terms_id = UUID(str(plan["expected_terms_id"]))
        expected_source_digest = str(plan["expected_source_digest"])
        effective_from = date.fromisoformat(str(proposed["effective_from"]))
        description = str(proposed["description"])
        unit_amount = Decimal(str(proposed["unit_amount"]))
        quantity = Decimal(str(proposed["quantity"]))
        currency = str(proposed["currency"])
        due_days = int(str(proposed["due_days"]))
        tax_rate_id = UUID(str(proposed["tax_rate_id"])) if proposed.get("tax_rate_id") else None
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise RecurrenceError("The terms preview is invalid; review the amendment again") from exc
    try:
        return amend_recurring_terms(
            user=user,
            organization=organization,
            schedule_id=schedule_id,
            business_date=timezone.localdate(),
            expected_terms_id=expected_terms_id,
            expected_source_digest=expected_source_digest,
            effective_from=effective_from,
            description=description,
            unit_amount=unit_amount,
            quantity=quantity,
            currency=currency,
            due_days=due_days,
            tax_rate_id=tax_rate_id,
        )
    except RecurrenceError:
        existing = _matching_applied_terms(user=user, organization=organization, schedule_id=schedule_id, plan=plan)
        if existing is not None:
            return existing
        raise
