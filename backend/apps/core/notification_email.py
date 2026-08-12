from __future__ import annotations

import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.accounts.policy import require_installation_member

from .email import send_notification_email
from .models import (
    NotificationEmailDelivery,
    NotificationEmailState,
    NotificationPreference,
    NotificationSurface,
    Tenant,
)
from .notifications import authorize_notification
from .outbox import OutboxTopic

MAX_EMAIL_ATTEMPTS = 5
EMAIL_PROCESSING_LEASE = timedelta(minutes=5)


class NotificationEmailError(StrEnum):
    SMTP_UNAVAILABLE = "smtp_unavailable"
    SMTP_REJECTED = "smtp_rejected"
    RECIPIENT_INVALID = "recipient_invalid"
    RECIPIENT_REJECTED = "recipient_rejected"
    DELIVERY_FAILED = "delivery_failed"


@dataclass(frozen=True, slots=True)
class ClaimedEmail:
    delivery_id: UUID
    locked_at: datetime
    recipient: str
    title: str
    message: str


EmailSender = Callable[..., int]


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * (2 ** max(attempts - 1, 0)), 30 * 60))


def _preference_allows(preference: NotificationPreference, topic: OutboxTopic) -> bool:
    if not preference.email_enabled:
        return False
    if topic in {OutboxTopic.INVITATION_ISSUED, OutboxTopic.INVITATION_ACCEPTED}:
        return preference.invitation_events
    return preference.publication_events


def preference_for(*, tenant: Tenant, user_id: UUID, surface: NotificationSurface | str) -> NotificationPreference:
    preference, _created = NotificationPreference.objects.get_or_create(
        tenant=tenant,
        user_id=user_id,
        surface=surface,
    )
    return preference


def _suppress(delivery: NotificationEmailDelivery, *, error_code: str = "") -> None:
    delivery.state = NotificationEmailState.SUPPRESSED
    delivery.locked_at = None
    delivery.last_error_code = error_code
    delivery.save(update_fields=("state", "locked_at", "last_error_code"))


def _claim_one(*, tenant: Tenant, delivery_id: UUID, now: datetime) -> ClaimedEmail | None:
    with transaction.atomic():
        delivery = (
            NotificationEmailDelivery.scoped.for_tenant(tenant)
            .select_for_update(skip_locked=connection.vendor == "postgresql")
            .select_related("notification__event", "notification__organization", "recipient")
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None or delivery.state in {
            NotificationEmailState.DELIVERED,
            NotificationEmailState.SUPPRESSED,
            NotificationEmailState.DEAD_LETTER,
        }:
            return None
        if delivery.state == NotificationEmailState.PROCESSING and (
            delivery.locked_at is None or delivery.locked_at > now - EMAIL_PROCESSING_LEASE
        ):
            return None
        if delivery.state == NotificationEmailState.PENDING and delivery.available_at > now:
            return None

        delivery.state = NotificationEmailState.PROCESSING
        delivery.locked_at = now
        delivery.attempts += 1
        delivery.last_error_code = ""
        delivery.save(update_fields=("state", "locked_at", "attempts", "last_error_code"))

        try:
            context = require_installation_member(delivery.recipient)
        except APIException:
            _suppress(delivery)
            return None
        if context.tenant.id != tenant.id or context.surface != delivery.surface or not delivery.recipient.is_active:
            _suppress(delivery)
            return None
        projection = authorize_notification(delivery.notification, context)
        if projection is None:
            _suppress(delivery)
            return None
        preference = preference_for(tenant=tenant, user_id=delivery.recipient_id, surface=delivery.surface)
        if not _preference_allows(preference, OutboxTopic(delivery.notification.event.topic)):
            _suppress(delivery)
            return None
        return ClaimedEmail(
            delivery_id=delivery.id,
            locked_at=now,
            recipient=delivery.recipient.email,
            title=projection.title,
            message=projection.message,
        )


def _finish(
    *,
    tenant: Tenant,
    claim: ClaimedEmail,
    now: datetime,
    error_code: NotificationEmailError | None = None,
    permanent: bool = False,
) -> bool:
    with transaction.atomic():
        delivery = (
            NotificationEmailDelivery.scoped.for_tenant(tenant)
            .select_for_update()
            .filter(
                pk=claim.delivery_id,
                state=NotificationEmailState.PROCESSING,
                locked_at=claim.locked_at,
            )
            .first()
        )
        if delivery is None:
            return False
        delivery.locked_at = None
        if error_code is None:
            delivery.state = NotificationEmailState.DELIVERED
            delivery.delivered_at = now
            delivery.last_error_code = ""
        else:
            delivery.state = (
                NotificationEmailState.DEAD_LETTER
                if permanent or delivery.attempts >= MAX_EMAIL_ATTEMPTS
                else NotificationEmailState.PENDING
            )
            delivery.available_at = now + _retry_delay(delivery.attempts)
            delivery.last_error_code = error_code.value
        delivery.save(
            update_fields=("state", "locked_at", "delivered_at", "available_at", "last_error_code")
        )
        return error_code is None


def _send_claim(*, tenant: Tenant, claim: ClaimedEmail, now: datetime, sender: EmailSender) -> bool:
    try:
        accepted = sender(
            recipient=claim.recipient,
            title=claim.title,
            message=claim.message,
            app_url=settings.TEKDOCS_PUBLIC_URL,
            delivery_id=str(claim.delivery_id),
        )
        if accepted != 1:
            return _finish(
                tenant=tenant,
                claim=claim,
                now=now,
                error_code=NotificationEmailError.SMTP_UNAVAILABLE,
            )
    except smtplib.SMTPRecipientsRefused:
        return _finish(
            tenant=tenant,
            claim=claim,
            now=now,
            error_code=NotificationEmailError.RECIPIENT_REJECTED,
            permanent=True,
        )
    except smtplib.SMTPResponseException as exc:
        return _finish(
            tenant=tenant,
            claim=claim,
            now=now,
            error_code=NotificationEmailError.SMTP_REJECTED,
            permanent=exc.smtp_code >= 500,
        )
    except ValidationError:
        return _finish(
            tenant=tenant,
            claim=claim,
            now=now,
            error_code=NotificationEmailError.RECIPIENT_INVALID,
            permanent=True,
        )
    except (OSError, TimeoutError, smtplib.SMTPException):
        return _finish(
            tenant=tenant,
            claim=claim,
            now=now,
            error_code=NotificationEmailError.SMTP_UNAVAILABLE,
        )
    except Exception:
        return _finish(
            tenant=tenant,
            claim=claim,
            now=now,
            error_code=NotificationEmailError.DELIVERY_FAILED,
        )
    return _finish(tenant=tenant, claim=claim, now=now)


def dispatch_due_notification_emails(
    *,
    tenant: Tenant,
    batch_size: int = 50,
    now: datetime | None = None,
    sender: EmailSender = send_notification_email,
) -> int:
    if batch_size < 1 or batch_size > 500:
        raise ValueError("Notification email batch size must be between 1 and 500.")
    current_time = now or timezone.now()
    stale_before = current_time - EMAIL_PROCESSING_LEASE
    due_ids = list(
        NotificationEmailDelivery.scoped.for_tenant(tenant)
        .filter(
            Q(state=NotificationEmailState.PENDING, available_at__lte=current_time)
            | Q(state=NotificationEmailState.PROCESSING, locked_at__lte=stale_before)
        )
        .order_by("available_at", "created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    delivered = 0
    for delivery_id in due_ids:
        claim = _claim_one(tenant=tenant, delivery_id=delivery_id, now=current_time)
        if claim is not None and _send_claim(tenant=tenant, claim=claim, now=current_time, sender=sender):
            delivered += 1
    return delivered
