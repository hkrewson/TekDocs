import json
import secrets
from datetime import timedelta
from uuid import uuid4

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.settings import api_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    AuditEvent,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    WebhookDeliveryState,
    WebhookDirection,
    WebhookEndpoint,
    WebhookInboundReceipt,
    WebhookOutboundDelivery,
)
from apps.core.outbox import OutboxTopic, enqueue_outbox_event
from apps.core.webhook_egress import WebhookEgressError, post_webhook, resolve_webhook_target, validate_webhook_url
from apps.core.webhook_secrets import encrypt_webhook_secret
from apps.core.webhooks import (
    accept_inbound_webhook,
    dispatch_due_webhooks,
    project_webhook_deliveries,
    signature,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Webhook MSP",
        owner_email="webhook-owner@example.com",
        owner_display_name="Webhook Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def organization(installation, name="Webhook client"):  # type: ignore[no-untyped-def]
    entity = Entity.objects.create_owned(
        tenant=installation.tenant, entity_type="organization", display_name=name
    )
    record = Organization.objects.create(tenant=installation.tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=installation.tenant, organization=record, kind="client")
    return record


def endpoint(installation, organization, *, direction, topics, secret=b"test-signing-secret"):  # type: ignore[no-untyped-def]
    endpoint_id = uuid4()
    return WebhookEndpoint.objects.create(
        id=endpoint_id,
        tenant=installation.tenant,
        organization=organization,
        direction=direction,
        name=f"{direction.title()} endpoint",
        url="https://hooks.example.com/events" if direction == WebhookDirection.OUTBOUND else "",
        topics=topics,
        secret_envelope=encrypt_webhook_secret(
            secret=secret,
            tenant_id=installation.tenant.id,
            endpoint_id=endpoint_id,
            generation=1,
        ),
        secret_prefix="test-signing-sec",
        created_by=installation.owner,
    )


def publication_event(installation, record):  # type: ignore[no-untyped-def]
    with transaction.atomic():
        return enqueue_outbox_event(
            tenant=installation.tenant,
            organization=record,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=uuid4(),
            idempotency_key=f"webhook:{uuid4()}",
            payload={"audience": "client_visible"},
        )


@pytest.mark.django_db
def test_management_api_issues_secret_once_and_keeps_audit_value_free(installation, monkeypatch):
    record = organization(installation)
    client = Client()
    client.force_login(installation.owner)
    monkeypatch.setattr("apps.core.webhooks.did_recently_authenticate", lambda _request: True)
    path = f"/api/v1/workspaces/organizations/{record.entity_id}/integrations/webhooks/endpoints"

    created = client.post(
        path,
        data=json.dumps(
            {
                "name": "PSA notifications",
                "direction": "outbound",
                "url": "https://hooks.example.com/tekdocs",
                "topics": [OutboxTopic.PUBLICATION_AVAILABLE],
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201
    issued = created.json()["signing_secret"]
    assert issued.startswith("tdwhsec_")
    listed = client.get(path)
    assert listed.status_code == 200
    assert "signing_secret" not in listed.json()[0]
    stored = WebhookEndpoint.objects.get()
    assert issued not in json.dumps(stored.secret_envelope)
    assert AuditEvent.objects.get(action="webhook_endpoint.created").metadata == {}
    assert created["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_inbound_signature_replay_tampering_and_expiration(installation):
    record = organization(installation)
    secret = b"inbound-signing-secret"
    inbound = endpoint(
        installation,
        record,
        direction=WebhookDirection.INBOUND,
        topics=["integration.ping"],
        secret=secret,
    )
    body = b'{"type":"integration.ping","data":{}}'
    delivery_id = "delivery-12345678"
    timestamp = int(timezone.now().timestamp())
    supplied = signature(secret, delivery_id=delivery_id, timestamp=timestamp, body=body)

    receipt = accept_inbound_webhook(
        endpoint_id=inbound.id,
        delivery_id=delivery_id,
        timestamp_value=str(timestamp),
        supplied_signature=supplied,
        body=body,
    )
    assert receipt.body_sha256 and not hasattr(receipt, "body")
    with pytest.raises(Exception, match="already been accepted"):
        accept_inbound_webhook(
            endpoint_id=inbound.id,
            delivery_id=delivery_id,
            timestamp_value=str(timestamp),
            supplied_signature=supplied,
            body=body,
        )
    with pytest.raises(Exception, match="invalid or expired"):
        accept_inbound_webhook(
            endpoint_id=inbound.id,
            delivery_id="delivery-tampered",
            timestamp_value=str(timestamp),
            supplied_signature=supplied,
            body=body + b" ",
        )
    old = int((timezone.now() - timedelta(minutes=6)).timestamp())
    with pytest.raises(Exception, match="invalid or expired"):
        accept_inbound_webhook(
            endpoint_id=inbound.id,
            delivery_id="delivery-expired",
            timestamp_value=str(old),
            supplied_signature=signature(secret, delivery_id="delivery-expired", timestamp=old, body=body),
            body=body,
        )


@pytest.mark.django_db
def test_outbound_projection_signing_retry_and_metadata_only_inspection(installation):
    record = organization(installation)
    outbound = endpoint(
        installation,
        record,
        direction=WebhookDirection.OUTBOUND,
        topics=[OutboxTopic.PUBLICATION_AVAILABLE],
    )
    event = publication_event(installation, record)
    assert project_webhook_deliveries(event) == 1
    captured = {}
    baseline_savepoints = len(connection.savepoint_ids)

    def reject_once(**request):  # type: ignore[no-untyped-def]
        assert len(connection.savepoint_ids) == baseline_savepoints
        captured.update(request)
        return 503

    now = timezone.now()
    assert dispatch_due_webhooks(tenant=installation.tenant, now=now, sender=reject_once) == 0
    delivery = WebhookOutboundDelivery.objects.get(endpoint=outbound)
    assert delivery.state == WebhookDeliveryState.PENDING
    assert delivery.attempts == 1
    assert delivery.last_error_code == "remote_temporary_failure"
    assert captured["headers"]["TekDocs-Webhook-Signature"] == signature(
        b"test-signing-secret",
        delivery_id=str(delivery.id),
        timestamp=int(now.timestamp()),
        body=captured["body"],
    )
    assert not hasattr(delivery, "response_body")

    assert dispatch_due_webhooks(
        tenant=installation.tenant,
        now=delivery.available_at + timedelta(seconds=1),
        sender=lambda **_request: 204,
    ) == 1
    delivery.refresh_from_db()
    assert delivery.state == WebhookDeliveryState.DELIVERED
    assert delivery.attempts == 2


@pytest.mark.django_db
def test_inbound_endpoint_failures_are_uniform_and_requests_are_throttled(installation, monkeypatch):
    record = organization(installation)
    inbound = endpoint(
        installation,
        record,
        direction=WebhookDirection.INBOUND,
        topics=["integration.ping"],
    )
    monkeypatch.setitem(api_settings.DEFAULT_THROTTLE_RATES, "inbound_webhooks", "1/m")
    cache.clear()
    client = Client(REMOTE_ADDR="192.0.2.40")
    headers = {
        "TekDocs-Webhook-Id": "delivery-12345678",
        "TekDocs-Webhook-Timestamp": str(int(timezone.now().timestamp())),
        "TekDocs-Webhook-Signature": "v1=" + "0" * 64,
    }

    known = client.post(
        reverse("inbound-webhook", kwargs={"endpoint_id": inbound.id}),
        data=b'{"type":"integration.ping","data":{}}',
        content_type="application/json",
        headers=headers,
    )
    unknown = client.post(
        reverse("inbound-webhook", kwargs={"endpoint_id": uuid4()}),
        data=b'{"type":"integration.ping","data":{}}',
        content_type="application/json",
        headers=headers,
    )
    throttled = client.post(
        reverse("inbound-webhook", kwargs={"endpoint_id": inbound.id}),
        data=b'{"type":"integration.ping","data":{}}',
        content_type="application/json",
        headers=headers,
    )

    assert known.status_code == unknown.status_code == 403
    assert known.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert known.json()["error"]["detail"] == unknown.json()["error"]["detail"]
    assert throttled.status_code == 429

    monkeypatch.setitem(api_settings.DEFAULT_THROTTLE_RATES, "inbound_webhooks", "100/m")
    monkeypatch.setitem(api_settings.DEFAULT_THROTTLE_RATES, "inbound_webhook_sources", "2/m")
    cache.clear()
    rotated = [
        client.post(
            reverse("inbound-webhook", kwargs={"endpoint_id": uuid4()}),
            data=b'{"type":"integration.ping","data":{}}',
            content_type="application/json",
            headers=headers,
        )
        for _index in range(3)
    ]
    assert [response.status_code for response in rotated] == [403, 403, 429]


@pytest.mark.parametrize(
    "value",
    [
        "http://hooks.example.com/path",
        "https://127.0.0.1/path",
        "https://hooks.example.com:8443/path",
        "https://hooks.example.com/path?token=secret",
        "https://user:pass@hooks.example.com/path",
    ],
)
def test_webhook_url_contract_rejects_unsafe_destinations(value):
    with pytest.raises(ValidationError):
        validate_webhook_url(value)


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_reject_cross_scope_and_receipt_mutation(installation):
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Webhook database guards require PostgreSQL")
    first = organization(installation, "First")
    second = organization(installation, "Second")
    inbound = endpoint(
        installation, first, direction=WebhookDirection.INBOUND, topics=["integration.ping"]
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        WebhookInboundReceipt.objects.create(
            tenant=installation.tenant,
            organization=second,
            endpoint=inbound,
            delivery_id="delivery-guarded",
            event_type="integration.ping",
            body_sha256="0" * 64,
        )
    receipt = WebhookInboundReceipt.objects.create(
        tenant=installation.tenant,
        organization=first,
        endpoint=inbound,
        delivery_id="delivery-valid",
        event_type="integration.ping",
        body_sha256="0" * 64,
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        WebhookInboundReceipt.objects.filter(pk=receipt.pk).update(event_type="changed")


def test_egress_error_codes_do_not_include_remote_values():
    error = WebhookEgressError("connection_failed")
    assert str(error) == "connection_failed"


def test_egress_rejects_any_private_dns_answer(monkeypatch):
    monkeypatch.setattr(
        "apps.core.webhook_egress.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(WebhookEgressError, match="destination_not_public"):
        resolve_webhook_target("https://hooks.example.com/events")


def test_egress_pins_public_address_and_tls_hostname_without_redirects(monkeypatch):
    observed = {}

    class Response:
        status = 202

        def close(self):
            observed["closed"] = True

    class Pool:
        def __init__(self, host, **kwargs):  # type: ignore[no-untyped-def]
            observed["host"] = host
            observed["pool"] = kwargs

        def urlopen(self, method, path, **kwargs):  # type: ignore[no-untyped-def]
            observed.update({"method": method, "path": path, "request": kwargs})
            return Response()

        def close(self):
            observed["pool_closed"] = True

    monkeypatch.setattr(
        "apps.core.webhook_egress.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("8.8.8.8", 443))],
    )
    monkeypatch.setattr("apps.core.webhook_egress.urllib3.HTTPSConnectionPool", Pool)
    assert post_webhook(url="https://hooks.example.com/events", body=b"{}", headers={"X-Test": "1"}) == 202
    assert observed["host"] == "8.8.8.8"
    assert observed["pool"]["assert_hostname"] == "hooks.example.com"
    assert observed["pool"]["server_hostname"] == "hooks.example.com"
    assert observed["request"]["redirect"] is False
    assert observed["request"]["headers"]["Host"] == "hooks.example.com"
