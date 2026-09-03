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

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.documents import create_document
from apps.core.git_exports import _manifest_has_credential_reference, create_git_export
from apps.core.integration_providers import (
    PROVIDERS,
    NetBoxProvider,
    ProviderObservation,
    ProviderPage,
    provider_catalog,
    validate_provider_adapter,
)
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import enqueue_sync, process_sync_job
from apps.core.models import (
    GitExportBundle,
    InstallationState,
    IntegrationConflict,
    IntegrationConnection,
    IntegrationJobState,
    IntegrationLogEvent,
    IntegrationObservation,
    IntegrationSyncJob,
    OrganizationKind,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core.tasks import dispatch_integration_syncs, process_integration_sync_job
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


def organization(installation, name):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=[OrganizationKind.CLIENT],
    )


def connection(installation, record, *, name="Primary NetBox", token=None):  # type: ignore[no-untyped-def]
    token = token or TEST_PROVIDER_TOKEN
    connection_id = uuid.uuid4()
    return IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=record),
        organization=record,
        provider="netbox",
        name=name,
        base_url="https://netbox.example.com/api/",
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
        {"key": "api_token", "label": "API token", "secret": True, "minimum_length": 8}
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
