"""Runtime-role recovery assertions; expected identities are stored outside the dump."""

import base64
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.core import serializers
from django.db import DatabaseError, connection, transaction

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.billing import create_tax_rate_version
from apps.core.commercial import create_contract, create_cost
from apps.core.invoice_recurrence import RecurrenceError
from apps.core.invoicing import (
    configure_issue_settings,
    create_invoice,
    create_invoice_from_issued,
    create_line,
    invoice_lifecycle,
    issue_invoice,
    void_invoice,
    withdraw_recurring_draft,
)
from apps.core.models import (
    AuditEvent,
    CommercialContract,
    ContractCost,
    InstallationState,
    Invoice,
    InvoiceArtifact,
    InvoiceDocumentKind,
    InvoiceEventType,
    InvoiceLifecycleEvent,
    InvoiceLine,
    InvoiceNumberSeries,
    InvoiceSourceKind,
    Organization,
    RecurringInvoicePeriod,
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
    RecurringInvoiceWithdrawal,
    TaxRate,
    TenantBillingProfile,
)
from apps.core.organizations import create_organization
from apps.core.recurring_invoice_preview import (
    apply_recurring_preview,
    discover_recurring_periods,
    preview_recurring_drafts,
)
from apps.core.recurring_invoices import (
    amend_recurring_terms,
    enroll_recurring_schedule,
    generate_recurring_draft,
    recurring_source_digest,
    stop_recurring_schedule,
)
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
    RecurringInvoiceWithdrawal,
    Invoice,
    InvoiceLine,
    InvoiceArtifact,
    InvoiceLifecycleEvent,
    InvoiceNumberSeries,
    TenantBillingProfile,
)
RECURRING_MODELS = (
    RecurringInvoiceSchedule,
    RecurringInvoiceTerms,
    RecurringInvoicePeriod,
    RecurringInvoiceWithdrawal,
)
ANCHOR = date(2025, 1, 31)
STOP_REASON = "Client ended the recurring service"
WITHDRAWAL_REASON = "Client cancelled this recovered billing period"
VOID_REASON = "Duplicate invoice retained for audit"


def snapshot():
    records = [record for model in MODELS for record in model.objects.order_by("pk")]
    return json.loads(serializers.serialize("json", records))


def audit_snapshot(event):
    return {
        "id": str(event.pk),
        "tenant_id": str(event.tenant_id),
        "actor_id": str(event.actor_id),
        "action": event.action,
        "entity_id": str(event.entity_id),
        "metadata": event.metadata,
        "occurred_at": event.occurred_at.isoformat(),
    }


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


def create_issued_invoice(owner, tenant, client, *, reference, amount):
    invoice = create_invoice(
        tenant=tenant,
        organization=client,
        actor_id=owner.pk,
        currency="USD",
        invoice_date=date(2025, 1, 15),
        due_date=date(2025, 2, 14),
        reference=reference,
    )
    create_line(
        invoice=invoice,
        actor_id=owner.pk,
        values={
            "description": f"Recovery evidence for {reference}",
            "quantity": "1.000",
            "unit": "service",
            "unit_amount": amount,
        },
    )
    return issue_invoice(invoice=invoice, actor_id=owner.pk)


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
        client.billing_contact_name = "Recovery Accounts"
        client.billing_email = "recovery-accounts@example.invalid"
        client.billing_address_line_1 = "100 Recovery Way"
        client.billing_city = "Austin"
        client.billing_region = "TX"
        client.billing_postal_code = "78701"
        client.billing_country_code = "US"
        client.save(
            update_fields=(
                "billing_contact_name",
                "billing_email",
                "billing_address_line_1",
                "billing_city",
                "billing_region",
                "billing_postal_code",
                "billing_country_code",
                "updated_at",
            )
        )
        configure_issue_settings(
            tenant=result.tenant,
            actor_id=result.owner.pk,
            values={
                "legal_name": "Recurring Recovery MSP, LLC",
                "address_line_1": "200 Restore Street",
                "city": "Austin",
                "region": "TX",
                "postal_code": "78701",
                "country_code": "US",
                "billing_email": "billing-recovery@example.invalid",
                "payment_instructions": "Include the document number.",
                "default_currency": "USD",
                "payment_terms_days": 30,
                "invoice_prefix": "INV",
                "credit_note_prefix": "CR",
                "invoice_date_component": "none",
                "invoice_separator": "-",
                "invoice_sequence_digits": 6,
                "invoice_reset_period": "never",
            },
        )
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
        first_terms = RecurringInvoiceTerms.objects.get(schedule=schedule, version=1)
        amended_terms = amend_recurring_terms(
            user=result.owner,
            organization=client,
            schedule_id=schedule.pk,
            expected_terms_id=first_terms.pk,
            expected_source_digest=recurring_source_digest(user=result.owner, organization=client, cost_id=cost.pk),
            effective_from=date(2025, 2, 28),
            business_date=date(2025, 2, 1),
            description="Amended recovery support",
            quantity=Decimal("3.000"),
            unit_amount=Decimal("80.00"),
            currency="USD",
            due_days=45,
            tax_rate_id=tax.pk,
        )
        withdrawal = withdraw_recurring_draft(
            invoice=claim.invoice,
            actor_id=result.owner.pk,
            reason=WITHDRAWAL_REASON,
        )
        amendment_event = AuditEvent.objects.get(
            action="invoice.recurring_terms_amended", metadata__terms_id=str(amended_terms.pk)
        )
        withdrawal_event = AuditEvent.objects.get(
            action="invoice.recurring_draft_withdrawn", entity_id=claim.invoice.entity_id
        )

        stopped_contract = create_contract(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.pk,
            values={
                "name": "Stopped recovery support",
                "provider_id": supplier.entity_id,
                "kind": "service",
                "status": "active",
                "starts_on": date(2025, 1, 1),
                "ends_on": date(2025, 12, 31),
            },
        )
        create_cost(
            contract=stopped_contract,
            actor_id=result.owner.pk,
            values={
                "label": "Stopped supplier fee",
                "amount": Decimal("35.00"),
                "quantity": Decimal("1.000"),
                "currency": "USD",
                "billing_interval": "monthly",
            },
        )
        stopped_cost = ContractCost.objects.get(contract=stopped_contract)
        stopped_schedule = enroll_recurring_schedule(
            user=result.owner,
            organization=client,
            cost_id=stopped_cost.pk,
            expected_source_digest=recurring_source_digest(
                user=result.owner, organization=client, cost_id=stopped_cost.pk
            ),
            anchor=ANCHOR,
            ends_on=date(2025, 12, 31),
            description="Approved stopped recovery support",
            quantity=Decimal("1.000"),
            unit_amount=Decimal("90.00"),
            currency="USD",
            due_days=14,
        )
        stopped_claim = review_and_apply(result.owner, client, stopped_schedule, ANCHOR)
        stop_recurring_schedule(
            user=result.owner,
            organization=client,
            schedule_id=stopped_schedule.pk,
            reason=STOP_REASON,
        )
        stop_event = AuditEvent.objects.get(
            action="invoice.recurring_stopped", metadata__schedule_id=str(stopped_schedule.pk)
        )
        credited_source = create_issued_invoice(
            result.owner,
            result.tenant,
            client,
            reference="RECOVERY-CREDIT",
            amount="125.00",
        )
        credit_note = create_invoice_from_issued(
            source=credited_source,
            actor_id=result.owner.pk,
            source_kind=InvoiceSourceKind.CREDIT_NOTE,
        )
        credit_note.reference = "Recovery service adjustment"
        credit_note.save(update_fields=("reference", "updated_at"))
        credit_note = issue_invoice(invoice=credit_note, actor_id=result.owner.pk)
        voided_invoice = create_issued_invoice(
            result.owner,
            result.tenant,
            client,
            reference="RECOVERY-VOID",
            amount="75.00",
        )
        voided_invoice = void_invoice(
            invoice=voided_invoice,
            actor_id=result.owner.pk,
            reason=VOID_REASON,
        )
        MANIFEST.write_text(
            json.dumps(
                {
                    "owner": str(result.owner.pk),
                    "client": str(client.pk),
                    "sibling": str(sibling.pk),
                    "schedule": str(schedule.pk),
                    "claim": str(claim.pk),
                    "amended_terms": str(amended_terms.pk),
                    "withdrawal": str(withdrawal.pk),
                    "amendment_event": audit_snapshot(amendment_event),
                    "withdrawal_event": audit_snapshot(withdrawal_event),
                    "stopped_schedule": str(stopped_schedule.pk),
                    "stopped_claim": str(stopped_claim.pk),
                    "stop_event": audit_snapshot(stop_event),
                    "credited_source": str(credited_source.pk),
                    "credit_note": str(credit_note.pk),
                    "voided_invoice": str(voided_invoice.pk),
                    "snapshot": snapshot(),
                }
            )
        )
    print("Created amended, withdrawn, active, and stopped recurring history with an external identity manifest.")


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
        amended_terms = RecurringInvoiceTerms.objects.get(pk=expected["amended_terms"])
        withdrawal = RecurringInvoiceWithdrawal.objects.select_related("period__invoice").get(pk=expected["withdrawal"])
        stopped_schedule = RecurringInvoiceSchedule.objects.get(pk=expected["stopped_schedule"])
        stopped_claim = RecurringInvoicePeriod.objects.select_related("line", "invoice", "terms").get(
            pk=expected["stopped_claim"]
        )
        credited_source = Invoice.objects.prefetch_related("lifecycle_events__related_invoice").get(
            pk=expected["credited_source"]
        )
        credit_note = Invoice.objects.prefetch_related("lifecycle_events").get(pk=expected["credit_note"])
        voided_invoice = Invoice.objects.prefetch_related("lifecycle_events").get(pk=expected["voided_invoice"])
        stop_event = AuditEvent.objects.get(pk=expected["stop_event"]["id"])
        amendment_event = AuditEvent.objects.get(pk=expected["amendment_event"]["id"])
        withdrawal_event = AuditEvent.objects.get(pk=expected["withdrawal_event"]["id"])
        assert audit_snapshot(stop_event) == expected["stop_event"]
        assert audit_snapshot(amendment_event) == expected["amendment_event"]
        assert audit_snapshot(withdrawal_event) == expected["withdrawal_event"]
        assert amended_terms.version == 2 and amended_terms.effective_from == date(2025, 2, 28)
        assert amended_terms.quantity == Decimal("3.000") and amended_terms.unit_amount == Decimal("80.0000")
        assert amended_terms.source_snapshot["amount"] == "20.00"
        assert withdrawal.period_id == claim.pk and withdrawal.reason == WITHDRAWAL_REASON
        assert withdrawal.withdrawn_by_id == owner.pk
        assert not stopped_schedule.enabled
        assert stopped_claim.line.unit_amount == Decimal("90.0000")
        assert stopped_claim.terms.source_snapshot["amount"] == "35.00"
        assert stopped_claim.invoice.state == "draft" and stopped_claim.invoice.number == ""
        assert claim.line.unit_amount == Decimal("75.0000") and claim.line.quantity == Decimal("2.000")
        assert claim.terms.source_snapshot["amount"] == "20.00"
        assert claim.line.tax_rate_value == Decimal("0.100000")
        assert claim.invoice.state == "draft" and claim.invoice.number == "" and claim.invoice.issued_at is None
        assert credited_source.number == "INV-000001"
        assert credit_note.number == "CR-000001"
        assert credit_note.document_kind == InvoiceDocumentKind.CREDIT_NOTE
        assert credit_note.source_invoice_id == credited_source.pk
        assert invoice_lifecycle(credited_source).state == "credited"
        assert invoice_lifecycle(credited_source).balance_amount == Decimal("0.00")
        assert invoice_lifecycle(credit_note).balance_amount == Decimal("0.00")
        assert voided_invoice.number == "INV-000002"
        assert invoice_lifecycle(voided_invoice).state == "voided"
        assert voided_invoice.lifecycle_events.get(event_type=InvoiceEventType.VOIDED).note == VOID_REASON
        assert InvoiceArtifact.objects.count() == 3
        assert InvoiceLifecycleEvent.objects.count() == 5
        assert InvoiceNumberSeries.objects.get(prefix="INV").next_number == 3
        assert InvoiceNumberSeries.objects.get(prefix="CR").next_number == 2
        for invoice in (credited_source, credit_note, voided_invoice):
            artifact = InvoiceArtifact.objects.get(invoice=invoice)
            payload = Path(artifact.file.path).read_bytes()
            assert payload.startswith(b"%PDF-")
            assert artifact.size == len(payload)
            assert artifact.checksum == hashlib.sha256(payload).hexdigest()
            Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(invoice.public_key)).verify(
                base64.urlsafe_b64decode(invoice.signature), bytes.fromhex(invoice.content_digest)
            )
        for attempt in (
            lambda: RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(anchor=date(2025, 2, 1)),
            lambda: RecurringInvoiceTerms.objects.filter(pk=claim.terms_id).update(unit_amount=Decimal("1.00")),
            lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).update(starts_on=date(2025, 2, 1)),
            lambda: RecurringInvoicePeriod.objects.filter(pk=claim.pk).delete(),
            lambda: RecurringInvoiceWithdrawal.objects.filter(pk=withdrawal.pk).update(reason="rewritten"),
            lambda: RecurringInvoiceWithdrawal.objects.filter(pk=withdrawal.pk).delete(),
            lambda: Invoice.objects.filter(pk=claim.invoice_id).update(notes="rewritten"),
            lambda: InvoiceLine.objects.filter(pk=claim.line_id).update(description="rewritten"),
            lambda: Invoice.objects.filter(pk=credited_source.pk).update(notes="rewritten"),
            lambda: InvoiceLine.objects.filter(invoice=credit_note).delete(),
            lambda: InvoiceArtifact.objects.filter(invoice=voided_invoice).update(size=1),
            lambda: InvoiceLifecycleEvent.objects.filter(
                invoice=voided_invoice, event_type=InvoiceEventType.VOIDED
            ).delete(),
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
        stopped_periods = discover_recurring_periods(
            user=owner,
            organization=client,
            schedule_id=stopped_schedule.pk,
            due_from=ANCHOR,
            as_of=date(2025, 2, 28),
        )["periods"]
        assert stopped_periods[0]["invoice_entity_id"] == str(stopped_claim.invoice.entity_id)
        assert all(item["blocked_reason"] == "disabled" and not item["can_generate"] for item in stopped_periods)
        retained_stopped = generate_recurring_draft(
            user=owner,
            organization=client,
            schedule_id=stopped_schedule.pk,
            starts_on=ANCHOR,
            as_of=ANCHOR,
        )
        assert retained_stopped.pk == stopped_claim.pk and retained_stopped.invoice_id == stopped_claim.invoice_id
        try:
            generate_recurring_draft(
                user=owner,
                organization=client,
                schedule_id=stopped_schedule.pk,
                starts_on=date(2025, 2, 28),
                as_of=date(2025, 2, 28),
            )
        except RecurrenceError as exc:
            assert str(exc) == "This recurring schedule is disabled"
        else:
            raise AssertionError("Restored stopped schedule generated a new draft")
        stop_recurring_schedule(
            user=owner,
            organization=client,
            schedule_id=stopped_schedule.pk,
            reason="Retry must not replace retained reason",
        )
        assert (
            AuditEvent.objects.filter(
                action="invoice.recurring_stopped", metadata__schedule_id=str(stopped_schedule.pk)
            ).count()
            == 1
        )
        assert audit_snapshot(AuditEvent.objects.get(pk=stop_event.pk)) == expected["stop_event"]
        assert snapshot() == expected["snapshot"], "Stopped-schedule checks changed the restored baseline"
        # Restore does not rely on an old signed token: obtain a fresh authorized review.
        for _ in range(2):
            retained = review_and_apply(owner, client, schedule, ANCHOR)
            assert retained.pk == claim.pk and retained.invoice_id == claim.invoice_id
        assert snapshot() == expected["snapshot"], "Retry rewrote or duplicated retained billing records"
        following = review_and_apply(owner, client, schedule, date(2025, 2, 28))
        assert following.ends_before == date(2025, 3, 31), "Restore lost the original month-end anchor"
        assert following.invoice_id != claim.invoice_id
        assert following.terms_id == amended_terms.pk
        assert following.line.quantity == Decimal("3.000")
        assert following.line.unit_amount == Decimal("80.0000")
        assert review_and_apply(owner, client, schedule, date(2025, 2, 28)).pk == following.pk
        assert RecurringInvoicePeriod.objects.count() == 3
        assert Invoice.objects.count() == InvoiceLine.objects.count() == 6
        assert InvoiceArtifact.objects.count() == 3
        assert InvoiceLifecycleEvent.objects.count() == 5
        assert RecurringInvoiceWithdrawal.objects.count() == 1
    print(
        "Verified exact restoration, amendments, withdrawal retention, stopped-schedule history, invoice "
        "corrections, signed artifacts, forced RLS, safe retries, and active continuation."
    )


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
