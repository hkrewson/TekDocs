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
    Site,
    Tenant,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="sites-owner@example.com",
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
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def site_payload(**overrides):
    return {
        "name": "North Campus",
        "code": "NORTH",
        "address_line_1": "100 Main Street",
        "address_line_2": "Suite 200",
        "city": "Madison",
        "region": "Wisconsin",
        "postal_code": "53703",
        "country_code": "us",
        "timezone": "America/Chicago",
        "phone": "+1 555 010 1000",
        **overrides,
    }


@pytest.mark.django_db
def test_owner_can_manage_nested_sites_and_locations_in_msp_and_organization_workspaces(
    owner_client,
    installation,
):
    client_organization = organization(installation.tenant, "Acme Dental")
    msp_url = reverse("msp-site-list-create")
    organization_url = reverse(
        "organization-site-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id},
    )
    msp_created = owner_client.post(msp_url, site_payload(), content_type="application/json")
    organization_created = owner_client.post(
        organization_url,
        site_payload(name="Acme Clinic", code="CLINIC", address_line_2=""),
        content_type="application/json",
    )

    assert msp_created.status_code == 201
    assert organization_created.status_code == 201
    assert msp_created.json()["organization_id"] is None
    assert organization_created.json()["organization_id"] == str(client_organization.entity_id)
    assert organization_created.json()["country_code"] == "US"
    site_id = organization_created.json()["id"]

    location_url = reverse(
        "organization-location-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id, "site_entity_id": site_id},
    )
    building = owner_client.post(
        location_url,
        {"name": "Building A", "kind": "building", "code": "A"},
        content_type="application/json",
    )
    office = owner_client.post(
        location_url,
        {"name": "Office 214", "kind": "office", "code": "214", "parent_id": building.json()["id"]},
        content_type="application/json",
    )
    assert building.status_code == 201
    assert office.status_code == 201
    assert office.json()["parent_id"] == building.json()["id"]

    listed = owner_client.get(organization_url, {"q": "Office 214"}).json()
    assert listed["count"] == 1
    assert [location["name"] for location in listed["results"][0]["locations"]] == ["Building A", "Office 214"]
    assert owner_client.get(msp_url).json()["results"][0]["name"] == "North Campus"

    detail_url = reverse(
        "organization-site-detail",
        kwargs={"organization_entity_id": client_organization.entity_id, "site_entity_id": site_id},
    )
    updated = owner_client.patch(detail_url, {"phone": "+1 555 010 2000"}, content_type="application/json")
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+1 555 010 2000"

    office_detail = reverse(
        "organization-location-detail",
        kwargs={
            "organization_entity_id": client_organization.entity_id,
            "site_entity_id": site_id,
            "location_entity_id": office.json()["id"],
        },
    )
    renamed = owner_client.patch(office_detail, {"name": "Office 215"}, content_type="application/json")
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Office 215"

    assert owner_client.delete(detail_url).status_code == 204
    assert owner_client.get(detail_url).status_code == 404
    assert not Location.objects.filter(site__entity_id=site_id, archived_at__isnull=True).exists()
    actions = list(AuditEvent.objects.values_list("action", flat=True))
    assert {"site.created", "site.updated", "site.archived", "location.created", "location.updated"} <= set(actions)
    assert (
        not AuditEvent.objects.filter(
            action__in={"site.created", "site.updated", "site.archived", "location.created", "location.updated"}
        )
        .exclude(metadata={})
        .exists()
    )


@pytest.mark.django_db
def test_location_hierarchy_rejects_cycles_and_cross_site_parents(owner_client):
    site_url = reverse("msp-site-list-create")
    first_site = owner_client.post(site_url, site_payload(), content_type="application/json").json()
    second_site = owner_client.post(
        site_url,
        site_payload(name="South Campus", code="SOUTH"),
        content_type="application/json",
    ).json()
    first_locations = reverse("msp-location-list-create", kwargs={"site_entity_id": first_site["id"]})
    second_locations = reverse("msp-location-list-create", kwargs={"site_entity_id": second_site["id"]})
    root = owner_client.post(
        first_locations,
        {"name": "First floor", "kind": "floor"},
        content_type="application/json",
    ).json()
    child = owner_client.post(
        first_locations,
        {"name": "Office 1", "kind": "office", "parent_id": root["id"]},
        content_type="application/json",
    ).json()
    foreign_parent = owner_client.post(
        second_locations,
        {"name": "Other building", "kind": "building"},
        content_type="application/json",
    ).json()
    root_detail = reverse(
        "msp-location-detail",
        kwargs={"site_entity_id": first_site["id"], "location_entity_id": root["id"]},
    )

    cycle = owner_client.patch(root_detail, {"parent_id": child["id"]}, content_type="application/json")
    wrong_site = owner_client.patch(root_detail, {"parent_id": foreign_parent["id"]}, content_type="application/json")

    assert cycle.status_code == 400
    assert "descendants" in str(cycle.json()["error"]["detail"])
    assert wrong_site.status_code == 400
    assert "unavailable" in str(wrong_site.json()["error"]["detail"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": "Bad\nSite"}, "name"),
        ({"country_code": "USA"}, "country_code"),
        ({"timezone": "Local/Imaginary"}, "timezone"),
    ],
)
def test_site_write_contract_rejects_invalid_values(owner_client, changes, field):
    response = owner_client.post(
        reverse("msp-site-list-create"),
        site_payload(**changes),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert field in str(response.json()["error"]["detail"])
    assert Site.objects.count() == 0


@pytest.mark.django_db
def test_site_endpoints_deny_anonymous_member_missing_mfa_csrf_and_cross_workspace(
    client,
    owner_client,
    installation,
):
    first = organization(installation.tenant, "First Client")
    second = organization(installation.tenant, "Second Client")
    first_url = reverse("organization-site-list-create", kwargs={"organization_entity_id": first.entity_id})
    created = owner_client.post(first_url, site_payload(), content_type="application/json")
    site_id = created.json()["id"]

    assert client.get(first_url).status_code == 403
    member = User.objects.create_user(email="sites-member@example.com", display_name="Member")
    client.force_login(member)
    assert client.get(first_url).status_code == 403

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(first_url).status_code == 200
    assert (
        owner_client.post(first_url, site_payload(name="MFA Required"), content_type="application/json").status_code
        == 403
    )
    TOTP.activate(installation.owner, generate_totp_secret())

    second_detail = reverse(
        "organization-site-detail",
        kwargs={"organization_entity_id": second.entity_id, "site_entity_id": site_id},
    )
    assert owner_client.get(second_detail).status_code == 404
    assert owner_client.patch(second_detail, {"name": "Hijacked"}, content_type="application/json").status_code == 404
    assert owner_client.delete(second_detail).status_code == 404

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    csrf_response = csrf_client.post(reverse("msp-site-list-create"), site_payload(), content_type="application/json")
    assert csrf_response.status_code == 403

    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-sites")
    foreign = organization(foreign_tenant, "Foreign Client")
    foreign_url = reverse("organization-site-list-create", kwargs={"organization_entity_id": foreign.entity_id})
    assert owner_client.get(foreign_url).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_reject_cross_scope_sites_locations_and_parents(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Database scope triggers require PostgreSQL")
    client_organization = organization(installation.tenant, "Scoped Client")
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-site-guards")
    foreign_organization = organization(foreign_tenant, "Foreign Client")
    foreign_entity = Entity.objects.create_owned(
        tenant=foreign_tenant,
        organization=foreign_organization,
        entity_type="site",
        display_name="Foreign Site",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Site.objects.create(
                tenant=installation.tenant,
                organization=client_organization,
                entity=foreign_entity,
            )

    site_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_organization,
        entity_type="site",
        display_name="Client Site",
    )
    site = Site.objects.create(tenant=installation.tenant, organization=client_organization, entity=site_entity)
    other_entity = Entity.objects.create_owned(tenant=installation.tenant, entity_type="site", display_name="MSP Site")
    other_site = Site.objects.create(tenant=installation.tenant, entity=other_entity)
    parent_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        entity_type="location",
        display_name="MSP Parent",
    )
    parent = Location.objects.create(
        tenant=installation.tenant,
        entity=parent_entity,
        site=other_site,
        kind="building",
    )
    location_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_organization,
        entity_type="location",
        display_name="Client Office",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Location.objects.create(
                tenant=installation.tenant,
                organization=client_organization,
                entity=location_entity,
                site=site,
                parent=parent,
                kind="office",
            )

    root_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_organization,
        entity_type="location",
        display_name="Root",
    )
    root = Location.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        entity=root_entity,
        site=site,
        kind="building",
    )
    child_entity = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_organization,
        entity_type="location",
        display_name="Child",
    )
    child = Location.objects.create(
        tenant=installation.tenant,
        organization=client_organization,
        entity=child_entity,
        site=site,
        parent=root,
        kind="office",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Location.objects.filter(pk=root.pk).update(parent=child)
