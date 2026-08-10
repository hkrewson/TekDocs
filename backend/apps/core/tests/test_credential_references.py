import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    BuiltInRole,
    CustomRole,
    CustomRolePermission,
    CustomRoleScope,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)
from apps.core.credential_references import normalize_credential_reference
from apps.core.models import AuditEvent, CredentialReference, InstallationState
from apps.core.organizations import create_organization

PRIVATE_LINK = (
    "https://start.1password.com/open/i?"
    "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
    "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Reference MSP",
        owner_email="reference-owner@example.invalid",
        owner_display_name="Reference Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    client = Client()
    client.force_login(result.owner)
    first = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="First Client",
        legal_name="First Client LLC",
        website="",
        classifications=["client"],
    )
    second = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Second Client",
        legal_name="Second Client LLC",
        website="",
        classifications=["client"],
    )
    return result, client, first, second


@pytest.mark.parametrize(
    "value",
    [
        "https://share.1password.com/s/example",
        "https://example.invalid/open/i?a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com",
        PRIVATE_LINK + "&extra=true",
        PRIVATE_LINK.replace("https://", "onepassword://"),
        PRIVATE_LINK.replace("example.1password.com", "example.invalid"),
        PRIVATE_LINK.replace("i=iiiiiiiiiiiiiiiiiiiiiiiiii", "i=secret-value"),
    ],
)
def test_onepassword_adapter_rejects_share_arbitrary_and_ambiguous_links(value):
    with pytest.raises(ValidationError):
        normalize_credential_reference("onepassword", value)


def test_credential_reference_api_omits_private_link_and_records_value_free_audit(installation):
    result, client, first, _second = installation
    collection = reverse(
        "organization-credential-reference-list-create",
        kwargs={"organization_entity_id": first.entity_id},
    )
    created = client.post(
        collection,
        {"title": "Firewall administrator", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    assert created.status_code == 201
    assert "reference_url" not in created.json()
    assert PRIVATE_LINK not in created.content.decode()

    listing = client.get(collection)
    assert listing.status_code == 200
    assert listing.json()["results"][0]["title"] == "Firewall administrator"
    assert PRIVATE_LINK not in listing.content.decode()

    entity_id = created.json()["id"]
    opened = client.get(
        reverse(
            "organization-credential-reference-open",
            kwargs={"organization_entity_id": first.entity_id, "credential_reference_entity_id": entity_id},
        )
    )
    assert opened.status_code == 302
    assert opened.headers["Location"] == PRIVATE_LINK
    event = AuditEvent.objects.get(action="credential_reference.opened", entity_id=uuid.UUID(entity_id))
    assert event.tenant == result.tenant
    assert event.metadata == {}


def test_client_scope_blocks_sibling_reference_idor_and_secret_shaped_fields(installation):
    _result, client, first, second = installation
    first_collection = reverse(
        "organization-credential-reference-list-create", kwargs={"organization_entity_id": first.entity_id}
    )
    created = client.post(
        first_collection,
        {"title": "Router", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    entity_id = created.json()["id"]
    sibling_detail = reverse(
        "organization-credential-reference-detail",
        kwargs={"organization_entity_id": second.entity_id, "credential_reference_entity_id": entity_id},
    )
    assert client.patch(sibling_detail, {"title": "Cross-scope"}, content_type="application/json").status_code == 404
    assert client.delete(sibling_detail).status_code == 404
    assert CredentialReference.objects.get(entity_id=entity_id).entity.display_name == "Router"

    rejected = client.post(
        first_collection,
        {
            "title": "Forbidden value",
            "provider": "onepassword",
            "reference_url": PRIVATE_LINK,
            "password": "must-not-be-stored",
        },
        content_type="application/json",
    )
    assert rejected.status_code == 400
    assert CredentialReference.objects.filter(entity__display_name="Forbidden value").exists() is False


def test_msp_and_client_references_never_cross_workspace_lists(installation):
    _result, client, first, _second = installation
    msp_collection = reverse("msp-credential-reference-list-create")
    client.post(
        msp_collection,
        {"title": "MSP private", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    client_collection = reverse(
        "organization-credential-reference-list-create", kwargs={"organization_entity_id": first.entity_id}
    )
    client.post(
        client_collection,
        {"title": "Client private", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    assert [item["title"] for item in client.get(msp_collection).json()["results"]] == ["MSP private"]
    assert [item["title"] for item in client.get(client_collection).json()["results"]] == ["Client private"]


def test_organization_scoped_custom_grant_does_not_reach_sibling_or_bypass_manage_mfa(installation):
    result, owner_client, first, second = installation
    first_collection = reverse(
        "organization-credential-reference-list-create", kwargs={"organization_entity_id": first.entity_id}
    )
    owner_client.post(
        first_collection,
        {"title": "Scoped reference", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    user = User.objects.create_user(email="reference-reader@example.invalid", display_name="Reference Reader")
    membership = TenantMembership.objects.create(tenant=result.tenant, user=user, role=BuiltInRole.READ_ONLY)
    role = CustomRole.objects.create(
        tenant=result.tenant,
        name="Client credential operator",
        scope=CustomRoleScope.ORGANIZATION,
        created_by=result.owner,
    )
    for permission in (
        "credential_references.view",
        "credential_references.open",
        "credential_references.manage",
    ):
        CustomRolePermission.objects.create(tenant=result.tenant, role=role, permission=permission)
    ScopedRoleAssignment.objects.create(
        tenant=result.tenant,
        membership=membership,
        role=role,
        organization=first,
        created_by=result.owner,
    )
    member_client = Client()
    member_client.force_login(user)

    assert member_client.get(first_collection).status_code == 200
    assert (
        member_client.get(
            reverse(
                "organization-credential-reference-list-create",
                kwargs={"organization_entity_id": second.entity_id},
            )
        ).status_code
        == 403
    )
    assert (
        member_client.post(
            first_collection,
            {"title": "MFA denied", "provider": "onepassword", "reference_url": PRIVATE_LINK},
            content_type="application/json",
        ).status_code
        == 403
    )


def test_collection_scoped_custom_grant_reaches_only_collection_organizations(installation):
    result, owner_client, first, second = installation
    first_collection = reverse(
        "organization-credential-reference-list-create", kwargs={"organization_entity_id": first.entity_id}
    )
    second_collection = reverse(
        "organization-credential-reference-list-create", kwargs={"organization_entity_id": second.entity_id}
    )
    owner_client.post(
        first_collection,
        {"title": "Collection reference", "provider": "onepassword", "reference_url": PRIVATE_LINK},
        content_type="application/json",
    )
    user = User.objects.create_user(email="collection-reference-reader@example.invalid")
    TenantMembership.objects.create(tenant=result.tenant, user=user, role=BuiltInRole.READ_ONLY)
    collection = owner_client.post(
        reverse("access-collection-list-create"),
        {"name": "Credential clients", "description": "", "organization_ids": [first.entity_id]},
        content_type="application/json",
    ).json()
    role = owner_client.post(
        reverse("custom-role-list-create"),
        {
            "name": "Collection credential reader",
            "description": "",
            "scope": "collection",
            "permissions": ["credential_references.view"],
        },
        content_type="application/json",
    ).json()
    owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {"user_id": user.id, "role_id": role["id"], "collection_id": collection["id"]},
        content_type="application/json",
    )
    member_client = Client()
    member_client.force_login(user)

    response = member_client.get(first_collection)
    assert response.status_code == 200
    assert [item["title"] for item in response.json()["results"]] == ["Collection reference"]
    assert member_client.get(second_collection).status_code == 403
