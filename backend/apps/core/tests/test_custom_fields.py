import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.custom_fields import CustomFieldValueError, build_schema, validate_custom_field_value
from apps.core.models import (
    AuditEvent,
    CustomFieldDefinition,
    CustomFieldDefinitionVersion,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="fields-owner@example.com",
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


def definition_payload(**overrides):
    return {
        "key": "service_tier",
        "entity_type": "site",
        "label": "Service tier",
        "description": "Support coverage assigned to this site.",
        "required": False,
        "field_type": "choice",
        "display_order": 20,
        "options": ["Silver", "Gold"],
        **overrides,
    }


def site_payload(**overrides):
    return {"name": "Main Office", "code": "MAIN", **overrides}


@pytest.mark.parametrize(
    ("field_type", "options", "valid_value", "invalid_value"),
    [
        ("text", [], "Remote access notes", 42),
        ("integer", [], 42, 42.5),
        ("number", [], 42.5, "42.5"),
        ("boolean", [], True, "true"),
        ("date", [], "2026-08-08", "08/08/2026"),
        ("url", [], "https://example.com/support", "javascript:alert(1)"),
        ("email", [], "support@example.com", "not-an-email"),
        ("choice", ["Silver", "Gold"], "Gold", "Platinum"),
        ("multi_choice", ["Remote", "On-site"], ["Remote", "On-site"], ["Remote", "Remote"]),
    ],
)
def test_supported_field_types_use_generated_json_schema(
    field_type,
    options,
    valid_value,
    invalid_value,
):
    schema = build_schema(field_type=field_type, options=options)

    validate_custom_field_value(schema=schema, value=valid_value)
    with pytest.raises(CustomFieldValueError):
        validate_custom_field_value(schema=schema, value=invalid_value)


@pytest.mark.django_db
def test_msp_and_organization_definitions_are_versioned_and_inherited(owner_client, installation):
    client_organization = organization(installation.tenant, "Acme Dental")
    msp_url = reverse("msp-custom-field-definition-list-create")
    organization_url = reverse(
        "organization-custom-field-definition-list-create",
        kwargs={"organization_entity_id": client_organization.entity_id},
    )

    msp_created = owner_client.post(msp_url, definition_payload(), content_type="application/json")
    organization_created = owner_client.post(
        organization_url,
        definition_payload(key="access_window", label="Access window", field_type="text", options=[]),
        content_type="application/json",
    )

    assert msp_created.status_code == 201
    assert organization_created.status_code == 201
    assert msp_created.json()["current_version"]["version"] == 1
    assert msp_created.json()["current_version"]["schema"]["enum"] == ["Silver", "Gold"]
    assert organization_created.json()["organization_id"] == str(client_organization.entity_id)
    listed = owner_client.get(organization_url).json()["results"]
    assert [(item["key"], item["inherited"]) for item in listed] == [
        ("access_window", False),
        ("service_tier", True),
    ]
    assert owner_client.get(msp_url).json()["count"] == 1


@pytest.mark.django_db
def test_values_pin_versions_and_incompatible_updates_preserve_history(owner_client, installation):
    client_organization = organization(installation.tenant, "Versioned Client")
    definition = owner_client.post(
        reverse("msp-custom-field-definition-list-create"),
        definition_payload(),
        content_type="application/json",
    ).json()
    site = owner_client.post(
        reverse(
            "organization-site-list-create",
            kwargs={"organization_entity_id": client_organization.entity_id},
        ),
        site_payload(),
        content_type="application/json",
    ).json()
    value_url = reverse(
        "organization-entity-custom-field-detail",
        kwargs={
            "organization_entity_id": client_organization.entity_id,
            "entity_id": site["id"],
            "definition_id": definition["id"],
        },
    )

    assigned = owner_client.patch(value_url, {"value": "Gold"}, content_type="application/json")
    assert assigned.status_code == 200
    original = assigned.json()["fields"][0]
    assert original["value"] == "Gold"
    assert original["value_version"] == 1
    assert original["is_current"] is True

    definition_url = reverse("msp-custom-field-definition-detail", kwargs={"definition_id": definition["id"]})
    versioned = owner_client.patch(
        definition_url,
        {
            "label": "Support plan",
            "description": "Updated plan names.",
            "required": False,
            "field_type": "choice",
            "display_order": 20,
            "options": ["Standard", "Premium"],
        },
        content_type="application/json",
    )
    assert versioned.status_code == 200
    assert versioned.json()["definition"]["current_version"]["version"] == 2
    assert versioned.json()["migration_impact"] == {"total": 1, "compatible": 0, "incompatible": 1}

    preserved = owner_client.get(
        reverse(
            "organization-entity-custom-field-list",
            kwargs={"organization_entity_id": client_organization.entity_id, "entity_id": site["id"]},
        )
    ).json()["fields"][0]
    assert preserved["value"] == "Gold"
    assert preserved["value_version"] == 1
    assert preserved["is_current"] is False
    assert preserved["valid_for_current"] is False

    invalid = owner_client.patch(value_url, {"value": "Gold"}, content_type="application/json")
    assert invalid.status_code == 400
    updated = owner_client.patch(value_url, {"value": "Premium"}, content_type="application/json")
    assert updated.status_code == 200
    assert updated.json()["fields"][0]["value_version"] == 2
    assert updated.json()["fields"][0]["is_current"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        definition_payload(field_type="choice", options=[]),
        definition_payload(field_type="text", options=["Unexpected"]),
        definition_payload(key="Bad Key"),
        definition_payload(field_type="secret", options=[]),
    ],
)
def test_definition_contract_rejects_unsafe_or_invalid_configuration(owner_client, payload):
    response = owner_client.post(
        reverse("msp-custom-field-definition-list-create"),
        payload,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert CustomFieldDefinition.objects.count() == 0


@pytest.mark.django_db
def test_definition_and_value_routes_reject_cross_workspace_and_inherited_mutation(owner_client, installation):
    first = organization(installation.tenant, "First Client")
    second = organization(installation.tenant, "Second Client")
    first_definitions = reverse(
        "organization-custom-field-definition-list-create",
        kwargs={"organization_entity_id": first.entity_id},
    )
    definition = owner_client.post(
        first_definitions,
        definition_payload(key="door_code_reference", label="Door-code reference", field_type="text", options=[]),
        content_type="application/json",
    ).json()
    site = owner_client.post(
        reverse("organization-site-list-create", kwargs={"organization_entity_id": first.entity_id}),
        site_payload(),
        content_type="application/json",
    ).json()
    wrong_value_url = reverse(
        "organization-entity-custom-field-detail",
        kwargs={
            "organization_entity_id": second.entity_id,
            "entity_id": site["id"],
            "definition_id": definition["id"],
        },
    )
    wrong_definition_url = reverse(
        "organization-custom-field-definition-detail",
        kwargs={"organization_entity_id": second.entity_id, "definition_id": definition["id"]},
    )

    wrong_value = owner_client.patch(
        wrong_value_url,
        {"value": "Record A"},
        content_type="application/json",
    )
    assert wrong_value.status_code == 404
    assert owner_client.delete(wrong_definition_url).status_code == 404

    msp_definition = owner_client.post(
        reverse("msp-custom-field-definition-list-create"),
        definition_payload(key="msp_standard", label="MSP standard", field_type="text", options=[]),
        content_type="application/json",
    ).json()
    inherited_url = reverse(
        "organization-custom-field-definition-detail",
        kwargs={"organization_entity_id": first.entity_id, "definition_id": msp_definition["id"]},
    )
    assert owner_client.delete(inherited_url).status_code == 404


@pytest.mark.django_db
def test_custom_field_endpoints_require_owner_mfa_and_csrf(client, owner_client, installation):
    url = reverse("msp-custom-field-definition-list-create")
    assert client.get(url).status_code == 403

    member = User.objects.create_user(email="fields-member@example.com", display_name="Member")
    client.force_login(member)
    assert client.get(url).status_code == 403

    installation.owner.authenticator_set.filter(type="totp").delete()
    assert owner_client.get(url).status_code == 200
    assert owner_client.post(url, definition_payload(), content_type="application/json").status_code == 403
    TOTP.activate(installation.owner, generate_totp_secret())

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(installation.owner)
    assert csrf_client.post(url, definition_payload(), content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_archive_retains_historical_value_but_blocks_new_assignment(owner_client, installation):
    client_organization = organization(installation.tenant, "Archive Client")
    definition = owner_client.post(
        reverse("msp-custom-field-definition-list-create"),
        definition_payload(field_type="text", options=[]),
        content_type="application/json",
    ).json()
    site = owner_client.post(
        reverse("organization-site-list-create", kwargs={"organization_entity_id": client_organization.entity_id}),
        site_payload(),
        content_type="application/json",
    ).json()
    value_url = reverse(
        "organization-entity-custom-field-detail",
        kwargs={
            "organization_entity_id": client_organization.entity_id,
            "entity_id": site["id"],
            "definition_id": definition["id"],
        },
    )
    owner_client.patch(value_url, {"value": "Retained"}, content_type="application/json")
    assert (
        owner_client.delete(
            reverse("msp-custom-field-definition-detail", kwargs={"definition_id": definition["id"]})
        ).status_code
        == 204
    )

    fields = owner_client.get(
        reverse(
            "organization-entity-custom-field-list",
            kwargs={"organization_entity_id": client_organization.entity_id, "entity_id": site["id"]},
        )
    ).json()["fields"]
    assert fields[0]["definition"]["archived"] is True
    assert fields[0]["value"] == "Retained"
    assert owner_client.patch(value_url, {"value": "Blocked"}, content_type="application/json").status_code == 404
    assert not AuditEvent.objects.filter(action__startswith="custom_field").exclude(metadata={}).exists()


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_reject_malformed_cross_scope_and_mutable_versions(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Database custom-field guards require PostgreSQL")
    first = organization(installation.tenant, "Guarded Client")
    second = organization(installation.tenant, "Other Client")
    definition = CustomFieldDefinition.objects.create(
        tenant=installation.tenant,
        organization=first,
        key="guarded",
        entity_type="site",
    )
    version = CustomFieldDefinitionVersion.objects.create(
        tenant=installation.tenant,
        definition=definition,
        version=1,
        label="Guarded field",
        field_type="text",
        schema={"type": "string"},
    )
    second_site = Entity.objects.create(
        tenant=installation.tenant,
        organization=second,
        entity_type="site",
        display_name="Other Site",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomFieldDefinition.objects.filter(pk=definition.pk).update(key="reinterpreted")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.filter(pk=second_site.pk).update(
                custom_fields={
                    str(definition.id): {
                        "definition_version_id": str(version.id),
                        "version": 1,
                        "value": "Cross-client",
                    }
                }
            )

    CustomFieldDefinition.objects.filter(pk=definition.pk).update(archived_at=timezone.now())
    first_site = Entity.objects.create(
        tenant=installation.tenant,
        organization=first,
        entity_type="site",
        display_name="First Site",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.filter(pk=first_site.pk).update(
                custom_fields={
                    str(definition.id): {
                        "definition_version_id": str(version.id),
                        "version": 1,
                        "value": "Archived",
                    }
                }
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.filter(pk=second_site.pk).update(custom_fields={str(definition.id): {"value": "Malformed"}})
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomFieldDefinitionVersion.objects.filter(pk=version.pk).update(label="Rewritten")
