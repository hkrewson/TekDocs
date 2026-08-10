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
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
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
            "organizations",
            "people",
            "sites",
            "custom_fields",
            "documentation",
            "files",
            "assets",
            "licenses",
            "networks",
            "domains",
            "certificates",
            "credentials",
            "services",
            "tickets",
            "vendors",
            "products",
            "compliance",
            "activity",
            "recycle_bin",
            "integrations",
            "accounting",
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
        "people",
        "sites",
        "custom_fields",
        "documentation",
        "files",
        "assets",
        "licenses",
        "networks",
        "domains",
        "certificates",
        "credentials",
        "services",
        "tickets",
        "vendors",
        "recycle_bin",
        "products",
    ]
    assert selected.json()["organization"]["legal_name"] == "Acme Workspace, LLC"
    resolved = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
    assert resolved.data_scope == DataScope.organization(installation.tenant, organization)


@pytest.mark.django_db
def test_workspace_context_denies_anonymous_and_allows_read_only_member_without_mfa(
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
    assert client.get(organization_url).status_code == 200

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(organization_url).status_code == 200


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


@pytest.mark.django_db
def test_workspace_search_is_ordered_searchable_and_page_bounded(owner_client, installation):
    for index in range(18):
        create_organization(
            installation.tenant,
            name=f"Client {index:02d}",
            classifications=("client", "vendor") if index == 7 else ("client",),
        )
    supplier = create_organization(
        installation.tenant,
        name="Supplier Alias",
        classifications=("manufacturer",),
    )
    supplier.legal_name = "Northwind Equipment"
    supplier.save(update_fields=("legal_name", "updated_at"))

    first = owner_client.get(reverse("workspace-organization-search"), {"page_size": 5})
    second = owner_client.get(reverse("workspace-organization-search"), {"page": 2, "page_size": 5})
    searched = owner_client.get(reverse("workspace-organization-search"), {"q": "northwind"})

    assert first.status_code == 200
    assert [result["name"] for result in first.json()["results"]] == [f"Client {index:02d}" for index in range(5)]
    assert {key: value for key, value in first.json().items() if key != "results"} == {
        "page": 1,
        "page_size": 5,
        "has_more": True,
    }
    assert [result["name"] for result in second.json()["results"]] == [f"Client {index:02d}" for index in range(5, 10)]
    assert searched.json()["results"] == [
        {
            "id": str(Entity.objects.get(display_name="Supplier Alias").id),
            "name": "Supplier Alias",
            "classifications": ["manufacturer"],
            "capabilities": [
                "overview",
                "people",
                "sites",
                "custom_fields",
                "documentation",
                "files",
                "products",
                "recycle_bin",
            ],
        }
    ]


@pytest.mark.django_db
def test_workspace_search_can_limit_results_to_client_context(owner_client, installation):
    client_only = create_organization(installation.tenant, name="Alpha Client", classifications=("client",))
    both = create_organization(installation.tenant, name="Beta Client Vendor", classifications=("client", "vendor"))
    create_organization(installation.tenant, name="Supplier Only", classifications=("vendor",))

    response = owner_client.get(reverse("workspace-organization-search"), {"classification": "client"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [str(client_only.entity_id), str(both.entity_id)]
    assert all("client" in item["classifications"] for item in response.json()["results"])
    assert (
        owner_client.get(
            reverse("workspace-organization-search"),
            {"classification": "unsupported"},
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_workspace_search_excludes_archived_and_foreign_records_and_validates_bounds(owner_client, installation):
    visible = create_organization(installation.tenant, name="Visible Client", classifications=("client",))
    archived = create_organization(installation.tenant, name="Archived Client", classifications=("client",))
    archived.entity.archived_at = archived.entity.updated_at
    archived.entity.save(update_fields=("archived_at", "updated_at"))
    foreign_tenant = Tenant.objects.create(name="Foreign Search", slug="foreign-search")
    create_organization(foreign_tenant, name="Foreign Client", classifications=("client",))

    response = owner_client.get(reverse("workspace-organization-search"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [str(visible.entity_id)]
    assert owner_client.get(reverse("workspace-organization-search"), {"page_size": 26}).status_code == 400
    assert owner_client.get(reverse("workspace-organization-search"), {"page": 101}).status_code == 400
    assert owner_client.get(reverse("workspace-organization-search"), {"q": "x" * 81}).status_code == 400


@pytest.mark.django_db
def test_workspace_search_denies_anonymous_and_allows_read_only_member_without_mfa(client, owner_client, installation):
    url = reverse("workspace-organization-search")
    assert client.get(url).status_code == 403

    member = User.objects.create_user(email="workspace-search-member@example.com", display_name="Search Member")
    TenantMembership.objects.create(tenant=installation.tenant, user=member)
    client.force_login(member)
    assert client.get(url).status_code == 200

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(url).status_code == 200
