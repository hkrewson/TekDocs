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
        "default_currency": "USD",
        "payment_terms_days": 30,
        "invoice_prefix": "INV",
        "yearly_reset": False,
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
        values={"description": f"Managed service {suffix}".strip(), "quantity": "2.000", "unit_amount": "12.50"},
    )
    return invoice


@pytest.mark.django_db
def test_issue_requires_recent_session_and_complete_settings(owner_client, installation, monkeypatch):
    organization = client_organization(installation)
    invoice = draft_with_line(installation, organization)
    settings_url = reverse(
        "organization-invoice-issue-settings", kwargs={"organization_entity_id": organization.entity_id}
    )
    issue_url = reverse(
        "organization-invoice-issue",
        kwargs={"organization_entity_id": organization.entity_id, "invoice_entity_id": invoice.entity_id},
    )

    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: False)
    assert owner_client.put(settings_url, settings_payload(), content_type="application/json").status_code == 403
    assert owner_client.post(issue_url).status_code == 403

    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    incomplete = owner_client.post(issue_url)
    assert incomplete.status_code == 400
    assert "configure" in str(incomplete.json()).lower()
    configured = owner_client.put(settings_url, settings_payload(), content_type="application/json")
    assert configured.status_code == 200
    assert configured.json()["issue_ready"] is True


@pytest.mark.django_db
def test_issue_allocates_number_signs_and_retains_immutable_pdf(owner_client, installation, monkeypatch, tmp_path):
    monkeypatch.setattr("apps.core.invoice_views.did_recently_authenticate", lambda _request: True)
    organization = client_organization(installation)
    invoice = draft_with_line(installation, organization)
    settings_url = reverse(
        "organization-invoice-issue-settings", kwargs={"organization_entity_id": organization.entity_id}
    )
    assert owner_client.put(settings_url, settings_payload(), content_type="application/json").status_code == 200
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
    assert payload["signature_algorithm"] == "Ed25519"
    assert len(payload["content_digest"]) == 64
    assert len(payload["key_fingerprint"]) == 64

    issued = Invoice.objects.get(pk=invoice.pk)
    assert artifact_bytes.startswith(b"%PDF-")
    assert artifact.size == artifact_size
    assert artifact.checksum == hashlib.sha256(artifact_bytes).hexdigest()
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
    )
    InvoiceNumberSeries.objects.create(tenant=installation.tenant, prefix="YEAR", yearly_reset=True)
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
    assert series.current_year == 2026
    assert series.next_number == 7
