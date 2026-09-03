import json
import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.integration_providers import ProviderObservation, ProviderPage
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import process_sync_job, resolve_conflict
from apps.core.models import (
    Entity,
    InstallationState,
    IntegrationConflict,
    IntegrationConnection,
    IntegrationEntityMapping,
    IntegrationObservation,
    IntegrationSyncJob,
    Tenant,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset
from apps.core.workspaces import resolve_msp_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="NinjaOne integration MSP",
        owner_email="ninja-owner@example.invalid",
        owner_display_name="Ninja Owner",
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


def ninja_connection(installation):
    connection_id = uuid.uuid4()
    return IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=None),
        organization=None,
        provider="ninjaone",
        name="Primary NinjaOne",
        base_url="https://app.ninjarmm.com/",
        configuration={"client_id": "ninjaone-client-id"},
        secret_envelope=encrypt_integration_secret(
            secret=json.dumps({"client_secret": "ninjaone-client-secret"}).encode(),
            tenant_id=installation.tenant.id,
            connection_id=connection_id,
            generation=1,
        ),
        sync_interval_minutes=60,
        created_by=installation.owner,
    )


class PageAdapter:
    key = "ninjaone"
    label = "NinjaOne"

    def __init__(self, observations, complete_types=()):
        from apps.core.integration_providers import NinjaOneProvider

        self.contract = NinjaOneProvider.contract
        self.observations = tuple(observations)
        self.complete_types = complete_types

    def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
        return ProviderPage(self.observations, "", complete_types=self.complete_types)


def sync(installation, connection, observations, *, key=None, complete_types=()):
    job = IntegrationSyncJob.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        idempotency_key=key or f"ninja:{uuid.uuid4()}",
        trigger="manual",
    )
    return process_sync_job(job_id=job.id, adapter=PageAdapter(observations, complete_types))


def accept(installation, conflict):
    return resolve_conflict(
        workspace=resolve_msp_workspace(installation.owner),
        conflict_id=conflict.id,
        actor=installation.owner,
        resolution="accept_remote",
    )


@pytest.mark.django_db
def test_ninjaone_setup_encrypts_secret_and_returns_only_client_id(installation, monkeypatch):
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: True)

    response = browser.post(
        reverse("msp-integration-connection-list-create"),
        data=json.dumps(
            {
                "provider": "ninjaone",
                "name": "Primary NinjaOne",
                "base_url": "https://app.ninjarmm.com/",
                "credentials": {"client_id": "dedicated-monitoring-app", "client_secret": "never-return-secret"},
                "sync_interval_minutes": 30,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["provider_details"] == {"client_id": "dedicated-monitoring-app"}
    assert "never-return-secret" not in response.content.decode()
    stored = IntegrationConnection.objects.get(name="Primary NinjaOne")
    plaintext = decrypt_integration_secret(
        envelope_payload=stored.secret_envelope,
        tenant_id=stored.tenant_id,
        connection_id=stored.id,
        generation=stored.secret_generation,
    )
    assert json.loads(plaintext) == {"client_secret": "never-return-secret"}


@pytest.mark.django_db
def test_device_requires_accepted_organization_then_previews_serial_manufacturer_match(installation):
    selected = organization(installation, "Mapped client")
    asset = create_network_hardware_asset(installation=installation, organization=selected, name="Original asset name")
    asset.hardware.serial_number = "SERIAL-42"
    asset.hardware.save(update_fields=("serial_number",))
    manufacturer = asset.supplier.entity.display_name
    connection = ninja_connection(installation)

    sync(
        installation,
        connection,
        [ProviderObservation("organization", "8", "a" * 64, {"id": 8, "name": "Mapped client"})],
    )
    organization_conflict = connection.conflicts.get(remote_type="organization", remote_id="8", status="open")
    assert organization_conflict.suggested_local_entity_id == selected.entity_id
    assert not IntegrationEntityMapping.objects.filter(connection=connection, remote_type="organization").exists()
    accept(installation, organization_conflict)

    sync(
        installation,
        connection,
        [
            ProviderObservation(
                "device_status",
                "42",
                "b" * 64,
                {"id": 42, "organizationId": 8, "displayName": "RENAMED-HOST"},
            ),
            ProviderObservation(
                "device",
                "42",
                "c" * 64,
                {"deviceId": 42, "name": "RENAMED-HOST", "manufacturer": manufacturer, "serialNumber": "SERIAL-42"},
            ),
        ],
    )
    conflict = connection.conflicts.get(remote_type="device", remote_id="42", status="open")
    assert conflict.suggested_local_entity_id == asset.entity_id
    assert asset.entity.display_name == "Original asset name"
    assert not IntegrationEntityMapping.objects.filter(connection=connection, remote_type="device").exists()

    accept(installation, conflict)
    mapping = IntegrationEntityMapping.objects.get(connection=connection, remote_type="device", remote_id="42")
    assert mapping.local_entity_id == asset.entity_id

    sync(
        installation,
        connection,
        [
            ProviderObservation(
                "device",
                "42",
                "d" * 64,
                {"deviceId": 42, "name": "RENAMED-AGAIN", "manufacturer": manufacturer, "serialNumber": "SERIAL-42"},
            )
        ],
    )
    rename_conflict = connection.conflicts.get(remote_type="device", remote_id="42", status="open")
    asset.entity.refresh_from_db()
    assert asset.entity.display_name == "Original asset name"
    accept(installation, rename_conflict)
    mapping.refresh_from_db()
    assert mapping.observed_fingerprint == "d" * 64


@pytest.mark.django_db
def test_hostname_only_and_second_remote_device_for_same_asset_are_not_auto_linked(installation):
    selected = organization(installation, "Collision client")
    asset = create_network_hardware_asset(installation=installation, organization=selected, name="SHARED-HOST")
    asset.hardware.serial_number = "DUPLICATE-SERIAL"
    asset.hardware.save(update_fields=("serial_number",))
    manufacturer = asset.supplier.entity.display_name
    connection = ninja_connection(installation)
    IntegrationEntityMapping.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        remote_type="organization",
        remote_id="9",
        local_entity=selected.entity,
        observed_fingerprint="a" * 64,
        last_observed_at=connection.created_at,
    )
    IntegrationObservation.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        job=IntegrationSyncJob.objects.create(
            tenant=installation.tenant,
            workspace=connection.workspace,
            organization=None,
            connection=connection,
            idempotency_key="ninja:status-fixture",
            trigger="manual",
        ),
        remote_type="device_status",
        remote_id="43",
        fingerprint="b" * 64,
        safe_projection={"id": 43, "organizationId": 9, "displayName": "SHARED-HOST"},
    )
    sync(
        installation,
        connection,
        [ProviderObservation("device", "43", "c" * 64, {"deviceId": 43, "name": "SHARED-HOST"})],
    )
    assert connection.conflicts.get(remote_type="device", remote_id="43", status="open").local_entity_id is None

    IntegrationEntityMapping.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        remote_type="device",
        remote_id="42",
        local_entity=asset.entity,
        observed_fingerprint="d" * 64,
        last_observed_at=connection.created_at,
    )
    sync(
        installation,
        connection,
        [
            ProviderObservation(
                "device",
                "43",
                "e" * 64,
                {"deviceId": 43, "manufacturer": manufacturer, "serialNumber": "DUPLICATE-SERIAL"},
            )
        ],
    )
    assert connection.conflicts.get(remote_type="device", remote_id="43", status="open").local_entity_id is None


@pytest.mark.django_db
def test_observation_api_labels_link_review_acceptance_and_staleness(installation):
    selected = organization(installation, "API state client")
    asset = create_network_hardware_asset(installation=installation, organization=selected, name="Reception laptop")
    asset.hardware.serial_number = "API-SERIAL"
    asset.hardware.save(update_fields=("serial_number",))
    connection = ninja_connection(installation)

    sync(
        installation,
        connection,
        [ProviderObservation("organization", "18", "a" * 64, {"id": 18, "name": "API state client"})],
    )
    accept(installation, connection.conflicts.get(remote_type="organization", remote_id="18", status="open"))
    sync(
        installation,
        connection,
        [
            ProviderObservation("device_status", "82", "b" * 64, {"id": 82, "organizationId": 18}),
            ProviderObservation(
                "device",
                "82",
                "c" * 64,
                {
                    "deviceId": 82,
                    "manufacturer": asset.supplier.entity.display_name,
                    "serialNumber": "API-SERIAL",
                },
            ),
        ],
    )
    connection.health_status = "degraded"
    connection.save(update_fields=("health_status",))

    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(reverse("msp-integration-observation-list"))

    assert response.status_code == 200
    device = next(item for item in response.json()["results"] if item["remote_type"] == "device")
    assert device["linked_local_entity_id"] is None
    assert device["linked_local_entity_name"] == ""
    assert device["accepted"] is False
    assert device["stale"] is True
    conflict = connection.conflicts.get(remote_type="device", remote_id="82", status="open")
    conflict_response = browser.get(reverse("msp-integration-conflict-list"))
    serialized = next(item for item in conflict_response.json()["results"] if item["id"] == str(conflict.id))
    assert serialized["local_entity_id"] == str(asset.entity_id)
    assert serialized["local_entity_name"] == "Reception laptop"
    assert serialized["provider_values"]["serialNumber"] == "API-SERIAL"

    accept(installation, conflict)
    accepted_response = browser.get(reverse("msp-integration-observation-list"))
    accepted_device = next(
        item for item in accepted_response.json()["results"] if item["remote_type"] == "device"
    )
    assert accepted_device["linked_local_entity_id"] == str(asset.entity_id)
    assert accepted_device["linked_local_entity_name"] == "Reception laptop"
    assert accepted_device["accepted"] is True
    asset.entity.refresh_from_db()
    assert asset.entity.display_name == "Reception laptop"

@pytest.mark.django_db
def test_removed_device_creates_review_without_archiving_local_inventory(installation):
    selected = organization(installation, "Removal client")
    asset = create_network_hardware_asset(installation=installation, organization=selected, name="Retained asset")
    connection = ninja_connection(installation)
    IntegrationEntityMapping.objects.create(
        tenant=installation.tenant,
        workspace=connection.workspace,
        organization=None,
        connection=connection,
        remote_type="device",
        remote_id="77",
        local_entity=asset.entity,
        observed_fingerprint="a" * 64,
        last_observed_at=connection.created_at,
    )

    sync(
        installation,
        connection,
        [ProviderObservation("device", "77", "a" * 64, {}, state="retired")],
    )

    conflict = connection.conflicts.get(remote_type="device", remote_id="77", status="open")
    assert conflict.difference == "retired_remote"
    asset.refresh_from_db()
    assert asset.archived_at is None


@pytest.mark.django_db
def test_database_rejects_a_cross_tenant_reconciliation_suggestion(installation):
    connection = ninja_connection(installation)
    foreign_tenant = Tenant.objects.create(name="Foreign Ninja tenant", slug=f"foreign-ninja-{uuid.uuid4()}")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        entity_type="asset",
        display_name="Foreign asset",
    )

    with pytest.raises(DatabaseError, match="suggestion tenant mismatch"), transaction.atomic():
        IntegrationConflict.objects.create(
            tenant=installation.tenant,
            workspace=connection.workspace,
            organization=None,
            connection=connection,
            suggested_local_entity=foreign_entity,
            remote_type="device",
            remote_id="foreign-device",
            difference="changed",
            remote_fingerprint="f" * 64,
        )
