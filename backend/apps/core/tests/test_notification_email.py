import smtplib
from datetime import timedelta

import pytest
from django.core import mail
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import NotificationEmailDelivery, NotificationEmailState, NotificationPreference
from apps.core.notification_email import dispatch_due_notification_emails
from apps.core.outbox import dispatch_due_outbox_events

pytest_plugins = ("apps.core.tests.test_portal_documents",)


def _project_all(tenant) -> None:  # type: ignore[no-untyped-def]
    while dispatch_due_outbox_events(tenant=tenant):
        pass


@pytest.mark.django_db(transaction=True)
def test_smtp_delivery_reauthorizes_and_renders_value_minimized_messages(portal_publications, settings):  # type: ignore[no-untyped-def]
    result, organization, portal_user, available, _pending, withdrawn, sibling, _unsafe = portal_publications
    settings.TEKDOCS_PUBLIC_URL = "https://tekdocs.example.test"
    _project_all(result.tenant)

    delivered = dispatch_due_notification_emails(tenant=result.tenant)

    assert delivered == NotificationEmailDelivery.objects.filter(
        state=NotificationEmailState.DELIVERED
    ).count()
    assert NotificationEmailDelivery.objects.filter(
        state=NotificationEmailState.SUPPRESSED
    ).count() == 1
    portal_messages = [message for message in mail.outbox if message.to == [portal_user.email]]
    assert len(portal_messages) == 1
    combined = "\n".join(message.body for message in portal_messages)
    assert available.title in combined
    assert "A previously available publication was withdrawn." in combined
    assert withdrawn.title not in combined
    assert sibling.title not in combined
    assert organization.entity.display_name not in combined
    assert "Client distribution" not in combined
    assert portal_messages[0].subject.startswith("TekDocs notification")
    assert portal_messages[0].extra_headers["Message-ID"].startswith("<tekdocs-notification-batch-")
    assert all("document content" in message.body for message in portal_messages)


@pytest.mark.django_db(transaction=True)
def test_preferences_are_surface_scoped_and_suppress_pending_publication_mail(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, *_rest = portal_publications
    _project_all(result.tenant)
    portal = Client(enforce_csrf_checks=True)
    portal.force_login(portal_user)
    assert portal.get("/_allauth/browser/v1/auth/session").status_code == 200
    csrf = portal.cookies["csrftoken"].value
    url = reverse("client-portal-notification-preferences")

    initial = portal.get(url)
    assert initial.status_code == 200
    assert initial.json() == {
        "email_enabled": True,
        "invitation_events": True,
        "publication_events": True,
        "delivery_mode": "immediate",
        "timezone": "UTC",
        "quiet_start": None,
        "quiet_end": None,
        "daily_digest_hour": 8,
    }
    changed = portal.patch(
        url,
        data={"publication_events": False},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert changed.status_code == 200
    assert changed.json()["publication_events"] is False
    assert changed["Cache-Control"] == "private, no-store"

    dispatch_due_notification_emails(tenant=result.tenant)
    assert not [message for message in mail.outbox if message.to == [portal_user.email]]
    assert set(
        NotificationEmailDelivery.objects.filter(recipient=portal_user).values_list("state", flat=True)
    ) == {NotificationEmailState.SUPPRESSED}

    msp = Client()
    msp.force_login(result.owner)
    assert msp.get(url).status_code in {403, 404}
    assert portal.get(reverse("notification-preferences")).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_mail_outage_retries_without_persisting_recipient_or_exception_values(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, _portal_user, *_rest = portal_publications
    _project_all(result.tenant)
    first_attempt = timezone.now()

    def unavailable(**_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("smtp-password-and-private-host-must-not-persist")

    assert dispatch_due_notification_emails(tenant=result.tenant, now=first_attempt, sender=unavailable) == 0
    deliveries = NotificationEmailDelivery.objects.all()
    retryable = deliveries.filter(state=NotificationEmailState.PENDING, attempts=1)
    suppressed = deliveries.filter(state=NotificationEmailState.SUPPRESSED, attempts=0)
    assert retryable.count() + suppressed.count() == deliveries.count()
    assert set(retryable.values_list("last_error_code", flat=True)) == {"smtp_unavailable"}
    assert "password" not in str(list(deliveries.values("last_error_code")))
    retryable_count = retryable.count()

    sent: list[dict[str, object]] = []

    def recovered(**kwargs):  # type: ignore[no-untyped-def]
        sent.append(kwargs)
        return 1

    later = first_attempt + timedelta(hours=1)
    assert dispatch_due_notification_emails(tenant=result.tenant, now=later, sender=recovered) == retryable_count
    assert 1 <= len(sent) <= retryable_count
    assert not NotificationEmailDelivery.objects.exclude(
        state__in=(NotificationEmailState.DELIVERED, NotificationEmailState.SUPPRESSED)
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_permanent_recipient_rejection_dead_letters_without_raw_smtp_response(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, _portal_user, *_rest = portal_publications
    _project_all(result.tenant)

    def rejected(**_kwargs):  # type: ignore[no-untyped-def]
        raise smtplib.SMTPRecipientsRefused({"private@example.invalid": (550, b"private mailbox detail")})

    assert dispatch_due_notification_emails(tenant=result.tenant, sender=rejected) == 0
    deliveries = NotificationEmailDelivery.objects.all()
    dead_letters = deliveries.filter(state=NotificationEmailState.DEAD_LETTER, attempts=1)
    suppressed = deliveries.filter(state=NotificationEmailState.SUPPRESSED, attempts=0)
    assert dead_letters.count() + suppressed.count() == deliveries.count()
    assert set(dead_letters.values_list("last_error_code", flat=True)) == {"recipient_rejected"}


@pytest.mark.django_db(transaction=True)
def test_database_rejects_email_retargeting_terminal_replay_and_preference_deletion(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, *_rest = portal_publications
    _project_all(result.tenant)
    delivery = NotificationEmailDelivery.objects.filter(recipient=portal_user).first()
    assert delivery is not None
    preference = NotificationPreference.objects.create(
        tenant=result.tenant,
        user=portal_user,
        surface="client_portal",
    )

    with (
        pytest.raises(DatabaseError, match="identity is immutable"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE core_notificationemaildelivery SET recipient_id=%s WHERE id=%s",
            [result.owner.id, delivery.id],
        )
    delivery.state = NotificationEmailState.PROCESSING
    delivery.locked_at = timezone.now()
    delivery.attempts = 1
    delivery.save(update_fields=("state", "locked_at", "attempts"))
    delivery.state = NotificationEmailState.DELIVERED
    delivery.locked_at = None
    delivery.delivered_at = timezone.now()
    delivery.save(update_fields=("state", "locked_at", "delivered_at"))
    with (
        pytest.raises(DatabaseError, match="terminal state is immutable"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE core_notificationemaildelivery SET "
            "state='processing', locked_at=NOW(), delivered_at=NULL WHERE id=%s",
            [delivery.id],
        )
    with pytest.raises(DatabaseError, match="cannot be deleted"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM core_notificationpreference WHERE id=%s", [preference.id])
