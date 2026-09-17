import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import AuditEvent, Entity, InstallationState, Organization, OrganizationClassification, Tenant


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="owner@example.com",
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


def organization_payload(**overrides):
    return {
        "name": "Acme Dental",
        "legal_name": "Acme Dental Associates, LLC",
        "website": "https://acme.example.com",
        "classifications": ["client", "partner"],
        **overrides,
    }


@pytest.mark.django_db
def test_owner_can_create_list_read_update_and_archive_organization(owner_client, installation):
    created = owner_client.post(
        reverse("organization-list-create"),
        organization_payload(),
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Acme Dental"
    assert created.json()["classifications"] == ["client", "partner"]
    entity_id = created.json()["id"]
    organization = Organization.objects.select_related("entity").get(entity_id=entity_id)
    assert organization.tenant_id == installation.tenant.id
    assert organization.entity.entity_type == "organization"
    assert organization.entity.organization_id is None
    assert organization.access_mode == "assigned_only"
    assert set(
        OrganizationClassification.scoped.for_tenant(installation.tenant)
        .filter(organization=organization)
        .values_list("kind", flat=True)
    ) == {"client", "partner"}

    listed = owner_client.get(reverse("organization-list-create"))
    detail = owner_client.get(reverse("organization-detail", kwargs={"entity_id": entity_id}))
    assert listed.status_code == 200
    assert listed.json()["results"] == [created.json()]
    assert listed.json()["page"] == 1
    assert listed.json()["page_size"] == 25
    assert listed.json()["count"] == 1
    assert listed.json()["has_more"] is False
    assert detail.json() == created.json()
    assert owner_client.get(reverse("organization-list-create"), {"typo": "ignored"}).status_code == 400

    updated = owner_client.patch(
        reverse("organization-detail", kwargs={"entity_id": entity_id}),
        organization_payload(
            name="Acme Health",
            legal_name="",
            website="",
            classifications=["client", "vendor", "manufacturer"],
        ),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Acme Health"
    assert updated.json()["classifications"] == ["client", "manufacturer", "vendor"]

    partially_updated = owner_client.patch(
        reverse("organization-detail", kwargs={"entity_id": entity_id}),
        {"website": "https://health.example.com"},
        content_type="application/json",
    )
    assert partially_updated.status_code == 200
    assert partially_updated.json()["name"] == "Acme Health"
    assert partially_updated.json()["classifications"] == ["client", "manufacturer", "vendor"]
    assert partially_updated.json()["website"] == "https://health.example.com"

    archived = owner_client.delete(reverse("organization-detail", kwargs={"entity_id": entity_id}))
    assert archived.status_code == 204
    organization.entity.refresh_from_db()
    assert organization.entity.archived_at is not None
    assert owner_client.get(reverse("organization-list-create")).json()["results"] == []
    assert owner_client.get(reverse("organization-detail", kwargs={"entity_id": entity_id})).status_code == 404
    assert list(
        AuditEvent.objects.filter(entity_id=entity_id).values_list("action", flat=True).order_by("occurred_at")
    ) == ["organization.created", "organization.updated", "organization.updated", "organization.archived"]
    assert not AuditEvent.objects.filter(entity_id=entity_id).exclude(metadata={}).exists()


@pytest.mark.django_db
def test_organization_collection_is_searchable_sorted_and_bounded(owner_client):
    url = reverse("organization-list-create")
    for index in range(27):
        response = owner_client.post(
            url,
            organization_payload(
                name=f"Organization {index:02d}",
                legal_name=f"Legal Entity {index:02d}",
                classifications=["vendor"] if index % 2 else ["client"],
            ),
            content_type="application/json",
        )
        assert response.status_code == 201

    first_page = owner_client.get(url, {"page_size": 10, "ordering": "-name"})
    filtered = owner_client.get(url, {"q": "Legal Entity 04", "classification": "client"})

    assert first_page.status_code == 200
    assert first_page.json()["count"] == 27
    assert first_page.json()["has_more"] is True
    assert [organization["name"] for organization in first_page.json()["results"]] == [
        f"Organization {index:02d}" for index in range(26, 16, -1)
    ]
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    assert filtered.json()["results"][0]["name"] == "Organization 04"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (organization_payload(name="\u0000Bad"), "name"),
        (organization_payload(website="javascript:alert(1)"), "website"),
        (organization_payload(website="ftp://acme.example.com"), "website"),
        (organization_payload(website="https://user:password@acme.example.com"), "website"),
        (organization_payload(classifications=[]), "classifications"),
        (organization_payload(classifications=["client", "client"]), "classifications"),
        (organization_payload(classifications=["unknown"]), "classifications"),
    ],
)
def test_organization_write_contract_rejects_invalid_input(owner_client, payload, field):
    response = owner_client.post(reverse("organization-list-create"), payload, content_type="application/json")

    assert response.status_code == 400
    assert field in str(response.json()["error"]["detail"])
    assert Organization.objects.count() == 0
    assert Entity.objects.filter(entity_type="organization").count() == 0


@pytest.mark.django_db
def test_organization_endpoints_deny_anonymous_non_owner_missing_mfa_and_foreign_records(
    client,
    owner_client,
    installation,
):
    assert client.get(reverse("organization-list-create")).status_code == 403

    member = User.objects.create_user(email="member@example.com", display_name="Member")
    client.force_login(member)
    assert (
        client.post(
            reverse("organization-list-create"),
            organization_payload(),
            content_type="application/json",
        ).status_code
        == 403
    )

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(reverse("organization-list-create")).status_code == 200
    assert (
        owner_client.post(
            reverse("organization-list-create"),
            organization_payload(name="MFA Required"),
            content_type="application/json",
        ).status_code
        == 403
    )
    TOTP.activate(installation.owner, generate_totp_secret())

    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        entity_type="organization",
        display_name="Foreign Client",
    )
    foreign = Organization.objects.create(tenant=foreign_tenant, entity=foreign_entity)
    assert owner_client.get(reverse("organization-detail", kwargs={"entity_id": foreign.entity_id})).status_code == 404
    assert (
        owner_client.patch(
            reverse("organization-detail", kwargs={"entity_id": foreign.entity_id}),
            organization_payload(name="Hijacked"),
            content_type="application/json",
        ).status_code
        == 404
    )
    foreign_delete = owner_client.delete(reverse("organization-detail", kwargs={"entity_id": foreign.entity_id}))
    assert foreign_delete.status_code == 404
    foreign.entity.refresh_from_db()
    assert foreign.entity.display_name == "Foreign Client"


@pytest.mark.django_db
def test_organization_mutations_require_csrf(installation):
    client = Client(enforce_csrf_checks=True)
    client.force_login(installation.owner)

    response = client.post(
        reverse("organization-list-create"),
        organization_payload(),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert Organization.objects.count() == 0
