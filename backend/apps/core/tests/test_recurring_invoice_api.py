from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import signing
from django.test import Client
from django.urls import reverse

from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.commercial import update_cost
from apps.core.models import Invoice, RecurringInvoicePeriod, RecurringInvoiceSchedule
from apps.core.recurring_invoice_preview import PREVIEW_SALT
from apps.core.tests import test_recurring_invoices as recurrence_fixtures

setup = recurrence_fixtures.setup
enroll = recurrence_fixtures.enroll


@pytest.fixture
def browser(setup):
    client = Client()
    client.force_login(setup[0].owner)
    return client


def url(setup, action, schedule=None, organization=None):
    kwargs = {"organization_entity_id": (organization or setup[1]).entity_id}
    if schedule:
        kwargs["schedule_id"] = schedule.pk
    if action == "source":
        kwargs["cost_id"] = setup[4].pk
    return reverse(f"organization-recurring-invoice-{action}", kwargs=kwargs)


def preview(browser, setup, schedule, **overrides):
    payload = {"starts_on": ["2025-01-01", "2025-02-01"], "as_of": "2025-02-01"}
    payload.update(overrides)
    return browser.post(url(setup, "preview", schedule), payload, content_type="application/json")


def apply(browser, setup, schedule, token, **overrides):
    return browser.post(
        url(setup, "apply", schedule, **overrides), {"preview_token": token}, content_type="application/json"
    )


@pytest.mark.django_db
def test_source_enrollment_preview_apply_and_retry(browser, setup):
    source = browser.get(url(setup, "source"))
    assert source.status_code == 200
    assert source.json()["source"]["amount"] == "20.00"
    enrolled = browser.post(
        url(setup, "enroll"),
        {
            "cost_id": str(setup[4].pk),
            "expected_source_digest": source.json()["source_digest"],
            "anchor": "2025-01-01",
            "ends_on": "2025-12-31",
            "description": "Approved service",
            "quantity": "2.000",
            "unit_amount": "75.00",
            "currency": "USD",
            "due_days": 30,
        },
        content_type="application/json",
    )
    assert enrolled.status_code == 201, enrolled.content
    schedule = RecurringInvoiceSchedule.objects.get(pk=enrolled.json()["id"])
    detail = browser.get(url(setup, "detail", schedule))
    assert detail.status_code == 200 and detail.json()["terms"][0]["unit_amount"] == "75.0000"
    reviewed = preview(browser, setup, schedule)
    assert reviewed.status_code == 200, reviewed.content
    data = reviewed.json()
    assert [p["total"] for p in data["periods"]] == ["150.00", "150.00"]
    assert data["periods"][0]["due_date"] == "2025-01-31"
    assert data["existing_invoices"] == [] and Invoice.objects.count() == 0
    assert preview(browser, setup, schedule).json()["preview_id"] == data["preview_id"]
    generated = apply(browser, setup, schedule, data["preview_token"])
    assert generated.status_code == 200, generated.content
    assert len(generated.json()) == 2
    assert apply(browser, setup, schedule, data["preview_token"]).json() == generated.json()
    assert Invoice.objects.count() == 2 and RecurringInvoicePeriod.objects.count() == 2
    assert set(Invoice.objects.values_list("state", "number")) == {("draft", "")}
    assert len(preview(browser, setup, schedule).json()["existing_invoices"]) == 2


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["source", "disabled", "tampered", "expired", "other_actor"])
def test_changed_or_invalid_previews_do_not_generate(browser, setup, change):
    schedule = enroll(setup)
    token = preview(browser, setup, schedule).json()["preview_token"]
    if change == "source":
        update_cost(
            contract=setup[3], cost_id=setup[4].pk, actor_id=setup[0].owner.pk, values={"amount": Decimal("21.00")}
        )
    elif change == "disabled":
        RecurringInvoiceSchedule.objects.filter(pk=schedule.pk).update(enabled=False)
    elif change == "tampered":
        token += "invalid"
    elif change == "expired":
        with patch("django.core.signing.time.time", return_value=1):
            token = signing.dumps(signing.loads(token, salt=PREVIEW_SALT), salt=PREVIEW_SALT)
    elif change == "other_actor":
        # A valid signature alone does not authorize the current operator.
        plan = signing.loads(token, salt=PREVIEW_SALT)
        plan["actor_id"] = "00000000-0000-0000-0000-000000000001"
        token = signing.dumps(plan, salt=PREVIEW_SALT)
    result = apply(browser, setup, schedule, token)
    assert result.status_code == 409, result.content
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_apply_rolls_back_every_period_if_a_later_generation_fails(browser, setup):
    from apps.core.invoice_recurrence import RecurrenceError
    from apps.core.recurring_invoices import generate_recurring_draft

    schedule = enroll(setup)
    token = preview(browser, setup, schedule).json()["preview_token"]

    def generate(**kwargs):
        if kwargs["starts_on"] == date(2025, 2, 1):
            raise RecurrenceError("Injected second-period failure")
        return generate_recurring_draft(**kwargs)

    with patch("apps.core.recurring_invoice_preview.generate_recurring_draft", side_effect=generate):
        assert apply(browser, setup, schedule, token).status_code == 409
    assert Invoice.objects.count() == 0 and RecurringInvoicePeriod.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "values,status",
    [
        ({"starts_on": []}, 400),
        ({"starts_on": ["2025-01-01"] * 121}, 400),
        ({"starts_on": ["2025-01-01", "2025-01-01"]}, 409),
        ({"starts_on": ["2025-01-02"]}, 409),
        ({"starts_on": ["2025-03-01"]}, 409),
        ({"as_of": "9999-01-01"}, 400),
        ({"currency": "EUR"}, 400),
    ],
)
def test_preview_rejects_invalid_or_unreviewed_selection(browser, setup, values, status):
    result = preview(browser, setup, enroll(setup), **values)
    assert result.status_code == status, result.content
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_sibling_workspace_cannot_read_or_apply_schedule(browser, setup):
    schedule = enroll(setup)
    token = preview(browser, setup, schedule).json()["preview_token"]
    for action in ("source", "detail"):
        assert browser.get(url(setup, action, schedule if action == "detail" else None, setup[2])).status_code == 404
    assert apply(browser, setup, schedule, token, organization=setup[2]).status_code == 404
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_current_permissions_rechecked_after_preview(browser, setup):
    schedule = enroll(setup)
    staff = User.objects.create_user(email="recurring-staff@example.invalid")
    TOTP.activate(staff, generate_totp_secret())
    membership = TenantMembership.objects.create(tenant=setup[0].tenant, user=staff, role=BuiltInRole.ADMINISTRATOR)
    browser.force_login(staff)
    reviewed = preview(browser, setup, schedule)
    assert reviewed.status_code == 200
    token = reviewed.json()["preview_token"]
    TenantMembership.objects.filter(pk=membership.pk).update(role=BuiltInRole.READ_ONLY)
    assert apply(browser, setup, schedule, token).status_code == 403
    assert browser.get(url(setup, "source")).status_code == 403
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_unauthenticated_and_no_mfa_operator_denied(browser, setup):
    schedule = enroll(setup)
    browser.logout()
    assert browser.get(url(setup, "detail", schedule)).status_code in (401, 403)
    user = User.objects.create_user(email="no-mfa-recurring@example.invalid")
    TenantMembership.objects.create(tenant=setup[0].tenant, user=user, role=BuiltInRole.ADMINISTRATOR)
    browser.force_login(user)
    assert preview(browser, setup, schedule).status_code == 403
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_foreign_tenant_paths_and_wrong_schedule_token_denied(browser, setup):
    from apps.core.models import Entity, Organization, Tenant

    schedule = enroll(setup)
    token = preview(browser, setup, schedule).json()["preview_token"]
    tenant = Tenant.objects.create(name="Foreign API MSP", slug="foreign-api-msp")
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name="Foreign client")
    foreign = Organization.objects.create(tenant=tenant, entity=entity)
    assert browser.get(url(setup, "detail", schedule, foreign)).status_code in (403, 404)
    assert apply(browser, setup, schedule, token, organization=foreign).status_code in (403, 404)
    plan = signing.loads(token, salt=PREVIEW_SALT)
    plan["schedule_id"] = "00000000-0000-0000-0000-000000000001"
    assert apply(browser, setup, schedule, signing.dumps(plan, salt=PREVIEW_SALT)).status_code == 409
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_enrollment_rejects_stale_review_and_extra_financial_fields(browser, setup):
    source = browser.get(url(setup, "source")).json()
    payload = {
        "cost_id": str(setup[4].pk),
        "expected_source_digest": source["source_digest"],
        "anchor": "2025-01-01",
        "ends_on": "2025-12-31",
        "description": "Reviewed service",
        "quantity": "1.000",
        "unit_amount": "75.00",
        "currency": "USD",
        "due_days": 30,
    }
    update_cost(contract=setup[3], cost_id=setup[4].pk, actor_id=setup[0].owner.pk, values={"amount": Decimal("22.00")})
    assert browser.post(url(setup, "enroll"), payload, content_type="application/json").status_code == 409
    assert (
        browser.post(
            url(setup, "enroll"), {**payload, "number": "UNREVIEWED"}, content_type="application/json"
        ).status_code
        == 400
    )
    assert RecurringInvoiceSchedule.objects.count() == 0


@pytest.mark.django_db
def test_partial_preview_and_apply_payload_expansion_refused(browser, setup):
    schedule = enroll(setup, ends_on=date(2025, 2, 15))
    assert preview(browser, setup, schedule).status_code == 409
    reviewed = preview(browser, setup, schedule, starts_on=["2025-01-01"])
    assert reviewed.status_code == 200
    result = browser.post(
        url(setup, "apply", schedule),
        {
            "preview_token": reviewed.json()["preview_token"],
            "starts_on": ["2025-02-01"],
        },
        content_type="application/json",
    )
    assert result.status_code == 400 and Invoice.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["enroll", "preview", "apply"])
def test_non_object_payload_is_a_controlled_bad_request(browser, setup, action):
    schedule = enroll(setup)
    response = browser.post(
        url(setup, action, None if action == "enroll" else schedule),
        [{}],
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_schedule_discovery_is_paginated_and_client_scoped(browser, setup):
    schedule = enroll(setup)
    result = browser.get(url(setup, "enroll"), {"page_size": 1}).json()
    assert result["count"] == 1 and result["results"][0]["id"] == str(schedule.pk)
    assert result["results"][0]["source_label"] == "Provider fee"
    assert browser.get(url(setup, "enroll", organization=setup[2])).json()["results"] == []
    assert browser.get(url(setup, "enroll"), {"page": 2}).json()["results"] == []
    assert browser.get(url(setup, "enroll"), {"unknown": "yes"}).status_code == 400


@pytest.mark.django_db
def test_due_discovery_marks_existing_partial_and_changed_periods(browser, setup):
    from apps.core.tests.test_recurring_invoices import generate

    schedule = enroll(setup, ends_on=date(2025, 3, 15))
    claim = generate(setup, schedule)
    address = url(setup, "due", schedule)
    query = {"due_from": "2025-01-01", "as_of": "2025-03-01"}
    result = browser.get(address, query)
    assert result.status_code == 200, result.content
    periods = result.json()["periods"]
    assert periods[0]["invoice_entity_id"] == str(claim.invoice.entity_id) and not periods[0]["can_generate"]
    assert periods[1]["can_generate"]
    assert periods[2]["blocked_reason"] == "partial" and not periods[2]["can_generate"]
    update_cost(contract=setup[3], cost_id=setup[4].pk, actor_id=setup[0].owner.pk, values={"amount": Decimal("23.00")})
    assert browser.get(address, query).json()["periods"][1]["blocked_reason"] == "source_changed"
    assert Invoice.objects.count() == 1
    assert browser.get(url(setup, "due", schedule, setup[2]), query).status_code == 404
    assert browser.get(address, {**query, "as_of": "9999-01-01"}).status_code == 400
    assert browser.get(address, {**query, "due_from": "2025-04-01"}).status_code == 409


@pytest.mark.django_db
def test_discovery_requires_current_permissions(browser, setup):
    schedule = enroll(setup)
    reader = User.objects.create_user(email="discovery-reader@example.invalid")
    TenantMembership.objects.create(tenant=setup[0].tenant, user=reader, role=BuiltInRole.READ_ONLY)
    browser.force_login(reader)
    assert browser.get(url(setup, "enroll")).status_code == 403
    assert (
        browser.get(url(setup, "due", schedule), {"due_from": "2025-01-01", "as_of": "2025-02-01"}).status_code == 403
    )
