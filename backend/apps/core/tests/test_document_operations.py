import secrets
from datetime import timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.models import AuditEvent, Document, Entity, InstallationState, Organization, Tenant


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Documentation Operations MSP",
        owner_email="operations-owner@example.invalid",
        owner_display_name="Operations Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


@pytest.fixture
def approver(installation):
    user = User.objects.create_user(
        email="operations-approver@example.invalid",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
        display_name="Documentation Approver",
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=user, role=BuiltInRole.ADMINISTRATOR)
    TOTP.activate(user, generate_totp_secret())
    return user


@pytest.fixture
def approver_client(approver):
    client = Client()
    client.force_login(approver)
    return client


def create_document(client: Client, title: str = "Recovery runbook", markdown: str = "Rotate the recovery key."):
    response = client.post(
        reverse("msp-document-list-create"),
        {"title": title, "markdown": markdown},
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.django_db
def test_full_text_search_returns_excerpt_and_facets(owner_client, installation):
    document = create_document(owner_client)
    operations_url = reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]})
    updated = owner_client.put(
        operations_url,
        {
            "owner_id": str(installation.owner.id),
            "review_due_on": (timezone.localdate() - timedelta(days=1)).isoformat(),
            "collection": "Operations Runbooks",
            "tags": ["Recovery", "critical", "recovery"],
        },
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["health_status"] == "stale"
    assert updated.json()["tags"] == ["recovery", "critical"]

    result = owner_client.get(reverse("msp-document-search"), {"q": "recovery key"})

    assert result.status_code == 200
    assert result.json()["count"] == 1
    assert "Rotate the recovery key" in result.json()["results"][0]["matching_excerpt"]
    assert result.json()["collections"] == [{"value": "Operations Runbooks", "count": 1}]
    assert {item["value"] for item in result.json()["tags"]} == {"critical", "recovery"}
    assert result.json()["health"] == [{"value": "stale", "count": 1}]


@pytest.mark.django_db
def test_review_request_decision_and_later_edit_invalidation(owner_client, approver_client, approver):
    document = create_document(owner_client)
    request_url = reverse("msp-document-review-request", kwargs={"document_entity_id": document["id"]})
    requested = owner_client.post(
        request_url,
        {"reviewer_id": str(approver.id), "note": "Please verify the recovery steps."},
        content_type="application/json",
    )
    assert requested.status_code == 200
    assert requested.json()["review_state"] == "pending"
    assert requested.json()["reviewer_name"] == "Documentation Approver"

    decision_url = reverse("msp-document-review-decision", kwargs={"document_entity_id": document["id"]})
    approved = approver_client.post(
        decision_url,
        {"decision": "approved", "note": "Verified against the current procedure."},
        content_type="application/json",
    )
    assert approved.status_code == 200
    assert approved.json()["review_state"] == "approved"
    assert approved.json()["last_reviewed_by_name"] == "Documentation Approver"

    edited = owner_client.put(
        reverse("msp-document-detail", kwargs={"document_entity_id": document["id"]}),
        {
            "title": document["title"],
            "markdown": "Rotate the recovery key and verify restoration.",
            "base_revision_id": approved.json()["current_revision_id"],
        },
        content_type="application/json",
    )
    assert edited.status_code == 200
    assert edited.json()["review_state"] == "unreviewed"
    assert edited.json()["health_status"] == "unowned"


@pytest.mark.django_db
def test_document_reminder_and_activity_are_exposed(owner_client, installation):
    document = create_document(owner_client)
    reminder = owner_client.post(
        reverse("msp-reminder-list-create"),
        {
            "source_entity_id": document["id"],
            "domain": "documentation",
            "kind": "review",
            "title": "Review recovery runbook",
            "due_on": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "lead_days": 7,
            "recurrence": "none",
            "owner_id": str(installation.owner.id),
        },
        content_type="application/json",
    )
    assert reminder.status_code == 201
    assert reminder.json()["domain"] == "documentation"
    assert owner_client.get(reverse("msp-reminder-list-create")).json()[0]["title"] == "Review recovery runbook"

    activity = owner_client.get(reverse("msp-activity-list"), {"q": "document."})
    assert activity.status_code == 200
    assert {item["action"] for item in activity.json()["results"]} >= {"document.created"}
    assert activity.json()["results"][0]["actor_name"] == "Operations Owner"


@pytest.mark.django_db
def test_organization_activity_is_exactly_workspace_and_tenant_scoped(owner_client, installation):
    first_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        entity_type="organization",
        display_name="First Client",
    )
    first = Organization.objects.create(
        tenant=installation.tenant,
        entity=first_entity,
        legal_name="First Client, LLC",
    )
    second_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        entity_type="organization",
        display_name="Second Client",
    )
    Organization.objects.create(
        tenant=installation.tenant,
        entity=second_entity,
        legal_name="Second Client, LLC",
    )
    foreign_tenant = Tenant.objects.create(name="Foreign Activity MSP", slug="foreign-activity")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        entity_type="organization",
        display_name="Foreign Client",
    )
    Organization.objects.create(tenant=foreign_tenant, entity=foreign_entity, legal_name="Foreign Client, LLC")
    AuditEvent.objects.bulk_create(
        [
            AuditEvent(tenant=installation.tenant, action="first.visible", entity_id=first_entity.id),
            AuditEvent(tenant=installation.tenant, action="second.hidden", entity_id=second_entity.id),
            AuditEvent(tenant=foreign_tenant, action="foreign.hidden", entity_id=foreign_entity.id),
        ]
    )

    response = owner_client.get(
        reverse("organization-activity-list", kwargs={"organization_entity_id": first.entity_id})
    )

    assert response.status_code == 200
    assert [item["action"] for item in response.json()["results"]] == ["first.visible"]
    assert (
        owner_client.get(
            reverse("organization-activity-list", kwargs={"organization_entity_id": foreign_entity.id})
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_read_only_member_cannot_mutate_document_operations(owner_client, installation):
    document = create_document(owner_client)
    reader = User.objects.create_user(
        email="operations-reader@example.invalid",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
        display_name="Operations Reader",
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    client = Client()
    client.force_login(reader)

    denied = client.put(
        reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]}),
        {"owner_id": str(reader.id), "review_due_on": None, "collection": "", "tags": []},
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert client.get(reverse("msp-activity-list")).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_database_rejects_document_people_outside_exact_workspace(owner_client):
    document = create_document(owner_client)
    outsider = User.objects.create_user(
        email="operations-outsider@example.invalid",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
        display_name="Outside User",
    )
    record = Document.objects.get(entity_id=document["id"])

    with pytest.raises(DatabaseError, match="authorized workspace"), transaction.atomic():
        Document.objects.filter(pk=record.pk).update(owner=outsider)
