import secrets
from uuid import UUID

import pytest
from django.test import Client
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import InstallationState


@pytest.fixture
def owner_client(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="API Contract MSP",
        owner_email="api-owner@example.com",
        owner_display_name="API Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    authenticated = Client()
    authenticated.force_login(installation.owner)
    return authenticated


@pytest.mark.django_db
def test_public_api_root_describes_versioned_conventions(client):
    response = client.get(reverse("api-root"))

    assert response.status_code == 200
    assert response.json() == {
        "name": "TekDocs API",
        "version": "0.7.9",
        "status": "pre-alpha",
        "api_version": "v1",
        "schema_url": "/api/v1/schema/",
        "documentation_url": "/api/v1/docs/",
        "conventions": {
            "pagination": {
                "offset": ["results", "page", "page_size", "count", "has_more"],
                "seek": ["results", "has_more", "next_cursor"],
                "maximum_page_size": 100,
            },
            "filtering": "Only documented query parameters are accepted; unknown filters return 400.",
            "errors": ["status", "code", "message", "fields", "request_id"],
            "idempotency": (
                "Keys are bounded and echoed for correlation; retry semantics apply only to operations that declare "
                "Idempotency-Key in OpenAPI."
            ),
        },
    }


@pytest.mark.django_db
def test_unknown_filter_uses_stable_error_contract(owner_client):
    response = owner_client.get(reverse("msp-networks"), {"typo_filter": "all"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["status"] == 400
    assert error["code"] == "validation_error"
    assert error["message"] == "The request is invalid."
    assert error["fields"] == {"typo_filter": ["Unknown query parameter."]}
    assert UUID(error["request_id"])
    assert response.headers["X-Request-ID"] == error["request_id"]


@pytest.mark.django_db
def test_idempotency_key_is_bounded_and_correlated(client):
    invalid = client.get(reverse("api-root"), headers={"Idempotency-Key": "bad key"})
    valid = client.get(reverse("api-root"), headers={"Idempotency-Key": "retry:api-root:0001"})

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_idempotency_key"
    assert invalid.json()["error"]["fields"]["Idempotency-Key"]
    assert invalid.headers["X-Request-ID"] == invalid.json()["error"]["request_id"]
    assert valid.status_code == 200
    assert valid.headers["Idempotency-Key"] == "retry:api-root:0001"


@pytest.mark.django_db
def test_openapi_exposes_error_request_id_and_declared_idempotency_contract():
    schema = SchemaGenerator().get_schema(request=None, public=True)

    assert "ApiErrorEnvelope" in schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/access-control/organizations/{organization_entity_id}/staff"]["post"]
    assert any(parameter["name"] == "Idempotency-Key" for parameter in operation["parameters"])
    for response in operation["responses"].values():
        assert response["headers"]["X-Request-ID"]["schema"]["format"] == "uuid"
    assert operation["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorEnvelope"
    }


@pytest.mark.django_db
def test_openapi_operation_ids_are_unique_and_use_stable_list_detail_names():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]

    assert len(operation_ids) == len(set(operation_ids))
    assert "workspaces_msp_assets_retrieve_list" in operation_ids
    assert "workspaces_msp_assets_retrieve_detail" in operation_ids
    assert "workspaces_organizations_networks_vlans_retrieve_list" in operation_ids
    assert "workspaces_organizations_networks_vlans_retrieve_detail" in operation_ids
