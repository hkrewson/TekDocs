import secrets
from datetime import date

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import SensitiveField, project_authorized_fields, require_client_portal_member
from apps.core.invoicing import create_invoice, create_line, issue_invoice
from apps.core.models import InstallationState, InvoiceNumberSeries, TenantBillingProfile
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
