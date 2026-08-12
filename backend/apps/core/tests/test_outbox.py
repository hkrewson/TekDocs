from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import (
    Entity,
    Organization,
    OutboxDeliveryReceipt,
    OutboxEvent,
    OutboxEventState,
    Tenant,
)
from apps.core.outbox import (
    MAX_DELIVERY_ATTEMPTS,
    OutboxDeliveryFailure,
    OutboxTopic,
    dispatch_due_outbox_events,
    enqueue_outbox_event,
)


def _organization(tenant: Tenant) -> Organization:
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name="Outbox client")
    return Organization.objects.create(tenant=tenant, entity=entity)


def _enqueue(tenant: Tenant, organization: Organization, *, key: str = "publication:1") -> OutboxEvent:
    with transaction.atomic():
        return enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=uuid4(),
            idempotency_key=key,
            payload={"audience": "client_visible"},
        )


@pytest.mark.django_db(transaction=True)
def test_enqueue_requires_transaction_and_rejects_non_allowlisted_payload():
    tenant = Tenant.objects.create(name="Outbox tenant", slug=f"outbox-{uuid4()}")
    organization = _organization(tenant)
    subject_id = uuid4()

    with pytest.raises(RuntimeError, match="transaction"):
        enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=subject_id,
            idempotency_key="outside-transaction",
            payload={"audience": "client_visible"},
        )

    with transaction.atomic(), pytest.raises(ValidationError):
        enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=subject_id,
            idempotency_key="contains-secret",
            payload={"audience": "client_visible", "password": "must-not-persist"},
        )
    assert not OutboxEvent.objects.filter(idempotency_key="contains-secret").exists()


@pytest.mark.django_db
def test_enqueue_is_transactional_and_idempotency_key_cannot_be_reinterpreted():
    tenant = Tenant.objects.create(name="Transactional tenant", slug=f"transactional-{uuid4()}")
    organization = _organization(tenant)
    subject_id = uuid4()

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            enqueue_outbox_event(
                tenant=tenant,
                organization=organization,
                topic=OutboxTopic.PUBLICATION_AVAILABLE,
                subject_id=subject_id,
                idempotency_key="rollback-key",
                payload={"audience": "client_visible"},
            )
            raise RuntimeError("rollback")
    assert not OutboxEvent.objects.filter(idempotency_key="rollback-key").exists()

    with transaction.atomic():
        first = enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=subject_id,
            idempotency_key="stable-key",
            payload={"audience": "client_visible"},
        )
        same = enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_AVAILABLE,
            subject_id=subject_id,
            idempotency_key="stable-key",
            payload={"audience": "client_visible"},
        )
    assert same.id == first.id

    with transaction.atomic(), pytest.raises(ValidationError):
        enqueue_outbox_event(
            tenant=tenant,
            organization=organization,
            topic=OutboxTopic.PUBLICATION_WITHDRAWN,
            subject_id=subject_id,
            idempotency_key="stable-key",
            payload={"audience": "client_visible"},
        )


@pytest.mark.django_db
def test_dispatch_is_idempotent_and_creates_one_append_only_receipt():
    tenant = Tenant.objects.create(name="Delivery tenant", slug=f"delivery-{uuid4()}")
    organization = _organization(tenant)
    event = _enqueue(tenant, organization)
    handled: list[str] = []

    assert dispatch_due_outbox_events(tenant=tenant, handler=lambda item: handled.append(item.topic)) == 1
    assert dispatch_due_outbox_events(tenant=tenant, handler=lambda item: handled.append(item.topic)) == 0
    event.refresh_from_db()
    assert event.state == OutboxEventState.DELIVERED
    assert event.attempts == 1
    assert event.delivered_at is not None
    assert handled == [OutboxTopic.PUBLICATION_AVAILABLE.value]
    receipt = OutboxDeliveryReceipt.objects.get(event=event)
    with pytest.raises(ValidationError, match="append-only"):
        receipt.delete()


@pytest.mark.django_db
def test_dispatch_retries_with_safe_errors_then_dead_letters():
    tenant = Tenant.objects.create(name="Retry tenant", slug=f"retry-{uuid4()}")
    organization = _organization(tenant)
    event = _enqueue(tenant, organization)
    current = timezone.now()

    def fail(_event: OutboxEvent) -> None:
        raise OutboxDeliveryFailure("temporary_failure")

    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        current += timedelta(hours=1)
        assert dispatch_due_outbox_events(tenant=tenant, now=current, handler=fail) == 0
        event.refresh_from_db()
        assert event.attempts == attempt
        expected = OutboxEventState.DEAD_LETTER if attempt == MAX_DELIVERY_ATTEMPTS else OutboxEventState.PENDING
        assert event.state == expected
        assert event.last_error_code == "temporary_failure"
        assert event.locked_at is None

    assert not OutboxDeliveryReceipt.objects.filter(event=event).exists()


@pytest.mark.django_db
def test_dispatch_does_not_persist_exception_messages_and_recovers_stale_claims():
    tenant = Tenant.objects.create(name="Safe failure tenant", slug=f"safe-failure-{uuid4()}")
    organization = _organization(tenant)
    event = _enqueue(tenant, organization)
    current = timezone.now()
    event.state = OutboxEventState.PROCESSING
    event.locked_at = current - timedelta(minutes=6)
    event.save(update_fields=("state", "locked_at"))

    def fail(_event: OutboxEvent) -> None:
        raise RuntimeError("credential-value-that-must-not-persist")

    assert dispatch_due_outbox_events(tenant=tenant, now=current, handler=fail) == 0
    event.refresh_from_db()
    assert event.state == OutboxEventState.PENDING
    assert event.last_error_code == "delivery_failed"
    assert "credential" not in event.last_error_code
