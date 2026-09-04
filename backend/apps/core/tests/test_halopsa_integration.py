import json
import secrets
import uuid
from datetime import timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import connection as database_connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.halopsa import halo_ticket_summaries
from apps.core.integration_providers import HaloPSAProvider, ProviderObservation, ProviderPage
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import process_sync_job
from apps.core.models import (
    InstallationState,
    IntegrationConnection,
    IntegrationEntityMapping,
    IntegrationObservation,
    IntegrationSyncJob,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Halo integration MSP",
        owner_email="halo-owner@example.invalid",
        owner_display_name="Halo Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def organization(installation, name):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )


def halo_connection(installation):
    connection_id = uuid.uuid4()
    return IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=None),
        organization=None,
        provider="halopsa",
        name="Primary HaloPSA",
        base_url="https://support.example.invalid/",
        configuration={"client_id": "halopsa-client-id"},
        secret_envelope=encrypt_integration_secret(
            secret=json.dumps({"client_secret": "halopsa-client-secret"}).encode(),
            tenant_id=installation.tenant.id,
            connection_id=connection_id,
            generation=1,
        ),
        health_status="degraded",
        last_successful_sync_at=timezone.now() - timedelta(hours=3),
        sync_interval_minutes=60,
        created_by=installation.owner,
    )


@pytest.mark.django_db
def test_halopsa_connection_keeps_client_secret_out_of_api_and_storage(installation, monkeypatch):
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: True)

    response = browser.post(
        reverse("msp-integration-connection-list-create"),
        data=json.dumps(
            {
                "provider": "halopsa",
                "name": "Primary HaloPSA",
                "base_url": "https://support.example.invalid/",
                "credentials": {
                    "client_id": "tekdocs-read-only",
                    "client_secret": "never-return-halo-secret",
                },
                "sync_interval_minutes": 30,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["provider_details"] == {"client_id": "tekdocs-read-only"}
    assert "never-return-halo-secret" not in response.content.decode()
    stored = IntegrationConnection.objects.get(name="Primary HaloPSA")
    assert stored.configuration == {"client_id": "tekdocs-read-only"}
    assert "never-return-halo-secret" not in json.dumps(stored.secret_envelope)
    secret = decrypt_integration_secret(
        envelope_payload=stored.secret_envelope,
        tenant_id=stored.tenant_id,
        connection_id=stored.id,
        generation=stored.secret_generation,
    )
    assert json.loads(secret) == {"client_secret": "never-return-halo-secret"}


def observed_ticket(installation, connection, client_record, *, remote_client_id="24"):
    job = IntegrationSyncJob.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        idempotency_key=f"fixture:{uuid.uuid4()}",
        trigger="manual",
    )
    client_observation = IntegrationObservation.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        job=job,
        remote_type="client",
        remote_id=remote_client_id,
        fingerprint="a" * 64,
        safe_projection={"id": int(remote_client_id), "name": client_record.entity.display_name},
    )
    IntegrationEntityMapping.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        remote_type="client",
        remote_id=remote_client_id,
        local_entity=client_record.entity,
        observed_fingerprint=client_observation.fingerprint,
        last_observed_at=client_observation.observed_at,
    )
    return IntegrationObservation.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        job=job,
        remote_type="ticket",
        remote_id="1042",
        fingerprint="b" * 64,
        safe_projection={
            "id": 1042,
            "summary": "Printer queue unavailable",
            "client_id": int(remote_client_id),
            "statusname": "In progress",
            "priority": "High",
            "team": "Service desk",
            "agent_name": "Taylor",
            "external_url": "https://support.example.invalid/tickets?id=1042",
        },
    )


class HaloClientAdapter:
    key = "halopsa"
    label = HaloPSAProvider.label
    contract = HaloPSAProvider.contract

    def __init__(self, name):
        self.name = name

    def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
        return ProviderPage(
            (
                ProviderObservation(
                    "client",
                    "24",
                    ("a" if self.name == "Mapped client" else "c") * 64,
                    {"id": 24, "name": self.name},
                ),
            ),
            "",
            complete_types=("client",),
        )


@pytest.mark.django_db
def test_exact_client_reconciliation_is_idempotent_across_provider_rename(installation):
    selected = organization(installation, "Mapped client")
    connection = halo_connection(installation)
    first = IntegrationSyncJob.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        idempotency_key="halo-client:first",
        trigger="manual",
    )

    process_sync_job(job_id=first.id, adapter=HaloClientAdapter("Mapped client"))
    mapping = IntegrationEntityMapping.objects.get(connection=connection, remote_type="client", remote_id="24")
    assert mapping.local_entity_id == selected.entity_id

    second = IntegrationSyncJob.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        idempotency_key="halo-client:renamed",
        trigger="manual",
    )
    process_sync_job(job_id=second.id, adapter=HaloClientAdapter("Mapped client renamed in Halo"))

    mapping.refresh_from_db()
    assert mapping.local_entity_id == selected.entity_id
    assert mapping.observed_fingerprint == "c" * 64
    assert IntegrationEntityMapping.objects.filter(connection=connection, remote_id="24").count() == 1


@pytest.mark.django_db
def test_mapped_ticket_summary_is_staff_only_client_scoped_and_stale(installation):
    selected = organization(installation, "Mapped client")
    sibling = organization(installation, "Sibling client")
    connection = halo_connection(installation)
    observed_ticket(installation, connection, selected)
    browser = Client()
    browser.force_login(installation.owner)

    selected_url = reverse(
        "organization-halopsa-ticket-summary-list",
        kwargs={"organization_entity_id": selected.entity_id},
    )
    response = browser.get(selected_url)
    sibling_response = browser.get(
        reverse(
            "organization-halopsa-ticket-summary-list",
            kwargs={"organization_entity_id": sibling.entity_id},
        )
    )

    assert response.status_code == 200
    assert response.json()[0]["number"] == "1042"
    assert response.json()[0]["stale"] is True
    assert response.json()[0]["external_url"] == "https://support.example.invalid/tickets?id=1042"
    assert sibling_response.json() == []
    assert "details" not in response.content.decode()

    portal_user = User.objects.create_user(email="halo-client@example.invalid", display_name="Client User")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=portal_user,
        role=BuiltInRole.CLIENT_USER,
        organization=selected,
    )
    portal = Client()
    portal.force_login(portal_user)
    assert portal.get(selected_url).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_runtime_role_can_project_msp_halo_data_into_only_the_selected_client(installation, django_runtime_role):
    selected = organization(installation, "Runtime mapped client")
    sibling = organization(installation, "Runtime sibling client")
    connection = halo_connection(installation)
    observed_ticket(installation, connection, selected)
    browser = Client()
    browser.force_login(installation.owner)

    with django_runtime_role():
        selected_response = browser.get(
            reverse(
                "organization-halopsa-ticket-summary-list",
                kwargs={"organization_entity_id": selected.entity_id},
            )
        )
        sibling_response = browser.get(
            reverse(
                "organization-halopsa-ticket-summary-list",
                kwargs={"organization_entity_id": sibling.entity_id},
            )
        )

    assert selected_response.status_code == 200
    assert [item["number"] for item in selected_response.json()] == ["1042"]
    assert sibling_response.status_code == 200
    assert sibling_response.json() == []


@pytest.mark.django_db
def test_global_search_returns_only_mapped_external_ticket_title_and_number(installation):
    selected = organization(installation, "Search client")
    connection = halo_connection(installation)
    observed_ticket(installation, connection, selected)
    browser = Client()
    browser.force_login(installation.owner)

    response = browser.get(
        reverse("organization-workspace-search", kwargs={"organization_entity_id": selected.entity_id}),
        {"q": "1042", "result_type": "external_ticket"},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["title"] == "#1042 Printer queue unavailable"
    assert result["target"] == "https://support.example.invalid/tickets?id=1042"
    assert result["result_type"] == "external_ticket"
    assert "ticket body" not in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_ticket_projection_works_without_an_outer_transaction(installation):
    if database_connection.vendor != "postgresql":
        pytest.skip("Transaction-local RLS restoration requires PostgreSQL")
    selected = organization(installation, "Direct search client")
    connection = halo_connection(installation)
    observed_ticket(installation, connection, selected)
    workspace = resolve_organization_workspace(installation.owner, entity_id=selected.entity_id)

    assert database_connection.in_atomic_block is False
    assert [item["number"] for item in halo_ticket_summaries(workspace)] == ["1042"]
