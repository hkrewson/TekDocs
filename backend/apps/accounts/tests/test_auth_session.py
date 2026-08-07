import json
import secrets

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import InstallationState

SESSION_URL = "/_allauth/browser/v1/auth/session"
LOGIN_URL = "/_allauth/browser/v1/auth/login"


@pytest.fixture
def owner_credentials(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    password = f"{secrets.token_urlsafe(24)}Aa7!"
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
        owner_display_name="Primary Owner",
        password=password,
    )
    return result, password


def csrf_value(client: Client) -> str:
    return client.cookies["csrftoken"].value


@pytest.mark.django_db
def test_browser_session_requires_csrf_for_login_and_logout(owner_credentials):
    client = Client(enforce_csrf_checks=True)
    result, password = owner_credentials

    anonymous = client.get(SESSION_URL)
    assert anonymous.status_code == 401
    assert anonymous.json()["meta"]["is_authenticated"] is False
    assert csrf_value(client)

    missing_login_csrf = client.post(
        LOGIN_URL,
        data=json.dumps({"email": result.owner.email, "password": password}),
        content_type="application/json",
    )
    assert missing_login_csrf.status_code == 403

    login = client.post(
        LOGIN_URL,
        data=json.dumps({"email": result.owner.email, "password": password}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf_value(client)},
    )
    assert login.status_code == 200
    assert login.json()["meta"]["is_authenticated"] is True
    assert login.json()["data"]["user"]["email"] == result.owner.email

    context = client.get(reverse("auth-context"))
    assert context.status_code == 200
    assert context.json() == {
        "user": {
            "id": str(result.owner.id),
            "email": result.owner.email,
            "display_name": result.owner.display_name,
        },
        "tenant": {"id": str(result.tenant.id), "name": result.tenant.name},
    }

    missing_logout_csrf = client.delete(SESSION_URL)
    assert missing_logout_csrf.status_code == 403
    assert client.get(reverse("auth-context")).status_code == 200

    logout = client.delete(SESSION_URL, headers={"X-CSRFToken": csrf_value(client)})
    assert logout.status_code == 401
    assert logout.json()["meta"]["is_authenticated"] is False
    assert client.get(reverse("auth-context")).status_code == 403


@pytest.mark.django_db
def test_invalid_credentials_do_not_create_a_session(owner_credentials):
    client = Client(enforce_csrf_checks=True)
    result, _password = owner_credentials
    client.get(SESSION_URL)

    response = client.post(
        LOGIN_URL,
        data=json.dumps({"email": result.owner.email, "password": secrets.token_urlsafe(24)}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf_value(client)},
    )

    assert response.status_code == 400
    assert client.get(reverse("auth-context")).status_code == 403


@pytest.mark.django_db
def test_authenticated_non_owner_cannot_enter_installation_shell(owner_credentials):
    client = Client()
    unrelated = User.objects.create_user(
        email="unrelated@example.com",
        password=secrets.token_urlsafe(24),
        display_name="Unrelated User",
    )
    client.force_login(unrelated)

    response = client.get(reverse("auth-context"))

    assert response.status_code == 403
