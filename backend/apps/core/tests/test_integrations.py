import io
import json
import secrets
import uuid
import zipfile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.policy import PermissionKey
from apps.core import integration_views
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
    GitExportBundle,
    InstallationState,
    IntegrationConflict,
    IntegrationConnection,
    IntegrationJobState,
    IntegrationLogEvent,
    IntegrationObservation,
    IntegrationSyncJob,
    NetBoxReference,
    NetworkRack,
    NetworkVLAN,
    OrganizationKind,
    workspace_for_owner,
)
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
    assert request["relative_path"] == "dcim/racks/"
    assert page.next_cursor == "1|dcim/devices/"


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
            observations=(ProviderObservation("ipam.vlan", "42", "a" * 64),),
            next_cursor="",
            complete_types=("ipam.vlan",),
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
    assert contract["direction"] == "read_only"
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
            item = ProviderObservation("ipam.vlan", "42", "a" * 64, {"id": 42, "name": "Users"})
            return ProviderPage((item, item), "")

    completed = process_sync_job(job_id=job.id, adapter=DuplicateAdapter())
    observation = IntegrationObservation.objects.get(job=completed)
    assert completed.state == IntegrationJobState.SUCCEEDED
    assert observation.safe_projection == {"id": 42, "name": "Users"}
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
        "ipam.vlan",
        "42",
        "a" * 64,
    )
    assert IntegrationConflict.objects.get().difference == "unmatched"
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
def test_unmatched_netbox_rack_can_create_and_link_a_starting_record(installation):
    record = organization(installation, "Blank NetBox client")
    source = connection(installation, record)
    site = create_site(
        tenant=installation.tenant,
        organization=record,
        actor_id=installation.owner.id,
        name="Main office",
        code="MAIN",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )

    class RackAdapter:
        key = "netbox"
        label = NetBoxProvider.label
        contract = PROVIDERS["netbox"].contract

        def fetch_page(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return ProviderPage(
                observations=(ProviderObservation("dcim.rack", "17", "b" * 64, {"id": 17, "name": "Core rack"}),),
                next_cursor="",
                complete_types=("dcim.rack",),
            )

    completed = process_sync_job(
        job_id=enqueue_sync(connection=source, trigger="manual", idempotency_key="rack:starting-record").id,
        adapter=RackAdapter(),
    )
    conflict = IntegrationConflict.objects.get(observation__job=completed)
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.post(
        reverse(
            "organization-integration-netbox-adopt",
            kwargs={"organization_entity_id": record.entity_id, "conflict_id": conflict.id},
        ),
        data=json.dumps(
            {
                "rack": {
                    "name": "Core rack",
                    "site_id": str(site.entity_id),
                    "location_id": None,
                    "unit_count": 42,
                    "status": "active",
                }
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accept_remote"
    rack = NetworkRack.objects.get(entity__display_name="Core rack")
    reference = NetBoxReference.objects.get(entity=rack.entity)
    assert (reference.object_type, reference.object_id, reference.observed_fingerprint) == (
        "dcim.rack",
        17,
        "b" * 64,
    )
    assert reference.last_observed_at is not None
    observations = browser.get(
        reverse(
            "organization-integration-observation-list",
            kwargs={"organization_entity_id": record.entity_id},
        )
    ).json()["results"]
    assert observations[0]["linked_local_entity_id"] == str(rack.entity_id)
    assert observations[0]["linked_local_entity_name"] == "Core rack"
    assert observations[0]["accepted"] is True


@pytest.mark.django_db
def test_unmatched_netbox_device_can_create_and_link_a_hardware_asset(installation, monkeypatch):
    record = organization(installation, "Blank device client")
    source = connection(installation, record)
    seed = create_network_hardware_asset(installation=installation, organization=record, name="Seed hardware")

    class DeviceAdapter:
        key = "netbox"
        label = NetBoxProvider.label
        contract = PROVIDERS["netbox"].contract

        def fetch_page(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return ProviderPage(
                observations=(ProviderObservation("dcim.device", "23", "d" * 64, {"id": 23, "name": "arrakis"}),),
                next_cursor="",
                complete_types=("dcim.device",),
            )

    completed = process_sync_job(
        job_id=enqueue_sync(connection=source, trigger="manual", idempotency_key="device:starting-record").id,
        adapter=DeviceAdapter(),
    )
    conflict = IntegrationConflict.objects.get(observation__job=completed)
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse(
        "organization-integration-netbox-adopt",
        kwargs={"organization_entity_id": record.entity_id, "conflict_id": conflict.id},
    )
    body = json.dumps({"asset": {"name": "arrakis", "model_id": str(seed.model.entity_id)}})
    original_require_permission = integration_views.require_permission

    def deny_asset_edit(user, permission, **kwargs):  # type: ignore[no-untyped-def]
        if permission == PermissionKey.ASSETS_EDIT:
            raise PermissionDenied("Asset editing denied.")
        return original_require_permission(user, permission, **kwargs)

    monkeypatch.setattr(integration_views, "require_permission", deny_asset_edit)
    denied = browser.post(url, data=body, content_type="application/json")
    assert denied.status_code == 403
    assert not ClientAsset.objects.filter(entity__display_name="arrakis").exists()

    monkeypatch.setattr(integration_views, "require_permission", original_require_permission)
    response = browser.post(url, data=body, content_type="application/json")

    assert response.status_code == 200
    assert response.json()["status"] == "accept_remote"
    asset = ClientAsset.objects.get(entity__display_name="arrakis")
    assert asset.hardware.lifecycle_state == "in_stock"
    reference = NetBoxReference.objects.get(entity=asset.entity)
    assert (reference.object_type, reference.object_id, reference.observed_fingerprint) == (
        "dcim.device",
        23,
        "d" * 64,
    )


@pytest.mark.django_db
def test_unmatched_netbox_vlan_can_create_and_link_a_vlan(installation):
    record = organization(installation, "Blank VLAN client")
    source = connection(installation, record)

    class VLANAdapter:
        key = "netbox"
        label = NetBoxProvider.label
        contract = PROVIDERS["netbox"].contract

        def fetch_page(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return ProviderPage(
                observations=(ProviderObservation("ipam.vlan", "31", "e" * 64, {"id": 31, "name": "Users"}),),
                next_cursor="",
                complete_types=("ipam.vlan",),
            )

    completed = process_sync_job(
        job_id=enqueue_sync(connection=source, trigger="manual", idempotency_key="vlan:starting-record").id,
        adapter=VLANAdapter(),
    )
    conflict = IntegrationConflict.objects.get(observation__job=completed)
    browser = Client()
    browser.force_login(installation.owner)
    response = browser.post(
        reverse(
            "organization-integration-netbox-adopt",
            kwargs={"organization_entity_id": record.entity_id, "conflict_id": conflict.id},
        ),
        data=json.dumps({"vlan": {"name": "Users", "vlan_id": 120, "description": "User access network"}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accept_remote"
    vlan = NetworkVLAN.objects.get(entity__display_name="Users")
    assert (vlan.vlan_id, vlan.description) == (120, "User access network")
    reference = NetBoxReference.objects.get(entity=vlan.entity)
    assert (reference.object_type, reference.object_id, reference.observed_fingerprint) == (
        "ipam.vlan",
        31,
        "e" * 64,
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
