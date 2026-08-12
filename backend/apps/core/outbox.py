from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Organization, OutboxDeliveryReceipt, OutboxEvent, OutboxEventState, Tenant

OUTBOX_CONSUMER = "notification-router-v1"
MAX_DELIVERY_ATTEMPTS = 5
PROCESSING_LEASE = timedelta(minutes=5)


class OutboxTopic(StrEnum):
    INVITATION_ISSUED = "client_invitation.issued"
    INVITATION_ACCEPTED = "client_invitation.accepted"
    PUBLICATION_AVAILABLE = "document_publication.available"
    PUBLICATION_WITHDRAWN = "document_publication.withdrawn"


_ALLOWED_PAYLOADS: dict[OutboxTopic, dict[str, frozenset[str]]] = {
    OutboxTopic.INVITATION_ISSUED: {"role": frozenset({"client_administrator", "client_user"})},
    OutboxTopic.INVITATION_ACCEPTED: {"role": frozenset({"client_administrator", "client_user"})},
    OutboxTopic.PUBLICATION_AVAILABLE: {"audience": frozenset({"client_visible"})},
    OutboxTopic.PUBLICATION_WITHDRAWN: {"audience": frozenset({"client_visible"})},
}


class OutboxDeliveryFailure(RuntimeError):
    def __init__(self, error_code: str = "delivery_failed") -> None:
        if error_code not in {"delivery_failed", "handler_unavailable", "temporary_failure"}:
            error_code = "delivery_failed"
        self.error_code = error_code
        super().__init__(error_code)


def _validated_payload(topic: OutboxTopic, payload: Mapping[str, Any]) -> dict[str, str]:
    schema = _ALLOWED_PAYLOADS[topic]
    if set(payload) != set(schema):
        raise ValidationError("The outbox payload does not match the topic contract.")
    normalized: dict[str, str] = {}
    for field, choices in schema.items():
        value = payload[field]
        if not isinstance(value, str) or value not in choices:
            raise ValidationError("The outbox payload does not match the topic contract.")
        normalized[field] = value
    return normalized


def enqueue_outbox_event(
    *,
    tenant: Tenant,
    organization: Organization | None,
    topic: OutboxTopic,
    subject_id: UUID,
    idempotency_key: str,
    payload: Mapping[str, Any],
) -> OutboxEvent:
    """Persist an allowlisted event in the caller's current database transaction."""

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Outbox events must be enqueued inside a database transaction.")
    if organization is None:
        raise ValidationError("The outbox topic requires organization scope.")
    if organization.tenant_id != tenant.id:
        raise ValidationError("The outbox organization must belong to the event tenant.")
    clean_key = idempotency_key.strip()
    if not clean_key or len(clean_key) > 200:
        raise ValidationError("A bounded outbox idempotency key is required.")
    normalized_payload = _validated_payload(topic, payload)
    event, created = OutboxEvent.objects.get_or_create(
        tenant=tenant,
        idempotency_key=clean_key,
        defaults={
            "organization": organization,
            "topic": topic.value,
            "subject_id": subject_id,
            "payload": normalized_payload,
        },
    )
    if not created and (
        event.organization_id != organization.id
        or event.topic != topic.value
        or event.subject_id != subject_id
        or event.payload != normalized_payload
    ):
        raise ValidationError("The outbox idempotency key is already bound to a different event.")
    return event


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(15 * (2 ** max(attempts - 1, 0)), 15 * 60))


def _default_handler(event: OutboxEvent) -> None:
    OutboxTopic(event.topic)


def _dispatch_one(
    *,
    tenant: Tenant,
    event_id: UUID,
    now: datetime,
    handler: Callable[[OutboxEvent], None],
) -> bool:
    with transaction.atomic():
        event = (
            OutboxEvent.scoped.for_tenant(tenant)
            .select_for_update(skip_locked=connection.vendor == "postgresql")
            .filter(pk=event_id)
            .first()
        )
        if event is None or event.state in {OutboxEventState.DELIVERED, OutboxEventState.DEAD_LETTER}:
            return False
        if event.state == OutboxEventState.PROCESSING and (
            event.locked_at is None or event.locked_at > now - PROCESSING_LEASE
        ):
            return False
        if event.state == OutboxEventState.PENDING and event.available_at > now:
            return False

        event.state = OutboxEventState.PROCESSING
        event.locked_at = now
        event.attempts += 1
        event.last_error_code = ""
        event.save(update_fields=("state", "locked_at", "attempts", "last_error_code"))

        try:
            with transaction.atomic():
                if not OutboxDeliveryReceipt.objects.filter(event=event, consumer=OUTBOX_CONSUMER).exists():
                    handler(event)
                    OutboxDeliveryReceipt.objects.create(
                        tenant=event.tenant,
                        event=event,
                        consumer=OUTBOX_CONSUMER,
                    )
        except OutboxDeliveryFailure as exc:
            event.state = (
                OutboxEventState.DEAD_LETTER
                if event.attempts >= MAX_DELIVERY_ATTEMPTS
                else OutboxEventState.PENDING
            )
            event.locked_at = None
            event.available_at = now + _retry_delay(event.attempts)
            event.last_error_code = exc.error_code
            event.save(update_fields=("state", "locked_at", "available_at", "last_error_code"))
            return False
        except Exception:
            event.state = (
                OutboxEventState.DEAD_LETTER
                if event.attempts >= MAX_DELIVERY_ATTEMPTS
                else OutboxEventState.PENDING
            )
            event.locked_at = None
            event.available_at = now + _retry_delay(event.attempts)
            event.last_error_code = "delivery_failed"
            event.save(update_fields=("state", "locked_at", "available_at", "last_error_code"))
            return False

        event.state = OutboxEventState.DELIVERED
        event.locked_at = None
        event.delivered_at = now
        event.last_error_code = ""
        event.save(update_fields=("state", "locked_at", "delivered_at", "last_error_code"))
        return True


def dispatch_due_outbox_events(
    *,
    tenant: Tenant,
    batch_size: int = 50,
    now: datetime | None = None,
    handler: Callable[[OutboxEvent], None] | None = None,
) -> int:
    if batch_size < 1 or batch_size > 500:
        raise ValueError("Outbox batch size must be between 1 and 500.")
    current_time = now or timezone.now()
    stale_before = current_time - PROCESSING_LEASE
    due_ids = list(
        OutboxEvent.scoped.for_tenant(tenant)
        .filter(
            Q(state=OutboxEventState.PENDING, available_at__lte=current_time)
            | Q(state=OutboxEventState.PROCESSING, locked_at__lte=stale_before)
        )
        .order_by("available_at", "created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    delivery_handler = handler or _default_handler
    return sum(
        _dispatch_one(tenant=tenant, event_id=event_id, now=current_time, handler=delivery_handler)
        for event_id in due_ids
    )
