import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState, NetBoxReference, workspace_for_owner
from apps.core.netbox_reconciliation import set_reference
from apps.core.network_inventory import create_rack
from apps.core.organizations import create_organization
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="NetBox seam MSP",
        owner_email="netbox-owner@example.invalid",
        owner_display_name="NetBox Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )


def _rack(installation, organization, name):  # type: ignore[no-untyped-def]
    site = create_site(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=f"{name} site",
        code=name.upper().replace(" ", "-")[:24],
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    return create_rack(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name=name,
        site_entity_id=site.entity_id,
        location_entity_id=None,
        unit_count=42,
        status="active",
    )


@pytest.mark.django_db
def test_netbox_reference_and_deterministic_preview_are_exact_workspace(owner_client, installation):
    client = _organization(installation, "Mapped client")
    sibling = _organization(installation, "Sibling client")
    rack = _rack(installation, client, "Mapped rack")
    second_rack = _rack(installation, client, "Second rack")
    sibling_rack = _rack(installation, sibling, "Sibling rack")
    kwargs = {"organization_entity_id": client.entity_id}
    collection = reverse("organization-netbox-reference-list-create", kwargs=kwargs)

    choices = owner_client.get(reverse("organization-netbox-reference-choices", kwargs=kwargs))
    assert choices.status_code == 200
    mapped_choice = next(item for item in choices.json()["results"] if item["id"] == str(rack.entity_id))
    assert mapped_choice == {
        "id": str(rack.entity_id),
        "name": "Mapped rack",
        "entity_type": "network_rack",
        "object_type": "dcim.rack",
        "linked": False,
    }

    created = owner_client.post(
        collection,
        {
            "entity_id": str(rack.entity_id),
            "object_type": "dcim.rack",
            "object_id": 41,
            "fingerprint": "a" * 64,
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["object_id"] == 41
    assert owner_client.get(reverse("msp-netbox-reference-list-create")).json() == []

    mismatch = owner_client.post(
        collection,
        {"entity_id": str(second_rack.entity_id), "object_type": "ipam.vlan", "object_id": 41},
        content_type="application/json",
    )
    assert mismatch.status_code == 400
    secret_like_extra = owner_client.post(
        collection,
        {
            "entity_id": str(second_rack.entity_id),
            "object_type": "dcim.rack",
            "object_id": 42,
            "api_token": "must-not-be-accepted",
        },
        content_type="application/json",
    )
    assert secret_like_extra.status_code == 400
    sibling_guess = owner_client.post(
        collection,
        {"entity_id": str(sibling_rack.entity_id), "object_type": "dcim.rack", "object_id": 42},
        content_type="application/json",
    )
    assert sibling_guess.status_code == 400

    preview_url = reverse("organization-netbox-reconcile-preview", kwargs=kwargs)
    preview = owner_client.post(
        preview_url,
        {
            "observations": [
                {"object_type": "dcim.rack", "object_id": 41, "fingerprint": "a" * 64},
                {"object_type": "ipam.vlan", "object_id": 77, "fingerprint": "b" * 64},
            ]
        },
        content_type="application/json",
    )
    assert preview.status_code == 200
    assert preview.json()["counts"] == {"current": 1, "unmatched": 1}
    assert [item["status"] for item in preview.json()["results"]] == ["current", "unmatched"]
    changed = owner_client.post(
        preview_url,
        {"observations": [{"object_type": "dcim.rack", "object_id": 41, "fingerprint": "c" * 64}]},
        content_type="application/json",
    )
    assert changed.json()["counts"] == {"changed": 1}
    missing = owner_client.post(preview_url, {"observations": []}, content_type="application/json")
    assert missing.json()["counts"] == {"missing_remote": 1}
    duplicate = owner_client.post(
        preview_url,
        {
            "observations": [
                {"object_type": "dcim.rack", "object_id": 41, "fingerprint": "a" * 64},
                {"object_type": "dcim.rack", "object_id": 41, "fingerprint": "b" * 64},
            ]
        },
        content_type="application/json",
    )
    assert duplicate.status_code == 400
    nested_extra = owner_client.post(
        preview_url,
        {
            "observations": [
                {
                    "object_type": "dcim.rack",
                    "object_id": 41,
                    "fingerprint": "a" * 64,
                    "url": "https://netbox.example.invalid",
                }
            ]
        },
        content_type="application/json",
    )
    assert nested_extra.status_code == 400

    removed = owner_client.delete(
        reverse("organization-netbox-reference-detail", kwargs={**kwargs, "reference_id": created.json()["id"]})
    )
    assert removed.status_code == 204
    assert owner_client.get(collection).json() == []
    assert Client().get(collection).status_code in {401, 403}


@pytest.mark.django_db
def test_netbox_register_collections_are_bounded_searchable_and_workspace_exact(owner_client, installation):
    client = _organization(installation, "Paged client")
    sibling = _organization(installation, "Paged sibling")
    racks = [_rack(installation, client, f"Rack {number:02d}") for number in range(1, 28)]
    sibling_rack = _rack(installation, sibling, "Sibling only rack")
    kwargs = {"organization_entity_id": client.entity_id}
    choice_url = reverse("organization-netbox-reference-choice-collection", kwargs=kwargs)

    first_choices = owner_client.get(choice_url, {"page": 1, "page_size": 25})
    assert first_choices.status_code == 200
    assert first_choices.json()["count"] == 27
    assert len(first_choices.json()["results"]) == 25
    assert first_choices.json()["has_more"] is True
    selected = owner_client.get(choice_url, {"page": 1, "page_size": 25, "selected_id": racks[-1].entity_id})
    assert selected.json()["selected"]["name"] == "Rack 27"
    assert owner_client.get(choice_url, {"q": "Sibling"}).json()["count"] == 0

    for number, rack in enumerate(racks[:26], start=1):
        set_reference(
            tenant=installation.tenant,
            organization=client,
            actor_id=installation.owner.id,
            entity_id=rack.entity_id,
            object_type="dcim.rack",
            object_id=number,
            fingerprint="",
        )
    set_reference(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        entity_id=sibling_rack.entity_id,
        object_type="dcim.rack",
        object_id=999,
        fingerprint="",
    )

    collection_url = reverse("organization-netbox-reference-collection", kwargs=kwargs)
    first = owner_client.get(collection_url, {"page": 1, "page_size": 25, "ordering": "name"})
    assert first.status_code == 200
    assert first.json()["count"] == 26
    assert len(first.json()["results"]) == 25
    assert first.json()["has_more"] is True
    assert first.json()["can_manage"] is True
    second = owner_client.get(collection_url, {"page": 2, "page_size": 25, "ordering": "name"})
    assert [record["entity_name"] for record in second.json()["results"]] == ["Rack 26"]
    off_page = owner_client.get(collection_url, {"q": "Rack 26", "page": 1, "page_size": 25})
    assert [record["entity_name"] for record in off_page.json()["results"]] == ["Rack 26"]
    by_identifier = owner_client.get(collection_url, {"q": "26"})
    assert any(record["object_id"] == 26 for record in by_identifier.json()["results"])
    assert owner_client.get(collection_url, {"object_type": "ipam.vlan"}).json()["count"] == 0
    assert owner_client.get(collection_url, {"unexpected": "1"}).status_code == 400
    assert owner_client.get(choice_url, {"unexpected": "1"}).status_code == 400
    assert all(record["object_id"] != 999 for record in owner_client.get(collection_url).json()["results"])


@pytest.mark.django_db(transaction=True)
def test_database_rejects_forged_netbox_workspace_edge(installation):
    if connection.vendor != "postgresql":
        pytest.skip("NetBox reference trigger validation requires PostgreSQL")
    client = _organization(installation, "Database client")
    sibling = _organization(installation, "Database sibling")
    sibling_rack = _rack(installation, sibling, "Database sibling rack")
    with pytest.raises(DatabaseError), transaction.atomic():
        NetBoxReference.objects.create(
            tenant=installation.tenant,
            workspace=workspace_for_owner(tenant=installation.tenant, organization=client),
            organization=client,
            entity=sibling_rack.entity,
            object_type="dcim.rack",
            object_id=99,
        )
