"""Exact, currency-aware arithmetic for invoicing.

This is the only module permitted to perform monetary calculations. Values
enter and leave as Decimal and rendered values are decimal strings.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class MoneyError(ValueError):
    """Raised when a value cannot participate in supported money arithmetic."""


# ISO 4217 List One, published 2026-01-01 by the ISO maintenance agency:
# https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml
# Entries whose minor unit is "N.A." (metals and test/reserved codes) are not
# currencies TekDocs can invoice in and are intentionally excluded.
ISO_4217_LIST_ONE_PUBLISHED = "2026-01-01"

_TWO_MINOR_UNIT_CODES = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD
    CDF CHE CHF CHW CNY COP COU CRC CUP CVE CZK DKK DOP DZD EGP ERN ETB EUR FJD FKP
    GBP GEL GHS GIP GMD GTQ GYD HKD HNL HTG HUF IDR ILS INR IRR ISK JMD KES KGS KHR KPW KYD
    KZT LAK LBP LKR LRD LSL MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR
    NZD PAB PEN PGK PHP PKR PLN QAR RON RSD RUB SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP
    STN SVC SYP SZL THB TJS TMT TOP TRY TTD TWD TZS UAH USD USN UYI UYU UZS VED VES WST XCD
    XAD XCG YER ZAR ZMW ZWG
    """.split()
)
_MINOR_UNIT_OVERRIDES = {
    "BHD": 3,
    "BIF": 0,
    "CLF": 4,
    "CLP": 0,
    "DJF": 0,
    "GNF": 0,
    "IQD": 3,
    "ISK": 0,
    "JOD": 3,
    "JPY": 0,
    "KMF": 0,
    "KRW": 0,
    "KWD": 3,
    "LYD": 3,
    "OMR": 3,
    "PYG": 0,
    "RWF": 0,
    "TND": 3,
    "UGX": 0,
    "UYI": 0,
    "UYW": 4,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
}
CURRENCY_MINOR_UNITS = {**{code: 2 for code in _TWO_MINOR_UNIT_CODES}, **_MINOR_UNIT_OVERRIDES}
SUPPORTED_CURRENCIES = frozenset(CURRENCY_MINOR_UNITS)


@dataclass(frozen=True, slots=True)
class LineAmounts:
    net: Decimal
    tax: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class InvoiceAmounts:
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal


def normalize_currency(code: str) -> str:
    if not isinstance(code, str):
        raise MoneyError("Currency must be an ISO 4217 alphabetic code")
    normalized = code.strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise MoneyError("Currency is not in the supported ISO 4217 registry")
    return normalized


def minor_unit(currency: str) -> int:
    return CURRENCY_MINOR_UNITS[normalize_currency(currency)]


def _require_decimal(value: Decimal, *, label: str) -> Decimal:
    if not isinstance(value, Decimal) or isinstance(value, bool):
        raise MoneyError(f"{label} must be a Decimal")
    if not value.is_finite():
        raise MoneyError(f"{label} must be finite")
    return value


def quantum(currency: str) -> Decimal:
    return Decimal(1).scaleb(-minor_unit(currency))


def round_amount(value: Decimal, currency: str) -> Decimal:
    """Round at a named commercial calculation point."""
    value = _require_decimal(value, label="Amount")
    try:
        return value.quantize(quantum(currency), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise MoneyError("Amount exceeds supported decimal precision") from exc


def validate_amount(value: Decimal, currency: str, *, allow_negative: bool = False) -> Decimal:
    """Validate a stored input amount without silently rounding it."""
    value = _require_decimal(value, label="Amount")
    normalize_currency(currency)
    if not allow_negative and value < 0:
        raise MoneyError("Amount cannot be negative")
    if value != round_amount(value, currency):
        raise MoneyError("Amount has more precision than the currency minor unit permits")
    return value


def calculate_line(
    *,
    quantity: Decimal,
    unit_amount: Decimal,
    currency: str,
    tax_rate: Decimal = Decimal("0"),
    tax_inclusive: bool = False,
) -> LineAmounts:
    """Calculate one visible invoice line using the ADR 0091 rounding points."""
    quantity = _require_decimal(quantity, label="Quantity")
    unit_amount = validate_amount(unit_amount, currency, allow_negative=True)
    tax_rate = _require_decimal(tax_rate, label="Tax rate")
    if quantity <= 0:
        raise MoneyError("Quantity must be greater than zero")
    if tax_rate < 0:
        raise MoneyError("Tax rate cannot be negative")

    extended = round_amount(quantity * unit_amount, currency)
    if tax_inclusive:
        divisor = Decimal("1") + tax_rate
        tax = round_amount((extended * tax_rate) / divisor, currency)
        net = extended - tax
        total = extended
    else:
        net = extended
        tax = round_amount(net * tax_rate, currency)
        total = net + tax
    return LineAmounts(net=net, tax=tax, total=total)


def calculate_invoice(lines: Iterable[LineAmounts], currency: str) -> InvoiceAmounts:
    """Sum already-rounded visible lines; never re-round hidden precision."""
    zero = round_amount(Decimal("0"), currency)
    materialized = tuple(lines)
    for line in materialized:
        if not isinstance(line, LineAmounts):
            raise MoneyError("Invoice totals accept only calculated line amounts")
        for amount in (line.net, line.tax, line.total):
            validate_amount(amount, currency, allow_negative=True)
        if line.net + line.tax != line.total:
            raise MoneyError("Line amounts do not reconcile")
    subtotal = sum((line.net for line in materialized), start=zero)
    tax_total = sum((line.tax for line in materialized), start=zero)
    total = sum((line.total for line in materialized), start=zero)
    if subtotal + tax_total != total:
        raise MoneyError("Invoice amounts do not reconcile")
    return InvoiceAmounts(subtotal=subtotal, tax_total=tax_total, total=total)


def render_amount(value: Decimal, currency: str) -> str:
    """Return a fixed-minor-unit decimal string suitable for JSON and artifacts."""
    validated = validate_amount(value, currency, allow_negative=True)
    return f"{validated:.{minor_unit(currency)}f}"
