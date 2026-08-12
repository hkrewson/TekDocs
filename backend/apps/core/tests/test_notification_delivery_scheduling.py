import smtplib
from datetime import UTC, datetime, time

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent, NotificationEmailDelivery, NotificationEmailState, NotificationPreference
from apps.core.notification_email import dispatch_due_notification_emails, next_delivery_at
from apps.core.outbox import dispatch_due_outbox_events

pytest_plugins = ("apps.core.tests.test_portal_documents",)


def test_timezone_aware_digest_boundaries_and_overnight_quiet_hours():
    preference = NotificationPreference(delivery_mode="hourly", timezone="America/Chicago")
    created = datetime(2026, 3, 8, 7, 35, tzinfo=UTC)
    assert next_delivery_at(preference, created_at=created, now=created) == datetime(2026, 3, 8, 8, 0, tzinfo=UTC)

    preference.delivery_mode = "immediate"
    preference.quiet_start = time(22)
    preference.quiet_end = time(7)
    late = datetime(2026, 8, 12, 4, 30, tzinfo=UTC)
    assert next_delivery_at(preference, created_at=late, now=late) == datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@pytest.mark.django_db(transaction=True)
def test_batch_delivery_and_admin_retry_are_bounded_and_audited(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, *_rest = portal_publications
    while dispatch_due_outbox_events(tenant=result.tenant):
        pass
    calls: list[dict[str, object]] = []

    def rejected(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        raise smtplib.SMTPRecipientsRefused({"private@example.invalid": (550, b"private detail")})

    dispatch_due_notification_emails(tenant=result.tenant, sender=rejected)
    assert len([call for call in calls if call["recipient"] == portal_user.email]) == 1
    dead_letter = NotificationEmailDelivery.objects.filter(
        recipient=portal_user, state=NotificationEmailState.DEAD_LETTER
    ).first()
    assert dead_letter is not None
    unaudited = (
        NotificationEmailDelivery.objects.filter(state=NotificationEmailState.DEAD_LETTER)
        .exclude(id=dead_letter.id)
        .first()
    )
    assert unaudited is not None
    with (
        pytest.raises(DatabaseError, match="requires matching audit evidence"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE core_notificationemaildelivery SET state='pending', attempts=0, retry_generation=1, "
            "locked_at=NULL, delivered_at=NULL, last_attempt_at=NULL, last_error_code='' WHERE id=%s",
            [unaudited.id],
        )

    Authenticator.objects.create(
        user=result.owner, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(result.owner)
    assert client.get("/_allauth/browser/v1/auth/session").status_code == 200
    csrf = client.cookies["csrftoken"].value
    listing = client.get(reverse("notification-delivery-list"))
    assert listing.status_code == 200
    encoded = str(listing.json())
    assert portal_user.email not in encoded
    assert "Approved client content" not in encoded
    portal_client = Client()
    portal_client.force_login(portal_user)
    assert portal_client.get(reverse("notification-delivery-list")).status_code == 403

    retried = client.post(
        reverse("notification-delivery-retry", kwargs={"delivery_id": dead_letter.id}),
        data={"reason": "Operator verified SMTP recovery"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert retried.status_code == 200
    dead_letter.refresh_from_db()
    assert dead_letter.state == NotificationEmailState.PENDING
    assert dead_letter.attempts == 0
    assert dead_letter.retry_generation == 1
    assert AuditEvent.objects.filter(action="notification.delivery_retried", entity_id=dead_letter.id).exists()


@pytest.mark.django_db
def test_preference_api_rejects_invalid_timezone_and_partial_quiet_window(portal_publications):  # type: ignore[no-untyped-def]
    _result, _organization, portal_user, *_rest = portal_publications
    client = Client(enforce_csrf_checks=True)
    client.force_login(portal_user)
    assert client.get("/_allauth/browser/v1/auth/session").status_code == 200
    csrf = client.cookies["csrftoken"].value
    url = reverse("client-portal-notification-preferences")
    invalid_zone = client.patch(
        url, data={"timezone": "Not/AZone"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    )
    assert invalid_zone.status_code == 400
    partial = client.patch(url, data={"quiet_start": "22:00"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    assert partial.status_code == 400
