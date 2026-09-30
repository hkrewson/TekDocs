import base64
import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import DatabaseError, close_old_connections, transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import invoicing
from apps.core.invoicing import create_invoice, create_line, issue_invoice
from apps.core.models import (
    InstallationState,
    Invoice,
    InvoiceArtifact,
    InvoiceLine,
    InvoiceNumberSeries,
    TenantBillingProfile,
)
from apps.core.organizations import create_organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Issue MSP",
        owner_email="issue-owner@example.invalid",
        owner_display_name="Issue Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client()
    browser.force_login(installation.owner)
    return browser


def client_organization(installation, name="Issue Client"):  # type: ignore[no-untyped-def]
    record = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, LLC",
        website="https://example.invalid",
        classifications=["client"],
        billing_contact_name="Morgan Lee",
        billing_email="accounts@example.invalid",
        billing_phone="512-555-0144",
        billing_address_line_1="400 Congress Avenue",
        billing_address_line_2="Suite 900",
        billing_city="Austin",
        billing_region="TX",
        billing_postal_code="78701",
        billing_country_code="US",
    )
    record.access_mode = "all_authorized"
    record.save(update_fields=("access_mode", "updated_at"))
    return record


def settings_payload(**overrides):  # type: ignore[no-untyped-def]
    return {
        "legal_name": "Issue MSP, LLC",
        "address_line_1": "100 Main Street",
        "address_line_2": "",
        "city": "Austin",
        "region": "TX",
        "postal_code": "78701",
        "country_code": "US",
        "billing_email": "billing@example.invalid",
        "phone": "",
        "tax_registration": "",
        "payment_instructions": "Pay by ACH and include the invoice number.",
        "default_currency": "USD",
        "payment_terms_days": 30,
        "invoice_prefix": "INV",
        "invoice_date_component": "none",
        "invoice_separator": "-",
        "invoice_sequence_digits": 6,
        "invoice_reset_period": "never",
        **overrides,
    }


def draft_with_line(installation, organization, suffix=""):  # type: ignore[no-untyped-def]
    invoice = create_invoice(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        currency="USD",
        invoice_date=date(2026, 8, 29),
        due_date=date(2026, 9, 28),
        reference=f"PO-{suffix}" if suffix else "PO-1",
    )
    create_line(
        invoice=invoice,
        actor_id=installation.owner.id,
        values={
            "description": f"Managed service {suffix}".strip(),
            "quantity": "2.000",
            "unit": "hour",
            "unit_amount": "12.50",
        },
    )
    return invoice


@pytest.mark.django_db
def test_issue_requires_recent_session_and_complete_settings(owner_client, installation, monkeypatch):
    organization = client_organization(installation)
    invoice = draft_with_line(installation, organization)
    settings_url = reverse("msp-invoice-settings")
    issue_url = reverse(
        "organization-invoice-issue",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": invoice.entity_id},
    )

    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: False)
    expired = owner_client.put(settings_url, settings_payload(), content_type="application/json")
    assert expired.status_code == 403
    assert expired.json()["error"]["code"] == "recent_authentication_required"
    assert owner_client.post(issue_url).status_code == 403

    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    incomplete = owner_client.post(issue_url)
    assert incomplete.status_code == 400
    assert "configure" in str(incomplete.json()).lower()
    configured = owner_client.put(settings_url, settings_payload(), content_type="application/json")
    assert configured.status_code == 200
    assert configured.json()["issue_ready"] is True
    assert configured.json()["payment_instructions"] == "Pay by ACH and include the invoice number."


@pytest.mark.django_db
def test_issue_allocates_number_signs_and_retains_immutable_pdf(owner_client, installation, monkeypatch, tmp_path):
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    organization = client_organization(installation)
    settings_url = reverse("msp-invoice-settings")
    assert owner_client.put(settings_url, settings_payload(), content_type="application/json").status_code == 200
    invoice = draft_with_line(installation, organization)
    issue_url = reverse(
        "organization-invoice-issue",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": invoice.entity_id},
    )

    with override_settings(MEDIA_ROOT=tmp_path):
        response = owner_client.post(issue_url)
        artifact = InvoiceArtifact.objects.get(invoice=invoice)
        artifact_bytes = Path(artifact.file.path).read_bytes()
        artifact_size = Path(artifact.file.path).stat().st_size
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "issued"
    assert payload["number"] == "INV-000001"
    assert payload["subtotal"] == "25.00"
    assert payload["total"] == "25.00"
    assert payload["lines"][0]["unit"] == "hour"
    assert payload["bill_to"]["contact_name"] == "Morgan Lee"
    assert payload["bill_to"]["address_line_1"] == "400 Congress Avenue"
    assert payload["signature_algorithm"] == "Ed25519"
    assert len(payload["content_digest"]) == 64
    assert len(payload["key_fingerprint"]) == 64

    issued = Invoice.objects.get(pk=invoice.pk)
    organization.billing_contact_name = "Changed after issue"
    organization.save(update_fields=("billing_contact_name", "updated_at"))
    issued.refresh_from_db()
    assert issued.customer_snapshot["contact_name"] == "Morgan Lee"
    assert artifact_bytes.startswith(b"%PDF-")
    assert artifact.size == artifact_size
    assert artifact.checksum == hashlib.sha256(artifact_bytes).hexdigest()
    assert b"/Author (Issue MSP, LLC)" in artifact_bytes
    assert b"/Creator (TekDocs)" in artifact_bytes
    assert b"1999" not in artifact_bytes
    Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(issued.public_key)).verify(
        base64.urlsafe_b64decode(issued.signature), bytes.fromhex(issued.content_digest)
    )
    assert InvoiceNumberSeries.objects.get(tenant=installation.tenant, prefix="INV").next_number == 2

    with pytest.raises(DatabaseError, match="issued invoice is immutable"), transaction.atomic():
        Invoice.objects.filter(pk=issued.pk).update(notes="forged")
    with pytest.raises(DatabaseError, match="issued invoice lines are immutable"), transaction.atomic():
        InvoiceLine.objects.filter(invoice=issued).delete()
    with pytest.raises(DatabaseError, match="retained and immutable"), transaction.atomic():
        InvoiceArtifact.objects.filter(pk=artifact.pk).update(size=1)
    assert owner_client.post(issue_url).status_code == 400
    assert InvoiceNumberSeries.objects.get(tenant=installation.tenant, prefix="INV").next_number == 2


@pytest.mark.django_db
def test_draft_reviews_invoice_specific_parties_and_creates_linked_follow_ups(
    owner_client, installation, monkeypatch, tmp_path
):
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    organization = client_organization(installation)
    assert owner_client.put(
        reverse("msp-invoice-settings"), settings_payload(), content_type="application/json"
    ).status_code == 200
    source = draft_with_line(installation, organization)
    detail_url = reverse(
        "organization-invoice-detail",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": source.entity_id},
    )
    draft_payload = owner_client.get(detail_url).json()
    assert draft_payload["issuer"]["legal_name"] == "Issue MSP, LLC"
    assert draft_payload["bill_to"]["address_line_1"] == "400 Congress Avenue"

    changed_bill_to = {
        **draft_payload["bill_to"],
        "legal_name": "Issue Client Accounts Payable",
        "address_line_1": "900 Invoice Lane",
    }
    changed_issuer = {**draft_payload["issuer"], "payment_instructions": "ACH reference PO-1"}
    updated = owner_client.patch(
        detail_url,
        {"issuer": changed_issuer, "bill_to": changed_bill_to},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["bill_to"]["address_line_1"] == "900 Invoice Lane"

    issue_url = reverse(
        "organization-invoice-issue",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": source.entity_id},
    )
    with override_settings(MEDIA_ROOT=tmp_path):
        issued = owner_client.post(issue_url)
    assert issued.status_code == 200
    assert issued.json()["bill_to"]["legal_name"] == "Issue Client Accounts Payable"
    assert issued.json()["issuer"]["payment_instructions"] == "ACH reference PO-1"

    organization.billing_address_line_1 = "Changed client default"
    organization.save(update_fields=("billing_address_line_1", "updated_at"))
    assert owner_client.get(detail_url).json()["bill_to"]["address_line_1"] == "900 Invoice Lane"

    follow_up_url = reverse(
        "organization-invoice-follow-up",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": source.entity_id},
    )
    supplement = owner_client.post(follow_up_url, {"mode": "supplement"}, content_type="application/json")
    assert supplement.status_code == 201
    assert supplement.json()["source"] == {
        "id": str(source.entity_id), "number": "INV-000001", "kind": "supplement"
    }
    assert supplement.json()["lines"] == []
    assert supplement.json()["bill_to"]["address_line_1"] == "900 Invoice Lane"

    replacement = owner_client.post(follow_up_url, {"mode": "replacement"}, content_type="application/json")
    assert replacement.status_code == 201
    assert replacement.json()["source"]["kind"] == "replacement"
    assert replacement.json()["lines"][0]["description"] == "Managed service"
    assert replacement.json()["lines"][0]["origin_type"] == ""


@pytest.mark.django_db
def test_failed_issue_rolls_back_the_number_and_draft(monkeypatch, installation, tmp_path):
    organization = client_organization(installation, "Rollback Client")
    TenantBillingProfile.objects.create(
        tenant=installation.tenant,
        legal_name="Rollback MSP, LLC",
        address_line_1="100 Main Street",
        city="Austin",
        postal_code="78701",
        country_code="US",
        billing_email="billing@example.invalid",
        invoice_prefix="ROLL",
    )
    series = InvoiceNumberSeries.objects.create(tenant=installation.tenant, prefix="ROLL")
    invoice = draft_with_line(installation, organization)
    original = invoicing.render_invoice_pdf
    monkeypatch.setattr(
        "apps.core.invoicing.render_invoice_pdf", lambda **_values: (_ for _ in ()).throw(RuntimeError("render failed"))
    )
    with pytest.raises(RuntimeError, match="render failed"), override_settings(MEDIA_ROOT=tmp_path):
        issue_invoice(invoice=invoice, actor_id=installation.owner.id)
    series.refresh_from_db()
    invoice.refresh_from_db()
    assert series.next_number == 1
    assert invoice.state == "draft"
    assert invoice.number == ""

    monkeypatch.setattr("apps.core.invoicing.render_invoice_pdf", original)
    with override_settings(MEDIA_ROOT=tmp_path):
        assert issue_invoice(invoice=invoice, actor_id=installation.owner.id).number == "ROLL-000001"


@pytest.mark.django_db(transaction=True)
def test_concurrent_issue_allocates_consecutive_gapless_yearly_numbers(installation, tmp_path):
    organization = client_organization(installation, "Concurrent Client")
    TenantBillingProfile.objects.create(
        tenant=installation.tenant,
        legal_name="Concurrent MSP, LLC",
        address_line_1="100 Main Street",
        city="Austin",
        postal_code="78701",
        country_code="US",
        billing_email="billing@example.invalid",
        invoice_prefix="YEAR",
        invoice_date_component="year",
        invoice_reset_period="yearly",
    )
    InvoiceNumberSeries.objects.create(
        tenant=installation.tenant,
        prefix="YEAR",
        date_component="year",
        reset_period="yearly",
    )
    invoice_ids = [draft_with_line(installation, organization, str(index)).id for index in range(6)]

    def issue(invoice_id):  # type: ignore[no-untyped-def]
        close_old_connections()
        try:
            with override_settings(MEDIA_ROOT=tmp_path):
                return issue_invoice(invoice=Invoice.objects.get(pk=invoice_id), actor_id=installation.owner.id).number
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=6) as executor:
        numbers = list(executor.map(issue, invoice_ids))

    assert sorted(numbers) == [f"YEAR-2026-{index:06d}" for index in range(1, 7)]
    series = InvoiceNumberSeries.objects.get(tenant=installation.tenant, prefix="YEAR")
    assert series.current_period == "2026"
    assert series.next_number == 7


@pytest.mark.django_db
def test_settings_offer_country_choices_and_validate_numbering_period(owner_client, installation, monkeypatch):
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    settings_url = reverse("msp-invoice-settings")

    result = owner_client.get(settings_url)
    assert result.status_code == 200
    assert {"value": "US", "label": "United States"} in result.json()["country_choices"]
    assert (
        owner_client.put(settings_url, settings_payload(country_code="ZZ"), content_type="application/json").status_code
        == 400
    )
    assert (
        owner_client.put(
            settings_url,
            settings_payload(invoice_reset_period="monthly", invoice_date_component="year"),
            content_type="application/json",
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_flexible_number_format_uses_month_letter_and_selected_width(owner_client, installation, monkeypatch, tmp_path):
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    organization = client_organization(installation, "Flexible Number Client")
    settings_url = reverse("msp-invoice-settings")
    configured = owner_client.put(
        settings_url,
        settings_payload(
            invoice_prefix="TC",
            invoice_date_component="short_year_month_code",
            invoice_separator="/",
            invoice_sequence_digits=4,
            invoice_reset_period="monthly",
        ),
        content_type="application/json",
    )
    assert configured.status_code == 200
    invoice = draft_with_line(installation, organization)
    issue_url = reverse(
        "organization-invoice-issue",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": invoice.entity_id},
    )
    with override_settings(MEDIA_ROOT=tmp_path):
        result = owner_client.post(issue_url)
    assert result.status_code == 200
    assert result.json()["number"] == "TC/26H/0001"
