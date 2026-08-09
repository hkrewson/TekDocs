import secrets
from hashlib import sha256

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    Block,
    BlockRevision,
    Document,
    DocumentationListingReference,
    DocumentPlacement,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="documents-owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(tenant, name):  # type: ignore[no-untyped-def]
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


@pytest.mark.django_db
def test_document_persists_from_msp_and_client_browser_routes(owner_client, installation):
    client_org = organization(installation.tenant, "Acme Dental")
    msp_url = reverse("msp-document-list-create")
    org_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": client_org.entity_id})

    msp_created = owner_client.post(
        msp_url,
        {"title": "Firewall standard", "markdown": "# Firewall\n\nUse **MFA**."},
        content_type="application/json",
    )
    org_created = owner_client.post(
        org_url, {"title": "Acme onboarding", "markdown": "- Call the client"}, content_type="application/json"
    )

    assert msp_created.status_code == 201
    assert org_created.status_code == 201
    assert msp_created.json()["block_id"]
    assert org_created.json()["owner_organization_id"] == str(client_org.entity_id)
    assert Document.objects.count() == 2
    assert Block.objects.count() == 2
    assert DocumentPlacement.objects.values_list("position", flat=True).order_by("position").first() == 0

    detail = reverse("msp-document-detail", kwargs={"document_entity_id": msp_created.json()["id"]})
    updated = owner_client.put(
        detail,
        {
            "title": "Firewall baseline",
            "markdown": "Updated from the browser.",
            "base_revision_id": msp_created.json()["current_revision_id"],
        },
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Firewall baseline"
    assert updated.json()["markdown"] == "Updated from the browser."
    assert updated.json()["revision_number"] == 2
    revisions = list(
        BlockRevision.objects.filter(block__entity_id=msp_created.json()["block_id"]).order_by("revision_number")
    )
    assert [item.markdown for item in revisions] == ["# Firewall\n\nUse **MFA**.", "Updated from the browser."]
    assert revisions[1].parent == revisions[0]
    assert revisions[1].checksum == sha256(b"Updated from the browser.").hexdigest()


@pytest.mark.django_db
def test_msp_document_reference_cross_lists_without_copying_or_lateral_disclosure(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Shared response guide", "markdown": "One canonical block."},
        content_type="application/json",
    ).json()
    references_url = reverse("msp-document-reference-list-create", kwargs={"document_entity_id": created["id"]})
    added = owner_client.post(
        references_url, {"organization_id": str(acme.entity_id)}, content_type="application/json"
    )
    assert added.status_code == 201
    assert Document.objects.count() == 1
    assert Block.objects.count() == 1
    assert DocumentationListingReference.objects.count() == 1

    acme_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    beta_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": beta.entity_id})
    assert owner_client.get(acme_url).json()["results"][0]["is_reference"] is True
    assert owner_client.get(acme_url).json()["results"][0]["title"] == "Shared response guide"
    assert owner_client.get(beta_url).json()["count"] == 0

    removed = owner_client.delete(
        reverse(
            "msp-document-reference-detail",
            kwargs={"document_entity_id": created["id"], "reference_id": added.json()["id"]},
        )
    )
    assert removed.status_code == 204
    assert owner_client.get(acme_url).json()["count"] == 0


@pytest.mark.django_db
def test_document_route_scope_returns_not_found_for_another_client(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    acme_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    created = owner_client.post(
        acme_url, {"title": "Acme private", "markdown": "Never disclose laterally."}, content_type="application/json"
    ).json()
    beta_detail = reverse(
        "organization-document-detail",
        kwargs={"organization_entity_id": beta.entity_id, "document_entity_id": created["id"]},
    )
    assert owner_client.get(beta_detail).status_code == 404
    assert owner_client.put(
        beta_detail,
        {"title": "Changed", "markdown": "Bad", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    ).status_code == 404


@pytest.mark.django_db
def test_stale_document_update_returns_diff_without_overwriting_draft(owner_client, installation):
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Runbook", "markdown": "line one\nline two\n"},
        content_type="application/json",
    ).json()
    detail = reverse("msp-document-detail", kwargs={"document_entity_id": created["id"]})
    first = owner_client.put(
        detail,
        {"title": "Runbook", "markdown": "line one\nserver edit\n", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    ).json()
    stale = owner_client.put(
        detail,
        {"title": "Runbook", "markdown": "line one\nmy draft\n", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"
    assert stale.json()["current_revision"]["id"] == first["current_revision_id"]
    assert "+server edit" in stale.json()["diff"]
    assert owner_client.get(detail).json()["markdown"] == "line one\nserver edit\n"
    assert BlockRevision.objects.count() == 2


@pytest.mark.django_db
def test_revision_history_is_scoped_and_noop_content_does_not_add_revision(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    collection = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    created = owner_client.post(
        collection, {"title": "Access guide", "markdown": "First"}, content_type="application/json"
    ).json()
    detail = reverse(
        "organization-document-detail",
        kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": created["id"]},
    )
    renamed = owner_client.put(
        detail,
        {"title": "Access procedure", "markdown": "First", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    ).json()
    assert renamed["revision_number"] == 1
    history_url = reverse(
        "organization-document-revision-list",
        kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": created["id"]},
    )
    history = owner_client.get(history_url)
    assert history.status_code == 200
    assert history.json()["count"] == 1
    revision_url = reverse(
        "organization-document-revision-detail",
        kwargs={
            "organization_entity_id": acme.entity_id,
            "document_entity_id": created["id"],
            "revision_id": created["current_revision_id"],
        },
    )
    assert owner_client.get(revision_url).json()["markdown"] == "First"
    beta_history = reverse(
        "organization-document-revision-list",
        kwargs={"organization_entity_id": beta.entity_id, "document_entity_id": created["id"]},
    )
    assert owner_client.get(beta_history).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_block_revisions_are_append_only_in_application_and_postgresql(owner_client, installation):
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Immutable runbook", "markdown": "Original"},
        content_type="application/json",
    ).json()
    revision = BlockRevision.objects.get(id=created["current_revision_id"])
    revision.markdown = "Mutated"
    with pytest.raises(ValidationError):
        revision.save()
    if connection.vendor == "postgresql":
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE core_blockrevision SET markdown = %s WHERE id = %s", ["Mutated", revision.id])
    revision.refresh_from_db()
    assert revision.markdown == "Original"
