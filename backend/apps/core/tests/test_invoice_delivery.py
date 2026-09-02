import secrets
from datetime import date
from decimal import Decimal

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.db import DatabaseError, transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import SensitiveField, project_authorized_fields, require_client_portal_member
from apps.core.invoicing import create_invoice, create_line, issue_invoice
from apps.core.models import (
    InstallationState,
    InvoiceLifecycleEvent,
    InvoiceNumberSeries,
    ReminderSchedule,
    TenantBillingProfile,
)
from apps.core.organizations import create_organization


@pytest.fixture
def invoice_delivery(db, tmp_path):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Delivery MSP",
        owner_email="delivery-owner@example.invalid",
        owner_display_name="Delivery Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(installation.owner, generate_totp_secret())
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Delivery Client",
        legal_name="Delivery Client, LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Client",
        legal_name="Sibling Client, LLC",
        website="",
        classifications=["client"],
    )
    for record in (organization, sibling):
        record.access_mode = "all_authorized"
        record.save(update_fields=("access_mode", "updated_at"))
    portal_user = User.objects.create_user(email="reader@example.invalid", display_name="Client Reader")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=portal_user,
        role=BuiltInRole.CLIENT_USER,
        organization=organization,
    )
    sibling_user = User.objects.create_user(email="sibling@example.invalid", display_name="Sibling Reader")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=sibling_user,
        role=BuiltInRole.CLIENT_USER,
        organization=sibling,
    )
    TenantBillingProfile.objects.create(
        tenant=installation.tenant,
        legal_name="Delivery MSP, LLC",
        address_line_1="100 Main Street",
        city="Austin",
        postal_code="78701",
        country_code="US",
        billing_email="billing@example.invalid",
        invoice_prefix="INV",
    )
    InvoiceNumberSeries.objects.create(tenant=installation.tenant, prefix="INV")

    def draft(target, description):  # type: ignore[no-untyped-def]
        invoice = create_invoice(
            tenant=installation.tenant,
            organization=target,
            actor_id=installation.owner.id,
            currency="USD",
            invoice_date=date(2026, 8, 29),
            due_date=date(2026, 9, 28),
            reference="=unsafe-reference",
        )
        create_line(
            invoice=invoice,
            actor_id=installation.owner.id,
            values={"description": description, "quantity": "2.000", "unit_amount": "12.50"},
        )
        return invoice

    with override_settings(MEDIA_ROOT=tmp_path):
        issued = issue_invoice(
            invoice=draft(organization, "=unsafe-description"), actor_id=installation.owner.id
        )
        sibling_invoice = issue_invoice(
            invoice=draft(sibling, "Sibling service"), actor_id=installation.owner.id
        )
    hidden_draft = draft(organization, "Draft service")
    return installation, organization, portal_user, sibling_user, issued, sibling_invoice, hidden_draft, tmp_path


@pytest.mark.django_db
def test_portal_exposes_only_exact_client_issued_invoices_with_pdf_csv_parity(invoice_delivery):
    installation, organization, portal_user, sibling_user, issued, sibling_invoice, hidden_draft, media_root = (
        invoice_delivery
    )
    portal = Client()
    portal.force_login(portal_user)
    portal_context = require_client_portal_member(portal_user)
    assert project_authorized_fields(
        portal_context,
        {"name": "Managed service", "cost": "8.00"},
        {"cost": SensitiveField.COST},
        organization=organization,
    ) == {"name": "Managed service"}
    with override_settings(MEDIA_ROOT=media_root):
        listing = portal.get(reverse("client-portal-invoice-list"))
        assert listing.status_code == 200
        assert listing["Cache-Control"] == "private, no-store"
        assert [item["number"] for item in listing.json()["results"]] == [issued.number]

        detail = portal.get(reverse("client-portal-invoice-detail", kwargs={"invoice_entity_id": issued.entity_id}))
        assert detail.status_code == 200
        assert detail.json()["total"] == "25.00"

        pdf = portal.get(reverse("client-portal-invoice-pdf", kwargs={"invoice_entity_id": issued.entity_id}))
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")
        assert pdf["Content-Type"] == "application/pdf"

        csv_export = portal.get(
            reverse("client-portal-invoice-csv", kwargs={"invoice_entity_id": issued.entity_id})
        )
        assert csv_export.status_code == 200
        assert csv_export["Content-Type"].startswith("text/csv")
        rendered_csv = csv_export.content.decode()
        assert "invoice_number" in rendered_csv
        assert "'=unsafe-reference" in rendered_csv
        assert "'=unsafe-description" in rendered_csv

        for hidden in (sibling_invoice, hidden_draft):
            assert portal.get(
                reverse("client-portal-invoice-detail", kwargs={"invoice_entity_id": hidden.entity_id})
            ).status_code == 404

        sibling_portal = Client()
        sibling_portal.force_login(sibling_user)
        assert sibling_portal.get(
            reverse("client-portal-invoice-detail", kwargs={"invoice_entity_id": issued.entity_id})
        ).status_code == 404

        staff = Client()
        staff.force_login(installation.owner)
        assert staff.get(reverse("client-portal-invoice-list")).status_code == 403
        assert staff.get(
            reverse(
                "organization-invoice-pdf",
                kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
            )
        ).status_code == 200


@pytest.mark.django_db
def test_staff_delivery_emails_matching_pdf_and_csv_and_records_delivery(
    invoice_delivery, monkeypatch
):
    installation, organization, _portal_user, _sibling_user, issued, _sibling_invoice, hidden_draft, media_root = (
        invoice_delivery
    )
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    staff = Client()
    staff.force_login(installation.owner)
    url = reverse(
        "organization-invoice-deliver",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
    )
    with override_settings(MEDIA_ROOT=media_root):
        delivered = staff.post(url, {"recipient": "accounts@example.invalid"}, content_type="application/json")
    assert delivered.status_code == 200
    assert delivered.json()["delivery_count"] == 1
    assert delivered.json()["delivered_at"] is not None
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["accounts@example.invalid"]
    assert {attachment[2] for attachment in mail.outbox[0].attachments} == {"application/pdf", "text/csv"}
    assert {attachment[0] for attachment in mail.outbox[0].attachments} == {
        f"{issued.number}.pdf",
        f"{issued.number}.csv",
    }

    with override_settings(MEDIA_ROOT=media_root):
        repeated = staff.post(url, {"recipient": "accounts@example.invalid"}, content_type="application/json")
    assert repeated.status_code == 200
    assert repeated.json()["delivery_count"] == 2

    draft_url = reverse(
        "organization-invoice-deliver",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": hidden_draft.entity_id},
    )
    assert staff.post(
        draft_url, {"recipient": "accounts@example.invalid"}, content_type="application/json"
    ).status_code == 400


@pytest.mark.django_db
def test_invoice_lifecycle_export_idempotency_and_portal_projection(invoice_delivery, monkeypatch):
    installation, organization, portal_user, _sibling_user, issued, _sibling, _draft, media_root = invoice_delivery
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    staff = Client()
    staff.force_login(installation.owner)
    event_url = reverse(
        "organization-invoice-event-create",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
    )
    export_url = reverse(
        "organization-invoice-accounting-export",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
    )

    exported = staff.get(export_url)
    assert exported.status_code == 200
    assert exported.json()["format"] == "tekdocs-accounting-invoice/v1"
    assert exported.json()["idempotency_key"] == f"tekdocs:invoice:{issued.entity_id}:v1"
    assert exported.json()["total"] == "25.00"

    payment = {
        "event_type": "payment_recorded",
        "amount": "10.0000",
        "currency": "USD",
        "idempotency_key": "payment-1",
        "note": "ACH receipt 44",
    }
    first = staff.post(event_url, payment, content_type="application/json")
    assert first.status_code == 201
    assert first.json()["lifecycle_state"] == "partially_paid"
    assert first.json()["paid_amount"] == "10.00"
    assert first.json()["balance_amount"] == "15.00"
    repeated = staff.post(event_url, payment, content_type="application/json")
    assert repeated.status_code == 200
    assert InvoiceLifecycleEvent.objects.filter(invoice=issued, idempotency_key="payment-1").count() == 1

    sync = staff.post(
        event_url,
        {
            "event_type": "accounting_synchronized",
            "provider": "example-ledger",
            "external_id": "event-884",
            "idempotency_key": "example-ledger:event-884",
            "note": "Invoice 991",
        },
        content_type="application/json",
    )
    assert sync.status_code == 201
    assert sync.json()["reconciliation_state"] == "synchronized"

    portal = Client()
    portal.force_login(portal_user)
    with override_settings(MEDIA_ROOT=media_root):
        detail = portal.get(reverse("client-portal-invoice-detail", kwargs={"invoice_entity_id": issued.entity_id}))
    assert detail.status_code == 200
    assert detail.json()["lifecycle_state"] == "partially_paid"
    assert detail.json()["paid_amount"] == "10.00"
    assert "lifecycle_events" not in detail.json()
    assert "reconciliation_state" not in detail.json()

    event = InvoiceLifecycleEvent.objects.get(invoice=issued, idempotency_key="payment-1")
    assert event.amount == Decimal("10.0000")
    with pytest.raises(DatabaseError, match="immutable and retained"), transaction.atomic():
        InvoiceLifecycleEvent.objects.filter(pk=event.pk).update(note="rewritten")
    assert ReminderSchedule.objects.filter(source_entity=issued.entity, kind="invoice_due").exists()


@pytest.mark.django_db
def test_void_and_credit_are_reference_events_not_invoice_mutations(invoice_delivery, monkeypatch):
    installation, organization, _portal_user, _sibling_user, issued, sibling, _draft, _media_root = invoice_delivery
    staff = Client()
    staff.force_login(installation.owner)
    url = reverse(
        "organization-invoice-event-create",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
    )
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: False)
    denied = staff.post(
        url, {"event_type": "voided", "note": "Entered in error"}, content_type="application/json"
    )
    assert denied.status_code == 403

    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    cross_workspace = staff.post(
        url,
        {"event_type": "credited", "related_invoice_id": str(sibling.entity_id), "note": "Credit memo"},
        content_type="application/json",
    )
    assert cross_workspace.status_code == 404
    voided = staff.post(url, {"event_type": "voided", "note": "Entered in error"}, content_type="application/json")
    assert voided.status_code == 201
    assert voided.json()["lifecycle_state"] == "voided"
    issued.refresh_from_db()
    assert issued.state == "issued"
    assert issued.number


@pytest.mark.django_db
def test_failed_delivery_is_visible_and_can_be_retried(invoice_delivery, monkeypatch):
    installation, organization, _portal_user, _sibling_user, issued, _sibling, _draft, media_root = invoice_delivery
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    monkeypatch.setattr(
        "apps.core.invoicing.send_invoice_email",
        lambda **_values: (_ for _ in ()).throw(RuntimeError("smtp unavailable")),
    )
    staff = Client()
    staff.force_login(installation.owner)
    url = reverse(
        "organization-invoice-deliver",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": issued.entity_id},
    )
    with override_settings(MEDIA_ROOT=media_root):
        failed = staff.post(url, {"recipient": "accounts@example.invalid"}, content_type="application/json")
    assert failed.status_code == 400
    assert "retry is safe" in str(failed.json()).lower()
    issued.refresh_from_db()
    assert issued.delivery_count == 0
    assert InvoiceLifecycleEvent.objects.filter(invoice=issued, event_type="delivery_failed").count() == 1
