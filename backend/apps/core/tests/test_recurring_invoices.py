import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import PermissionDenied

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.commercial import create_contract, create_cost, update_cost
from apps.core.invoice_recurrence import RecurrenceError
from apps.core.invoicing import InvoiceError, delete_invoice, delete_line
from apps.core.models import (
    ContractCost,
    Entity,
    InstallationState,
    Invoice,
    InvoiceLine,
    RecurringInvoicePeriod,
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
)
from apps.core.organizations import create_organization
from apps.core.recurring_invoices import (
    enroll_recurring_schedule,
    generate_recurring_draft,
    recurring_source_digest,
)


@pytest.fixture
def setup(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Recurring MSP",
        owner_email="recurring@example.invalid",
        owner_display_name="Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(installation.owner, generate_totp_secret())

    def organization(name, classification):
        result = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.pk,
            name=name,
            legal_name=name,
            website="https://example.invalid",
            classifications=[classification],
        )
        result.access_mode = "all_authorized"
        result.save(update_fields=("access_mode", "updated_at"))
        return result

    client = organization("Billing client", "client")
    sibling = organization("Sibling client", "client")
    supplier = organization("Provider", "vendor")
    contract = create_contract(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.pk,
        values={
            "name": "Service contract",
            "provider_id": supplier.entity_id,
            "kind": "service",
            "status": "active",
            "starts_on": date(2025, 1, 1),
            "ends_on": date(2025, 12, 31),
        },
    )
    create_cost(
        contract=contract,
        actor_id=installation.owner.pk,
        values={
            "label": "Provider fee",
            "amount": Decimal("20.00"),
            "quantity": Decimal("1.000"),
            "currency": "USD",
            "billing_interval": "monthly",
        },
    )
    cost = ContractCost.objects.get(contract=contract)
    return installation, client, sibling, contract, cost


def enroll(setup, **overrides):
    installation, client, _, _, cost = setup
    values = dict(
        user=installation.owner,
        organization=client,
        cost_id=cost.pk,
        expected_source_digest=recurring_source_digest(user=installation.owner, organization=client, cost_id=cost.pk),
        anchor=date(2025, 1, 1),
        ends_on=date(2025, 12, 31),
        description="Approved client service",
        unit_amount=Decimal("75.00"),
        quantity=Decimal("2.000"),
        currency="USD",
        due_days=30,
    )
    values.update(overrides)
    return enroll_recurring_schedule(**values)


def generate(setup, schedule, starts_on=date(2025, 1, 1), **overrides):
    installation, client, _, _, _ = setup
    values = dict(
        user=installation.owner,
        organization=client,
        schedule_id=schedule.pk,
        starts_on=starts_on,
        as_of=date(2025, 12, 31),
    )
    values.update(overrides)
    return generate_recurring_draft(**values)


@pytest.mark.django_db
def test_approved_sell_terms_generate_separate_drafts_and_retries_keep_one_claim(setup):
    schedule = enroll(setup)
    first = generate(setup, schedule)
    second = generate(setup, schedule, date(2025, 2, 1))
    assert first.pk == generate(setup, schedule).pk
    assert first.invoice_id != second.invoice_id
    assert Invoice.objects.count() == 2
    assert RecurringInvoicePeriod.objects.count() == 2
    assert first.invoice.state == "draft" and first.invoice.number == ""
    assert first.invoice.due_date == date(2025, 1, 31)
    assert first.line.unit_amount == Decimal("75.00")
    assert first.line.quantity == Decimal("2.000")
    assert first.line.contract_cost_id == setup[-1].pk
    assert first.terms.source_snapshot["amount"] == "20.00"
    assert first.ends_before == date(2025, 2, 1)
    with pytest.raises(RecurrenceError, match="already has"):
        enroll(setup)


@pytest.mark.django_db
def test_source_edit_invalidates_enrollment_and_future_generation_without_rewriting_history(setup):
    installation, client, _, contract, cost = setup
    digest = recurring_source_digest(user=installation.owner, organization=client, cost_id=cost.pk)
    schedule = enroll(setup)
    first = generate(setup, schedule)
    update_cost(contract=contract, cost_id=cost.pk, actor_id=installation.owner.pk, values={"amount": Decimal("25.00")})
    with pytest.raises(RecurrenceError, match="source terms changed"):
        enroll(setup, expected_source_digest=digest)
    with pytest.raises(RecurrenceError, match="source terms changed"):
        generate(setup, schedule, date(2025, 2, 1))
    assert generate(setup, schedule).pk == first.pk
    first.terms.refresh_from_db()
    assert first.terms.source_snapshot["amount"] == "20.00"


@pytest.mark.django_db
def test_failed_line_creation_rolls_back_draft_entity_and_period_claim(setup, monkeypatch):
    schedule = enroll(setup)
    before = Entity.objects.count()

    def fail(**kwargs):
        raise RuntimeError("synthetic line failure")

    monkeypatch.setattr("apps.core.recurring_invoices.create_line", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        generate(setup, schedule)
    assert Invoice.objects.count() == InvoiceLine.objects.count() == RecurringInvoicePeriod.objects.count() == 0
    assert Entity.objects.count() == before


@pytest.mark.django_db
def test_generated_draft_and_line_cannot_be_deleted_or_release_the_period(setup):
    schedule = enroll(setup)
    claim = generate(setup, schedule)
    with pytest.raises(InvoiceError, match="cannot be deleted"):
        delete_invoice(invoice=claim.invoice, actor_id=setup[0].owner.pk)
    with pytest.raises(InvoiceError, match="cannot be deleted"):
        delete_line(line=claim.line, actor_id=setup[0].owner.pk)
    with pytest.raises(ProtectedError):
        claim.invoice.delete()
    with pytest.raises(ProtectedError):
        claim.line.delete()
    assert generate(setup, schedule).pk == claim.pk


@pytest.mark.django_db
def test_guards_retain_calendar_terms_and_claims_below_the_service(setup):
    schedule = enroll(setup)
    claim = generate(setup, schedule)
    attempts = [
        lambda: RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(anchor=date(2025, 1, 2)),
        lambda: RecurringInvoiceTerms.objects.filter(pk=claim.terms_id).update(unit_amount=Decimal("1.00")),
        lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).update(starts_on=date(2025, 1, 2)),
        lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).delete(),
    ]
    for attempt in attempts:
        with pytest.raises(DatabaseError), transaction.atomic():
            attempt()
    RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(enabled=False)
    assert generate(setup, schedule).pk == claim.pk
    with pytest.raises(RecurrenceError, match="disabled"):
        generate(setup, schedule, date(2025, 2, 1))


@pytest.mark.django_db
def test_client_scope_and_read_only_membership_are_enforced_before_data_is_returned(setup):
    installation, client, sibling, _, cost = setup
    schedule = enroll(setup)
    with pytest.raises(RecurrenceError, match="unavailable"):
        generate(setup, schedule, organization=sibling)
    with pytest.raises(RecurrenceError, match="unavailable"):
        recurring_source_digest(user=installation.owner, organization=sibling, cost_id=cost.pk)
    reader = User.objects.create_user(email="reader@example.invalid", password=secrets.token_urlsafe(32))
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    with pytest.raises(PermissionDenied):
        generate(setup, schedule, user=reader)
    with pytest.raises(PermissionDenied):
        enroll(setup, user=reader)
    assert RecurringInvoicePeriod.objects.count() == 0
    with pytest.raises(DatabaseError), transaction.atomic():
        RecurringInvoiceTerms.objects.create(
            tenant=installation.tenant,
            organization=sibling,
            schedule=schedule,
            description="Wrong scope",
            quantity=1,
            unit_amount=1,
            currency="USD",
            due_days=1,
            source_digest="a" * 64,
            source_snapshot={},
            approved_by=installation.owner,
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"anchor": date(2024, 12, 1)},
        {"ends_on": None},
        {"ends_on": date(2026, 1, 1)},
        {"currency": "EUR"},
        {"expected_source_digest": "0" * 64},
    ],
)
def test_enrollment_refuses_invalid_dates_currency_and_stale_source(setup, overrides):
    with pytest.raises(RecurrenceError):
        enroll(setup, **overrides)
    assert RecurringInvoiceSchedule.objects.count() == RecurringInvoiceTerms.objects.count() == 0


@pytest.mark.django_db
def test_partial_future_unaligned_and_inactive_periods_fail_without_drafts(setup):
    schedule = enroll(setup, ends_on=date(2025, 2, 10))
    with pytest.raises(RecurrenceError, match="Partial"):
        generate(setup, schedule, date(2025, 2, 1))
    with pytest.raises(RecurrenceError, match="period start"):
        generate(setup, schedule, date(2025, 1, 2))
    with pytest.raises(RecurrenceError, match="Future"):
        generate(setup, schedule, as_of=date(2024, 12, 31))
    setup[3].status = "terminated"
    setup[3].save(update_fields=("status", "updated_at"))
    with pytest.raises(RecurrenceError, match="active"):
        generate(setup, schedule)
    assert Invoice.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_generation_returns_one_committed_invoice(setup):
    schedule = enroll(setup)
    user_id, organization_id = setup[0].owner.pk, setup[1].pk

    def run(_index):
        close_old_connections()
        try:
            from apps.core.models import Organization

            return generate_recurring_draft(
                user=User.objects.get(pk=user_id),
                organization=Organization.objects.get(pk=organization_id),
                schedule_id=schedule.pk,
                starts_on=date(2025, 1, 1),
                as_of=date(2025, 2, 1),
            ).invoice_id
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as executor:
        invoice_ids = list(executor.map(run, range(4)))
    assert len(set(invoice_ids)) == Invoice.objects.count() == RecurringInvoicePeriod.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_guard_rollback_reapply_preserves_records_and_restores_rls(setup):
    schedule = enroll(setup)
    claim = generate(setup, schedule)
    migration = import_module("apps.core.migrations.0148_recurring_invoice_guards")
    try:
        with connection.cursor() as cursor:
            cursor.execute(migration.REVERSE_SQL)
            cursor.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname='core_recurringinvoiceperiod'")
            assert cursor.fetchone() == (False,)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(migration.FORWARD_SQL)
    claim.refresh_from_db()
    assert claim.invoice.state == "draft" and claim.terms.unit_amount == Decimal("75.00")
    call_command("migrate", interactive=False, verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname='core_recurringinvoiceperiod'"
        )
        assert cursor.fetchone() == (True, True)


@pytest.mark.django_db(transaction=True)
def test_runtime_role_can_read_own_claims_but_cannot_see_or_update_sibling_claims(setup):
    from apps.core.tests.test_runtime_rls import _bind, _runtime_connection

    schedule = enroll(setup)
    claim = generate(setup, schedule)
    installation, client, sibling, _, _ = setup
    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, installation.tenant.pk, "organization", client.pk, installation.owner.pk)
        cursor.execute("SELECT id FROM core_recurringinvoiceperiod")
        assert cursor.fetchall() == [(claim.pk,)]
        runtime.rollback()
        _bind(cursor, installation.tenant.pk, "organization", sibling.pk, installation.owner.pk)
        for table in ("core_recurringinvoiceschedule", "core_recurringinvoiceterms", "core_recurringinvoiceperiod"):
            from psycopg import sql

            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            assert cursor.fetchone() == (0,)
        cursor.execute("UPDATE core_recurringinvoiceschedule SET enabled=false WHERE id=%s", [schedule.pk])
        assert cursor.rowcount == 0
        runtime.rollback()


@pytest.mark.django_db
def test_approved_tax_version_must_cover_the_generated_period(setup):
    from apps.core.models import TaxRate

    tax = TaxRate.objects.create(
        tenant=setup[0].tenant,
        name="Reviewed rate",
        rate=Decimal("0.075000"),
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 1, 31),
        inclusive=False,
    )
    schedule = enroll(setup, tax_rate_id=tax.pk)
    claim = generate(setup, schedule)
    assert claim.line.tax_rate_value == Decimal("0.075000")
    with pytest.raises(RecurrenceError, match="tax version"):
        generate(setup, schedule, date(2025, 2, 1))
    assert Invoice.objects.count() == 1


@pytest.mark.django_db
def test_mfa_is_required_even_for_an_owner_with_source_access(setup):
    from allauth.mfa.models import Authenticator

    schedule = enroll(setup)
    Authenticator.objects.filter(user=setup[0].owner).delete()
    with pytest.raises(PermissionDenied):
        generate(setup, schedule)
    assert Invoice.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_upgrade_from_previous_schema_preserves_existing_invoice_and_adds_enrollment(setup):
    from apps.core.invoicing import create_invoice, create_line

    installation, client, _, _, _ = setup
    invoice = create_invoice(
        tenant=installation.tenant,
        organization=client,
        actor_id=installation.owner.pk,
        currency="USD",
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
    )
    line = create_line(
        invoice=invoice,
        actor_id=installation.owner.pk,
        values={
            "description": "Pre-existing draft",
            "quantity": Decimal("1"),
            "unit_amount": Decimal("15.00"),
        },
    )
    try:
        call_command("migrate", "core", "0146", interactive=False, verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('core_recurringinvoiceperiod')")
            assert cursor.fetchone() == (None,)
    finally:
        call_command("migrate", interactive=False, verbosity=0)
    invoice.refresh_from_db()
    line.refresh_from_db()
    assert invoice.state == "draft" and line.unit_amount == Decimal("15.00")
    assert generate(setup, enroll(setup)).invoice_id != invoice.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("interval", "anchor", "period_start", "period_end"),
    [
        ("monthly", date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31)),
        ("quarterly", date(2025, 1, 31), date(2025, 4, 30), date(2025, 7, 31)),
        ("annual", date(2024, 2, 29), date(2025, 2, 28), date(2026, 2, 28)),
    ],
)
def test_calendar_and_database_guards_agree_at_clamped_month_boundaries(
    setup, interval, anchor, period_start, period_end
):
    contract, cost = setup[3], setup[4]
    contract.starts_on, contract.ends_on = date(2024, 1, 1), None
    contract.save(update_fields=("starts_on", "ends_on", "updated_at"))
    update_cost(contract=contract, cost_id=cost.pk, actor_id=setup[0].owner.pk, values={"billing_interval": interval})
    schedule = enroll(setup, anchor=anchor, ends_on=None)
    claim = generate(setup, schedule, period_start)
    assert claim.starts_on == period_start and claim.ends_before == period_end


@pytest.mark.django_db
def test_foreign_tenant_cannot_reuse_enrollment_or_terms(setup):
    from apps.core.models import Organization, Tenant

    schedule = enroll(setup)
    foreign_tenant = Tenant.objects.create(name="Other MSP", slug="recurrence-other-msp")
    anchor = Entity.objects.create_owned(tenant=foreign_tenant, entity_type="organization", display_name="Other client")
    foreign_client = Organization.objects.create(tenant=foreign_tenant, entity=anchor)
    with pytest.raises(PermissionDenied):
        generate(setup, schedule, organization=foreign_client)
    with pytest.raises(DatabaseError), transaction.atomic():
        RecurringInvoiceTerms.objects.create(
            tenant=foreign_tenant,
            organization=foreign_client,
            schedule=schedule,
            description="Foreign terms",
            quantity=1,
            unit_amount=1,
            currency="USD",
            due_days=30,
            source_digest="b" * 64,
            source_snapshot={},
            approved_by=setup[0].owner,
        )
    assert Invoice.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_stops_retain_one_audit_event(setup):
    from apps.core.models import AuditEvent, Organization
    from apps.core.recurring_invoices import stop_recurring_schedule

    schedule = enroll(setup)
    user_id, organization_id = setup[0].owner.pk, setup[1].pk

    def stop(index):
        close_old_connections()
        try:
            return stop_recurring_schedule(
                user=User.objects.get(pk=user_id),
                organization=Organization.objects.get(pk=organization_id),
                schedule_id=schedule.pk,
                reason=f"Operator stop {index}",
            ).enabled
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(stop, range(4))) == [False] * 4
    assert AuditEvent.objects.filter(action="invoice.recurring_stopped").count() == 1
    assert Invoice.objects.count() == 0
    with pytest.raises(RecurrenceError, match="disabled"):
        generate(setup, schedule)
