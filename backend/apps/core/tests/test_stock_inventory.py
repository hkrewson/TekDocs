import secrets
from decimal import Decimal

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState, InvoiceLine, StockItem, StockMovement, Tenant
from apps.core.organizations import create_organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Stock MSP",
        owner_email="stock-owner@example.invalid",
        owner_display_name="Stock Owner",
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


def item_payload(vendor):  # type: ignore[no-untyped-def]
    return {
        "name": "Cat6 bulk cable",
        "description": "Riser-rated solid copper cable",
        "vendor_id": str(vendor.entity_id),
        "vendor_part_number": "PART-1000",
        "unit": "foot",
        "initial_quantity": "1000.000",
        "reorder_level": "150.000",
        "currency": "usd",
        "cost_per_unit": "0.145430",
        "client_price_per_unit": "0.3000",
        "purchase_quantity": "1000.000",
        "purchase_price": "107.9900",
        "order_total": "145.4300",
        "order_number": "ORDER-1001",
        "order_url": "https://orders.example.invalid/ORDER-1001",
        "ordered_on": "2026-08-01",
        "tracking_number": "TRACK-1001",
        "tracking_url": "https://tracking.example.invalid/TRACK-1001",
    }


@pytest.mark.django_db
def test_stock_item_records_exact_cost_and_append_only_client_usage(owner_client, installation):
    vendor = organization(installation, "Cable Supplier", "vendor")
    client = organization(installation, "Client Site", "client")
    collection = reverse("msp-stock-list-create")

    created = owner_client.post(collection, item_payload(vendor), content_type="application/json")
    assert created.status_code == 201, created.content
    item_id = created.json()["id"]
    assert created.json()["cost_per_unit"] == "0.145430"
    assert created.json()["quantity_on_hand"] == "1000.000"
    assert created.json()["movements"][0]["movement_type"] == "received"

    used = owner_client.post(
        reverse("msp-stock-movement-create", kwargs={"item_id": item_id}),
        {
            "movement_type": "used",
            "quantity_change": "-125.500",
            "client_id": str(client.entity_id),
            "note": "Conference room runs",
            "occurred_at": "2026-08-02T15:00:00Z",
        },
        content_type="application/json",
    )
    assert used.status_code == 201, used.content
    assert used.json()["quantity_on_hand"] == "874.500"
    usage = next(entry for entry in used.json()["movements"] if entry["movement_type"] == "used")
    assert usage["client_name"] == "Client Site"

    rejected = owner_client.post(
        reverse("msp-stock-movement-create", kwargs={"item_id": item_id}),
        {"movement_type": "used", "quantity_change": "-900.000", "client_id": str(client.entity_id)},
        content_type="application/json",
    )
    assert rejected.status_code == 400
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("874.500")
    assert StockMovement.objects.filter(stock_item_id=item_id).count() == 2

    movement = StockMovement.objects.filter(stock_item_id=item_id).first()
    with pytest.raises(ValidationError, match="immutable"):
        movement.save()
    with pytest.raises(ValidationError, match="retained"):
        movement.delete()
    with pytest.raises(DatabaseError, match="retained"), transaction.atomic():
        StockMovement.objects.filter(pk=movement.pk).update(note="Rewrite history")
    with pytest.raises(DatabaseError, match="retained"), transaction.atomic():
        StockMovement.objects.filter(pk=movement.pk).delete()


@pytest.mark.django_db
def test_stock_item_invoice_line_tracks_quantity_through_draft_changes(owner_client, installation):
    vendor = organization(installation, "Parts Supplier", "vendor")
    client = organization(installation, "Invoice Client", "client")
    created = owner_client.post(reverse("msp-stock-list-create"), item_payload(vendor), content_type="application/json")
    item_id = created.json()["id"]
    invoice = owner_client.post(
        reverse("organization-invoice-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"currency": "USD", "invoice_date": "2026-08-05", "due_date": "2026-09-04"},
        content_type="application/json",
    )
    line = owner_client.post(
        reverse(
            "organization-invoice-line-list-create",
            kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": invoice.json()["id"]},
        ),
        {"origin_type": "stock_item", "origin_id": item_id, "quantity": "125.500"},
        content_type="application/json",
    )
    assert line.status_code == 201, line.content
    assert line.json()["lines"][0]["origin_type"] == "stock_item"
    assert line.json()["lines"][0]["unit_amount"] == "0.30"
    line_id = line.json()["lines"][0]["id"]
    invoice_line = InvoiceLine.objects.get(id=line_id)
    assert invoice_line.stock_item_id == StockItem.objects.get(id=item_id).id
    assert invoice_line.stock_quantity_consumed == Decimal("125.500")
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("874.500")
    movement = StockMovement.objects.filter(stock_item_id=item_id, movement_type="used").get()
    assert movement.quantity_change == Decimal("-125.500")
    assert movement.client_id == client.id
    choices = owner_client.get(
        reverse("organization-invoice-origin-choices", kwargs={"organization_entity_id": client.entity_id})
    )
    stock_choice = next(origin for origin in choices.json()["origins"] if origin["id"] == item_id)
    assert stock_choice["available_quantity"] == "874.500"
    assert stock_choice["unit"] == "foot"

    blocked_archive = owner_client.delete(reverse("msp-stock-detail", kwargs={"item_id": item_id}))
    assert blocked_archive.status_code == 400

    line_detail = reverse(
        "organization-invoice-line-detail",
        kwargs={
            "organization_entity_id": client.entity_id,
            "invoice_entity_id": invoice.json()["id"],
            "line_id": line_id,
        },
    )
    increased = owner_client.patch(line_detail, {"quantity": "150.000"}, content_type="application/json")
    assert increased.status_code == 200, increased.content
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("850.000")

    reduced = owner_client.patch(line_detail, {"quantity": "100.000"}, content_type="application/json")
    assert reduced.status_code == 200, reduced.content
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("900.000")

    removed = owner_client.delete(line_detail)
    assert removed.status_code == 200, removed.content
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("1000.000")
    assert [entry.quantity_change for entry in StockMovement.objects.filter(stock_item_id=item_id)] == [
        Decimal("100.000"),
        Decimal("50.000"),
        Decimal("-24.500"),
        Decimal("-125.500"),
        Decimal("1000.000"),
    ]

    replacement = owner_client.post(
        reverse(
            "organization-invoice-line-list-create",
            kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": invoice.json()["id"]},
        ),
        {"origin_type": "stock_item", "origin_id": item_id, "quantity": "10.000"},
        content_type="application/json",
    )
    assert replacement.status_code == 201, replacement.content
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("990.000")
    deleted_draft = owner_client.delete(
        reverse(
            "organization-invoice-detail",
            kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": invoice.json()["id"]},
        )
    )
    assert deleted_draft.status_code == 204, deleted_draft.content
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("1000.000")

    archived = owner_client.delete(reverse("msp-stock-detail", kwargs={"item_id": item_id}))
    assert archived.status_code == 204
    choices = owner_client.get(
        reverse("organization-invoice-origin-choices", kwargs={"organization_entity_id": client.entity_id})
    )
    assert all(origin["id"] != item_id for origin in choices.json()["origins"])


@pytest.mark.django_db
def test_stock_invoice_line_rejects_insufficient_quantity_atomically(owner_client, installation):
    vendor = organization(installation, "Limited Supplier", "vendor")
    client = organization(installation, "Limited Client", "client")
    created = owner_client.post(reverse("msp-stock-list-create"), item_payload(vendor), content_type="application/json")
    item_id = created.json()["id"]
    invoice = owner_client.post(
        reverse("organization-invoice-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {"currency": "USD", "invoice_date": "2026-08-05", "due_date": "2026-09-04"},
        content_type="application/json",
    )

    response = owner_client.post(
        reverse(
            "organization-invoice-line-list-create",
            kwargs={"organization_entity_id": client.entity_id, "invoice_entity_id": invoice.json()["id"]},
        ),
        {"origin_type": "stock_item", "origin_id": item_id, "quantity": "1000.001"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Only 1000.000 foot are on hand" in str(response.json())
    assert InvoiceLine.objects.filter(invoice_id=invoice.json()["id"]).count() == 0
    assert StockItem.objects.get(id=item_id).quantity_on_hand == Decimal("1000.000")
    assert StockMovement.objects.filter(stock_item_id=item_id).count() == 1


@pytest.mark.django_db
def test_stock_rejects_wrong_organization_classification(owner_client, installation):
    client = organization(installation, "Not A Vendor", "client")
    response = owner_client.post(
        reverse("msp-stock-list-create"), item_payload(client), content_type="application/json"
    )
    assert response.status_code == 404
    assert StockItem.objects.count() == 0


@pytest.mark.django_db
def test_stock_item_from_another_tenant_is_not_addressable(owner_client, installation):
    other_tenant = Tenant.objects.create(name="Other MSP", slug="other-msp")
    foreign_item = StockItem.objects.create(
        tenant=other_tenant,
        name="Other tenant cable",
        unit="foot",
        quantity_on_hand=Decimal("50.000"),
        currency="USD",
        cost_per_unit=Decimal("0.100000"),
        client_price_per_unit=Decimal("0.2000"),
    )

    listing = owner_client.get(reverse("msp-stock-list-create"))
    assert listing.status_code == 200
    assert all(record["id"] != str(foreign_item.id) for record in listing.json()["results"])

    changed = owner_client.patch(
        reverse("msp-stock-detail", kwargs={"item_id": foreign_item.id}),
        {"name": "Cross-tenant rewrite"},
        content_type="application/json",
    )
    moved = owner_client.post(
        reverse("msp-stock-movement-create", kwargs={"item_id": foreign_item.id}),
        {"movement_type": "received", "quantity_change": "1.000"},
        content_type="application/json",
    )
    assert changed.status_code == 404
    assert moved.status_code == 404
    foreign_item.refresh_from_db()
    assert foreign_item.name == "Other tenant cable"
    assert foreign_item.quantity_on_hand == Decimal("50.000")
