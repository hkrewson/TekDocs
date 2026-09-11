from datetime import date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.core.invoice_recurrence import BillingPeriod, RecurrenceError, recurring_periods_due


def test_month_end_is_anchored_to_original_day_and_catch_up_keeps_periods_separate():
    periods = recurring_periods_due(anchor=date(2025, 1, 31), interval="monthly", as_of=date(2025, 4, 1))
    assert periods == (
        BillingPeriod(date(2025, 1, 31), date(2025, 2, 28), False),
        BillingPeriod(date(2025, 2, 28), date(2025, 3, 31), False),
        BillingPeriod(date(2025, 3, 31), date(2025, 4, 30), False),
    )


def test_february_anchor_does_not_imply_end_of_month():
    periods = recurring_periods_due(anchor=date(2025, 2, 28), interval="monthly", as_of=date(2025, 3, 28))
    assert periods[-1] == BillingPeriod(date(2025, 3, 28), date(2025, 4, 28), False)


def test_annual_leap_day_returns_in_next_leap_year():
    periods = recurring_periods_due(anchor=date(2024, 2, 29), interval="annual", as_of=date(2028, 2, 29))
    assert [period.starts_on for period in periods] == [
        date(2024, 2, 29), date(2025, 2, 28), date(2026, 2, 28), date(2027, 2, 28), date(2028, 2, 29)
    ]
    assert periods[-1].ends_before == date(2029, 2, 28)


def test_quarterly_periods_cross_years_without_day_drift():
    periods = recurring_periods_due(anchor=date(2025, 8, 31), interval="quarterly", as_of=date(2026, 6, 1))
    assert [period.starts_on for period in periods] == [
        date(2025, 8, 31), date(2025, 11, 30), date(2026, 2, 28), date(2026, 5, 31)
    ]


def test_future_schedule_is_not_due_and_anchor_day_is_due():
    arguments = {"anchor": date(2025, 6, 15), "interval": "monthly"}
    assert recurring_periods_due(**arguments, as_of=date(2025, 6, 14)) == ()
    assert recurring_periods_due(**arguments, as_of=date(2025, 6, 15)) == (
        BillingPeriod(date(2025, 6, 15), date(2025, 7, 15), False),
    )


@pytest.mark.parametrize(
    ("ends_on", "expected"),
    [
        (date(2025, 1, 31), (BillingPeriod(date(2025, 1, 1), date(2025, 2, 1), False),)),
        (date(2025, 1, 10), (BillingPeriod(date(2025, 1, 1), date(2025, 1, 11), True),)),
        (date(2025, 1, 1), (BillingPeriod(date(2025, 1, 1), date(2025, 1, 2), True),)),
        (date(2025, 2, 1), (
            BillingPeriod(date(2025, 1, 1), date(2025, 2, 1), False),
            BillingPeriod(date(2025, 2, 1), date(2025, 2, 2), True),
        )),
    ],
)
def test_inclusive_end_dates_and_partial_period_review(ends_on, expected):
    assert recurring_periods_due(
        anchor=date(2025, 1, 1), interval="monthly", as_of=date(2025, 12, 1), ends_on=ends_on
    ) == expected


def test_due_from_filters_start_dates_inclusively_without_moving_anchor():
    arguments = {"anchor": date(2025, 1, 31), "interval": "monthly", "as_of": date(2025, 4, 30)}
    full = recurring_periods_due(**arguments)
    assert recurring_periods_due(**arguments, due_from=date(2025, 2, 28)) == full[1:]
    assert recurring_periods_due(**arguments, due_from=date(2025, 3, 1)) == full[2:]
    assert recurring_periods_due(**arguments, due_from=date(2024, 1, 1)) == full


def test_distant_anchor_can_be_planned_in_a_bounded_window():
    periods = recurring_periods_due(
        anchor=date(1, 1, 31), interval="monthly", due_from=date(2025, 1, 1), as_of=date(2025, 2, 28)
    )
    assert [period.starts_on for period in periods] == [date(2025, 1, 31), date(2025, 2, 28)]


def test_catch_up_limit_is_explicit_and_does_not_silently_drop_periods():
    assert len(recurring_periods_due(
        anchor=date(2015, 1, 1), interval="monthly", as_of=date(2024, 12, 1)
    )) == 120
    with pytest.raises(RecurrenceError, match="narrow"):
        recurring_periods_due(anchor=date(2015, 1, 1), interval="monthly", as_of=date(2025, 1, 1))


@pytest.mark.parametrize("interval", ["one_time", "weekly", "", "MONTHLY"])
def test_unsupported_intervals_fail_explicitly(interval):
    with pytest.raises(RecurrenceError, match="supports"):
        recurring_periods_due(anchor=date(2025, 1, 1), interval=interval, as_of=date(2025, 2, 1))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"due_from": date(2025, 3, 1)}, "first due date"),
        ({"ends_on": date(2024, 12, 31)}, "precede"),
        ({"anchor": datetime(2025, 1, 1)}, "business date"),
        ({"as_of": datetime(2025, 2, 1)}, "business date"),
        ({"due_from": datetime(2025, 1, 1)}, "business date"),
        ({"ends_on": datetime(2025, 2, 1)}, "business date"),
        ({"ends_on": date.max}, "end-exclusive"),
        ({"anchor": date(9999, 12, 1), "as_of": date.max}, "supported date range"),
    ],
)
def test_invalid_or_unrepresentable_dates_fail_explicitly(override, message):
    arguments = {"anchor": date(2025, 1, 1), "interval": "monthly", "as_of": date(2025, 2, 1)}
    with pytest.raises(RecurrenceError, match=message):
        recurring_periods_due(**(arguments | override))


@given(
    anchor=st.dates(min_value=date(1900, 1, 1), max_value=date(2090, 12, 31)),
    interval=st.sampled_from(["monthly", "quarterly", "annual"]),
    elapsed_days=st.integers(min_value=0, max_value=3000),
)
def test_periods_partition_coverage_and_windowed_catch_up_matches_full_plan(anchor, interval, elapsed_days):
    as_of = anchor + timedelta(days=elapsed_days)
    periods = recurring_periods_due(anchor=anchor, interval=interval, as_of=as_of)
    assert periods[0].starts_on == anchor
    assert periods[-1].starts_on <= as_of < periods[-1].ends_before
    assert all(period.starts_on < period.ends_before and not period.requires_proration_review for period in periods)
    assert all(left.ends_before == right.starts_on for left, right in zip(periods, periods[1:], strict=False))
    due_from = anchor + timedelta(days=elapsed_days // 2)
    assert recurring_periods_due(anchor=anchor, interval=interval, as_of=as_of, due_from=due_from) == tuple(
        period for period in periods if period.starts_on >= due_from
    )
