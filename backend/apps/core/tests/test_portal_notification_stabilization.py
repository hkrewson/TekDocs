import time
from unittest.mock import patch

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.models import (
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    EntityVisibility,
    InboxNotification,
    NotificationEmailDelivery,
    OutboxEvent,
    PublicationAudience,
    PublicationControlAction,
    PublicationRetention,
)
from apps.core.outbox import OutboxTopic
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope

pytest_plugins = ("apps.core.tests.test_portal_documents",)

NOTIFICATION_HISTORY_SIZE = 250
NOTIFICATION_QUERY_BUDGET = 32
PORTAL_DOCUMENT_HISTORY_SIZE = 125
PORTAL_DOCUMENT_QUERY_BUDGET = 32
P95_TARGET_SECONDS = 0.5


def _p95(samples: list[float]) -> float:
    return sorted(samples)[max(0, round(0.95 * len(samples) + 0.5) - 1)]


def _create_portal_document_history(*, result, organization, source, count: int) -> None:  # type: ignore[no-untyped-def]
    approver = User.objects.get(display_name="Approver")
    entities = [
        Entity(
            tenant=result.tenant,
            organization=organization,
            workspace=organization.ownership_workspace,
            entity_type="document_publication",
            display_name=f"History guide {index:03d}",
            visibility=EntityVisibility.CLIENT_VISIBLE,
        )
        for index in range(count)
    ]
    Entity.objects.bulk_create(entities, batch_size=100)
    artifact_entities = [
        Entity(
            tenant=result.tenant,
            organization=organization,
            workspace=organization.ownership_workspace,
            entity_type="document_publication_artifact",
            display_name=f"History guide {index:03d}.pdf",
            visibility=EntityVisibility.CLIENT_VISIBLE,
        )
        for index in range(count)
    ]
    Entity.objects.bulk_create(artifact_entities, batch_size=100)
    source_artifact = source.artifacts.get(kind="pdf")
    publications = []
    artifacts = []
    for index, (entity, artifact_entity) in enumerate(zip(entities, artifact_entities, strict=True)):
        publication = DocumentPublication(
            tenant=result.tenant,
            organization=organization,
            document=source.document,
            entity=entity,
            title=entity.display_name,
            category="guide",
            reason="Scale fixture",
            audience=PublicationAudience.CLIENT_VISIBLE,
            retention=PublicationRetention.PERMANENT,
            canonical_markdown="# Scale fixture",
            sanitized_html="<h1>Scale fixture</h1>",
            manifest={},
            content_digest=f"{index:064x}",
            signature="fixture-signature",
            public_key="fixture-key",
            key_fingerprint="a" * 64,
            published_by=result.owner,
            published_at=timezone.now(),
        )
        artifact = DocumentPublicationArtifact(
            tenant=result.tenant,
            organization=organization,
            publication=publication,
            entity=artifact_entity,
            kind="pdf",
            file=source_artifact.file.name,
            original_filename=f"History guide {index:03d}.pdf",
            media_type="application/pdf",
            size=source_artifact.size,
            checksum=source_artifact.checksum,
            created_at=publication.published_at,
        )
        publication.manifest = {
            "format": "tekdocs-static-publication/v2",
            "publication_id": str(publication.id),
            "publication_entity_id": str(entity.id),
            "source_document_id": str(source.document.entity_id),
            "workspace": {"kind": "organization", "id": str(organization.entity_id)},
            "entities": [],
            "reason": "Scale fixture",
            "audience": "client_visible",
            "retention": "permanent",
            "retention_review_on": None,
            "supersedes_id": None,
            "artifacts": [
                {
                    "id": str(artifact.id),
                    "entity_id": str(artifact_entity.id),
                    "kind": "pdf",
                    "filename": artifact.original_filename,
                    "media_type": artifact.media_type,
                    "size": artifact.size,
                    "checksum": artifact.checksum,
                    "source_attachment_id": None,
                }
            ],
        }
        publications.append(publication)
        artifacts.append(artifact)
    DocumentPublication.objects.bulk_create(publications, batch_size=50)
    DocumentPublicationArtifact.objects.bulk_create(artifacts, batch_size=50)
    DocumentPublicationControlEvent.objects.bulk_create(
        [
            DocumentPublicationControlEvent(
                tenant=result.tenant,
                organization=organization,
                publication=publication,
                action=PublicationControlAction.SUBMITTED,
                reason="Scale fixture submitted",
                actor=result.owner,
                occurred_at=publication.published_at,
            )
            for publication in publications
        ],
        batch_size=50,
    )
    DocumentPublicationControlEvent.objects.bulk_create(
        [
            DocumentPublicationControlEvent(
                tenant=result.tenant,
                organization=organization,
                publication=publication,
                action=PublicationControlAction.APPROVED,
                reason="Scale fixture approved",
                actor=approver,
                occurred_at=publication.published_at,
            )
            for publication in publications
        ],
        batch_size=50,
    )


@pytest.mark.django_db(transaction=True)
def test_portal_document_history_has_fixed_queries_and_scope_bound_seek_pages(portal_publications):  # type: ignore[no-untyped-def]
    result, organization, portal_user, available, *_rest = portal_publications
    with rls_scope(
        DataScope.organization(result.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        _create_portal_document_history(
            result=result,
            organization=organization,
            source=available,
            count=PORTAL_DOCUMENT_HISTORY_SIZE,
        )

    client = Client()
    client.force_login(portal_user)
    url = reverse("client-portal-document-list")
    with CaptureQueriesContext(connection) as queries:
        first = client.get(url)
    assert first.status_code == 200
    assert first["Cache-Control"] == "private, no-store"
    assert len(queries) <= PORTAL_DOCUMENT_QUERY_BUDGET
    first_payload = first.json()
    assert len(first_payload["results"]) == 50
    assert first_payload["has_more"] is True
    assert first_payload["next_cursor"]

    second = client.get(url, {"cursor": first_payload["next_cursor"]})
    assert second.status_code == 200
    assert len(second.json()["results"]) == 50
    assert {item["id"] for item in first_payload["results"]}.isdisjoint(
        {item["id"] for item in second.json()["results"]}
    )
    assert client.get(url, {"cursor": f"{first_payload['next_cursor']}x"}).status_code == 400
    with patch("django.core.signing.time.time", return_value=time.time() + 31 * 24 * 60 * 60):
        assert client.get(url, {"cursor": first_payload["next_cursor"]}).status_code == 400

    samples = []
    for _ in range(8):
        started = time.perf_counter()
        response = client.get(url)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
    assert _p95(samples) < P95_TARGET_SECONDS


@pytest.mark.django_db(transaction=True)
def test_portal_notification_history_is_bounded_seek_paginated_and_scope_bound(portal_publications):  # type: ignore[no-untyped-def]
    result, organization, portal_user, available, *_rest = portal_publications
    with rls_scope(
        DataScope.organization(result.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        events = [
            OutboxEvent(
                tenant=result.tenant,
                organization=organization,
                topic=OutboxTopic.PUBLICATION_AVAILABLE,
                subject_id=available.id,
                idempotency_key=f"history-{index}",
                payload={"audience": "client_visible"},
            )
            for index in range(NOTIFICATION_HISTORY_SIZE)
        ]
        OutboxEvent.objects.bulk_create(events, batch_size=100)
        notifications = [
            InboxNotification(
                tenant=result.tenant,
                organization=organization,
                event=event,
                recipient=portal_user,
                surface="client_portal",
            )
            for event in events
        ]
        InboxNotification.objects.bulk_create(notifications, batch_size=100)
        NotificationEmailDelivery.objects.bulk_create(
            [
                NotificationEmailDelivery(
                    tenant=result.tenant,
                    organization=organization,
                    notification=notification,
                    recipient=portal_user,
                    surface="client_portal",
                )
                for notification in notifications
            ],
            batch_size=100,
        )

    client = Client()
    client.force_login(portal_user)
    url = reverse("client-portal-notification-list")
    with CaptureQueriesContext(connection) as queries:
        first = client.get(url)
    assert first.status_code == 200
    assert first["Cache-Control"] == "private, no-store"
    assert len(queries) <= NOTIFICATION_QUERY_BUDGET
    first_payload = first.json()
    assert len(first_payload["results"]) == 50
    assert first_payload["has_more"] is True
    assert first_payload["next_cursor"]

    second = client.get(url, {"cursor": first_payload["next_cursor"]})
    assert second.status_code == 200
    second_payload = second.json()
    assert len(second_payload["results"]) == 50
    assert {item["id"] for item in first_payload["results"]}.isdisjoint(
        {item["id"] for item in second_payload["results"]}
    )

    tampered = client.get(url, {"cursor": f"{first_payload['next_cursor']}x"})
    assert tampered.status_code == 400

    other_user = User.objects.create_user(email="other-reader@example.invalid", display_name="Other reader")
    TenantMembership.objects.create(
        tenant=result.tenant,
        user=other_user,
        role=BuiltInRole.CLIENT_USER,
        organization=organization,
    )
    other_client = Client()
    other_client.force_login(other_user)
    assert other_client.get(url, {"cursor": first_payload["next_cursor"]}).status_code == 400

    samples = []
    for _ in range(8):
        started = time.perf_counter()
        response = client.get(url)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
    assert _p95(samples) < P95_TARGET_SECONDS

    Authenticator.objects.create(
        user=result.owner,
        type=Authenticator.Type.TOTP,
        data={"secret": generate_totp_secret()},
    )
    admin = Client()
    admin.force_login(result.owner)
    deliveries = admin.get(reverse("notification-delivery-list"))
    assert deliveries.status_code == 200
    delivery_payload = deliveries.json()
    assert len(delivery_payload["results"]) == 100
    assert delivery_payload["has_more"] is True
    assert delivery_payload["next_cursor"]
    assert (
        admin.get(
            reverse("notification-delivery-list"),
            {"state": "pending", "cursor": delivery_payload["next_cursor"]},
        ).status_code
        == 400
    )
