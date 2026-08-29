from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import TaxRate, Tenant


@transaction.atomic
def create_tax_rate_version(
    *,
    tenant: Tenant,
    name: str,
    rate: Decimal,
    inclusive: bool,
    effective_from: date,
    effective_to: date | None = None,
    previous: TaxRate | None = None,
) -> TaxRate:
    """Create an immutable tax-rate version, serializing updates to one series."""
    series_id = None
    version = 1
    if previous is not None:
        if previous.tenant_id != tenant.id:
            raise ValueError("Previous tax rate must belong to the selected tenant")
        latest = (
            TaxRate.objects.select_for_update()
            .filter(tenant=tenant, series_id=previous.series_id)
            .order_by("-version")
            .first()
        )
        if latest is None:
            raise ValueError("Previous tax rate series does not exist")
        series_id = latest.series_id
        version = latest.version + 1

    tax_rate = TaxRate(
        tenant=tenant,
        version=version,
        name=name,
        rate=rate,
        inclusive=inclusive,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    if series_id is not None:
        tax_rate.series_id = series_id
    tax_rate.full_clean()
    tax_rate.save()
    return tax_rate
