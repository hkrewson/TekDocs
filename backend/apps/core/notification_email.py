from __future__ import annotations

import hashlib
import smtplib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.accounts.policy import require_installation_member

from .email import send_notification_digest_email
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
MAX_DIGEST_ITEMS = 25
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
    preference, _created = NotificationPreference.objects.get_or_create(tenant=tenant, user_id=user_id, surface=surface)
    return preference


def _outside_quiet_hours(candidate: datetime, preference: NotificationPreference) -> datetime:
    if preference.quiet_start is None or preference.quiet_end is None:
        return candidate
    zone = ZoneInfo(preference.timezone)
    local = candidate.astimezone(zone)
    start, end = preference.quiet_start, preference.quiet_end
    inside = (
        start <= local.timetz().replace(tzinfo=None) < end
        if start < end
        else (local.timetz().replace(tzinfo=None) >= start or local.timetz().replace(tzinfo=None) < end)
    )
    if not inside:
        return candidate
    end_date = local.date()
    if start > end and local.timetz().replace(tzinfo=None) >= start:
        end_date += timedelta(days=1)
    return datetime.combine(end_date, end, tzinfo=zone).astimezone(UTC)


def next_delivery_at(preference: NotificationPreference, *, created_at: datetime, now: datetime) -> datetime:
    """Return the first schedule boundary at which this pending item may be sent."""
    zone = ZoneInfo(preference.timezone)
    if preference.delivery_mode == "immediate":
        candidate = now
    elif preference.delivery_mode == "hourly":
        local = created_at.astimezone(zone)
        candidate = (local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).astimezone(UTC)
    else:
        local_created = created_at.astimezone(zone)
        candidate_local = datetime.combine(local_created.date(), time(preference.daily_digest_hour), tzinfo=zone)
        if candidate_local <= local_created:
            candidate_local += timedelta(days=1)
        candidate = candidate_local.astimezone(UTC)
    return _outside_quiet_hours(candidate, preference)


def _suppress(delivery: NotificationEmailDelivery) -> None:
    delivery.state = NotificationEmailState.SUPPRESSED
    delivery.locked_at = None
    delivery.last_error_code = ""
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
        eligible_at = next_delivery_at(preference, created_at=delivery.created_at, now=now)
        if eligible_at > now:
            delivery.available_at = eligible_at
            delivery.save(update_fields=("available_at",))
            return None
        delivery.state = NotificationEmailState.PROCESSING
        delivery.locked_at = now
        delivery.last_attempt_at = now
        delivery.attempts += 1
        delivery.last_error_code = ""
        delivery.save(update_fields=("state", "locked_at", "last_attempt_at", "attempts", "last_error_code"))
        return ClaimedEmail(delivery.id, now, delivery.recipient.email, projection.title, projection.message)


def _finish(
    *,
    tenant: Tenant,
    claims: list[ClaimedEmail],
    now: datetime,
    error_code: NotificationEmailError | None = None,
    permanent: bool = False,
) -> int:
    completed = 0
    with transaction.atomic():
        for claim in claims:
            delivery = (
                NotificationEmailDelivery.scoped.for_tenant(tenant)
                .select_for_update()
                .filter(pk=claim.delivery_id, state=NotificationEmailState.PROCESSING, locked_at=claim.locked_at)
                .first()
            )
            if delivery is None:
                continue
            delivery.locked_at = None
            if error_code is None:
                delivery.state = NotificationEmailState.DELIVERED
                delivery.delivered_at = now
                delivery.last_error_code = ""
                completed += 1
            else:
                delivery.state = (
                    NotificationEmailState.DEAD_LETTER
                    if permanent or delivery.attempts >= MAX_EMAIL_ATTEMPTS
                    else NotificationEmailState.PENDING
                )
                delivery.available_at = now + _retry_delay(delivery.attempts)
                delivery.last_error_code = error_code.value
            delivery.save(update_fields=("state", "locked_at", "delivered_at", "available_at", "last_error_code"))
    return completed


def _send_batch(*, tenant: Tenant, claims: list[ClaimedEmail], now: datetime, sender: EmailSender) -> int:
    digest = hashlib.sha256(":".join(sorted(str(item.delivery_id) for item in claims)).encode()).hexdigest()[:32]
    try:
        accepted = sender(
            recipient=claims[0].recipient,
            notifications=[{"title": item.title, "message": item.message} for item in claims],
            app_url=settings.TEKDOCS_PUBLIC_URL,
            batch_id=digest,
        )
        if accepted != 1:
            return _finish(tenant=tenant, claims=claims, now=now, error_code=NotificationEmailError.SMTP_UNAVAILABLE)
    except smtplib.SMTPRecipientsRefused:
        return _finish(
            tenant=tenant, claims=claims, now=now, error_code=NotificationEmailError.RECIPIENT_REJECTED, permanent=True
        )
    except smtplib.SMTPResponseException as exc:
        return _finish(
            tenant=tenant,
            claims=claims,
            now=now,
            error_code=NotificationEmailError.SMTP_REJECTED,
            permanent=exc.smtp_code >= 500,
        )
    except ValidationError:
        return _finish(
            tenant=tenant, claims=claims, now=now, error_code=NotificationEmailError.RECIPIENT_INVALID, permanent=True
        )
    except (OSError, TimeoutError, smtplib.SMTPException):
        return _finish(tenant=tenant, claims=claims, now=now, error_code=NotificationEmailError.SMTP_UNAVAILABLE)
    except Exception:
        return _finish(tenant=tenant, claims=claims, now=now, error_code=NotificationEmailError.DELIVERY_FAILED)
    return _finish(tenant=tenant, claims=claims, now=now)


def dispatch_due_notification_emails(
    *,
    tenant: Tenant,
    batch_size: int = 50,
    now: datetime | None = None,
    sender: EmailSender = send_notification_digest_email,
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
    grouped: dict[tuple[str, str], list[ClaimedEmail]] = defaultdict(list)
    for delivery_id in due_ids:
        claim = _claim_one(tenant=tenant, delivery_id=delivery_id, now=current_time)
        if claim is not None:
            key = (
                claim.recipient,
                str(NotificationEmailDelivery.objects.only("surface").get(pk=claim.delivery_id).surface),
            )
            grouped[key].append(claim)
    delivered = 0
    for claims in grouped.values():
        for offset in range(0, len(claims), MAX_DIGEST_ITEMS):
            delivered += _send_batch(
                tenant=tenant, claims=claims[offset : offset + MAX_DIGEST_ITEMS], now=current_time, sender=sender
            )
    return delivered
