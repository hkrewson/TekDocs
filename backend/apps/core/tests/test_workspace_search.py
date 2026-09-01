import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.documents import create_document
from apps.core.models import Entity, InstallationState, Organization, OrganizationClassification, Tenant
from apps.core.network_addressing import create_subnet
from apps.core.organizations import create_organization
from apps.core.people import create_person
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Search MSP",
        owner_email="search-owner@example.com",
        owner_display_name="Search Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(installation, name: str) -> Organization:  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name} LLC",
        website="https://example.invalid",
        classifications=["client"],
    )


def organization_search_url(record: Organization) -> str:
    return reverse("organization-workspace-search", kwargs={"organization_entity_id": record.entity_id})


@pytest.mark.django_db
def test_unified_search_ranks_title_identifier_and_document_content(owner_client, installation):
    client_org = organization(installation, "Acme Search Client")
    create_document(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        title="Firewall recovery guide",
        markdown="# Recovery\n\nRotate the cobalt recovery key before maintenance.",
    )
    create_document(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        title="Cobalt",
        markdown="Exact-title result.",
    )
    person = create_person(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        full_name="Morgan Rivera",
        preferred_name="Morgan",
        kind="contact",
        role="Infrastructure lead",
        responsibility="Cobalt recovery owner",
        location="",
        office="",
        site=None,
        structured_location=None,
        phone="+1 515 555 0100",
        email="morgan@example.com",
    )

    response = owner_client.get(organization_search_url(client_org), {"q": "cobalt", "page_size": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert payload["has_more"] is True
    assert payload["results"][0]["title"] == "Cobalt"
    assert payload["results"][0]["score"] > payload["results"][1]["score"]
    assert {facet["value"] for facet in payload["facets"]} == {"document", "person"}

    documents = owner_client.get(organization_search_url(client_org), {"q": "cobalt", "result_type": "document"}).json()
    assert documents["count"] == 2
    body_hit = next(item for item in documents["results"] if item["title"] == "Firewall recovery guide")
    assert "Rotate the cobalt recovery key" in body_hit["excerpt"]
    assert body_hit["review_state"] == "unreviewed"
    assert body_hit["target"].endswith(f"/documentation?document={body_hit['id']}")
    assert str(person.person.entity_id) not in {item["id"] for item in documents["results"]}


@pytest.mark.django_db
def test_unified_search_finds_safe_operational_identifiers(owner_client, installation):
    client_org = organization(installation, "Identifier Client")
    create_site(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        name="North office",
        code="DSM-044",
        address_line_1="100 Main Street",
        address_line_2="",
        city="Des Moines",
        region="Iowa",
        postal_code="50309",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    subnet = create_subnet(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        name="Operations network",
        cidr="10.44.0.0/24",
        vrf_entity_id=None,
        vlan_entity_id=None,
        description="",
    )

    site_result = owner_client.get(organization_search_url(client_org), {"q": "DSM-044"}).json()["results"]
    network_result = owner_client.get(organization_search_url(client_org), {"q": "10.44.0.0/24"}).json()["results"]

    assert site_result[0]["result_type"] == "site"
    assert site_result[0]["excerpt"] == "Site code: DSM-044"
    assert network_result[0]["id"] == str(subnet.entity_id)
    assert network_result[0]["excerpt"] == "CIDR: 10.44.0.0/24"


@pytest.mark.django_db
def test_unified_search_fails_closed_across_workspace_archive_and_tenant_boundaries(owner_client, installation):
    selected = organization(installation, "Selected Client")
    sibling = organization(installation, "Sibling Client")
    create_document(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        title="Visible boundary phrase",
        markdown="boundary-token",
    )
    create_document(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        title="Sibling boundary phrase",
        markdown="boundary-token",
    )
    archived = create_document(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        title="Archived boundary phrase",
        markdown="boundary-token",
    )
    archived.entity.archived_at = archived.updated_at
    archived.entity.save(update_fields=("archived_at", "updated_at"))
    archived.archived_at = archived.updated_at
    archived.save(update_fields=("archived_at", "updated_at"))
    foreign_tenant = Tenant.objects.create(name="Foreign Search MSP", slug="foreign-search-msp")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant, entity_type="organization", display_name="Foreign boundary phrase"
    )
    foreign_org = Organization.objects.create(tenant=foreign_tenant, entity=foreign_entity)
    OrganizationClassification.objects.create(tenant=foreign_tenant, organization=foreign_org, kind="client")
    client_user = User.objects.create_user(email="client-search@example.com", display_name="Client Search User")
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=client_user,
        role=BuiltInRole.CLIENT_USER,
        organization=selected,
    )
    client_portal = Client()
    client_portal.force_login(client_user)

    organization_results = owner_client.get(organization_search_url(selected), {"q": "boundary phrase"}).json()[
        "results"
    ]
    msp_results = owner_client.get(reverse("msp-workspace-search"), {"q": "boundary phrase"}).json()["results"]
    client_response = client_portal.get(organization_search_url(selected), {"q": "boundary phrase"})

    assert [item["title"] for item in organization_results] == ["Visible boundary phrase"]
    assert msp_results == []
    assert client_response.status_code == 403
    assert b"boundary phrase" not in client_response.content


@pytest.mark.django_db
def test_unified_search_rejects_unbounded_queries_and_requires_workspace_access(owner_client, client, installation):
    client_org = organization(installation, "Bounded Search Client")
    url = organization_search_url(client_org)

    assert owner_client.get(url, {"q": "x"}).status_code == 400
    assert owner_client.get(url, {"q": "valid", "page_size": 26}).status_code == 400
    assert owner_client.get(url, {"q": "valid", "result_type": "secret"}).status_code == 400
    assert client.get(url, {"q": "valid"}).status_code == 403


@pytest.mark.django_db
def test_unified_search_handles_unicode_and_keeps_pagination_stable(owner_client, installation):
    client_org = organization(installation, "Unicode Search Client")
    for title in ("Résumé alpha", "Résumé beta", "Résumé gamma"):
        create_document(
            tenant=installation.tenant,
            organization=client_org,
            actor_id=installation.owner.id,
            title=title,
            markdown="Unicode documentation result.",
        )
    url = organization_search_url(client_org)

    first = owner_client.get(url, {"q": "RÉSUMÉ", "page_size": 2}).json()
    repeated = owner_client.get(url, {"q": "RÉSUMÉ", "page_size": 2}).json()
    second = owner_client.get(url, {"q": "RÉSUMÉ", "page": 2, "page_size": 2}).json()

    assert [item["id"] for item in first["results"]] == [item["id"] for item in repeated["results"]]
    assert first["count"] == 3
    assert first["has_more"] is True
    assert {item["id"] for item in first["results"]}.isdisjoint({item["id"] for item in second["results"]})


@pytest.mark.django_db
def test_unified_search_returns_bounded_unavailable_response_on_database_failure(
    owner_client, installation, monkeypatch
):
    client_org = organization(installation, "Search Failure Client")

    def fail_search(**_kwargs):  # type: ignore[no-untyped-def]
        raise DatabaseError("internal database detail must not be returned")

    monkeypatch.setattr("apps.core.search_views.search_workspace", fail_search)
    response = owner_client.get(organization_search_url(client_org), {"q": "firewall"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "search_unavailable"
    assert "execution budget" in str(response.json()["error"]["detail"])
    assert b"internal database detail" not in response.content


@pytest.mark.django_db
def test_unified_search_does_not_search_credential_provider_pointers(owner_client, installation):
    client_org = organization(installation, "Credential Search Client")
    private_link = (
        "https://start.1password.com/open/i?"
        "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
        "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
    )
    created = owner_client.post(
        reverse(
            "organization-credential-reference-list-create",
            kwargs={"organization_entity_id": client_org.entity_id},
        ),
        {"title": "Firewall administrator", "provider": "onepassword", "reference_url": private_link},
        content_type="application/json",
    )
    assert created.status_code == 201

    response = owner_client.get(organization_search_url(client_org), {"q": "aaaaaaaaaaaaaaaaaaaaaaaaaa"})

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert private_link.encode() not in response.content
