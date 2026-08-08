import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import (
    AuditEvent,
    Entity,
    InstallationState,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    PersonAssociation,
    Site,
    Tenant,
)
from apps.core.scoping import DataScope


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="people-owner@example.com",
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


def organization(tenant: Tenant, name: str) -> Organization:
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def person_payload(**overrides):
    return {
        "full_name": "Jordan Avery",
        "preferred_name": "Jordy",
        "kind": "employee",
        "role": "Systems Administrator",
        "responsibility": "Network and identity operations",
        "location": "North Office",
        "office": "Desk 214",
        "phone": "+1 555 010 0240",
        "email": "jordan.avery@example.com",
        **overrides,
    }


@pytest.mark.django_db
def test_owner_can_create_list_read_update_and_archive_people_in_msp_and_client_scopes(owner_client, installation):
    client_organization = organization(installation.tenant, "Acme Dental")
    msp_created = owner_client.post(
        reverse("msp-people-list-create"),
        person_payload(),
        content_type="application/json",
    )
    client_created = owner_client.post(
        reverse(
            "organization-people-list-create",
            kwargs={"organization_entity_id": client_organization.entity_id},
        ),
        person_payload(
            full_name="Morgan Ellis",
            preferred_name="",
            kind="contact",
            role="Office Manager",
            email="morgan.ellis@example.com",
        ),
        content_type="application/json",
    )

    assert msp_created.status_code == 201
    assert client_created.status_code == 201
    assert msp_created.json()["organization_id"] is None
    assert client_created.json()["organization_id"] == str(client_organization.entity_id)
    msp_id = msp_created.json()["id"]
    client_id = client_created.json()["id"]

    msp_list = owner_client.get(reverse("msp-people-list-create")).json()
    client_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id},
    )
    client_list = owner_client.get(client_url).json()
    assert [record["id"] for record in msp_list["results"]] == [msp_id]
    assert [record["id"] for record in client_list["results"]] == [client_id]

    detail_url = reverse("msp-person-detail", kwargs={"person_entity_id": msp_id})
    assert owner_client.get(detail_url).json() == msp_created.json()
    updated = owner_client.patch(
        detail_url,
        {"preferred_name": "Jordan", "office": "Office 12"},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Jordan Avery"
    assert updated.json()["preferred_name"] == "Jordan"
    assert updated.json()["office"] == "Office 12"

    archived = owner_client.delete(detail_url)
    assert archived.status_code == 204
    assert owner_client.get(detail_url).status_code == 404
    assert owner_client.get(reverse("msp-people-list-create")).json()["results"] == []
    assert list(
        AuditEvent.objects.filter(entity_id=msp_id).values_list("action", flat=True).order_by("occurred_at")
    ) == ["person.created", "person.updated", "person.association_archived"]
    assert not AuditEvent.objects.filter(entity_id=msp_id).exclude(metadata={}).exists()


@pytest.mark.django_db
def test_people_search_filter_sort_and_pagination_are_bounded(owner_client):
    url = reverse("msp-people-list-create")
    for index, (name, role, location) in enumerate(
        [
            ("Taylor Brooks", "Technician", "East Office"),
            ("Alex Chen", "Account Manager", "West Office"),
            ("Morgan Diaz", "Technician", "West Office"),
        ]
    ):
        response = owner_client.post(
            url,
            person_payload(
                full_name=name,
                preferred_name=f"P{index}",
                role=role,
                location=location,
                email=f"p{index}@example.com",
            ),
            content_type="application/json",
        )
        assert response.status_code == 201

    searched = owner_client.get(url, {"q": "west"}).json()
    filtered = owner_client.get(
        url,
        {"filter_field": "role", "filter_value": "technician", "ordering": "-full_name"},
    ).json()
    paged = owner_client.get(url, {"ordering": "full_name", "page_size": 2}).json()

    assert [person["full_name"] for person in searched["results"]] == ["Alex Chen", "Morgan Diaz"]
    assert [person["full_name"] for person in filtered["results"]] == ["Taylor Brooks", "Morgan Diaz"]
    assert [person["full_name"] for person in paged["results"]] == ["Alex Chen", "Morgan Diaz"]
    assert paged == {**paged, "page": 1, "page_size": 2, "count": 3, "has_more": True}

    assert owner_client.get(url, {"ordering": "password"}).status_code == 400
    assert owner_client.get(url, {"filter_field": "role"}).status_code == 400
    assert owner_client.get(url, {"filter_field": "unknown", "filter_value": "x"}).status_code == 400
    assert owner_client.get(url, {"page_size": 51}).status_code == 400
    assert owner_client.get(url, {"q": "x" * 81}).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"full_name": "\u0000Bad"}, "full_name"),
        ({"role": "Bad\nRole"}, "role"),
        ({"email": "not-an-email"}, "email"),
        ({"kind": "administrator"}, "kind"),
    ],
)
def test_people_write_contract_rejects_invalid_values(owner_client, changes, field):
    response = owner_client.post(
        reverse("msp-people-list-create"),
        person_payload(**changes),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert field in str(response.json()["error"]["detail"])
    assert Person.objects.count() == 0
    assert Entity.objects.filter(entity_type="person").count() == 0


@pytest.mark.django_db
def test_people_endpoints_deny_anonymous_member_missing_mfa_and_cross_workspace_records(
    client,
    owner_client,
    installation,
):
    first = organization(installation.tenant, "First Client")
    second = organization(installation.tenant, "Second Client")
    first_url = reverse("organization-people-list-create", kwargs={"organization_entity_id": first.entity_id})
    created = owner_client.post(first_url, person_payload(), content_type="application/json")
    person_id = created.json()["id"]

    assert client.get(first_url).status_code == 403
    member = User.objects.create_user(email="people-member@example.com", display_name="Member")
    client.force_login(member)
    assert client.get(first_url).status_code == 403

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(first_url).status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())

    second_detail = reverse(
        "organization-person-detail",
        kwargs={"organization_entity_id": second.entity_id, "person_entity_id": person_id},
    )
    assert owner_client.get(second_detail).status_code == 404
    assert owner_client.patch(second_detail, {"role": "Hijacked"}, content_type="application/json").status_code == 404
    assert owner_client.delete(second_detail).status_code == 404

    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-people")
    foreign = organization(foreign_tenant, "Foreign Client")
    foreign_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": foreign.entity_id},
    )
    assert owner_client.get(foreign_url).status_code == 404
    association = PersonAssociation.objects.get(person__entity_id=person_id)
    assert association.role == "Systems Administrator"
    assert association.archived_at is None


@pytest.mark.django_db
def test_people_mutations_require_csrf(installation):
    client = Client(enforce_csrf_checks=True)
    client.force_login(installation.owner)

    response = client.post(
        reverse("msp-people-list-create"),
        person_payload(),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert Person.objects.count() == 0


@pytest.mark.django_db
def test_one_person_identity_can_have_msp_and_organization_associations(installation):
    client_organization = organization(installation.tenant, "Shared Client")
    entity = Entity.objects.create(tenant=installation.tenant, entity_type="person", display_name="Shared Person")
    person = Person.objects.create(tenant=installation.tenant, entity=entity)
    msp = PersonAssociation.objects.create(tenant=installation.tenant, person=person, kind="employee")
    client_contact = PersonAssociation.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        person=person,
        kind="contact",
    )

    assert list(PersonAssociation.scoped.for_scope(DataScope.tenant(installation.tenant))) == [msp]
    assert list(
        PersonAssociation.scoped.for_scope(DataScope.organization(installation.tenant, client_organization))
    ) == [client_contact]


@pytest.mark.django_db
def test_people_can_reference_active_structured_placement_only_within_their_workspace(owner_client, installation):
    client_organization = organization(installation.tenant, "Placed Client")
    other_organization = organization(installation.tenant, "Other Client")
    site_response = owner_client.post(
        reverse(
            "organization-site-list-create",
            kwargs={"organization_entity_id": client_organization.entity_id},
        ),
        {"name": "Main Campus", "code": "MAIN"},
        content_type="application/json",
    )
    site_id = site_response.json()["id"]
    location_response = owner_client.post(
        reverse(
            "organization-location-list-create",
            kwargs={"organization_entity_id": client_organization.entity_id, "site_entity_id": site_id},
        ),
        {"name": "Desk 214", "kind": "desk"},
        content_type="application/json",
    )
    location_id = location_response.json()["id"]
    people_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id},
    )

    created = owner_client.post(
        people_url,
        person_payload(
            location="Old campus label",
            office="Old desk label",
            site_id=site_id,
            structured_location_id=location_id,
        ),
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["site_id"] == site_id
    assert created.json()["structured_location_id"] == location_id
    assert created.json()["location"] == "Main Campus"
    assert created.json()["office"] == "Desk 214"

    other_people_url = reverse(
        "organization-people-list-create",
        kwargs={"organization_entity_id": other_organization.entity_id},
    )
    cross_workspace = owner_client.post(
        other_people_url,
        person_payload(full_name="Wrong Workspace", site_id=site_id, structured_location_id=location_id),
        content_type="application/json",
    )
    missing_site = owner_client.post(
        people_url,
        person_payload(full_name="Missing Site", site_id=None, structured_location_id=location_id),
        content_type="application/json",
    )
    assert cross_workspace.status_code == 404
    assert missing_site.status_code == 400

    association = PersonAssociation.objects.get(person__entity_id=created.json()["id"])
    assert isinstance(association.site, Site)
    assert isinstance(association.structured_location, Location)


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_reject_cross_tenant_person_associations(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Database scope triggers require PostgreSQL")
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-person-guard")
    foreign_organization = organization(foreign_tenant, "Foreign Client")
    entity = Entity.objects.create(tenant=installation.tenant, entity_type="person", display_name="Scoped Person")
    person = Person.objects.create(tenant=installation.tenant, entity=entity)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PersonAssociation.objects.create(
                tenant=installation.tenant,
                organization=foreign_organization,
                person=person,
                kind="contact",
            )

    foreign_entity = Entity.objects.create(tenant=foreign_tenant, entity_type="person", display_name="Foreign Person")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Person.objects.create(tenant=installation.tenant, entity=foreign_entity)
