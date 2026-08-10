import secrets

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState
from tekdocs.version import VERSION


@pytest.mark.django_db
def test_liveness_contract(client):
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend", "version": VERSION}
    assert response.headers["X-Request-ID"]
    assert response.headers["Content-Security-Policy"]


@pytest.mark.django_db
def test_readiness_checks_database(client):
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    assert response.json()["database"] == "ready"


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN="")
def test_readiness_fails_closed_without_bootstrap_token_before_owner_claim(client):
    assert not InstallationState.objects.get(pk=InstallationState.SINGLETON_ID).is_bootstrapped

    response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ready",
        "bootstrap": "unavailable",
        "version": VERSION,
    }


@pytest.mark.django_db
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN="")
def test_readiness_allows_bootstrap_token_removal_after_owner_claim(client):
    bootstrap_owner(
        tenant_name="Health MSP",
        owner_email="health-owner@example.invalid",
        owner_display_name="Health Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )

    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["database"] == "ready"
