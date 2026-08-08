import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import TenantMembership, User
from apps.core.models import Entity, InstallationState, Organization, OrganizationClassification, Tenant
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Workspace MSP",
        owner_email="workspace-owner@example.com",
        owner_display_name="Workspace Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def create_organization(tenant: Tenant, *, name: str, classifications: tuple[str, ...]) -> Organization:
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    organization = Organization.objects.create(
        tenant=tenant,
        entity=entity,
        legal_name=f"{name}, LLC",
        website="https://workspace.example.com",
    )
    OrganizationClassification.objects.bulk_create(
        [OrganizationClassification(tenant=tenant, organization=organization, kind=kind) for kind in classifications]
    )
    return organization


@pytest.mark.django_db
def test_msp_and_organization_workspace_contexts_are_explicit_and_stable(owner_client, installation):
    organization = create_organization(
        installation.tenant,
        name="Acme Workspace",
        classifications=("client", "vendor"),
    )

    msp = owner_client.get(reverse("workspace-msp"))
    selected = owner_client.get(reverse("workspace-organization", kwargs={"entity_id": organization.entity_id}))

    assert msp.status_code == 200
    assert msp.json() == {
        "kind": "msp",
        "id": str(installation.tenant.id),
        "name": "Workspace MSP",
        "classifications": [],
        "capabilities": [
            "overview",
            "documentation",
            "organizations",
            "people",
            "assets",
            "networks",
            "credentials",
            "compliance",
            "activity",
        ],
        "organization": None,
    }
    assert selected.status_code == 200
    assert selected.json()["kind"] == "organization"
    assert selected.json()["id"] == str(organization.entity_id)
    assert selected.json()["name"] == "Acme Workspace"
    assert selected.json()["classifications"] == ["client", "vendor"]
    assert selected.json()["capabilities"] == [
        "overview",
        "documentation",
        "people",
        "assets",
        "networks",
        "credentials",
        "products",
    ]
    assert selected.json()["organization"]["legal_name"] == "Acme Workspace, LLC"
    resolved = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
    assert resolved.data_scope == DataScope.organization(installation.tenant, organization)


@pytest.mark.django_db
def test_workspace_context_denies_anonymous_member_without_owner_policy_and_owner_without_mfa(
    client,
    owner_client,
    installation,
):
    organization = create_organization(installation.tenant, name="Protected", classifications=("client",))
    organization_url = reverse("workspace-organization", kwargs={"entity_id": organization.entity_id})

    assert client.get(reverse("workspace-msp")).status_code == 403
    assert client.get(organization_url).status_code == 403

    member = User.objects.create_user(email="member@example.com", display_name="Member")
    TenantMembership.objects.create(tenant=installation.tenant, user=member)
    client.force_login(member)
    assert client.get(reverse("workspace-msp")).status_code == 200
    assert client.get(organization_url).status_code == 403

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(organization_url).status_code == 403


@pytest.mark.django_db
def test_workspace_context_hides_archived_cross_tenant_missing_and_malformed_organizations(owner_client, installation):
    archived = create_organization(installation.tenant, name="Archived", classifications=("client",))
    archived.entity.archived_at = archived.entity.updated_at
    archived.entity.save(update_fields=("archived_at", "updated_at"))
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-workspace")
    foreign = create_organization(foreign_tenant, name="Foreign", classifications=("vendor",))

    for entity_id in (archived.entity_id, foreign.entity_id, uuid.uuid4()):
        response = owner_client.get(reverse("workspace-organization", kwargs={"entity_id": entity_id}))
        assert response.status_code == 404
        assert "Foreign" not in str(response.content)

    malformed = owner_client.get("/api/v1/workspaces/organizations/not-a-uuid")
    assert malformed.status_code == 404
