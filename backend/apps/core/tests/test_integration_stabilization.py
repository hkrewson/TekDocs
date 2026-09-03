from __future__ import annotations

from datetime import timedelta
from time import perf_counter

import pytest
from django.core.exceptions import ValidationError
from django.db import connection as db_connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.integration_egress import MAX_INTEGRATION_RESPONSE_BYTES, ProviderRateLimited, get_provider_json
from apps.core.integration_providers import ProviderObservation, ProviderPage
from apps.core.integrations import JOB_LEASE, cancel_sync_job, enqueue_sync, process_sync_job
from apps.core.models import IntegrationConflict, IntegrationJobState, IntegrationObservation
from apps.core.webhook_egress import WebhookEgressError, WebhookTarget
from apps.core.workspaces import resolve_organization_workspace

from .test_integrations import SuccessfulAdapter, connection, organization

pytest_plugins = ("apps.core.tests.test_integrations",)


class FakeResponse:
    def __init__(self, *, status: int = 200, content_type: str = "application/json", body: bytes = b"{}", headers=None):  # type: ignore[no-untyped-def]
        self.status = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.body = body
        self.closed = False

    def read(self, _amount: int) -> bytes:
        return self.body

    def close(self) -> None:
        self.closed = True


class FakePool:
    response = FakeResponse()
    created: list[tuple[tuple[object, ...], dict[str, object]]] = []
    requests: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.created.append((args, kwargs))

    def urlopen(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.requests.append((args, kwargs))
        return self.response

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_fake_pool():
    FakePool.response = FakeResponse()
    FakePool.created = []
    FakePool.requests = []


def _mock_egress(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr("apps.core.integration_egress.urllib3.HTTPSConnectionPool", FakePool)
    monkeypatch.setattr(
        "apps.core.integration_egress.resolve_webhook_target",
        lambda _url: WebhookTarget("https://provider.example/api/", "provider.example", "203.0.113.10", "/api/"),
    )


def test_provider_egress_pins_tls_hostname_disables_redirects_and_bounds_body(monkeypatch):
    _mock_egress(monkeypatch)
    payload = get_provider_json(
        base_url="https://provider.example/api/", relative_path="ipam/vlans/?limit=50", authorization="Token value"
    )

    assert payload == {}
    assert FakePool.created[0][0] == ("203.0.113.10",)
    assert FakePool.created[0][1]["assert_hostname"] == "provider.example"
    assert FakePool.created[0][1]["server_hostname"] == "provider.example"
    request = FakePool.requests[0]
    assert request[0] == ("GET", "/api/ipam/vlans/?limit=50")
    assert request[1]["redirect"] is False
    assert request[1]["preload_content"] is False
    assert request[1]["headers"] == {
        "Host": "provider.example",
        "Accept": "application/json",
        "Authorization": "Token value",
    }


@pytest.mark.parametrize(
    ("response", "error"),
    (
        (FakeResponse(status=302), "provider_http_error"),
        (FakeResponse(content_type="text/html"), "provider_content_type_invalid"),
        (FakeResponse(body=b"x" * (MAX_INTEGRATION_RESPONSE_BYTES + 1)), "provider_response_too_large"),
        (FakeResponse(body=b"[]"), "provider_response_invalid"),
        (FakeResponse(body=b"{"), "provider_connection_failed"),
    ),
)
def test_provider_egress_rejects_redirect_content_type_size_and_invalid_json(monkeypatch, response, error):
    _mock_egress(monkeypatch)
    FakePool.response = response
    with pytest.raises(WebhookEgressError, match=error):
        get_provider_json(
            base_url="https://provider.example/api/",
            relative_path="dcim/devices/",
            authorization="Token x",
        )
    assert response.closed


def test_provider_egress_honors_bounded_rate_limit_without_exposing_response(monkeypatch):
    _mock_egress(monkeypatch)
    FakePool.response = FakeResponse(status=429, body=b"sensitive provider text", headers={"Retry-After": "999999"})
    started = timezone.now()
    with pytest.raises(ProviderRateLimited) as caught:
        get_provider_json(
            base_url="https://provider.example/api/",
            relative_path="dcim/devices/",
            authorization="Token x",
        )
    assert timedelta(seconds=1) <= caught.value.retry_at - started <= timedelta(hours=1, seconds=1)
    assert "sensitive" not in str(caught.value)


def test_provider_cursor_cannot_escape_with_credentials_fragment_or_non_https():
    for cursor in (
        "https://user:pass@provider.example/api/",
        "https://provider.example/api/#fragment",
        "http://provider.example/api/",
        "//other.example/api/",
    ):
        with pytest.raises(ValidationError):
            get_provider_json(base_url="https://provider.example/api/", relative_path=cursor, authorization="Token x")


class FinalizationFailureAdapter:
    key = "netbox"
    label = SuccessfulAdapter.label
    contract = SuccessfulAdapter.contract

    def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
        return ProviderPage((ProviderObservation("ipam.vlan", "91", "f" * 64),), "")


@pytest.mark.django_db
def test_failed_page_finalization_rolls_back_observations_for_safe_retry(installation, monkeypatch):
    record = organization(installation, "Rollback client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:rollback")
    monkeypatch.setattr("apps.core.integrations._conflicts_for_observations", lambda *_args, **_kwargs: 1 / 0)

    result = process_sync_job(job_id=job.id, adapter=FinalizationFailureAdapter())

    assert result.state == IntegrationJobState.PENDING
    assert IntegrationObservation.objects.filter(job=job).count() == 0


@pytest.mark.django_db
def test_stale_worker_lease_is_recovered_without_replaying_a_completed_job(installation):
    record = organization(installation, "Lease client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:lease")
    stale = timezone.now() - JOB_LEASE - timedelta(seconds=1)
    job.state = IntegrationJobState.PROCESSING
    job.locked_at = stale
    job.attempts = 1
    job.save(update_fields=("state", "locked_at", "attempts"))

    completed = process_sync_job(job_id=job.id, adapter=SuccessfulAdapter())
    repeated = process_sync_job(job_id=job.id, adapter=SuccessfulAdapter())

    assert completed.state == IntegrationJobState.SUCCEEDED
    assert completed.attempts == 2
    assert repeated.attempts == 2
    assert IntegrationObservation.objects.filter(job=job).count() == 1


@pytest.mark.django_db
def test_pending_job_can_be_cancelled_and_cannot_be_replayed(installation):
    record = organization(installation, "Cancellation client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:cancel")
    workspace = resolve_organization_workspace(installation.owner, entity_id=record.entity_id)

    cancelled = cancel_sync_job(workspace=workspace, job_id=job.id, actor=installation.owner)
    repeated = process_sync_job(job_id=job.id, adapter=SuccessfulAdapter())

    assert cancelled.state == IntegrationJobState.CANCELLED
    assert repeated.state == IntegrationJobState.CANCELLED
    assert repeated.attempts == 0
    assert IntegrationObservation.objects.filter(job=job).count() == 0


@pytest.mark.django_db
def test_missing_remote_identity_becomes_reviewable_retirement_without_local_delete(installation):
    record = organization(installation, "Retirement client")
    source = connection(installation, record)
    first = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:present")
    process_sync_job(job_id=first.id, adapter=SuccessfulAdapter())
    second = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:missing")

    class EmptyAdapter(SuccessfulAdapter):
        def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
            return ProviderPage((), "", complete_types=("ipam.vlan",))

    process_sync_job(job_id=second.id, adapter=EmptyAdapter())

    retired = IntegrationObservation.objects.get(job=second)
    assert retired.state == "retired"
    assert retired.provenance == "provider_absence"
    assert retired.safe_projection == {}
    assert IntegrationConflict.objects.get(connection=source, remote_id="42").difference == "retired_remote"


@pytest.mark.django_db
def test_provider_conformance_rejects_unsupported_object_types(installation):
    record = organization(installation, "Conformance client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:bad-contract")

    class InvalidAdapter(SuccessfulAdapter):
        def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
            return ProviderPage((ProviderObservation("unknown.type", "1", "a" * 64),), "")

    failed = process_sync_job(job_id=job.id, adapter=InvalidAdapter())
    assert failed.state == IntegrationJobState.PENDING
    assert failed.last_error_code == "provider_response_invalid"


@pytest.mark.django_db
def test_rate_limited_job_uses_provider_retry_window(installation):
    record = organization(installation, "Rate limit client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:rate-limit")
    retry_at = timezone.now() + timedelta(minutes=7)

    class RateLimitedAdapter(SuccessfulAdapter):
        def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
            raise ProviderRateLimited(retry_at)

    retried = process_sync_job(job_id=job.id, adapter=RateLimitedAdapter())
    source.refresh_from_db()
    assert retried.state == IntegrationJobState.PENDING
    assert retried.last_error_code == "provider_rate_limited"
    assert retried.available_at == retry_at
    assert source.rate_limit_reset_at == retry_at


@pytest.mark.django_db
def test_large_job_history_remains_bounded_exact_workspace_and_fast(installation):
    first = organization(installation, "History client")
    second = organization(installation, "Sibling history client")
    source = connection(installation, first)
    sibling = connection(installation, second)
    for index in range(250):
        enqueue_sync(connection=source, trigger="manual", idempotency_key=f"history:first:{index:04d}")
        enqueue_sync(connection=sibling, trigger="manual", idempotency_key=f"history:sibling:{index:04d}")
    browser = Client()
    browser.force_login(installation.owner)
    path = reverse("organization-integration-job-list-create", kwargs={"organization_entity_id": first.entity_id})

    with CaptureQueriesContext(db_connection) as first_page_queries:
        first_page = browser.get(path, {"page": 1, "page_size": 50})
    started = perf_counter()
    with CaptureQueriesContext(db_connection) as last_page_queries:
        response = browser.get(path, {"page": 5, "page_size": 50})
    elapsed_ms = (perf_counter() - started) * 1000

    assert response.status_code == 200
    assert response.json()["count"] == 250
    assert len(response.json()["results"]) == 50
    assert {item["connection_id"] for item in response.json()["results"]} == {str(source.id)}
    assert first_page.status_code == 200
    assert abs(len(first_page_queries) - len(last_page_queries)) <= 1
    assert len(last_page_queries) <= 32
    assert elapsed_ms < 500
