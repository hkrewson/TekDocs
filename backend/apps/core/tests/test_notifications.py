import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.core.models import InboxNotification, OutboxEvent, OutboxEventState
from apps.core.outbox import dispatch_due_outbox_events

pytest_plugins = ("apps.core.tests.test_portal_documents",)


def _dispatch_all(tenant) -> None:  # type: ignore[no-untyped-def]
    while dispatch_due_outbox_events(tenant=tenant):
        pass


@pytest.mark.django_db(transaction=True)
def test_client_inbox_projects_only_current_authorized_value_minimized_events(portal_publications):  # type: ignore[no-untyped-def]
    result, organization, portal_user, available, _pending, withdrawn, sibling, _unsafe = portal_publications
    _dispatch_all(result.tenant)

    client = Client()
    client.force_login(portal_user)
    response = client.get(reverse("client-portal-notification-list"))

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    payload = response.json()
    assert payload["unread_count"] == 2
    assert {item["title"] for item in payload["results"]} == {
        "Documentation published",
        "Documentation access changed",
    }
    published = next(item for item in payload["results"] if item["title"] == "Documentation published")
    assert published["target"] == {
        "kind": "portal_document",
        "organization_id": None,
        "publication_id": str(available.entity_id),
    }
    withdrawn_item = next(item for item in payload["results"] if item["title"] == "Documentation access changed")
    assert withdrawn_item["target"] is None
    encoded = str(payload)
    assert withdrawn.title not in encoded
    assert sibling.title not in encoded
    assert "Client distribution" not in encoded
    assert organization.entity.display_name not in encoded


@pytest.mark.django_db(transaction=True)
def test_notification_read_state_is_recipient_scoped_and_reversible(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, _available, _pending, _withdrawn, _sibling, _unsafe = portal_publications
    _dispatch_all(result.tenant)
    notification = InboxNotification.objects.filter(recipient=portal_user, surface="client_portal").first()
    assert notification is not None

    client = Client()
    client.force_login(portal_user)
    url = reverse("client-portal-notification-read", kwargs={"notification_id": notification.id})
    read = client.patch(url, data={"read": True}, content_type="application/json")
    assert read.status_code == 200
    assert read.json()["read"] is True
    assert client.get(reverse("client-portal-notification-list")).json()["unread_count"] == 1

    unread = client.patch(url, data={"read": False}, content_type="application/json")
    assert unread.status_code == 200
    assert unread.json()["read"] is False
    assert client.get(reverse("client-portal-notification-list")).json()["unread_count"] == 2

    msp = Client()
    msp.force_login(result.owner)
    assert msp.patch(url, data={"read": True}, content_type="application/json").status_code in {403, 404}


@pytest.mark.django_db(transaction=True)
def test_msp_inbox_reauthorizes_subjects_and_client_cannot_enter_msp_surface(portal_publications):  # type: ignore[no-untyped-def]
    result, organization, portal_user, available, _pending, withdrawn, sibling, _unsafe = portal_publications
    _dispatch_all(result.tenant)

    msp = Client()
    msp.force_login(result.owner)
    response = msp.get(reverse("notification-list"))
    assert response.status_code == 200
    payload = response.json()
    messages = {item["message"] for item in payload["results"]}
    assert f"{available.title} was published for {organization.entity.display_name}." in messages
    assert f"{withdrawn.title} was withdrawn for {organization.entity.display_name}." in messages
    assert any(sibling.title in message for message in messages)
    assert all(item["target"]["kind"] == "organization_documentation" for item in payload["results"])

    portal = Client()
    portal.force_login(portal_user)
    assert portal.get(reverse("notification-list")).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_default_outbox_consumer_is_idempotent_for_inbox_recipients(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, _portal_user, *_rest = portal_publications
    _dispatch_all(result.tenant)
    count = InboxNotification.objects.count()
    assert count > 0
    assert dispatch_due_outbox_events(tenant=result.tenant) == 0
    assert InboxNotification.objects.count() == count
    assert not OutboxEvent.objects.exclude(state=OutboxEventState.DELIVERED).exists()


@pytest.mark.django_db(transaction=True)
def test_database_rejects_inbox_identity_retargeting_and_deletion(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, *_rest = portal_publications
    _dispatch_all(result.tenant)
    notification = InboxNotification.objects.filter(recipient=portal_user, surface="client_portal").first()
    assert notification is not None

    with (
        pytest.raises(DatabaseError, match="identity is immutable"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE core_inboxnotification SET recipient_id=%s WHERE id=%s",
            [result.owner.id, notification.id],
        )
    with pytest.raises(DatabaseError, match="cannot be deleted"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM core_inboxnotification WHERE id=%s", [notification.id])
