import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.models import (
    AuditEvent,
    Entity,
    EntityLink,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Relationship MSP",
        owner_email="relationships-owner@example.com",
        owner_display_name="Relationship Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(tenant: Tenant, name: str, *classifications: str) -> Organization:
    entity = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity)
    for kind in classifications or ("client",):
        OrganizationClassification.objects.create(tenant=tenant, organization=record, kind=kind)
    return record


def organization_links_url(organization_record: Organization) -> str:
    return reverse(
        "organization-entity-relationship-list-create",
        kwargs={
            "organization_entity_id": organization_record.entity_id,
            "entity_id": organization_record.entity_id,
        },
    )


@pytest.mark.django_db
def test_link_type_catalog_is_bounded_and_requires_membership(owner_client, client):
    response = owner_client.get(reverse("entity-link-type-catalog"))

    assert response.status_code == 200
    assert [item["value"] for item in response.json()] == [
        "related_to",
        "depends_on",
        "managed_by",
        "supplied_by",
        "manufactured_by",
        "partnered_with",
        "located_at",
        "assigned_to",
        "references",
    ]
    assert response.json()[0] == {
        "value": "related_to",
        "forward_label": "Related to",
        "inverse_label": "Related to",
        "symmetric": True,
        "target_types": [],
    }
    assert client.get(reverse("entity-link-type-catalog")).status_code == 403


@pytest.mark.django_db
def test_entity_search_respects_msp_and_organization_visibility(owner_client, installation):
    client_org = organization(installation.tenant, "Acme Client", "client")
    vendor_org = organization(installation.tenant, "Beacon Vendor", "vendor")
    sibling_org = organization(installation.tenant, "Cedar Client", "client")
    msp_site = Entity.objects.create_owned(tenant=installation.tenant, entity_type="site", display_name="MSP Office")
    own_site = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_org,
        entity_type="site",
        display_name="Acme Office",
    )
    Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=sibling_org,
        entity_type="site",
        display_name="Cedar Private Office",
    )
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug="foreign-relationship-search")
    Entity.objects.create_owned(tenant=foreign_tenant, entity_type="organization", display_name="Foreign Vendor")

    msp = owner_client.get(reverse("msp-entity-search"), {"entity_type": "site"}).json()
    organization_result = owner_client.get(
        reverse(
            "organization-entity-search",
            kwargs={"organization_entity_id": client_org.entity_id},
        ),
        {"q": "office"},
    ).json()

    assert [item["id"] for item in msp["results"]] == [str(msp_site.id)]
    assert {item["id"] for item in organization_result["results"]} == {str(own_site.id)}
    organization_candidates = owner_client.get(
        reverse(
            "organization-entity-search",
            kwargs={"organization_entity_id": client_org.entity_id},
        ),
        {"entity_type": "organization", "page_size": 2},
    ).json()
    assert organization_candidates["count"] == 3
    assert organization_candidates["has_more"] is True
    assert all(item["workspace_label"] == "MSP organization directory" for item in organization_candidates["results"])
    assert str(vendor_org.entity_id) in {
        item["id"]
        for item in owner_client.get(
            reverse(
                "organization-entity-search",
                kwargs={"organization_entity_id": client_org.entity_id},
            ),
            {"q": "Beacon", "entity_type": "organization"},
        ).json()["results"]
    }


@pytest.mark.django_db
def test_entity_search_rejects_malformed_and_over_broad_queries(owner_client, client, installation):
    client_org = organization(installation.tenant, "Bounded Search Client", "client")
    url = reverse(
        "organization-entity-search",
        kwargs={"organization_entity_id": client_org.entity_id},
    )

    assert owner_client.get(url, {"entity_type": "secret"}).status_code == 400
    assert owner_client.get(url, {"page_size": 26}).status_code == 400
    assert owner_client.get(url, {"q": "x" * 81}).status_code == 400
    assert client.get(url).status_code == 403


@pytest.mark.django_db
def test_directional_relationship_and_backlink_are_workspace_visible(owner_client, installation):
    client_org = organization(installation.tenant, "Direction Client", "client")
    vendor_org = organization(installation.tenant, "Direction Vendor", "vendor")

    created = owner_client.post(
        organization_links_url(client_org),
        {"target_id": str(vendor_org.entity_id), "link_type": "supplied_by"},
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["label"] == "Supplied by"
    assert created.json()["direction"] == "outgoing"
    assert created.json()["related_entity"]["display_name"] == "Direction Vendor"
    client_links = owner_client.get(organization_links_url(client_org)).json()["relationships"]
    vendor_links = owner_client.get(organization_links_url(vendor_org)).json()["relationships"]
    assert client_links[0]["label"] == "Supplied by"
    assert vendor_links[0]["label"] == "Supplies"
    assert vendor_links[0]["direction"] == "incoming"
    assert vendor_links[0]["related_entity"]["display_name"] == "Direction Client"
    assert AuditEvent.objects.filter(action="entity_link.created", metadata={}).count() == 1


@pytest.mark.django_db
def test_symmetric_links_are_canonical_and_reject_duplicates_self_links_and_metadata(owner_client, installation):
    first = organization(installation.tenant, "Zulu Partner", "partner")
    second = organization(installation.tenant, "Alpha Partner", "partner")
    url = organization_links_url(first)

    created = owner_client.post(
        url,
        {"target_id": str(second.entity_id), "link_type": "partnered_with"},
        content_type="application/json",
    )
    duplicate = owner_client.post(
        organization_links_url(second),
        {"target_id": str(first.entity_id), "link_type": "partnered_with"},
        content_type="application/json",
    )
    self_link = owner_client.post(
        url,
        {"target_id": str(first.entity_id), "link_type": "related_to"},
        content_type="application/json",
    )
    metadata = owner_client.post(
        url,
        {"target_id": str(second.entity_id), "link_type": "related_to", "metadata": {"note": "hidden"}},
        content_type="application/json",
    )

    assert created.status_code == 201
    stored = EntityLink.scoped.for_tenant(installation.tenant).get(id=created.json()["id"])
    assert stored.source_id.int < stored.target_id.int
    assert duplicate.status_code == 400
    assert self_link.status_code == 400
    assert metadata.status_code == 400


@pytest.mark.django_db
def test_relationship_type_enforces_target_kind_and_classification(owner_client, installation):
    client_org = organization(installation.tenant, "Typed Client", "client")
    partner_org = organization(installation.tenant, "Typed Partner", "partner")
    site = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=client_org,
        entity_type="site",
        display_name="Client site",
    )

    wrong_classification = owner_client.post(
        organization_links_url(client_org),
        {"target_id": str(partner_org.entity_id), "link_type": "supplied_by"},
        content_type="application/json",
    )
    wrong_type = owner_client.post(
        organization_links_url(client_org),
        {"target_id": str(site.id), "link_type": "assigned_to"},
        content_type="application/json",
    )

    assert wrong_classification.status_code == 400
    assert wrong_type.status_code == 400
    assert EntityLink.scoped.for_tenant(installation.tenant).count() == 0


@pytest.mark.django_db
def test_cross_workspace_and_foreign_relationship_targets_do_not_disclose_existence(owner_client, installation):
    first = organization(installation.tenant, "First Scope", "client")
    second = organization(installation.tenant, "Second Scope", "client")
    second_private = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=second,
        entity_type="site",
        display_name="Second private site",
    )
    foreign_tenant = Tenant.objects.create(name="Foreign Scope", slug="foreign-link-target")
    foreign = Entity.objects.create_owned(tenant=foreign_tenant, entity_type="organization", display_name="Foreign")

    sibling = owner_client.post(
        organization_links_url(first),
        {"target_id": str(second_private.id), "link_type": "related_to"},
        content_type="application/json",
    )
    foreign_response = owner_client.post(
        organization_links_url(first),
        {"target_id": str(foreign.id), "link_type": "related_to"},
        content_type="application/json",
    )
    wrong_source = owner_client.get(
        reverse(
            "organization-entity-relationship-list-create",
            kwargs={"organization_entity_id": first.entity_id, "entity_id": second_private.id},
        )
    )

    assert sibling.status_code == 404
    assert foreign_response.status_code == 404
    assert wrong_source.status_code == 404


@pytest.mark.django_db
def test_relationship_mutations_require_owner_mfa_and_csrf(client, owner_client, installation):
    source = organization(installation.tenant, "Policy Client", "client")
    target = organization(installation.tenant, "Policy Vendor", "vendor")
    url = organization_links_url(source)
    payload = {"target_id": str(target.entity_id), "link_type": "supplied_by"}

    assert client.post(url, payload, content_type="application/json").status_code == 403
    member = User.objects.create_user(email="relationship-member@example.com", display_name="Member")
    client.force_login(member)
    assert client.post(url, payload, content_type="application/json").status_code == 403
    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.post(url, payload, content_type="application/json").status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.post(url, payload, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_relationship_archive_preserves_history_and_hides_active_link(owner_client, installation):
    source = organization(installation.tenant, "Archive Client", "client")
    target = organization(installation.tenant, "Archive Vendor", "vendor")
    created = owner_client.post(
        organization_links_url(source),
        {"target_id": str(target.entity_id), "link_type": "supplied_by"},
        content_type="application/json",
    ).json()
    detail_url = reverse(
        "organization-entity-relationship-detail",
        kwargs={
            "organization_entity_id": source.entity_id,
            "entity_id": source.entity_id,
            "link_id": created["id"],
        },
    )

    assert owner_client.delete(detail_url).status_code == 204
    assert owner_client.get(organization_links_url(source)).json()["relationships"] == []
    stored = EntityLink.scoped.for_tenant(installation.tenant).get(id=created["id"])
    assert stored.archived_at is not None
    assert stored.metadata == {}
    assert AuditEvent.objects.filter(action="entity_link.archived", metadata={}).count() == 1
    recreated = owner_client.post(
        organization_links_url(source),
        {"target_id": str(target.entity_id), "link_type": "supplied_by"},
        content_type="application/json",
    )
    assert recreated.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_postgres_link_guards_reject_scope_identity_metadata_and_noncanonical_writes(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Database entity-link guards require PostgreSQL")
    first = organization(installation.tenant, "Guard First", "partner")
    second = organization(installation.tenant, "Guard Second", "partner")
    foreign_tenant = Tenant.objects.create(name="Guard Foreign", slug="guard-foreign-link")
    foreign = Entity.objects.create_owned(tenant=foreign_tenant, entity_type="organization", display_name="Foreign")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.create(
                tenant=installation.tenant,
                source=first.entity,
                target=foreign,
                link_type="related_to",
            )
    high, low = sorted((first.entity, second.entity), key=lambda item: item.id.int, reverse=True)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.create(
                tenant=installation.tenant,
                source=high,
                target=low,
                link_type="partnered_with",
            )
    low, high = sorted((first.entity, second.entity), key=lambda item: item.id.int)
    link = EntityLink.objects.create(
        tenant=installation.tenant,
        source=low,
        target=high,
        link_type="partnered_with",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.filter(id=link.id).update(link_type="related_to")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.filter(id=link.id).update(metadata={"unsafe": True})
    EntityLink.objects.filter(id=link.id).update(archived_at=timezone.now())
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityLink.objects.filter(id=link.id).update(archived_at=None)
