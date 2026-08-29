import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from apps.core.billing import create_tax_rate_version
from apps.core.models import TaxRate, Tenant, TenantBillingProfile
from apps.core.rls_contract import RUNTIME_ROLE


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Billing foundation MSP", slug=f"billing-{uuid.uuid4()}")


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def test_billing_profile_normalizes_defaults_and_reports_issue_readiness(tenant):
    profile = TenantBillingProfile(
        tenant=tenant,
        legal_name="Example Services LLC",
        address_line_1="100 Main Street",
        city="Example",
        postal_code="12345",
        country_code="us",
        billing_email="billing@example.invalid",
        default_currency="usd",
        invoice_prefix="td-inv",
    )
    profile.full_clean()
    profile.save()

    assert profile.default_currency == "USD"
    assert profile.country_code == "US"
    assert profile.invoice_prefix == "TD-INV"
    assert profile.is_issue_ready is True

    profile.default_currency = "ZZZ"
    with pytest.raises(ValidationError, match="supported ISO 4217"):
        profile.full_clean()

    profile.refresh_from_db()
    profile.legal_name = ""
    assert profile.is_issue_ready is False


@pytest.mark.django_db(transaction=True)
def test_billing_profile_database_guards_reject_invalid_direct_writes(tenant):
    profile = TenantBillingProfile.objects.create(tenant=tenant)

    with pytest.raises(DatabaseError, match="currency invalid"), transaction.atomic():
        TenantBillingProfile.objects.filter(pk=profile.pk).update(default_currency="usd")
    with pytest.raises(DatabaseError, match="country invalid"), transaction.atomic():
        TenantBillingProfile.objects.filter(pk=profile.pk).update(country_code="u1")
    with pytest.raises(DatabaseError, match="invoice prefix invalid"), transaction.atomic():
        TenantBillingProfile.objects.filter(pk=profile.pk).update(invoice_prefix="invoice 1")


@pytest.mark.django_db(transaction=True)
def test_tax_rate_changes_create_versions_and_database_rejects_mutation(tenant):
    first = create_tax_rate_version(
        tenant=tenant,
        name="Sales tax",
        rate=Decimal("0.082500"),
        inclusive=False,
        effective_from=date(2026, 1, 1),
    )
    second = create_tax_rate_version(
        tenant=tenant,
        previous=first,
        name="Sales tax",
        rate=Decimal("0.087500"),
        inclusive=False,
        effective_from=date(2027, 1, 1),
    )

    assert second.series_id == first.series_id
    assert second.version == 2
    with pytest.raises(ValidationError, match="immutable"):
        second.save()
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        TaxRate.objects.filter(pk=first.pk).update(rate=Decimal("0.090000"))
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        TaxRate.objects.filter(pk=first.pk).delete()


@pytest.mark.django_db(transaction=True)
def test_billing_foundation_scoped_managers_and_forced_rls_deny_cross_tenant_access():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    first = Tenant.objects.create(name="First billing tenant", slug=f"billing-first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second billing tenant", slug=f"billing-second-{uuid.uuid4()}")
    first_profile = TenantBillingProfile.objects.create(tenant=first, legal_name="First issuer")
    TenantBillingProfile.objects.create(tenant=second, legal_name="Second issuer")
    first_rate = create_tax_rate_version(
        tenant=first,
        name="First sales tax",
        rate=Decimal("0.050000"),
        inclusive=False,
        effective_from=date(2026, 1, 1),
    )
    second_rate = create_tax_rate_version(
        tenant=second,
        name="Second sales tax",
        rate=Decimal("0.060000"),
        inclusive=False,
        effective_from=date(2026, 1, 1),
    )

    assert list(TenantBillingProfile.scoped.for_tenant(first)) == [first_profile]
    assert list(TaxRate.scoped.for_tenant(first)) == [first_rate]

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(first.id)])
        cursor.execute("SELECT id FROM core_tenantbillingprofile")
        assert cursor.fetchall() == [(first_profile.id,)]
        cursor.execute("SELECT id FROM core_taxrate")
        assert cursor.fetchall() == [(first_rate.id,)]
        cursor.execute("UPDATE core_taxrate SET name = 'forged' WHERE id = %s", [second_rate.id])
        assert cursor.rowcount == 0
        runtime.rollback()

    with pytest.raises(ValueError, match="selected tenant"):
        create_tax_rate_version(
            tenant=first,
            previous=second_rate,
            name="Forged cross-tenant rate",
            rate=Decimal("0.070000"),
            inclusive=False,
            effective_from=date(2027, 1, 1),
        )
