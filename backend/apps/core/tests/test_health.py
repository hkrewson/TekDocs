import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_liveness_contract(client):
    response = client.get(reverse("health-live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend", "version": "0.0.9"}
    assert response.headers["X-Request-ID"]
    assert response.headers["Content-Security-Policy"]


@pytest.mark.django_db
def test_readiness_checks_database(client):
    response = client.get(reverse("health-ready"))
    assert response.status_code == 200
    assert response.json()["database"] == "ready"
