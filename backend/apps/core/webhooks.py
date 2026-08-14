from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_installation_member, require_permission

from .models import (
    AuditEvent,
    Organization,
    OutboxEvent,
    Tenant,
    WebhookDeliveryState,
    WebhookDirection,
    WebhookEndpoint,
    WebhookInboundReceipt,
    WebhookOutboundDelivery,
)
from .outbox import OutboxTopic
from .scoping import DataScope
from .webhook_egress import WebhookEgressError, post_webhook, validate_webhook_url
from .webhook_secrets import decrypt_webhook_secret, encrypt_webhook_secret

SIGNATURE_VERSION = "v1"
INBOUND_EVENT_TYPES = frozenset({"integration.ping"})
MAX_ENDPOINTS_PER_ORGANIZATION = 50
MAX_WEBHOOK_ATTEMPTS = 8
PROCESSING_LEASE = timedelta(minutes=5)
REPLAY_WINDOW = timedelta(minutes=5)
DELIVERY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")
SIGNATURE_PATTERN = re.compile(r"^v1=[0-9a-f]{64}$")

WebhookSender = Callable[..., int]


@dataclass(frozen=True, slots=True)
class ClaimedWebhookDelivery:
    delivery_id: UUID
    attempt: int
    locked_at: datetime
    url: str
    body: bytes
    headers: dict[str, str]


def _raw_secret() -> str:
    return "tdwhsec_" + base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def signature(secret: bytes, *, delivery_id: str, timestamp: int, body: bytes) -> str:
    message = f"{delivery_id}.{timestamp}.".encode("ascii") + body
    return f"{SIGNATURE_VERSION}=" + hmac.digest(secret, message, "sha256").hex()


def _verify_signature(
    secret: bytes,
    *,
    delivery_id: str,
    timestamp: int,
    body: bytes,
    supplied: str,
    now: datetime,
) -> None:
    if not SIGNATURE_PATTERN.fullmatch(supplied):
        raise PermissionDenied("The webhook signature is invalid or expired.")
    try:
        observed = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise PermissionDenied("The webhook signature is invalid or expired.") from exc
    if abs(now - observed) > REPLAY_WINDOW:
        raise PermissionDenied("The webhook signature is invalid or expired.")
    expected = signature(secret, delivery_id=delivery_id, timestamp=timestamp, body=body)
    if not hmac.compare_digest(expected, supplied):
        raise PermissionDenied("The webhook signature is invalid or expired.")


def _organization_for_permission(
    user: User, organization_entity_id: UUID, permission: PermissionKey
) -> tuple[Any, Organization]:
    context = require_installation_member(user)
    try:
        organization = (
            Organization.scoped.for_tenant(context.tenant)
            .select_related("entity")
            .get(entity_id=organization_entity_id, entity__archived_at__isnull=True)
        )
    except Organization.DoesNotExist as exc:
        raise NotFound("The organization is unavailable.") from exc
    require_permission(user, permission, organization=organization)
    return context, organization


def _require_recent_session(request: Any) -> None:
    if getattr(request, "auth", None) is not None or getattr(request, "api_token", None) is not None:
        raise PermissionDenied("API tokens cannot manage webhook signing keys.")
    if not did_recently_authenticate(request._request):
        raise PermissionDenied("Recent password or MFA reauthentication is required.")


def authorize_webhook_management(*, request: Any, organization_entity_id: UUID) -> None:
    _require_recent_session(request)
    _organization_for_permission(request.user, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE)


def _normalized_topics(direction: WebhookDirection, topics: list[str]) -> list[str]:
    allowed = (
        frozenset(topic.value for topic in OutboxTopic)
        if direction == WebhookDirection.OUTBOUND
        else INBOUND_EVENT_TYPES
    )
    normalized = sorted(set(topics))
    if not normalized or len(normalized) > 20 or any(topic not in allowed for topic in normalized):
        raise ValidationError({"topics": "Select one or more supported webhook event types."})
    return normalized


@transaction.atomic
def create_webhook_endpoint(
    *,
    request: Any,
    organization_entity_id: UUID,
    name: str,
    direction: WebhookDirection,
    url: str,
    topics: list[str],
) -> tuple[WebhookEndpoint, str]:
    _require_recent_session(request)
    context, organization = _organization_for_permission(
        request.user, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE
    )
    endpoint_count = WebhookEndpoint.scoped.for_tenant(context.tenant).filter(organization=organization).count()
    if endpoint_count >= MAX_ENDPOINTS_PER_ORGANIZATION:
        raise ValidationError({"endpoint": "This organization has reached the webhook endpoint limit."})
    normalized_name = " ".join(name.split())
    if not normalized_name or any(ord(character) < 32 for character in normalized_name):
        raise ValidationError({"name": "Enter a visible endpoint name without control characters."})
    normalized_url = validate_webhook_url(url) if direction == WebhookDirection.OUTBOUND else ""
    normalized_topics = _normalized_topics(direction, topics)
    endpoint_id = uuid4()
    raw_secret = _raw_secret()
    endpoint = WebhookEndpoint.objects.create(
        id=endpoint_id,
        tenant=context.tenant,
        organization=organization,
        direction=direction,
        name=normalized_name,
        url=normalized_url,
        topics=normalized_topics,
        secret_envelope=encrypt_webhook_secret(
            secret=raw_secret.encode(),
            tenant_id=context.tenant.id,
            endpoint_id=endpoint_id,
            generation=1,
        ),
        secret_prefix=raw_secret[:16],
        created_by=request.user,
    )
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=request.user,
        action="webhook_endpoint.created",
        entity_id=endpoint.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    return endpoint, raw_secret


def endpoints_for_organization(*, user: User, organization_entity_id: UUID) -> tuple[Organization, Any]:
    context, organization = _organization_for_permission(user, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
    return organization, WebhookEndpoint.scoped.for_tenant(context.tenant).filter(organization=organization)


@transaction.atomic
def set_webhook_endpoint_active(
    *, request: Any, organization_entity_id: UUID, endpoint_id: UUID, active: bool
) -> WebhookEndpoint:
    _require_recent_session(request)
    context, organization = _organization_for_permission(
        request.user, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE
    )
    endpoint = (
        WebhookEndpoint.scoped.for_tenant(context.tenant)
        .select_for_update()
        .filter(pk=endpoint_id, organization=organization)
        .first()
    )
    if endpoint is None:
        raise PermissionDenied("The webhook signature is invalid or expired.")
    if endpoint.active != active:
        endpoint.active = active
        endpoint.save(update_fields=("active", "updated_at"))
        AuditEvent.objects.create(
            tenant=context.tenant,
            actor=request.user,
            action="webhook_endpoint.activated" if active else "webhook_endpoint.deactivated",
            entity_id=endpoint.id,
            request_id=getattr(request, "request_id", None),
            metadata={},
        )
    return endpoint


@transaction.atomic
def rotate_webhook_secret(
    *, request: Any, organization_entity_id: UUID, endpoint_id: UUID
) -> tuple[WebhookEndpoint, str]:
    _require_recent_session(request)
    context, organization = _organization_for_permission(
        request.user, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE
    )
    endpoint = (
        WebhookEndpoint.scoped.for_tenant(context.tenant)
        .select_for_update()
        .filter(pk=endpoint_id, organization=organization)
        .first()
    )
    if endpoint is None:
        raise NotFound("The webhook endpoint is unavailable.")
    raw_secret = _raw_secret()
    endpoint.secret_generation += 1
    endpoint.secret_envelope = encrypt_webhook_secret(
        secret=raw_secret.encode(),
        tenant_id=context.tenant.id,
        endpoint_id=endpoint.id,
        generation=endpoint.secret_generation,
    )
    endpoint.secret_prefix = raw_secret[:16]
    endpoint.save(update_fields=("secret_generation", "secret_envelope", "secret_prefix", "updated_at"))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=request.user,
        action="webhook_endpoint.secret_rotated",
        entity_id=endpoint.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    return endpoint, raw_secret


def project_webhook_deliveries(event: OutboxEvent) -> int:
    endpoints = list(
        WebhookEndpoint.scoped.for_tenant(event.tenant)
        .filter(organization=event.organization, direction=WebhookDirection.OUTBOUND, active=True)
        .order_by("id")[: MAX_ENDPOINTS_PER_ORGANIZATION + 1]
    )
    if len(endpoints) > MAX_ENDPOINTS_PER_ORGANIZATION:
        raise RuntimeError("Webhook endpoint projection exceeded its reviewed bound.")
    matches = [endpoint for endpoint in endpoints if event.topic in endpoint.topics]
    WebhookOutboundDelivery.objects.bulk_create(
        [
            WebhookOutboundDelivery(
                tenant=event.tenant,
                organization=event.organization,
                endpoint=endpoint,
                event=event,
            )
            for endpoint in matches
        ],
        ignore_conflicts=True,
    )
    return len(matches)


def _delivery_payload(delivery: WebhookOutboundDelivery) -> bytes:
    event = delivery.event
    return _canonical_json(
        {
            "api_version": "v1",
            "delivery_id": str(delivery.id),
            "event": {
                "id": str(event.id),
                "occurred_at": event.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "organization_id": str(delivery.organization.entity_id),
                "payload": event.payload,
                "subject_id": str(event.subject_id),
                "topic": event.topic,
            },
        }
    )


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * (2 ** max(attempts - 1, 0)), 60 * 60))


def _response_error(status: int) -> tuple[str, bool]:
    if status in {408, 425, 429} or status >= 500:
        return "remote_temporary_failure", False
    return "remote_rejected", True


def _claim_delivery(*, tenant: Tenant, delivery_id: UUID, now: datetime) -> ClaimedWebhookDelivery | None:
    with transaction.atomic():
        delivery = (
            WebhookOutboundDelivery.scoped.for_tenant(tenant)
            .select_for_update(skip_locked=connection.vendor == "postgresql")
            .select_related("endpoint", "event", "organization__entity")
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None or delivery.state in {
            WebhookDeliveryState.DELIVERED,
            WebhookDeliveryState.DEAD_LETTER,
        }:
            return None
        if delivery.state == WebhookDeliveryState.PROCESSING and (
            delivery.locked_at is None or delivery.locked_at > now - PROCESSING_LEASE
        ):
            return None
        if delivery.state == WebhookDeliveryState.PENDING and delivery.available_at > now:
            return None
        if not delivery.endpoint.active:
            delivery.state = WebhookDeliveryState.DEAD_LETTER
            delivery.last_error_code = "endpoint_inactive"
            delivery.locked_at = None
            delivery.save(update_fields=("state", "last_error_code", "locked_at"))
            return None
        delivery.state = WebhookDeliveryState.PROCESSING
        delivery.locked_at = now
        delivery.last_attempt_at = now
        delivery.attempts += 1
        delivery.response_status = None
        delivery.last_error_code = ""
        delivery.save(
            update_fields=(
                "state",
                "locked_at",
                "last_attempt_at",
                "attempts",
                "response_status",
                "last_error_code",
            )
        )
        body = _delivery_payload(delivery)
        timestamp = int(now.timestamp())
        secret = decrypt_webhook_secret(
            envelope_payload=delivery.endpoint.secret_envelope,
            tenant_id=tenant.id,
            endpoint_id=delivery.endpoint.id,
            generation=delivery.endpoint.secret_generation,
        )
        headers = {
            "TekDocs-Webhook-Id": str(delivery.id),
            "TekDocs-Webhook-Timestamp": str(timestamp),
            "TekDocs-Webhook-Signature": signature(
                secret,
                delivery_id=str(delivery.id),
                timestamp=timestamp,
                body=body,
            ),
            "User-Agent": "TekDocs-Webhooks/0.6.3",
        }
        return ClaimedWebhookDelivery(
            delivery_id=delivery.id,
            attempt=delivery.attempts,
            locked_at=now,
            url=delivery.endpoint.url,
            body=body,
            headers=headers,
        )


def _record_delivery_outcome(
    *, tenant: Tenant, claim: ClaimedWebhookDelivery, now: datetime, status: int | None, error_code: str
) -> bool:
    with transaction.atomic():
        delivery = (
            WebhookOutboundDelivery.scoped.for_tenant(tenant)
            .select_for_update()
            .filter(
                pk=claim.delivery_id,
                state=WebhookDeliveryState.PROCESSING,
                attempts=claim.attempt,
                locked_at=claim.locked_at,
            )
            .first()
        )
        if delivery is None:
            return False
        delivery.response_status = status
        delivery.last_error_code = error_code
        permanent = False
        if status is not None and not 200 <= status < 300:
            delivery.last_error_code, permanent = _response_error(status)
        if not delivery.last_error_code:
            delivery.state = WebhookDeliveryState.DELIVERED
            delivery.delivered_at = now
            delivery.locked_at = None
            delivery.save(update_fields=("state", "delivered_at", "locked_at", "response_status", "last_error_code"))
            return True
        exhausted = delivery.attempts >= MAX_WEBHOOK_ATTEMPTS
        delivery.state = WebhookDeliveryState.DEAD_LETTER if permanent or exhausted else WebhookDeliveryState.PENDING
        delivery.available_at = now + _retry_delay(delivery.attempts)
        delivery.locked_at = None
        delivery.save(
            update_fields=(
                "state",
                "available_at",
                "locked_at",
                "response_status",
                "last_error_code",
            )
        )
        return False


def _dispatch_delivery(*, tenant: Tenant, delivery_id: UUID, now: datetime, sender: WebhookSender) -> bool:
    claim = _claim_delivery(tenant=tenant, delivery_id=delivery_id, now=now)
    if claim is None:
        return False
    status: int | None = None
    error_code = ""
    try:
        status = sender(url=claim.url, body=claim.body, headers=claim.headers)
    except WebhookEgressError as exc:
        error_code = str(exc)
    except Exception:
        error_code = "delivery_failed"
    return _record_delivery_outcome(
        tenant=tenant,
        claim=claim,
        now=now,
        status=status,
        error_code=error_code,
    )


def dispatch_due_webhooks(
    *, tenant: Tenant, batch_size: int = 50, now: datetime | None = None, sender: WebhookSender = post_webhook
) -> int:
    if not 1 <= batch_size <= 200:
        raise ValueError("Webhook batch size must be between 1 and 200.")
    current = now or timezone.now()
    stale_before = current - PROCESSING_LEASE
    delivery_ids = list(
        WebhookOutboundDelivery.scoped.for_tenant(tenant)
        .filter(
            Q(state=WebhookDeliveryState.PENDING, available_at__lte=current)
            | Q(state=WebhookDeliveryState.PROCESSING, locked_at__lte=stale_before)
        )
        .order_by("available_at", "created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    return sum(
        _dispatch_delivery(tenant=tenant, delivery_id=delivery_id, now=current, sender=sender)
        for delivery_id in delivery_ids
    )


def accept_inbound_webhook(
    *, endpoint_id: UUID, delivery_id: str, timestamp_value: str, supplied_signature: str, body: bytes
) -> WebhookInboundReceipt:
    if not DELIVERY_ID_PATTERN.fullmatch(delivery_id):
        raise PermissionDenied("The webhook signature is invalid or expired.")
    try:
        timestamp = int(timestamp_value)
    except ValueError as exc:
        raise PermissionDenied("The webhook signature is invalid or expired.") from exc
    endpoint = WebhookEndpoint.objects.filter(
        pk=endpoint_id,
        direction=WebhookDirection.INBOUND,
        active=True,
    ).first()
    if endpoint is None:
        raise PermissionDenied("The webhook signature is invalid or expired.")
    secret = decrypt_webhook_secret(
        envelope_payload=endpoint.secret_envelope,
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint.id,
        generation=endpoint.secret_generation,
    )
    _verify_signature(
        secret,
        delivery_id=delivery_id,
        timestamp=timestamp,
        body=body,
        supplied=supplied_signature,
        now=timezone.now(),
    )
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError({"body": "The webhook body must be valid JSON."}) from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"type", "data"}
        or payload.get("type") not in INBOUND_EVENT_TYPES
        or payload.get("data") != {}
    ):
        raise ValidationError({"body": "The inbound webhook event is not supported."})
    from .rls import OrganizationRLSMode, rls_scope

    try:
        with rls_scope(DataScope.tenant(endpoint.tenant_id), organization_mode=OrganizationRLSMode.MSP_ONLY):
            with transaction.atomic():
                return WebhookInboundReceipt.objects.create(
                    tenant_id=endpoint.tenant_id,
                    organization_id=endpoint.organization_id,
                    endpoint_id=endpoint.id,
                    delivery_id=delivery_id,
                    event_type=payload["type"],
                    body_sha256=hashlib.sha256(body).hexdigest(),
                )
    except IntegrityError as exc:
        raise PermissionDenied("The webhook delivery has already been accepted.") from exc


def deliveries_for_organization(*, user: User, organization_entity_id: UUID) -> tuple[Organization, Any]:
    context, organization = _organization_for_permission(user, organization_entity_id, PermissionKey.INTEGRATIONS_VIEW)
    return (
        organization,
        WebhookOutboundDelivery.scoped.for_scope(DataScope.organization(context.tenant, organization)).select_related(
            "endpoint", "event"
        ),
    )


@transaction.atomic
def retry_webhook_delivery(
    *, request: Any, organization_entity_id: UUID, delivery_id: UUID, reason: str
) -> WebhookOutboundDelivery:
    _require_recent_session(request)
    context, organization = _organization_for_permission(
        request.user, organization_entity_id, PermissionKey.INTEGRATIONS_MANAGE
    )
    normalized_reason = " ".join(reason.split())
    if not 5 <= len(normalized_reason) <= 200:
        raise ValidationError({"reason": "Enter a retry reason between 5 and 200 characters."})
    delivery = (
        WebhookOutboundDelivery.scoped.for_scope(DataScope.organization(context.tenant, organization))
        .select_for_update()
        .filter(pk=delivery_id, state=WebhookDeliveryState.DEAD_LETTER)
        .first()
    )
    if delivery is None:
        raise NotFound("The webhook delivery is unavailable.")
    if not delivery.endpoint.active:
        raise ValidationError({"delivery": "Activate the endpoint before retrying this delivery."})
    delivery.state = WebhookDeliveryState.PENDING
    delivery.available_at = timezone.now()
    delivery.last_error_code = ""
    delivery.response_status = None
    delivery.save(update_fields=("state", "available_at", "last_error_code", "response_status"))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=request.user,
        action="webhook_delivery.retry_requested",
        entity_id=delivery.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    return delivery
