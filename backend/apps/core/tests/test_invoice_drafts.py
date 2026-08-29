import secrets
import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.billing import create_tax_rate_version
from apps.core.models import (
    CatalogProduct,
    ContractCost,
    InstallationState,
    Invoice,
    InvoiceLine,
    ServiceRate,
    Tenant,
)
from apps.core.organizations import create_organization
from apps.core.rls_contract import RUNTIME_ROLE


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Invoice MSP",
        owner_email="invoice-owner@example.invalid",
        owner_display_name="Invoice Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client()
    browser.force_login(installation.owner)
    return browser


def organization(installation, name, classification):  # type: ignore[no-untyped-def]
    record = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, LLC",
        website="https://example.invalid",
        classifications=[classification],
    )
    record.access_mode = "all_authorized"
    record.save(update_fields=("access_mode", "updated_at"))
    return record


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


@pytest.mark.django_db
def test_priced_product_service_rate_and_all_origins_snapshot_into_one_currency(owner_client, installation):
    client = organization(installation, "Invoice Client", "client")
    sibling = organization(installation, "Sibling Client", "client")
    supplier = organization(installation, "Invoice Supplier", "vendor")

    product_response = owner_client.post(
        reverse("organization-catalog-product-list-create", kwargs={"organization_entity_id": supplier.entity_id}),
        {
            "name": "Managed firewall",
            "kind": "hardware",
            "description": "Managed edge appliance",
            "unit_amount": "125.00",
            "currency": "usd",
        },
        content_type="application/json",
    )
    assert product_response.status_code == 201
    assert product_response.json()["unit_amount"] == "125.0000"
    assert product_response.json()["currency"] == "USD"

    service_response = owner_client.post(
        reverse("msp-service-rate-list-create"),
        {"name": "Remote support", "description": "Per-hour support", "unit_amount": "90.00", "currency": "USD"},
        content_type="application/json",
    )
    assert service_response.status_code == 201

    contract = owner_client.post(
        reverse("organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"name": "Client service", "provider_id": str(supplier.entity_id), "kind": "service"},
        content_type="application/json",
    )
    assert contract.status_code == 201
    cost = owner_client.post(
        reverse(
            "organization-commercial-contract-cost-list-create",
            kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract.json()["id"]},
        ),
        {
            "label": "Managed seats",
            "amount": "12.50",
            "currency": "USD",
            "billing_interval": "monthly",
            "quantity": "2.000",
        },
        content_type="application/json",
    )
    assert cost.status_code == 201

    tax = create_tax_rate_version(
        tenant=installation.tenant,
        name="Sales tax",
        rate=Decimal("0.100000"),
        inclusive=False,
        effective_from=date(2026, 1, 1),
    )
    collection = reverse("organization-invoice-list-create", kwargs={"organization_entity_id": client.entity_id})
    created = owner_client.post(
        collection,
        {
            "currency": "usd",
            "invoice_date": "2026-08-29",
            "due_date": "2026-09-28",
            "reference": "PO-44",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    invoice_id = created.json()["id"]
    assert created.json()["state"] == "draft"
    assert created.json()["total"] == "0.00"
    assert "number" not in created.json()

    choices = owner_client.get(
        reverse("organization-invoice-origin-choices", kwargs={"organization_entity_id": client.entity_id})
    )
    assert choices.status_code == 200
    origin_types = {item["origin_type"] for item in choices.json()["origins"]}
    assert origin_types == {"catalog_product", "service_rate", "contract_cost"}

    line_url = reverse(
        "organization-invoice-line-list-create",
        kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": invoice_id},
    )
    for payload in (
        {
            "origin_type": "catalog_product",
            "origin_id": product_response.json()["id"],
            "tax_rate_id": str(tax.id),
        },
        {"origin_type": "service_rate", "origin_id": service_response.json()["id"]},
        {"origin_type": "contract_cost", "origin_id": cost.json()["costs"][0]["id"]},
    ):
        response = owner_client.post(line_url, payload, content_type="application/json")
        assert response.status_code == 201

    draft = owner_client.get(collection).json()["results"][0]
    assert [line["origin_type"] for line in draft["lines"]] == [
        "catalog_product",
        "service_rate",
        "contract_cost",
    ]
    assert [str(line["origin_id"]) for line in draft["lines"]] == [
        str(product_response.json()["id"]),
        str(service_response.json()["id"]),
        str(cost.json()["costs"][0]["id"]),
    ]
    assert draft["subtotal"] == "240.00"
    assert draft["tax_total"] == "12.50"
    assert draft["total"] == "252.50"

    product = CatalogProduct.objects.get(entity_id=product_response.json()["id"])
    product.unit_amount = Decimal("200.0000")
    product.save(update_fields=("unit_amount", "updated_at"))
    rate_detail = reverse("msp-service-rate-detail", kwargs={"rate_id": service_response.json()["id"]})
    rate_changed = owner_client.patch(
        rate_detail,
        {"name": "Remote support", "description": "Per-hour support", "unit_amount": "100.00", "currency": "USD"},
        content_type="application/json",
    )
    assert rate_changed.status_code == 200
    assert rate_changed.json()["unit_amount"] == "100.00"
    ContractCost.objects.filter(pk=cost.json()["costs"][0]["id"]).update(amount=Decimal("20.00"))
    unchanged = owner_client.get(collection).json()["results"][0]
    assert unchanged["total"] == "252.50"

    assert owner_client.delete(rate_detail).status_code == 204
    assert all(
        item["id"] != service_response.json()["id"]
        for item in owner_client.get(reverse("msp-service-rate-list-create")).json()
    )

    assert (
        owner_client.get(
            reverse(
                "organization-invoice-detail",
                kwargs={"organization_entity_id": sibling.entity_id, "invoice_entity_id": invoice_id},
            )
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_invoice_draft_rejects_cross_currency_origins_and_allows_line_edit_and_delete(owner_client, installation):
    client = organization(installation, "Currency Client", "client")
    service = owner_client.post(
        reverse("msp-service-rate-list-create"),
        {"name": "UK support", "unit_amount": "50.00", "currency": "GBP"},
        content_type="application/json",
    ).json()
    created = owner_client.post(
        reverse("organization-invoice-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"currency": "USD", "invoice_date": "2026-08-29", "due_date": "2026-09-01"},
        content_type="application/json",
    ).json()
    line_collection = reverse(
        "organization-invoice-line-list-create",
        kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": created["id"]},
    )
    rejected = owner_client.post(
        line_collection,
        {"origin_type": "service_rate", "origin_id": service["id"]},
        content_type="application/json",
    )
    assert rejected.status_code == 400
    assert "currency" in str(rejected.json()).lower()

    manual = owner_client.post(
        line_collection,
        {"description": "Manual work", "quantity": "2.000", "unit_amount": "10.00"},
        content_type="application/json",
    )
    assert manual.status_code == 201
    line = manual.json()["lines"][0]
    changed = owner_client.patch(
        reverse(
            "organization-invoice-line-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "invoice_entity_id": created["id"],
                "line_id": line["id"],
            },
        ),
        {"quantity": "3.000"},
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert changed.json()["total"] == "30.00"
    assert (
        owner_client.patch(
            reverse(
                "organization-invoice-detail",
                kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": created["id"]},
            ),
            {"currency": "GBP"},
            content_type="application/json",
        ).status_code
        == 400
    )
    with pytest.raises(DatabaseError, match="fixed while lines exist"), transaction.atomic():
        Invoice.objects.filter(entity_id=created["id"]).update(currency="GBP")
    removed = owner_client.delete(
        reverse(
            "organization-invoice-line-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "invoice_entity_id": created["id"],
                "line_id": line["id"],
            },
        )
    )
    assert removed.status_code == 200
    assert removed.json()["lines"] == []
    deleted = owner_client.delete(
        reverse(
            "organization-invoice-detail",
            kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": created["id"]},
        )
    )
    assert deleted.status_code == 204
    assert not Invoice.objects.filter(entity_id=created["id"]).exists()


@pytest.mark.django_db(transaction=True)
def test_invoice_database_guards_and_forced_rls_reject_cross_scope_links():
    first = Tenant.objects.create(name="First invoice tenant", slug=f"invoice-first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second invoice tenant", slug=f"invoice-second-{uuid.uuid4()}")
    first_rate = ServiceRate.objects.create(tenant=first, name="First rate", unit_amount="10.0000", currency="USD")
    second_rate = ServiceRate.objects.create(tenant=second, name="Second rate", unit_amount="20.0000", currency="USD")

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(first.id)])
        cursor.execute("SELECT id FROM core_servicerate")
        assert cursor.fetchall() == [(first_rate.id,)]
        cursor.execute("UPDATE core_servicerate SET name='forged' WHERE id=%s", [second_rate.id])
        assert cursor.rowcount == 0
        runtime.rollback()

    with pytest.raises(DatabaseError, match="currency invalid"), transaction.atomic():
        ServiceRate.objects.filter(pk=first_rate.pk).update(currency="usd")

    assert Invoice.objects.count() == 0
    assert InvoiceLine.objects.count() == 0
