from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.core.money import (
    ISO_4217_LIST_ONE_PUBLISHED,
    SUPPORTED_CURRENCIES,
    MoneyError,
    calculate_invoice,
    calculate_line,
    minor_unit,
    render_amount,
    validate_amount,
)


def test_currency_registry_and_minor_unit_precision():
    assert ISO_4217_LIST_ONE_PUBLISHED == "2026-01-01"
    assert len(SUPPORTED_CURRENCIES) == 165
    assert minor_unit("usd") == 2
    assert minor_unit("JPY") == 0
    assert minor_unit("KWD") == 3
    assert minor_unit("ISK") == 0
    assert minor_unit("UYI") == 0
    assert minor_unit("XCG") == 2
    assert render_amount(Decimal("12"), "USD") == "12.00"
    assert render_amount(Decimal("12"), "JPY") == "12"
    assert render_amount(Decimal("12.3"), "KWD") == "12.300"

    with pytest.raises(MoneyError, match="supported ISO 4217"):
        minor_unit("ZZZ")
    with pytest.raises(MoneyError, match="more precision"):
        validate_amount(Decimal("1.001"), "USD")
    with pytest.raises(MoneyError, match="Decimal"):
        validate_amount(1.25, "USD")  # type: ignore[arg-type]


def test_round_half_up_and_inclusive_tax_are_explicit():
    exclusive = calculate_line(
        quantity=Decimal("1"), unit_amount=Decimal("1.25"), currency="USD", tax_rate=Decimal("0.10")
    )
    assert exclusive.net == Decimal("1.25")
    assert exclusive.tax == Decimal("0.13")
    assert exclusive.total == Decimal("1.38")

    inclusive = calculate_line(
        quantity=Decimal("1"),
        unit_amount=Decimal("110.00"),
        currency="USD",
        tax_rate=Decimal("0.10"),
        tax_inclusive=True,
    )
    assert inclusive.net == Decimal("100.00")
    assert inclusive.tax == Decimal("10.00")
    assert inclusive.total == Decimal("110.00")


@given(
    currency=st.sampled_from(sorted(SUPPORTED_CURRENCIES)),
    raw_units=st.lists(st.integers(min_value=-1_000_000, max_value=1_000_000), max_size=30),
    quantity=st.integers(min_value=1, max_value=1000),
    rate_basis_points=st.integers(min_value=0, max_value=5000),
    inclusive=st.booleans(),
)
def test_rendered_line_sets_reconcile_exactly(currency, raw_units, quantity, rate_basis_points, inclusive):
    scale = Decimal(1).scaleb(-minor_unit(currency))
    rate = Decimal(rate_basis_points) / Decimal("10000")
    lines = [
        calculate_line(
            quantity=Decimal(quantity) / Decimal("100"),
            unit_amount=Decimal(raw) * scale,
            currency=currency,
            tax_rate=rate,
            tax_inclusive=inclusive,
        )
        for raw in raw_units
    ]
    totals = calculate_invoice(lines, currency)

    rendered_subtotal = render_amount(
        sum((Decimal(render_amount(line.net, currency)) for line in lines), Decimal(0)),
        currency,
    )
    rendered_tax_total = render_amount(
        sum((Decimal(render_amount(line.tax, currency)) for line in lines), Decimal(0)),
        currency,
    )
    rendered_total = render_amount(Decimal(rendered_subtotal) + Decimal(rendered_tax_total), currency)

    assert rendered_subtotal == render_amount(totals.subtotal, currency)
    assert rendered_tax_total == render_amount(totals.tax_total, currency)
    assert rendered_total == render_amount(totals.total, currency)
