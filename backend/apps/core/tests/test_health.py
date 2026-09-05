import os
import secrets
import time

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
def test_readiness_reports_only_coarse_diagram_renderer_health(client, tmp_path):
    marker = tmp_path / ".renderer-ready"
    marker.write_text("internal value is not returned\n", encoding="utf-8")

    with override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY=str(tmp_path)):
        ready = client.get(reverse("health-ready"))
        assert ready.status_code == 200
        assert ready.json()["diagram_renderer"] == "ready"
        assert str(tmp_path) not in ready.content.decode()
        assert "internal value" not in ready.content.decode()

        old = time.time() - 30
        os.utime(marker, (old, old))
        stale = client.get(reverse("health-ready"))
        assert stale.status_code == 503
        assert stale.json()["diagram_renderer"] == "stale"
        assert str(tmp_path) not in stale.content.decode()


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
