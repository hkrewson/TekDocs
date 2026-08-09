import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import PERMISSION_BY_KEY
from apps.core.models import InstallationState
from apps.core.permission_inventory import AUTHENTICATED_ROUTE_PERMISSIONS, PUBLIC_API_ROUTE_NAMES


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Matrix MSP",
        owner_email="matrix-owner@example.com",
        owner_display_name="Matrix Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def _api_route_names():
    pending = [("", get_resolver().url_patterns)]
    names: set[str] = set()
    while pending:
        prefix, patterns = pending.pop()
        for pattern in patterns:
            route_pattern = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                pending.append((route_pattern, pattern.url_patterns))
            elif isinstance(pattern, URLPattern) and route_pattern.startswith("api/v1/") and pattern.name:
                names.add(pattern.name)
    return names


def _api_route_methods():
    pending = [("", get_resolver().url_patterns)]
    methods: dict[str, set[str]] = {}
    supported = {"GET", "POST", "PATCH", "PUT", "DELETE"}
    while pending:
        prefix, patterns = pending.pop()
        for pattern in patterns:
            route_pattern = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                pending.append((route_pattern, pattern.url_patterns))
            elif isinstance(pattern, URLPattern) and route_pattern.startswith("api/v1/") and pattern.name:
                view_class = getattr(pattern.callback, "view_class", None)
                if view_class is not None:
                    methods[pattern.name] = {method for method in supported if hasattr(view_class, method.lower())}
    return methods


def _kwargs_for(route_name: str) -> dict[str, object]:
    value = uuid.UUID("00000000-0000-4000-8000-000000000001")
    route_kwargs: dict[str, tuple[str, ...]] = {
        "access-collection-detail": ("collection_id",),
        "custom-role-detail": ("role_id",),
        "scoped-role-assignment-detail": ("assignment_id",),
        "access-control-member-role": ("user_id",),
        "access-control-organization-detail": ("organization_entity_id",),
        "access-control-organization-staff": ("organization_entity_id",),
        "access-control-organization-staff-detail": ("organization_entity_id", "user_id"),
        "invitation-revoke": ("invitation_id",),
        "invitation-resend": ("invitation_id",),
        "organization-detail": ("entity_id",),
        "msp-entity-relationship-list-create": ("entity_id",),
        "msp-entity-relationship-detail": ("entity_id", "link_id"),
        "msp-person-detail": ("person_entity_id",),
        "msp-site-detail": ("site_entity_id",),
        "msp-location-list-create": ("site_entity_id",),
        "msp-location-detail": ("site_entity_id", "location_entity_id"),
        "msp-custom-field-definition-detail": ("definition_id",),
        "msp-entity-custom-field-list": ("entity_id",),
        "msp-entity-custom-field-detail": ("entity_id", "definition_id"),
        "workspace-organization": ("entity_id",),
        "organization-people-list-create": ("organization_entity_id",),
        "organization-person-detail": ("organization_entity_id", "person_entity_id"),
        "organization-site-list-create": ("organization_entity_id",),
        "organization-site-detail": ("organization_entity_id", "site_entity_id"),
        "organization-location-list-create": ("organization_entity_id", "site_entity_id"),
        "organization-location-detail": (
            "organization_entity_id",
            "site_entity_id",
            "location_entity_id",
        ),
        "organization-custom-field-definition-list-create": ("organization_entity_id",),
        "organization-custom-field-definition-detail": ("organization_entity_id", "definition_id"),
        "organization-entity-custom-field-list": ("organization_entity_id", "entity_id"),
        "organization-entity-custom-field-detail": (
            "organization_entity_id",
            "entity_id",
            "definition_id",
        ),
        "organization-entity-search": ("organization_entity_id",),
        "organization-entity-relationship-list-create": ("organization_entity_id", "entity_id"),
        "organization-entity-relationship-detail": ("organization_entity_id", "entity_id", "link_id"),
        "organization-recycle-bin": ("organization_entity_id",),
    }
    if route_name in {"msp-recycle-bin-restore", "organization-recycle-bin-restore"}:
        kwargs = {"record_type": "site", "record_id": value}
        if route_name.startswith("organization-"):
            kwargs["organization_entity_id"] = value
        return kwargs
    return {name: value for name in route_kwargs.get(route_name, ())}


def _request(client: Client, method: str, route_name: str):
    url = reverse(route_name, kwargs=_kwargs_for(route_name))
    return client.generic(method, url, data="{}", content_type="application/json")


def test_route_permission_inventory_covers_every_api_route_and_has_stable_unique_contracts():
    contracts = {contract.route_name: contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS}

    assert len(contracts) == len(AUTHENTICATED_ROUTE_PERMISSIONS)
    assert set(contracts) | PUBLIC_API_ROUTE_NAMES == _api_route_names()
    route_methods = _api_route_methods()
    for contract in contracts.values():
        assert contract.methods
        assert set(contract.methods) == route_methods[contract.route_name]
        assert len(contract.mutation_permissions) <= len(contract.methods)
        for permission in contract.mutation_permissions:
            assert PERMISSION_BY_KEY[permission].requires_mfa


@pytest.mark.django_db
@pytest.mark.parametrize("contract", AUTHENTICATED_ROUTE_PERMISSIONS, ids=lambda item: item.route_name)
def test_every_authenticated_route_denies_anonymous_and_non_member(contract, installation):  # type: ignore[no-untyped-def]
    anonymous = Client()
    outsider = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Outsider",
    )
    outsider_client = Client()
    outsider_client.force_login(outsider)
    method = contract.methods[0]

    assert _request(anonymous, method, contract.route_name).status_code == 403
    assert _request(outsider_client, method, contract.route_name).status_code in {403, 404}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS if contract.mutation_permissions),
    ids=lambda item: item.route_name,
)
def test_every_cataloged_mutation_denies_read_only_members(contract, installation):  # type: ignore[no-untyped-def]
    reader = User.objects.create_user(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Reader",
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    client = Client()
    client.force_login(reader)
    method = next(method for method in contract.methods if method != "GET")

    assert _request(client, method, contract.route_name).status_code in {403, 404}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(
        contract
        for contract in AUTHENTICATED_ROUTE_PERMISSIONS
        if any(_kwargs_for(contract.route_name).values())
    ),
    ids=lambda item: item.route_name,
)
def test_identifier_routes_reject_malformed_uuid_paths_without_entering_a_view(contract, installation):  # type: ignore[no-untyped-def]
    client = Client()
    client.force_login(installation.owner)
    url = reverse(contract.route_name, kwargs=_kwargs_for(contract.route_name))
    malformed = url.replace("00000000-0000-4000-8000-000000000001", "not-a-uuid")

    assert client.get(malformed).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(
        contract
        for contract in AUTHENTICATED_ROUTE_PERMISSIONS
        if any(method != "GET" for method in contract.methods)
    ),
    ids=lambda item: item.route_name,
)
def test_every_unsafe_route_rejects_a_session_without_csrf(contract, installation):  # type: ignore[no-untyped-def]
    client = Client(enforce_csrf_checks=True)
    client.force_login(installation.owner)
    method = next(method for method in contract.methods if method != "GET")

    assert _request(client, method, contract.route_name).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "contract",
    tuple(contract for contract in AUTHENTICATED_ROUTE_PERMISSIONS if contract.mutation_permissions),
    ids=lambda item: item.route_name,
)
def test_every_cataloged_privileged_mutation_requires_mfa(contract, installation):  # type: ignore[no-untyped-def]
    installation.owner.authenticator_set.all().delete()
    client = Client()
    client.force_login(installation.owner)
    method = next(method for method in contract.methods if method != "GET")

    assert _request(client, method, contract.route_name).status_code in {403, 404}
