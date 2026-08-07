import secrets
import threading

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.adapters import InviteOnlyAccountAdapter
from apps.accounts.models import User
from apps.core.models import AuditEvent, InstallationState, Tenant

BOOTSTRAP_TOKEN = secrets.token_urlsafe(32)
OWNER_PASSWORD = f"{secrets.token_urlsafe(24)}Aa7!"
BOOTSTRAP_PAYLOAD = {
    "tenant_name": "Example MSP",
    "owner_email": "owner@example.com",
    "owner_display_name": "Primary Owner",
    "password": OWNER_PASSWORD,
}


@pytest.fixture
def installation_state(db):
    return InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)[0]


@pytest.mark.django_db
def test_bootstrap_status_is_public_and_non_sensitive(client, installation_state):
    response = client.get(reverse("bootstrap-status"))

    assert response.status_code == 200
    assert response.json() == {"bootstrap_required": True}


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN)
def test_owner_bootstrap_creates_exactly_one_tenant_owner_and_audit_event(client, installation_state):
    response = client.post(
        reverse("bootstrap-owner"),
        BOOTSTRAP_PAYLOAD,
        content_type="application/json",
        headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
    )

    assert response.status_code == 201
    assert Tenant.objects.count() == 1
    assert User.objects.count() == 1
    owner = User.objects.get()
    assert owner.email == "owner@example.com"
    assert owner.check_password(BOOTSTRAP_PAYLOAD["password"])
    assert owner.is_staff is False
    assert owner.is_superuser is False
    installation_state.refresh_from_db()
    assert installation_state.tenant_id == Tenant.objects.get().id
    assert installation_state.owner_id == owner.id
    assert installation_state.is_bootstrapped
    event = AuditEvent.objects.get(action="installation.owner_bootstrapped")
    assert event.metadata == {"method": "deployment_token"}
    assert BOOTSTRAP_TOKEN not in str(response.json())
    assert BOOTSTRAP_PAYLOAD["password"] not in str(response.json())


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN)
@pytest.mark.parametrize("supplied_token", [None, "incorrect-bootstrap-token"])
def test_owner_bootstrap_rejects_missing_or_wrong_secret(client, installation_state, supplied_token):
    headers = {"X-TekDocs-Bootstrap-Token": supplied_token} if supplied_token else {}
    response = client.post(
        reverse("bootstrap-owner"),
        BOOTSTRAP_PAYLOAD,
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 403
    assert Tenant.objects.count() == 0
    assert User.objects.count() == 0
    assert BOOTSTRAP_TOKEN not in str(response.json())


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN)
def test_owner_bootstrap_rejects_invalid_input_and_repeated_claim(client, installation_state):
    invalid = {**BOOTSTRAP_PAYLOAD, "owner_email": "not-an-email"}
    invalid_response = client.post(
        reverse("bootstrap-owner"),
        invalid,
        content_type="application/json",
        headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
    )
    assert invalid_response.status_code == 400

    first = client.post(
        reverse("bootstrap-owner"),
        BOOTSTRAP_PAYLOAD,
        content_type="application/json",
        headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
    )
    second = client.post(
        reverse("bootstrap-owner"),
        {**BOOTSTRAP_PAYLOAD, "owner_email": "second@example.com"},
        content_type="application/json",
        headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert Tenant.objects.count() == 1
    assert User.objects.count() == 1


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN)
def test_owner_bootstrap_rejects_weak_password(client, installation_state):
    response = client.post(
        reverse("bootstrap-owner"),
        {**BOOTSTRAP_PAYLOAD, "password": "password"},
        content_type="application/json",
        headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
    )

    assert response.status_code == 400
    assert "password" in str(response.json()).lower()
    assert Tenant.objects.count() == 0
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_ordinary_public_signup_is_closed(client):
    assert InviteOnlyAccountAdapter().is_open_for_signup(None) is False
    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "public@example.com", "password": OWNER_PASSWORD},
        content_type="application/json",
    )
    assert response.status_code in {400, 403, 405}
    assert User.objects.count() == 0


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN)
def test_concurrent_owner_claims_create_one_owner():
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency contract requires PostgreSQL")
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def claim(email: str) -> None:
        thread_client = Client()
        barrier.wait()
        response = thread_client.post(
            reverse("bootstrap-owner"),
            {**BOOTSTRAP_PAYLOAD, "owner_email": email},
            content_type="application/json",
            headers={"X-TekDocs-Bootstrap-Token": BOOTSTRAP_TOKEN},
        )
        statuses.append(response.status_code)

    threads = [
        threading.Thread(target=claim, args=("first@example.com",)),
        threading.Thread(target=claim, args=("second@example.com",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(statuses) == [201, 409]
    assert Tenant.objects.count() == 1
    assert User.objects.count() == 1
