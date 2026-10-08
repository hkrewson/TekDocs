import hashlib
import io
import json
import secrets
import uuid
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_service, repository_storage
from apps.core.content_index import index_repository_content
from apps.core.content_profile import parse_content
from apps.core.documents import create_document
from apps.core.git_exports import _manifest_has_credential_reference, create_git_export
from apps.core.integration_providers import (
    PROVIDERS,
    NetBoxProvider,
    ProviderObservation,
    ProviderPage,
    netbox_authorization,
    provider_catalog,
    validate_provider_adapter,
)
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import enqueue_sync, process_sync_job
from apps.core.models import (
    ClientAsset,
    CredentialReference,
    Entity,
    GitExportBundle,
    InstallationState,
    IntegrationConflict,
    IntegrationConnection,
    IntegrationJobState,
    IntegrationLogEvent,
    IntegrationObservation,
    IntegrationSyncJob,
    NetBoxReference,
    NetworkDevice,
    NetworkIPAddress,
    NetworkMACAddress,
    NetworkSubnet,
    OrganizationKind,
    Workspace,
    workspace_for_owner,
)
from apps.core.netbox_publication import preview_netbox_publication, publish_netbox_proposal
from apps.core.network_addressing import create_subnet, create_vlan, create_vrf
from apps.core.network_endpoints import create_interface, create_ip_address, create_mac_address
from apps.core.network_inventory import create_device, create_rack
from apps.core.organizations import create_organization
from apps.core.sites import create_site
from apps.core.tasks import dispatch_integration_syncs, process_integration_sync_job
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Integration MSP",
        owner_email="integration-owner@example.invalid",
        owner_display_name="Integration Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


TEST_PROVIDER_TOKEN = "-".join(("provider", "token", "value"))


def test_static_manifest_credential_metadata_is_not_exportable():
    assert _manifest_has_credential_reference(
        {"entities": [{"id": str(uuid.uuid4()), "entity_type": "credential_reference"}]}
    )
    assert not _manifest_has_credential_reference({"entities": [{"id": str(uuid.uuid4()), "entity_type": "network"}]})


@pytest.mark.parametrize(
    ("secret", "expected_scheme"),
    (("nbt_key.plaintext-value", "Bearer"), (TEST_PROVIDER_TOKEN, "Token")),
)
def test_netbox_authentication_scheme_matches_token_version(secret, expected_scheme):  # type: ignore[no-untyped-def]
    authorization = netbox_authorization(secret)

    assert authorization == f"{expected_scheme} {secret}"


def organization(installation, name):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=[OrganizationKind.CLIENT],
    )


@pytest.mark.django_db
def test_network_cleanup_rehearsal_is_report_only_by_default(installation):
    record = organization(installation, "Cleanup rehearsal client")
    output = io.StringIO()

    call_command("rehearse_network_model_cleanup", organization=str(record.entity_id), stdout=output)

    report = json.loads(output.getvalue())
    assert report["workspace"] == str(record.entity_id)
    assert report["applied"] is False
    assert report["blockers"] == []


@pytest.mark.django_db
def test_network_cleanup_rehearsal_backfills_only_stable_relationships_in_one_workspace(installation):
    record = organization(installation, "Cleanup rehearsal client")
    sibling = organization(installation, "Cleanup rehearsal sibling")
    asset = create_network_hardware_asset(installation=installation, organization=record, name="Cleanup switch")
    site = create_site(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup site",
        code="CLEAN",
        address_line_1="",
        address_line_2="",
        city="Madison",
        region="WI",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    rack = create_rack(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup rack",
        site_entity_id=site.entity_id,
        location_entity_id=None,
        unit_count=42,
        status="active",
    )
    device = create_device(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup switch",
        role="switch",
        status="active",
        hardware_asset_entity_id=asset.entity_id,
        site_entity_id=None,
        location_entity_id=None,
        rack_entity_id=rack.entity_id,
        rack_unit=10,
        rack_units=2,
    )
    vlan = create_vlan(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup VLAN",
        vlan_id=42,
        description="",
    )
    vrf = create_vrf(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup VRF",
        route_distinguisher="65000:42",
        description="",
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Cleanup subnet",
        cidr="192.0.2.0/24",
        vrf_entity_id=vrf.entity_id,
        vlan_entity_id=vlan.entity_id,
        description="",
    )
    interface = create_interface(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Ethernet1",
        device_entity_id=device.entity_id,
        kind="physical",
        status="active",
        description="",
    )
    ip_address = create_ip_address(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        address="192.0.2.10",
        subnet_entity_id=subnet.entity_id,
        interface_entity_id=interface.entity_id,
        status="active",
        dns_name="",
        description="",
    )
    mac_address = create_mac_address(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        address="02:00:00:00:00:10",
        interface_entity_id=interface.entity_id,
        description="",
    )
    NetworkSubnet.objects.filter(pk=subnet.pk).update(vlan_number=None)
    NetworkDevice.objects.filter(pk=device.pk).update(
        source_rack_name="", source_rack_position=None, source_rack_units=None
    )

    sibling_output = io.StringIO()
    call_command("rehearse_network_model_cleanup", organization=str(sibling.entity_id), stdout=sibling_output)
    assert json.loads(sibling_output.getvalue())["legacy"]["interfaces"] == 0

    preview_output = io.StringIO()
    call_command("rehearse_network_model_cleanup", organization=str(record.entity_id), stdout=preview_output)
    preview = json.loads(preview_output.getvalue())
    assert preview["legacy"] == {
        "racks": 1,
        "vlans": 1,
        "vrfs": 1,
        "interfaces": 1,
        "circuits": 0,
        "circuit_handoffs": 0,
        "unbacked_devices": 0,
    }
    assert preview["legacy_relationships"] == {
        "subnets_to_vlans": 1,
        "subnets_to_vrfs": 1,
        "devices_to_racks": 1,
        "ip_addresses_to_interfaces": 1,
        "mac_addresses_to_interfaces": 1,
        "handoffs_to_interfaces": 0,
    }
    assert preview["planned_backfills"] == {
        "network_vlan_numbers": 1,
        "device_rack_facts": 1,
        "ip_asset_assignments": 1,
        "mac_asset_assignments": 1,
    }
    assert preview["blockers"] == []
    assert preview["applied"] is False
    assert NetworkIPAddress.objects.get(pk=ip_address.pk).hardware_asset_id is None
    assert NetworkMACAddress.objects.get(pk=mac_address.pk).hardware_asset_id is None

    apply_output = io.StringIO()
    call_command(
        "rehearse_network_model_cleanup",
        organization=str(record.entity_id),
        apply=True,
        stdout=apply_output,
    )
    applied = json.loads(apply_output.getvalue())
    assert applied["applied"] is True
    subnet.refresh_from_db()
    device.refresh_from_db()
    ip_address.refresh_from_db()
    mac_address.refresh_from_db()
    assert subnet.vlan_number == 42
    assert device.source_rack_name == "Cleanup rack"
    assert device.source_rack_position == 10
    assert device.source_rack_units == 2
    assert ip_address.hardware_asset_id == asset.id
    assert mac_address.hardware_asset_id == asset.id
    assert preview["disposition"] == {
        "legacy_records": "retained",
        "destructive_removal": "requires_separate_deprecation_and_operator_approved_migration",
    }
    assert NetworkSubnet.objects.filter(pk=subnet.pk, vlan=vlan, vrf=vrf).exists()


def connection(  # type: ignore[no-untyped-def]
    installation, record, *, name="Primary NetBox", token=None, base_url="https://netbox.example.com/api/"
):
    token = token or TEST_PROVIDER_TOKEN
    connection_id = uuid.uuid4()
    return IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=record),
        organization=record,
        provider="netbox",
        name=name,
        base_url=base_url,
        configuration={},
        secret_envelope=encrypt_integration_secret(
            secret=token.encode(),
            tenant_id=installation.tenant.id,
            connection_id=connection_id,
            generation=1,
        ),
        created_by=installation.owner,
    )


@pytest.mark.django_db
def test_connection_api_identifies_expired_reauthentication_without_saving(installation, monkeypatch):
    record = organization(installation, "Expired session client")
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: False)
    response = browser.post(
        reverse(
            "organization-integration-connection-list-create",
            kwargs={"organization_entity_id": record.entity_id},
        ),
        data=json.dumps(
            {
                "provider": "netbox",
                "name": "Production NetBox",
                "base_url": "https://netbox.example.com/",
                "credentials": {"api_token": TEST_PROVIDER_TOKEN},
                "sync_interval_minutes": 30,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "recent_authentication_required"
    assert not IntegrationConnection.objects.exists()


@pytest.mark.django_db
def test_connection_api_encrypts_token_and_never_returns_it(installation, monkeypatch):
    record = organization(installation, "Connection client")
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: True)
    path = reverse(
        "organization-integration-connection-list-create",
        kwargs={"organization_entity_id": record.entity_id},
    )
    response = browser.post(
        path,
        data=json.dumps(
            {
                "provider": "netbox",
                "name": "Production NetBox",
                "base_url": "https://netbox.example.com/api/",
                "api_token": "do-not-return-this-token",
                "sync_interval_minutes": 30,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["base_url"] == "https://netbox.example.com/api/"
    assert response.json()["credential_configured"] is True
    assert "api_token" not in response.json()
    stored = IntegrationConnection.objects.get()
    assert "do-not-return-this-token" not in json.dumps(stored.secret_envelope)
    assert (
        decrypt_integration_secret(
            envelope_payload=stored.secret_envelope,
            tenant_id=stored.tenant_id,
            connection_id=stored.id,
            generation=stored.secret_generation,
        )
        == b"do-not-return-this-token"
    )
    assert "api_token" not in browser.get(path).content.decode()


@pytest.mark.django_db
def test_netbox_provider_tolerates_a_preexisting_site_root_connection(installation):
    record = organization(installation, "Root URL client")
    source = connection(installation, record, base_url="https://netbox.example.com/")
    request: dict[str, str] = {}

    def fetcher(**kwargs):  # type: ignore[no-untyped-def]
        request.update(kwargs)
        return {"results": [], "next": None}

    page = NetBoxProvider(fetcher=fetcher).fetch_page(source, secret=TEST_PROVIDER_TOKEN, cursor="")

    assert request["base_url"] == "https://netbox.example.com/api/"
    assert request["relative_path"] == "ipam/prefixes/"
    assert page.next_cursor == "1|dcim/devices/"


@pytest.mark.django_db
def test_netbox_provider_retains_only_supported_prefix_and_device_facts(installation):
    record = organization(installation, "Projection client")
    source = connection(installation, record)
    pages = {
        "ipam/prefixes/": {
            "results": [
                {
                    "id": 41,
                    "prefix": "10.42.0.0/24",
                    "description": "Users",
                    "vlan": {"id": 3, "vid": 120},
                    "tenant": {"id": 9, "name": "Private"},
                }
            ],
            "next": None,
        },
        "dcim/devices/": {
            "results": [
                {
                    "id": 51,
                    "name": "arrakis",
                    "serial": "SERIAL-1",
                    "status": {"value": "active"},
                    "role": {"slug": "switch"},
                    "device_type": {"model": "C9300", "u_height": 1, "manufacturer": {"name": "Cisco"}},
                    "rack": {"name": "Core rack"},
                    "position": 12.0,
                    "tenant": {"id": 9},
                }
            ],
            "next": None,
        },
    }

    def fetcher(**kwargs):  # type: ignore[no-untyped-def]
        return pages[kwargs["relative_path"]]

    prefix = NetBoxProvider(fetcher=fetcher).fetch_page(source, secret=TEST_PROVIDER_TOKEN, cursor="")
    device = NetBoxProvider(fetcher=fetcher).fetch_page(source, secret=TEST_PROVIDER_TOKEN, cursor=prefix.next_cursor)
    assert prefix.observations[0].safe_projection == {
        "id": 41,
        "prefix": "10.42.0.0/24",
        "description": "Users",
        "vlan_id": 120,
    }
    assert device.observations[0].safe_projection == {
        "id": 51,
        "name": "arrakis",
        "serial": "SERIAL-1",
        "status": "active",
        "role": "switch",
        "model": "C9300",
        "manufacturer": "Cisco",
        "rack": "Core rack",
        "position": 12.0,
        "height": 1,
    }


@pytest.mark.django_db
def test_connection_api_edits_details_without_rotating_the_credential(installation):
    record = organization(installation, "Editable connection client")
    source = connection(installation, record, base_url="https://netbox.example.com/")
    source.health_status = "degraded"
    source.last_error_code = "provider_http_error"
    source.save(update_fields=("health_status", "last_error_code", "updated_at"))
    original_envelope = source.secret_envelope
    original_generation = source.secret_generation
    browser = Client()
    browser.force_login(installation.owner)

    response = browser.patch(
        reverse(
            "organization-integration-connection-detail",
            kwargs={"organization_entity_id": record.entity_id, "connection_id": source.id},
        ),
        data=json.dumps(
            {
                "name": "  Client   NetBox  ",
                "base_url": "https://netbox.example.com/",
                "active": True,
                "sync_interval_minutes": 30,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Client NetBox"
    assert response.json()["base_url"] == "https://netbox.example.com/api/"
    source.refresh_from_db()
    assert source.health_status == "unknown"
    assert source.last_error_code == ""
    assert source.secret_generation == original_generation
    assert source.secret_envelope == original_envelope


@pytest.mark.django_db
def test_microsoft_connection_fixes_graph_origin_and_separates_secret_configuration(installation, monkeypatch):
    record = organization(installation, "Microsoft client")
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: True)
    path = reverse(
        "organization-integration-connection-list-create",
        kwargs={"organization_entity_id": record.entity_id},
    )
    tenant_id = "11111111-1111-1111-1111-111111111111"
    client_id = "22222222-2222-2222-2222-222222222222"
    response = browser.post(
        path,
        data=json.dumps(
            {
                "provider": "microsoft_graph",
                "name": "Client Microsoft 365",
                "credentials": {
                    "tenant_id": tenant_id,
                    "client_id": client_id,
                    "client_secret": "microsoft-client-secret",
                },
                "sync_interval_minutes": 60,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["base_url"] == "https://graph.microsoft.com/v1.0/"
    assert response.json()["provider_details"] == {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "permission_status": "not_validated",
    }
    assert "client_secret" not in response.content.decode()
    stored = IntegrationConnection.objects.get(name="Client Microsoft 365")
    assert stored.configuration == {"tenant_id": tenant_id, "client_id": client_id}
    envelope = json.dumps(stored.secret_envelope)
    assert "microsoft-client-secret" not in envelope


@pytest.mark.django_db
def test_connection_listing_is_exact_workspace(installation, monkeypatch):
    first = organization(installation, "First client")
    second = organization(installation, "Second client")
    connection(installation, first, name="First source")
    connection(installation, second, name="Second source")
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(
        reverse(
            "organization-integration-connection-list-create",
            kwargs={"organization_entity_id": first.entity_id},
        )
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["First source"]


@pytest.mark.django_db
def test_observation_api_returns_only_safe_exact_workspace_projections(installation):
    first = organization(installation, "Observed client")
    second = organization(installation, "Sibling observed client")
    first_connection = connection(installation, first, name="Observed source")
    second_connection = connection(installation, second, name="Sibling source")
    for source, key in ((first_connection, "visible"), (second_connection, "hidden")):
        job = enqueue_sync(connection=source, trigger="manual", idempotency_key=f"observation:{key}")
        IntegrationObservation.objects.create(
            tenant=source.tenant,
            workspace=source.workspace,
            organization=source.organization,
            job=job,
            remote_type="user",
            remote_id=key,
            fingerprint="a" * 64,
            safe_projection={"displayName": key},
        )
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.get(
        reverse(
            "organization-integration-observation-list",
            kwargs={"organization_entity_id": first.entity_id},
        )
    )
    assert response.status_code == 200
    assert [item["remote_id"] for item in response.json()["results"]] == ["visible"]
    assert response.json()["results"][0]["safe_projection"] == {"displayName": "visible"}
    assert "fingerprint" not in response.content.decode()


@pytest.mark.django_db
def test_observation_api_lists_each_current_source_record_once_and_supports_search(installation):
    record = organization(installation, "Current observations")
    source = connection(installation, record, name="Current source")
    first_job = enqueue_sync(connection=source, trigger="manual", idempotency_key="observation:current:first")
    second_job = enqueue_sync(connection=source, trigger="manual", idempotency_key="observation:current:second")
    IntegrationObservation.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        job=first_job,
        remote_type="dcim.device",
        remote_id="17",
        fingerprint="a" * 64,
        safe_projection={"name": "Old Arrakis"},
    )
    current = IntegrationObservation.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        job=second_job,
        remote_type="dcim.device",
        remote_id="17",
        fingerprint="b" * 64,
        safe_projection={"name": "Arrakis"},
    )
    conflict = IntegrationConflict.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        connection=source,
        observation=current,
        remote_type="dcim.device",
        remote_id="17",
        difference="unmatched",
    )
    IntegrationObservation.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        job=second_job,
        remote_type="ipam.ipaddress",
        remote_id="44",
        fingerprint="c" * 64,
        safe_projection={"display": "192.0.2.44/32"},
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-integration-observation-list",
        kwargs={"organization_entity_id": record.entity_id},
    )

    response = browser.get(url, {"page": 1, "page_size": 25})
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [item["remote_type"] for item in response.json()["results"]] == ["dcim.device", "ipam.ipaddress"]
    assert response.json()["results"][0]["id"] == str(current.id)
    assert response.json()["results"][0]["open_conflict"]["id"] == str(conflict.id)
    assert response.json()["results"][0]["open_conflict"]["provider_values"] == {"name": "Arrakis"}
    assert response.json()["results"][1]["open_conflict"] is None

    searched = browser.get(url, {"q": "arrakis", "remote_type": "dcim.device"})
    assert searched.status_code == 200
    assert [item["id"] for item in searched.json()["results"]] == [str(current.id)]


@pytest.mark.django_db
def test_conflict_api_filters_open_review_queue_before_paging(installation):
    record = organization(installation, "Bounded review client")
    source = connection(installation, record, name="Review source")
    for number in range(30):
        IntegrationConflict.objects.create(
            tenant=source.tenant,
            workspace=source.workspace,
            organization=source.organization,
            connection=source,
            remote_type="ipam.ipaddress",
            remote_id=f"resolved-{number}",
            difference="unmatched",
            status="ignored",
            resolved_by=installation.owner,
            resolved_at=timezone.now(),
        )
    expected = IntegrationConflict.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        connection=source,
        remote_type="dcim.device",
        remote_id="arrakis-23",
        difference="unmatched",
    )
    IntegrationConflict.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        connection=source,
        remote_type="dcim.rack",
        remote_id="rack-24",
        difference="unmatched",
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-integration-conflict-list",
        kwargs={"organization_entity_id": record.entity_id},
    )

    open_queue = browser.get(url, {"page": 1, "page_size": 25, "status": "open"})
    assert open_queue.status_code == 200
    assert open_queue.json()["count"] == 2

    searched = browser.get(
        url,
        {"page": 1, "page_size": 25, "status": "open", "remote_type": "dcim.device", "q": "arrakis"},
    )
    assert searched.status_code == 200
    assert searched.json()["count"] == 1
    assert searched.json()["results"][0]["id"] == str(expected.id)


@pytest.mark.django_db
def test_netbox_review_links_only_a_compatible_existing_supported_record(installation):
    record = organization(installation, "Link-only review client")
    source = connection(installation, record, name="Link source")
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="link-only:prefix")
    observation = IntegrationObservation.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        job=job,
        remote_type="ipam.prefix",
        remote_id="41",
        fingerprint="d" * 64,
        safe_projection={"prefix": "10.42.0.0/24"},
    )
    conflict = IntegrationConflict.objects.create(
        tenant=source.tenant,
        workspace=source.workspace,
        organization=source.organization,
        connection=source,
        observation=observation,
        remote_type="ipam.prefix",
        remote_id="41",
        difference="unmatched",
        remote_fingerprint=observation.fingerprint,
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Users",
        cidr="10.42.0.0/24",
        vrf_entity_id=None,
        vlan_entity_id=None,
        description="",
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-integration-netbox-adopt",
        kwargs={"organization_entity_id": record.entity_id, "conflict_id": conflict.id},
    )

    rejected = browser.post(
        url,
        data=json.dumps({"prefix": {"name": "Duplicate", "cidr": "10.42.0.0/24"}}),
        content_type="application/json",
    )
    assert rejected.status_code == 400
    assert NetworkSubnet.objects.filter(organization=record).count() == 1

    linked = browser.post(url, data=json.dumps({"entity_id": str(subnet.entity_id)}), content_type="application/json")
    assert linked.status_code == 200
    assert linked.json()["status"] == "accept_remote"
    assert NetBoxReference.objects.get(entity_id=subnet.entity_id).object_id == 41


@pytest.mark.django_db(transaction=True)
def test_database_rejects_a_cross_workspace_job_connection(installation):
    first = organization(installation, "Job owner")
    second = organization(installation, "Foreign connection owner")
    foreign_connection = connection(installation, second)
    with pytest.raises(DatabaseError), transaction.atomic():
        IntegrationSyncJob.objects.create(
            tenant=installation.tenant,
            workspace=workspace_for_owner(tenant=installation.tenant, organization=first),
            organization=first,
            connection=foreign_connection,
            idempotency_key="forged:cross-workspace",
            trigger="manual",
        )


class SuccessfulAdapter:
    key = "netbox"
    label = NetBoxProvider.label
    contract = NetBoxProvider.contract

    def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
        assert secret == TEST_PROVIDER_TOKEN
        assert cursor == ""
        return ProviderPage(
            observations=(ProviderObservation("ipam.prefix", "42", "a" * 64, {"id": 42, "prefix": "10.42.0.0/24"}),),
            next_cursor="",
            complete_types=("ipam.prefix",),
        )


class FailingAdapter:
    key = "netbox"
    label = NetBoxProvider.label
    contract = NetBoxProvider.contract

    def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
        raise ValueError("provider_response_invalid")


@pytest.mark.parametrize("adapter", (*PROVIDERS.values(), SuccessfulAdapter()), ids=lambda item: item.label)
def test_every_registered_and_fake_provider_obeys_the_reusable_contract(adapter):  # type: ignore[no-untyped-def]
    validate_provider_adapter(adapter)


def test_provider_catalog_is_a_complete_versioned_contract():
    contract = provider_catalog()[0]
    assert contract["key"] == "netbox"
    assert contract["version"] == "1.0"
    assert contract["direction"] == "read_write_reviewed"
    assert contract["pagination"] == "opaque_cursor"
    assert contract["observation_schema_version"] == 1
    assert contract["credential_fields"] == [
        {
            "key": "api_token",
            "label": "API token",
            "secret": True,
            "minimum_length": 8,
            "input_type": "password",
            "help_text": "Paste the complete token. NetBox v2 tokens start with nbt_ and include a period.",
        }
    ]


@pytest.mark.django_db
def test_duplicate_provider_objects_are_idempotent_and_safe(installation):
    record = organization(installation, "Duplicate page client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:duplicate-page")

    class DuplicateAdapter(SuccessfulAdapter):
        def fetch_page(self, connection, *, secret, cursor):  # type: ignore[no-untyped-def]
            item = ProviderObservation("ipam.prefix", "42", "a" * 64, {"id": 42, "prefix": "10.42.0.0/24"})
            return ProviderPage((item, item), "")

    completed = process_sync_job(job_id=job.id, adapter=DuplicateAdapter())
    observation = IntegrationObservation.objects.get(job=completed)
    assert completed.state == IntegrationJobState.SUCCEEDED
    assert observation.safe_projection == {"id": 42, "prefix": "10.42.0.0/24"}
    assert observation.schema_version == 1
    assert source.__class__.objects.get(pk=source.pk).health_status == "healthy"


@pytest.mark.django_db
def test_netbox_pagination_rejects_a_cross_origin_cursor(installation):
    record = organization(installation, "Cursor client")
    source = connection(installation, record)

    def hostile_page(**_kwargs):  # type: ignore[no-untyped-def]
        return {"results": [], "next": "https://attacker.example/api/ipam/vlans/?offset=50"}

    with pytest.raises(ValueError, match="provider_cursor_invalid"):
        NetBoxProvider(fetcher=hostile_page).fetch_page(source, secret=TEST_PROVIDER_TOKEN, cursor="")


@pytest.mark.django_db
def test_sync_job_is_idempotent_value_minimized_and_retryable(installation):
    record = organization(installation, "Sync client")
    source = connection(installation, record)
    first = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:stable-key")
    repeated = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:stable-key")
    assert repeated.id == first.id

    completed = process_sync_job(job_id=first.id, adapter=SuccessfulAdapter())
    assert completed.state == IntegrationJobState.SUCCEEDED
    observation = IntegrationObservation.objects.get(job=completed)
    assert (observation.remote_type, observation.remote_id, observation.fingerprint) == (
        "ipam.prefix",
        "42",
        "a" * 64,
    )
    assert NetworkSubnet.objects.filter(cidr="10.42.0.0/24").exists()
    assert not IntegrationConflict.objects.exists()
    assert set(IntegrationLogEvent.objects.values_list("code", flat=True)) == {
        "sync_started",
        "sync_page_succeeded",
        "sync_completed",
    }

    failed = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:failing-key")
    retried = process_sync_job(job_id=failed.id, adapter=FailingAdapter())
    assert retried.state == IntegrationJobState.PENDING
    assert retried.attempts == 1
    assert retried.last_error_code == "provider_response_invalid"


@pytest.mark.django_db
def test_netbox_sync_automatically_creates_asset_backed_device(installation):
    record = organization(installation, "Automatic device client")
    source = connection(installation, record)

    class DeviceAdapter:
        key = "netbox"
        label = NetBoxProvider.label
        contract = PROVIDERS["netbox"].contract

        def fetch_page(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return ProviderPage(
                observations=(
                    ProviderObservation(
                        "dcim.device",
                        "23",
                        "d" * 64,
                        {
                            "id": 23,
                            "name": "arrakis",
                            "serial": "ARR-1",
                            "manufacturer": "Cisco",
                            "model": "C9300",
                            "role": "switch",
                            "status": "active",
                            "rack": "Core rack",
                            "position": 12.0,
                            "height": 1,
                        },
                    ),
                ),
                next_cursor="",
                complete_types=("dcim.device",),
            )

    completed = process_sync_job(
        job_id=enqueue_sync(connection=source, trigger="manual", idempotency_key="device:auto").id,
        adapter=DeviceAdapter(),
    )
    asset = ClientAsset.objects.get(entity__display_name="arrakis")
    device = asset.network_device
    assert asset.hardware.serial_number == "ARR-1"
    assert asset.model.model_number == "C9300"
    assert (
        device.role,
        device.status,
        device.source_rack_name,
        device.source_rack_position,
        device.source_rack_units,
    ) == ("switch", "active", "Core rack", 12, 1)
    assert NetBoxReference.objects.get(entity=asset.entity).object_id == 23
    assert IntegrationObservation.objects.filter(job=completed).count() == 1
    assert not IntegrationConflict.objects.exists()


@pytest.mark.django_db
def test_unifi_network_publication_requires_exact_reviewed_current_proposal(installation):
    record = organization(installation, "Publication client")
    target = connection(installation, record)
    target.write_secret_envelope = encrypt_integration_secret(
        secret=b"separate-write-token",
        tenant_id=installation.tenant.id,
        connection_id=target.id,
        generation=1,
    )
    target.save(update_fields=("write_secret_envelope", "updated_at"))
    source_id = uuid.uuid4()
    source = IntegrationConnection.objects.create(
        id=source_id,
        tenant=installation.tenant,
        workspace=target.workspace,
        organization=record,
        provider="unifi",
        name="UniFi source",
        base_url="https://unifi.example.com/proxy/network/integration/",
        configuration={},
        secret_envelope=encrypt_integration_secret(
            secret=b'{"api_key":"unifi-test-key"}',
            tenant_id=installation.tenant.id,
            connection_id=source_id,
            generation=1,
        ),
        created_by=installation.owner,
    )
    job = IntegrationSyncJob.objects.create(
        tenant=installation.tenant,
        workspace=target.workspace,
        organization=record,
        connection=source,
        idempotency_key="publication:source",
        trigger="manual",
    )
    observation = IntegrationObservation.objects.create(
        tenant=installation.tenant,
        workspace=target.workspace,
        organization=record,
        job=job,
        remote_type="unifi.network",
        remote_id="network-1",
        fingerprint="a" * 64,
        safe_projection={"name": "Users", "cidr": "10.42.0.0/24"},
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=record.entity_id)
    current = {"results": []}
    proposal = preview_netbox_publication(
        workspace=workspace,
        source_observation_id=observation.id,
        connection_id=target.id,
        fetcher=lambda **_kwargs: current,
    )
    assert proposal["action"] == "create"
    assert proposal["fields"]["prefix"] == "10.42.0.0/24"

    sent = []
    result = publish_netbox_proposal(
        workspace=workspace,
        actor_id=installation.owner.id,
        source_observation_id=observation.id,
        connection_id=target.id,
        proposal_digest=str(proposal["proposal_digest"]),
        fetcher=lambda **_kwargs: current,
        sender=lambda **kwargs: sent.append(kwargs) or {"id": 99},
    )
    assert result["status"] == "published"
    assert sent[0]["method"] == "POST"
    assert sent[0]["authorization"] == "Token separate-write-token"

    current = {"results": [{"id": 99, "prefix": "10.42.0.0/24"}]}
    with pytest.raises(ValidationError, match="Review a fresh proposal"):
        publish_netbox_proposal(
            workspace=workspace,
            actor_id=installation.owner.id,
            source_observation_id=observation.id,
            connection_id=target.id,
            proposal_digest=str(proposal["proposal_digest"]),
            fetcher=lambda **_kwargs: current,
            sender=lambda **_kwargs: {"id": 99},
        )


@pytest.mark.django_db
def test_dispatcher_submits_provider_io_to_an_exact_workspace_worker_task(installation, monkeypatch):
    record = organization(installation, "Dispatch client")
    source = connection(installation, record)
    job = enqueue_sync(connection=source, trigger="manual", idempotency_key="request:dispatch-key")
    calls = []
    monkeypatch.setattr(process_integration_sync_job, "delay", lambda *args: calls.append(args))

    assert dispatch_integration_syncs() == 1
    assert calls == [
        (
            str(job.id),
            str(installation.tenant.id),
            str(source.workspace_id),
            str(source.organization_id),
        )
    ]


@pytest.mark.django_db
@override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
def test_git_export_is_deterministic_and_sanitizes_credential_and_attachment_links(installation, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    record = organization(installation, "Export client")
    document = create_document(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        title="Runbook",
        markdown=(
            "# Runbook\n\n"
            "[Open vault](https://start.1password.com/open/i?a=acct&v=vault&i=item)\n\n"
            "[Attachment](tekdocs://attachment/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa)\n"
        ),
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=record.entity_id)
    first = create_git_export(
        workspace=workspace,
        actor=installation.owner,
        document_entity_ids=[document.entity_id],
        publication_entity_ids=[],
    )
    second = create_git_export(
        workspace=workspace,
        actor=installation.owner,
        document_entity_ids=[document.entity_id],
        publication_entity_ids=[],
    )
    assert first.content_digest == second.content_digest
    assert first.byte_size == second.byte_size
    with first.artifact.open("rb") as stored:
        content = stored.read()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        exported_markdown = archive.read(f"documents/runbook--{document.entity_id}.md")
        export_manifest = json.loads(archive.read("tekdocs-export.json"))
    assert b"start.1password.com" not in exported_markdown
    assert b"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in exported_markdown
    assert "attachment_content" in export_manifest["exclusions"]
    assert GitExportBundle.objects.count() == 2


@pytest.mark.django_db(transaction=True)
@override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
def test_git_export_includes_exact_sanitized_repository_snapshot(installation, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.TEKDOCS_REPOSITORY_ROOT = str(tmp_path / "repositories")
    record = organization(installation, "Repository export client")
    workspace = resolve_organization_workspace(installation.owner, entity_id=record.entity_id)
    repository = repository_storage.ensure_workspace_repository(
        Workspace.objects.get(pk=workspace.data_scope.workspace_id)
    ).repository
    repository.refresh_from_db()
    credential_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=record,
        entity_type="credential_reference",
        display_name="Export credential",
    )
    CredentialReference.objects.create(
        tenant=installation.tenant,
        organization=record,
        entity=credential_entity,
        provider="onepassword",
        reference_url=(
            "https://start.1password.com/open/i?"
            "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
            "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
        ),
    )
    content_id = uuid.uuid4()
    source = (
        f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: document\ntitle: Export runbook\n"
        f"key_bindings:\n  admin: {credential_entity.id}\n"
        f"entity_links:\n  - id: {credential_entity.id}\n    relationship: maintenance\n"
        "---\n# Export runbook\n\n"
        f"[Credential](tekdocs://entity/{credential_entity.id})\n\n"
        "[File](tekdocs://attachment/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa)\n"
    ).encode()
    committed = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
        changes={"documents/export-runbook.md": source},
        message="Add export runbook",
    )
    index_repository_content(repository_id=repository.id)
    first = create_git_export(
        workspace=workspace,
        actor=installation.owner,
        document_entity_ids=[],
        publication_entity_ids=[],
        include_repository=True,
    )
    second = create_git_export(
        workspace=workspace,
        actor=installation.owner,
        document_entity_ids=[],
        publication_entity_ids=[],
        include_repository=True,
    )
    assert first.content_digest == second.content_digest
    with first.artifact.open("rb") as stored, zipfile.ZipFile(io.BytesIO(stored.read())) as archive:
        exported = archive.read("repository/documents/export-runbook.md")
        manifest = json.loads(archive.read("tekdocs-export.json"))
        readme = archive.read("README.md")
    parsed = parse_content(exported)
    assert parsed.content_id == content_id
    assert "key_bindings" not in parsed.frontmatter
    assert parsed.entity_links == ()
    assert str(credential_entity.id).encode() not in exported
    assert b"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in exported
    assert manifest["repository"]["accepted_commit"] == committed.object_id
    assert manifest["repository"]["snapshot_only"] is True
    assert manifest["repository"]["files"][0]["sha256"] == hashlib.sha256(exported).hexdigest()
    assert b"not a complete backup" in readme
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=committed.object_id,
        changes={
            "documents/export-runbook.md": None,
            f"documents/{credential_entity.id}.md": source,
        },
        message="Move runbook to credential-named path",
    )
    index_repository_content(repository_id=repository.id)
    with pytest.raises(ValidationError, match="path contains credential-reference"):
        create_git_export(
            workspace=workspace,
            actor=installation.owner,
            document_entity_ids=[],
            publication_entity_ids=[],
            include_repository=True,
        )


@pytest.mark.django_db(transaction=True)
@override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
def test_git_export_repository_fails_closed_for_lagging_and_other_workspace(installation, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.TEKDOCS_REPOSITORY_ROOT = str(tmp_path / "repositories")
    first_org = organization(installation, "First export client")
    second_org = organization(installation, "Second export client")
    first_workspace = resolve_organization_workspace(installation.owner, entity_id=first_org.entity_id)
    second_workspace = resolve_organization_workspace(installation.owner, entity_id=second_org.entity_id)
    repository = repository_storage.ensure_workspace_repository(
        Workspace.objects.get(pk=first_workspace.data_scope.workspace_id)
    ).repository
    repository.refresh_from_db()
    content_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
        changes={
            "documents/private.md": (
                f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: document\n"
                "title: Private\n---\nPrivate content.\n"
            ).encode()
        },
        message="Add private content",
    )
    with pytest.raises(ValidationError, match="not fully indexed"):
        create_git_export(
            workspace=first_workspace,
            actor=installation.owner,
            document_entity_ids=[],
            publication_entity_ids=[],
            include_repository=True,
        )
    index_repository_content(repository_id=repository.id)
    second_repository = repository_storage.ensure_workspace_repository(
        Workspace.objects.get(pk=second_workspace.data_scope.workspace_id)
    ).repository
    second_repository.refresh_from_db()
    public_content_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=second_repository.id,
        expected_base=second_repository.accepted_commit.object_id if second_repository.accepted_commit_id else None,
        changes={
            "documents/other.md": (
                f"---\nschema: tekdocs.content/v1\nid: {public_content_id}\nkind: document\n"
                "title: Other\n---\nOther client content.\n"
            ).encode()
        },
        message="Add other client content",
    )
    index_repository_content(repository_id=second_repository.id)
    other = create_git_export(
        workspace=second_workspace,
        actor=installation.owner,
        document_entity_ids=[],
        publication_entity_ids=[],
        include_repository=True,
    )
    with other.artifact.open("rb") as stored, zipfile.ZipFile(io.BytesIO(stored.read())) as archive:
        assert "repository/documents/private.md" not in archive.namelist()
        assert b"Private content" not in b"".join(archive.read(path) for path in archive.namelist())
    assert GitExportBundle.objects.count() == 1
