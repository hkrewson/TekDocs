import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.custom_fields import archive_definition, create_definition
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
from apps.core.organizations import archive_organization
from apps.core.people import archive_person_association
from apps.core.sites import archive_location, archive_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Recovery MSP",
        owner_email="recovery-owner@example.com",
        owner_display_name="Recovery Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(tenant: Tenant, name: str, *, access_mode: str = "all_authorized") -> Organization:
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity, access_mode=access_mode)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def site_with_locations(tenant: Tenant, organization_record: Organization | None, name: str):  # type: ignore[no-untyped-def]
    site_entity = Entity.objects.create(
        tenant=tenant,
        organization=organization_record,
        entity_type="site",
        display_name=name,
    )
    site = Site.objects.create(tenant=tenant, organization=organization_record, entity=site_entity)
    parent_entity = Entity.objects.create(
        tenant=tenant,
        organization=organization_record,
        entity_type="location",
        display_name="First floor",
    )
    parent = Location.objects.create(
        tenant=tenant,
        organization=organization_record,
        entity=parent_entity,
        site=site,
        kind="floor",
    )
    child_entity = Entity.objects.create(
        tenant=tenant,
        organization=organization_record,
        entity_type="location",
        display_name="Office 101",
    )
    child = Location.objects.create(
        tenant=tenant,
        organization=organization_record,
        entity=child_entity,
        site=site,
        parent=parent,
        kind="office",
    )
    return site, parent, child


def person_association(tenant: Tenant, organization_record: Organization, site: Site, location: Location):
    entity = Entity.objects.create(tenant=tenant, entity_type="person", display_name="Morgan Ellis")
    person = Person.objects.create(tenant=tenant, entity=entity)
    return PersonAssociation.objects.create(
        tenant=tenant,
        organization=organization_record,
        person=person,
        kind="employee",
        site=site,
        structured_location=location,
    )


def restore_url(record_type: str, record_id: uuid.UUID, organization_record: Organization | None = None) -> str:
    if organization_record is None:
        return reverse(
            "msp-recycle-bin-restore",
            kwargs={"record_type": record_type, "record_id": record_id},
        )
    return reverse(
        "organization-recycle-bin-restore",
        kwargs={
            "organization_entity_id": organization_record.entity_id,
            "record_type": record_type,
            "record_id": record_id,
        },
    )


@pytest.mark.django_db
def test_recycle_bin_lists_exact_workspace_records_and_recovers_each_supported_type(owner_client, installation):
    client_org = organization(installation.tenant, "Client One")
    sibling = organization(installation.tenant, "Client Two")
    msp_site, _, _ = site_with_locations(installation.tenant, None, "MSP office")
    client_site, parent, _ = site_with_locations(installation.tenant, client_org, "Client office")
    sibling_site, _, _ = site_with_locations(installation.tenant, sibling, "Sibling office")
    association = person_association(installation.tenant, client_org, client_site, parent)
    definition = create_definition(
        tenant=installation.tenant,
        organization=client_org,
        actor_id=installation.owner.id,
        key="door_code",
        entity_type="site",
        label="Door code",
        description="",
        required=False,
        field_type="text",
        display_order=0,
        options=[],
    )
    archive_site(site=msp_site, actor_id=installation.owner.id)
    archive_site(site=sibling_site, actor_id=installation.owner.id)
    archive_person_association(association=association, actor_id=installation.owner.id)
    archive_definition(definition=definition, actor_id=installation.owner.id)

    msp_response = owner_client.get(reverse("msp-recycle-bin"))
    client_response = owner_client.get(
        reverse("organization-recycle-bin", kwargs={"organization_entity_id": client_org.entity_id})
    )

    assert msp_response.status_code == 200
    assert {(item["record_type"], item["label"]) for item in msp_response.json()["results"]} == {
        ("site", "MSP office")
    }
    assert client_response.status_code == 200
    assert {(item["record_type"], item["label"]) for item in client_response.json()["results"]} == {
        ("person_association", "Morgan Ellis"),
        ("custom_field_definition", "Door code"),
    }
    assert all(item["workspace_id"] == str(client_org.entity_id) for item in client_response.json()["results"])
    assert all(item["can_restore"] for item in client_response.json()["results"])

    recovered = owner_client.post(
        restore_url("custom_field_definition", definition.id, client_org),
        content_type="application/json",
    )
    assert recovered.status_code == 204
    definition.refresh_from_db()
    assert definition.archived_at is None
    assert not AuditEvent.objects.get(action="custom_field_definition.restored").metadata


@pytest.mark.django_db
def test_site_and_location_recovery_preserve_older_archives_and_restore_one_cascade(owner_client, installation):
    client_org = organization(installation.tenant, "Cascade Client")
    site, parent, child = site_with_locations(installation.tenant, client_org, "Cascade site")
    archive_location(location=child, actor_id=installation.owner.id)
    child.refresh_from_db()
    older_archive = child.archived_at
    archive_site(site=site, actor_id=installation.owner.id)
    parent.refresh_from_db()
    site.refresh_from_db()

    listed = owner_client.get(
        reverse("organization-recycle-bin", kwargs={"organization_entity_id": client_org.entity_id})
    )
    site_item = next(item for item in listed.json()["results"] if item["record_type"] == "site")
    assert site_item["cascade_count"] == 2

    restored = owner_client.post(restore_url("site", site.entity_id, client_org), content_type="application/json")
    assert restored.status_code == 204
    site.refresh_from_db()
    parent.refresh_from_db()
    child.refresh_from_db()
    parent.entity.refresh_from_db()
    child.entity.refresh_from_db()
    assert site.archived_at is None
    assert parent.archived_at is None
    assert parent.entity.archived_at is None
    assert child.archived_at == older_archive
    assert child.entity.archived_at == older_archive

    child_restore = owner_client.post(
        restore_url("location", child.entity_id, client_org),
        content_type="application/json",
    )
    assert child_restore.status_code == 204
    child.refresh_from_db()
    child.entity.refresh_from_db()
    assert child.archived_at is None
    assert child.entity.archived_at is None


@pytest.mark.django_db
def test_person_recovery_requires_active_structured_dependencies_and_is_atomic(owner_client, installation):
    client_org = organization(installation.tenant, "Dependency Client")
    site, location, _ = site_with_locations(installation.tenant, client_org, "Dependency site")
    association = person_association(installation.tenant, client_org, site, location)
    archive_person_association(association=association, actor_id=installation.owner.id)
    archive_site(site=site, actor_id=installation.owner.id)

    blocked = owner_client.post(
        restore_url("person_association", association.person.entity_id, client_org),
        content_type="application/json",
    )
    assert blocked.status_code == 409
    association.refresh_from_db()
    assert association.archived_at is not None
    assert not AuditEvent.objects.filter(action="person_association.restored").exists()

    assert owner_client.post(restore_url("site", site.entity_id, client_org)).status_code == 204
    assert owner_client.post(
        restore_url("person_association", association.person.entity_id, client_org)
    ).status_code == 204


@pytest.mark.django_db
def test_archived_organization_is_recoverable_only_from_msp_scope(owner_client, installation):
    archived = organization(installation.tenant, "Archived Client")
    archive_organization(organization=archived, actor_id=installation.owner.id)

    listed = owner_client.get(reverse("msp-recycle-bin"))
    assert ("organization", "Archived Client") in {
        (item["record_type"], item["label"]) for item in listed.json()["results"]
    }
    assert owner_client.get(
        reverse("organization-recycle-bin", kwargs={"organization_entity_id": archived.entity_id})
    ).status_code == 404
    assert owner_client.post(restore_url("organization", archived.entity_id)).status_code == 204
    archived.entity.refresh_from_db()
    assert archived.entity.archived_at is None


@pytest.mark.django_db
def test_recovery_denies_anonymous_reader_missing_mfa_csrf_foreign_and_sibling_identifiers(
    client,
    owner_client,
    installation,
):
    selected_org = organization(installation.tenant, "Selected Client")
    sibling = organization(installation.tenant, "Sibling Client")
    site, _, _ = site_with_locations(installation.tenant, selected_org, "Selected site")
    sibling_site, _, _ = site_with_locations(installation.tenant, sibling, "Sibling site")
    archive_site(site=site, actor_id=installation.owner.id)
    archive_site(site=sibling_site, actor_id=installation.owner.id)
    list_url = reverse("organization-recycle-bin", kwargs={"organization_entity_id": selected_org.entity_id})

    assert client.get(list_url).status_code == 403
    reader = User.objects.create_user(email="reader-recovery@example.com", display_name="Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    reader_client = Client()
    reader_client.force_login(reader)
    reader_list = reader_client.get(list_url)
    assert reader_list.status_code == 200
    assert reader_list.json()["results"][0]["can_restore"] is False
    assert reader_client.post(restore_url("site", site.entity_id, selected_org)).status_code == 403

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.post(restore_url("site", site.entity_id, selected_org)).status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.post(restore_url("site", site.entity_id, selected_org)).status_code == 403
    assert owner_client.post(restore_url("site", sibling_site.entity_id, selected_org)).status_code == 404

    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-recovery")
    foreign_site, _, _ = site_with_locations(foreign_tenant, None, "Foreign site")
    archive_site(site=foreign_site, actor_id=installation.owner.id)
    assert owner_client.post(restore_url("site", foreign_site.entity_id)).status_code == 404
    assert owner_client.post(restore_url("site", uuid.uuid4(), selected_org)).status_code == 404


@pytest.mark.django_db
def test_recycle_bin_query_is_bounded_and_validated(owner_client, installation):
    for name in ("Alpha", "Beta"):
        site, _, _ = site_with_locations(installation.tenant, None, name)
        archive_site(site=site, actor_id=installation.owner.id)

    filtered = owner_client.get(reverse("msp-recycle-bin"), {"q": "alp", "record_type": "site"})
    invalid = owner_client.get(reverse("msp-recycle-bin"), {"record_type": "secret", "page_size": 1000})

    assert filtered.status_code == 200
    assert [item["label"] for item in filtered.json()["results"]] == ["Alpha"]
    assert invalid.status_code == 400
