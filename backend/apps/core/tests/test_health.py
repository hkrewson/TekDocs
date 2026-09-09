import json
import os
import secrets
import time

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
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
@override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY="")
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
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN="", TEKDOCS_DIAGRAM_JOB_DIRECTORY="")
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
@override_settings(TEKDOCS_BOOTSTRAP_TOKEN="", TEKDOCS_DIAGRAM_JOB_DIRECTORY="")
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


@pytest.mark.django_db
def test_system_diagnostics_are_authorized_bounded_and_value_free(client, tmp_path):
    result = bootstrap_owner(
        tenant_name="Diagnostics MSP",
        owner_email="diagnostics-owner@example.invalid",
        owner_display_name="Diagnostics Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    marker = tmp_path / ".renderer-ready"
    marker.write_text("private heartbeat content\n", encoding="utf-8")
    waiting = tmp_path / ("a" * 32)
    processing = tmp_path / ("b" * 32)
    waiting.mkdir()
    processing.mkdir()
    (waiting / "ready").write_text("", encoding="utf-8")
    (processing / "processing").write_text("", encoding="utf-8")
    telemetry = {
        "checked_at": int(time.time() * 1000),
        "renderer": "@mermaid-js/mermaid-cli@11.16.0",
        "capacity": 999,
        "queue": {"waiting": 999, "processing": 999, "total": 999},
        "recent_failures": [
            {"code": "renderer_timeout", "occurred_at": int(time.time() * 1000)},
            {"code": "private document title", "occurred_at": int(time.time() * 1000)},
        ],
        "private": "customer diagram source and /private/path",
    }
    (tmp_path / ".renderer-diagnostics.json").write_text(json.dumps(telemetry), encoding="utf-8")

    with override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY=str(tmp_path)):
        assert client.get(reverse("system-diagnostics")).status_code == 403
        client.force_login(result.owner)
        response = client.get(reverse("system-diagnostics"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["application_version"] == VERSION
    assert payload["database"] == "ready"
    assert payload["diagram_renderer"] == {
        "status": "ready",
        "version": "@mermaid-js/mermaid-cli@11.16.0",
        "capacity": 8,
        "queue": {"waiting": 1, "processing": 1, "total": 2},
        "recent_failures": [
            {"code": "renderer_timeout", "occurred_at": telemetry["recent_failures"][0]["occurred_at"]}
        ],
        "last_checked_at": telemetry["checked_at"],
    }
    serialized = response.content.decode()
    assert "customer diagram source" not in serialized
    assert "/private/path" not in serialized
    assert str(tmp_path) not in serialized


@pytest.mark.django_db
def test_system_diagnostics_allow_administrators_but_not_read_only_members(client, tmp_path):
    result = bootstrap_owner(
        tenant_name="Operator MSP",
        owner_email="operator-owner@example.invalid",
        owner_display_name="Operator Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    (tmp_path / ".renderer-ready").write_text("ready\n", encoding="utf-8")
    administrator = User.objects.create_user(email="admin@example.invalid", display_name="Admin")
    reader = User.objects.create_user(email="reader@example.invalid", display_name="Reader")
    TenantMembership.objects.create(tenant=result.tenant, user=administrator, role=BuiltInRole.ADMINISTRATOR)
    TenantMembership.objects.create(tenant=result.tenant, user=reader, role=BuiltInRole.READ_ONLY)

    with override_settings(TEKDOCS_DIAGRAM_JOB_DIRECTORY=str(tmp_path)):
        client.force_login(administrator)
        assert client.get(reverse("system-diagnostics")).status_code == 200
        client.force_login(reader)
        assert client.get(reverse("system-diagnostics")).status_code == 403
