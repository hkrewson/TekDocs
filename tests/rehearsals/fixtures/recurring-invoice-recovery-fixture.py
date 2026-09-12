"""Runtime-role recovery assertions; expected identities are stored outside the dump."""

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import serializers
from django.db import DatabaseError, connection, transaction

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.billing import create_tax_rate_version
from apps.core.commercial import create_contract, create_cost
from apps.core.models import (
    CommercialContract,
    ContractCost,
    InstallationState,
    Invoice,
    InvoiceArtifact,
    InvoiceLifecycleEvent,
    InvoiceLine,
    Organization,
    RecurringInvoicePeriod,
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
    TaxRate,
)
from apps.core.organizations import create_organization
from apps.core.recurring_invoice_preview import apply_recurring_preview, preview_recurring_drafts
from apps.core.recurring_invoices import enroll_recurring_schedule, recurring_source_digest
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope, rls_scope
from apps.core.rls_contract import RUNTIME_ROLE
from apps.core.scoping import DataScope

MANIFEST = Path("/recovery/expected.json")
MODELS = (
    CommercialContract,
    ContractCost,
    TaxRate,
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
    RecurringInvoicePeriod,
    Invoice,
    InvoiceLine,
)
RECURRING_MODELS = (RecurringInvoiceSchedule, RecurringInvoiceTerms, RecurringInvoicePeriod)
ANCHOR = date(2025, 1, 31)


def snapshot():
    records = [record for model in MODELS for record in model.objects.order_by("pk")]
    return json.loads(serializers.serialize("json", records))


def review_and_apply(owner, client, schedule, start):
    preview = preview_recurring_drafts(
        user=owner,
        organization=client,
        schedule_id=schedule.pk,
        starts_on=[start],
        as_of=start,
    )
    claims = apply_recurring_preview(
        user=owner,
        organization=client,
        schedule_id=schedule.pk,
        preview_token=preview["preview_token"],
    )
    assert len(claims) == 1
    return claims[0]


def bind(tenant, client):
    bind_local_rls_scope(DataScope.organization(tenant, client), organization_mode=OrganizationRLSMode.ORGANIZATION)


def create_fixture():
    result = bootstrap_owner(
        tenant_name="Recurring Recovery MSP",
        owner_email="recurring-recovery@example.invalid",
        owner_display_name="Recurring Recovery Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    TOTP.activate(result.owner, generate_totp_secret())
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        bind_local_rls_scope(
            DataScope.tenant(result.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=result.owner.pk,
            principal_mode=RLSPrincipalMode.USER,
        )

        def organization(name, kind):
            record = create_organization(
                tenant=result.tenant,
                actor_id=result.owner.pk,
                name=name,
                legal_name=name,
                website="",
                classifications=[kind],
            )
            record.access_mode = "all_authorized"
            record.save(update_fields=("access_mode", "updated_at"))
            return record

        client = organization("Recurring Recovery Client", "client")
        sibling = organization("Recurring Recovery Sibling", "client")
        supplier = organization("Recurring Recovery Supplier", "vendor")
        tax = create_tax_rate_version(
            tenant=result.tenant,
            name="Recovery tax",
            rate=Decimal("0.100000"),
            inclusive=False,
            effective_from=date(2025, 1, 1),
        )
        bind(result.tenant, client)
        contract = create_contract(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.pk,
            values={
                "name": "Recovery support",
                "provider_id": supplier.entity_id,
                "kind": "service",
                "status": "active",
                "starts_on": date(2025, 1, 1),
                "ends_on": date(2025, 12, 31),
            },
        )
        create_cost(
            contract=contract,
            actor_id=result.owner.pk,
            values={
                "label": "Supplier fee",
                "amount": Decimal("20.00"),
                "quantity": Decimal("1.000"),
                "currency": "USD",
                "billing_interval": "monthly",
            },
        )
        cost = ContractCost.objects.get(contract=contract)
        schedule = enroll_recurring_schedule(
            user=result.owner,
            organization=client,
            cost_id=cost.pk,
            expected_source_digest=recurring_source_digest(user=result.owner, organization=client, cost_id=cost.pk),
            anchor=ANCHOR,
            ends_on=date(2025, 12, 31),
            description="Approved recovery support",
            quantity=Decimal("2.000"),
            unit_amount=Decimal("75.00"),
            currency="USD",
            due_days=30,
            tax_rate_id=tax.pk,
        )
        claim = review_and_apply(result.owner, client, schedule, ANCHOR)
        assert claim.ends_before == date(2025, 2, 28)
        MANIFEST.write_text(
            json.dumps(
                {
                    "owner": str(result.owner.pk),
                    "client": str(client.pk),
                    "sibling": str(sibling.pk),
                    "schedule": str(schedule.pk),
                    "claim": str(claim.pk),
                    "snapshot": snapshot(),
                }
            )
        )
    print("Created approved taxed recurring draft and external identity manifest.")


def verify_fixture():
    expected = json.loads(MANIFEST.read_text())
    tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (RUNTIME_ROLE, False, False)
        for model in RECURRING_MODELS:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = %s::regclass",
                [model._meta.db_table],
            )
            assert cursor.fetchone() == (True, True)
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED):
        client = Organization.objects.get(pk=expected["client"])
        sibling = Organization.objects.get(pk=expected["sibling"])
        owner = User.objects.get(pk=expected["owner"])
        bind_local_rls_scope(
            DataScope.tenant(tenant),
            organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
            actor_user_id=owner.pk,
            principal_mode=RLSPrincipalMode.USER,
        )
        bind(tenant, client)
        assert snapshot() == expected["snapshot"], "Restored billing identities or values differ from backup"
        schedule = RecurringInvoiceSchedule.objects.get(pk=expected["schedule"])
        claim = RecurringInvoicePeriod.objects.select_related("line", "invoice", "terms").get(pk=expected["claim"])
        assert claim.line.unit_amount == Decimal("75.0000") and claim.line.quantity == Decimal("2.000")
        assert claim.terms.source_snapshot["amount"] == "20.00"
        assert claim.line.tax_rate_value == Decimal("0.100000")
        assert claim.invoice.state == "draft" and claim.invoice.number == "" and claim.invoice.issued_at is None
        assert not InvoiceArtifact.objects.exists() and not InvoiceLifecycleEvent.objects.exists()
        for attempt in (
            lambda: RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(anchor=date(2025, 2, 1)),
            lambda: RecurringInvoiceTerms.objects.filter(pk=claim.terms_id).update(unit_amount=Decimal("1.00")),
            lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).update(starts_on=date(2025, 2, 1)),
            lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).delete(),
        ):
            try:
                with transaction.atomic():
                    attempt()
            except DatabaseError:
                pass
            else:
                raise AssertionError("Restored database accepted a protected billing-history mutation")
        bind(tenant, sibling)
        for model in RECURRING_MODELS:
            assert not model.objects.exists(), "Sibling scope disclosed recurring records"
        assert RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(enabled=False) == 0
        own_scope = DataScope.organization(tenant, client)
        bind_local_rls_scope(
            DataScope(tenant_id=uuid4(), workspace_id=own_scope.workspace_id, organization_id=client.pk),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        for model in RECURRING_MODELS:
            assert not model.objects.exists(), "Wrong-tenant scope disclosed recurring records"
        bind(tenant, client)
        # Restore does not rely on an old signed token: obtain a fresh authorized review.
        for _ in range(2):
            retained = review_and_apply(owner, client, schedule, ANCHOR)
            assert retained.pk == claim.pk and retained.invoice_id == claim.invoice_id
        assert snapshot() == expected["snapshot"], "Retry rewrote or duplicated retained billing records"
        following = review_and_apply(owner, client, schedule, date(2025, 2, 28))
        assert following.ends_before == date(2025, 3, 31), "Restore lost the original month-end anchor"
        assert following.invoice_id != claim.invoice_id
        assert review_and_apply(owner, client, schedule, date(2025, 2, 28)).pk == following.pk
        assert RecurringInvoicePeriod.objects.count() == Invoice.objects.count() == InvoiceLine.objects.count() == 2
    print("Verified exact restoration, forced RLS, immutable history, safe retries, and next-period generation.")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
