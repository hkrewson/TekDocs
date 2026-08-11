import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState, NetBoxReference, workspace_for_owner
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


@pytest.mark.django_db(transaction=True)
def test_database_rejects_forged_netbox_workspace_edge(installation):
    if connection.vendor != "postgresql":
        pytest.skip("NetBox reference trigger certification requires PostgreSQL")
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
