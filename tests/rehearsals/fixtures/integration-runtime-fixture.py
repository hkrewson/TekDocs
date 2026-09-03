import os
import uuid
from contextlib import ExitStack

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.documents import create_document
from apps.core.git_exports import create_git_export
from apps.core.integration_providers import NetBoxProvider, ProviderObservation, ProviderPage
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import enqueue_sync, process_sync_job
from apps.core.models import (
    GitExportBundle,
    InstallationState,
    IntegrationConnection,
    IntegrationJobState,
    IntegrationObservation,
    OrganizationKind,
    Organization,
    Tenant,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core import rls as rls_runtime
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace


mode = os.environ["TEKDOCS_FIXTURE_MODE"]
provider_token = os.environ["TEKDOCS_FIXTURE_PROVIDER_TOKEN"]


def fixture_scope(scope, *, organization_mode):
    scope_factory = getattr(rls_runtime, "system_rls_scope", rls_scope)
    return scope_factory(scope, organization_mode=organization_mode)


class FixtureAdapter:
    key = "netbox"
    label = NetBoxProvider.label
    # The 0.6.9 provider protocol predates explicit provider contracts. Keep
    # this fixture runnable on both sides of the supported upgrade boundary.
    contract = getattr(NetBoxProvider, "contract", None)

    def fetch_page(self, connection, *, secret, cursor):
        assert secret == provider_token
        assert cursor == ""
        return ProviderPage((ProviderObservation("ipam.vlan", "619", "6" * 64),), "")


if mode == "create":
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installed = bootstrap_owner(
        tenant_name="Integration Rehearsal MSP",
        owner_email="integration-rehearsal@example.invalid",
        owner_display_name="Integration Rehearsal Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    scope_stack = ExitStack()
    scope_stack.enter_context(
        fixture_scope(DataScope.tenant(installed.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
    )
    organization = create_organization(
        tenant=installed.tenant,
        actor_id=installed.owner.id,
        name="Integration Rehearsal Client",
        legal_name="Integration Rehearsal Client, Inc.",
        website="https://example.invalid",
        classifications=[OrganizationKind.CLIENT],
    )
    scope_stack.close()
    organization_workspace = workspace_for_owner(tenant=installed.tenant, organization=organization)
    scope_stack = ExitStack()
    scope_stack.enter_context(
        fixture_scope(
            DataScope(installed.tenant.id, organization_workspace.id, organization.id),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
    )
    connection_id = uuid.uuid4()
    provider = IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installed.tenant,
        workspace=organization_workspace,
        organization=organization,
        provider="netbox",
        name="Rehearsal NetBox",
        base_url="https://netbox.example.invalid/api/",
        configuration={},
        secret_envelope=encrypt_integration_secret(
            secret=provider_token.encode(),
            tenant_id=installed.tenant.id,
            connection_id=connection_id,
            generation=1,
        ),
        created_by=installed.owner,
    )
    job = enqueue_sync(connection=provider, trigger="manual", idempotency_key="rehearsal:provider-page:0001")
    process_sync_job(job_id=job.id, adapter=FixtureAdapter())
    document = create_document(
        tenant=installed.tenant,
        organization=organization,
        actor_id=installed.owner.id,
        title="Integration export rehearsal",
        markdown="# Integration export rehearsal\n\nRetained without provider credentials.\n",
    )
    create_git_export(
        workspace=resolve_organization_workspace(installed.owner, entity_id=organization.entity_id),
        actor=installed.owner,
        document_entity_ids=[document.entity_id],
        publication_entity_ids=[],
    )
    scope_stack.close()
elif mode == "verify":
    tenant = Tenant.objects.get(slug="integration-rehearsal-msp")
    scope_stack = ExitStack()
    scope_stack.enter_context(
        fixture_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
    )
    owner = User.objects.get(email="integration-rehearsal@example.invalid")
    organization = Organization.objects.get(
        tenant=tenant,
        entity__display_name="Integration Rehearsal Client",
    )
    scope_stack.close()
    organization_workspace = workspace_for_owner(tenant=tenant, organization=organization)
    scope_stack = ExitStack()
    scope_stack.enter_context(
        fixture_scope(
            DataScope(tenant.id, organization_workspace.id, organization.id),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
    )
    provider = IntegrationConnection.objects.get(tenant=tenant, organization=organization)
    assert decrypt_integration_secret(
        envelope_payload=provider.secret_envelope,
        tenant_id=tenant.id,
        connection_id=provider.id,
        generation=provider.secret_generation,
    ) == provider_token.encode()
    assert provider.sync_jobs.get().state == IntegrationJobState.SUCCEEDED
    assert IntegrationObservation.objects.filter(job=provider.sync_jobs.get(), remote_id="619").count() == 1
    export = GitExportBundle.objects.get(tenant=tenant, organization=organization)
    assert export.artifact.size == export.byte_size
    assert len(export.content_digest) == 64
    assert owner.tenant_memberships.filter(tenant=tenant).exists()
    scope_stack.close()
else:
    raise AssertionError(f"Unsupported fixture mode: {mode}")
