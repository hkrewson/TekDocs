"""Calendar planning for recurring drafts; enrollment and authorization live above this layer."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

MAX_RECURRING_PERIODS = 120
_INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


class RecurrenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BillingPeriod:
    starts_on: date
    ends_before: date
    requires_proration_review: bool


def _business_date(value: date, name: str) -> None:
    # datetime inherits date, but mixing clock timestamps into a billing calendar is ambiguous.
    if type(value) is not date:
        raise RecurrenceError(f"{name} must be a business date without a time")


def _boundary(anchor: date, months: int) -> date:
    year, month_index = divmod((anchor.year - 1) * 12 + anchor.month - 1 + months, 12)
    year += 1
    month = month_index + 1
    if year > date.max.year:
        raise RecurrenceError("The next billing boundary is outside the supported date range")
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def recurring_periods_due(
    *,
    anchor: date,
    interval: str,
    as_of: date,
    due_from: date | None = None,
    ends_on: date | None = None,
) -> tuple[BillingPeriod, ...]:
    """Return started periods under the calendar contract in TekDocs issue #75 (ADR 0103).

    ``due_from`` filters period starts, not service coverage or generation history.
    ``ends_on`` is inclusive; returned service intervals are end-exclusive.
    A shortened final period is flagged, never priced or automatically prorated.
    """
    _business_date(anchor, "anchor")
    _business_date(as_of, "as_of")
    for name, value in (("due_from", due_from), ("ends_on", ends_on)):
        if value is not None:
            _business_date(value, name)
    if interval not in _INTERVAL_MONTHS:
        raise RecurrenceError("Recurring billing supports monthly, quarterly, or annual intervals")
    if due_from is not None and due_from > as_of:
        raise RecurrenceError("The first due date cannot follow the planning date")
    if ends_on is not None and ends_on < anchor:
        raise RecurrenceError("The schedule end cannot precede its billing anchor")
    if ends_on == date.max:
        raise RecurrenceError("The inclusive schedule end must allow an end-exclusive boundary")

    stride = _INTERVAL_MONTHS[interval]
    first_due = max(anchor, due_from) if due_from is not None else anchor
    last_due = min(as_of, ends_on) if ends_on is not None else as_of
    if first_due > last_due:
        return ()

    month_distance = (first_due.year - anchor.year) * 12 + first_due.month - anchor.month
    index = month_distance // stride
    start = _boundary(anchor, index * stride)
    if start < first_due:
        index += 1
        start = _boundary(anchor, index * stride)

    end_limit = ends_on + timedelta(days=1) if ends_on is not None else None
    periods: list[BillingPeriod] = []
    while start <= last_due:
        if len(periods) == MAX_RECURRING_PERIODS:
            raise RecurrenceError("More than 120 periods are due; narrow the planning date window")
        natural_end = _boundary(anchor, (index + 1) * stride)
        end = min(natural_end, end_limit) if end_limit is not None else natural_end
        periods.append(BillingPeriod(start, end, end < natural_end))
        if end_limit is not None and natural_end >= end_limit:
            break
        index += 1
        start = natural_end
    return tuple(periods)
