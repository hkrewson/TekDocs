import base64
import json
from types import SimpleNamespace

import pytest

from apps.core.integration_providers import (
    GRAPH_REQUIRED_ROLES,
    MicrosoftGraphProvider,
    _cursor,
    _encode_cursor,
    validate_provider_page,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"


def token(*, roles=None, tenant_id=TENANT_ID, audience="https://graph.microsoft.com"):
    claims = {
        "tid": tenant_id,
        "aud": audience,
        "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "azp": CLIENT_ID,
        "roles": sorted(roles or GRAPH_REQUIRED_ROLES),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def connection(**configuration):
    return SimpleNamespace(
        base_url="https://graph.microsoft.com/v1.0/",
        configuration={"tenant_id": TENANT_ID, "client_id": CLIENT_ID, **configuration},
    )


def test_graph_provider_validates_tenant_permissions_and_projects_only_safe_fields():
    requests = []

    def post(**kwargs):
        requests.append(kwargs)
        return {"access_token": token()}

    def get(**kwargs):
        requests.append(kwargs)
        return {
            "value": [
                {
                    "id": TENANT_ID,
                    "displayName": "Example tenant",
                    "verifiedDomains": [
                        {"name": "example.invalid", "isDefault": True, "isInitial": False, "type": "Managed"}
                    ],
                    "unsafeProviderValue": "must not leave boundary",
                }
            ]
        }

    provider = MicrosoftGraphProvider(getter=get, poster=post)
    page = provider.fetch_page(connection(), secret="client-secret-value", cursor="")
    validate_provider_page(provider, page)

    assert [item.remote_type for item in page.observations] == ["tenant", "domain"]
    assert page.observations[0].safe_projection == {"id": TENANT_ID, "displayName": "Example tenant"}
    assert "unsafeProviderValue" not in json.dumps(page.observations[0].safe_projection)
    assert page.configuration_updates["validated_tenant_id"] == TENANT_ID
    assert len(page.configuration_updates["scope_fingerprint"]) == 64
    assert requests[0]["fields"]["scope"] == "https://graph.microsoft.com/.default"
    assert requests[1]["authorization"].startswith("Bearer ")


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (GRAPH_REQUIRED_ROLES - {"User.Read.All"}, "provider_permissions_missing"),
        (GRAPH_REQUIRED_ROLES | {"Mail.Read"}, "provider_permissions_excessive"),
        (GRAPH_REQUIRED_ROLES | {"User.ReadWrite.All"}, "provider_permissions_excessive"),
        (GRAPH_REQUIRED_ROLES | {"ChannelMessage.Read.All"}, "provider_permissions_excessive"),
    ],
)
def test_graph_provider_rejects_missing_or_excessive_permissions(roles, expected):
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: {"value": []},
        poster=lambda **_kwargs: {"access_token": token(roles=roles)},
    )
    with pytest.raises(ValueError, match=expected):
        provider.fetch_page(connection(), secret="client-secret-value", cursor="")


def test_graph_provider_rejects_permission_drift_before_requesting_data():
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: pytest.fail("Graph data must not be requested after permission drift"),
        poster=lambda **_kwargs: {"access_token": token()},
    )
    with pytest.raises(ValueError, match="provider_permission_drift"):
        provider.fetch_page(connection(scope_fingerprint="0" * 64), secret="client-secret-value", cursor="")


def test_graph_user_delta_emits_explicit_retirement_and_preserves_delta_cursor():
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: {
            "value": [{"id": "user-1", "@removed": {"reason": "deleted"}}],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/delta?$deltatoken=opaque",
        },
        poster=lambda **_kwargs: {"access_token": token()},
    )
    page = provider.fetch_page(
        connection(),
        secret="client-secret-value",
        cursor=_encode_cursor({"stage": "users", "path": "users/delta?$deltatoken=prior", "incremental": True}),
    )
    assert page.observations[0].state == "retired"
    assert page.complete_types == ()
    assert page.configuration_updates["users_delta_link"] == "users/delta?$deltatoken=opaque"
    assert page.next_cursor


def test_graph_user_delta_projects_individual_license_assignments():
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: {
            "value": [
                {
                    "id": "user-1",
                    "displayName": "Example User",
                    "assignedLicenses": [{"skuId": "sku-1", "disabledPlans": ["sensitive-plan-detail"]}],
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/delta?$deltatoken=next",
        },
        poster=lambda **_kwargs: {"access_token": token()},
    )
    page = provider.fetch_page(
        connection(),
        secret="client-secret-value",
        cursor=_encode_cursor({"stage": "users", "path": "users/delta", "incremental": True}),
    )
    assignment = next(item for item in page.observations if item.remote_type == "user_license_assignment")
    assert assignment.remote_id == "user-1:sku-1"
    assert assignment.safe_projection == {"userId": "user-1", "skuId": "sku-1"}
    assert "disabledPlans" not in json.dumps(assignment.safe_projection)
    assert page.complete_id_prefixes == (("user_license_assignment", "user-1:"),)


def test_graph_group_pages_resume_through_direct_memberships():
    responses = iter(
        [
            {"value": [{"id": "group-1", "displayName": "Support"}]},
            {"value": [{"id": "user-1"}]},
        ]
    )
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: next(responses),
        poster=lambda **_kwargs: {"access_token": token()},
    )
    group_page = provider.fetch_page(
        connection(),
        secret="client-secret-value",
        cursor=_encode_cursor({"stage": "groups", "path": "groups"}),
    )
    assert _cursor(group_page.next_cursor)["stage"] == "members"
    member_page = provider.fetch_page(connection(), secret="client-secret-value", cursor=group_page.next_cursor)
    membership = member_page.observations[0]
    assert membership.remote_type == "group_membership"
    assert membership.safe_projection == {"groupId": "group-1", "memberId": "user-1"}
    assert member_page.complete_types == ("group", "group_membership")


def test_graph_managed_devices_include_only_the_documented_safe_inventory_fields():
    provider = MicrosoftGraphProvider(
        getter=lambda **_kwargs: {
            "value": [
                {
                    "id": "device-1",
                    "deviceName": "LAPTOP-1",
                    "operatingSystem": "Windows",
                    "osVersion": "11.0",
                    "complianceState": "compliant",
                    "managedDeviceOwnerType": "company",
                    "lastSyncDateTime": "2026-09-02T00:00:00Z",
                    "manufacturer": "Example",
                    "model": "Model 1",
                    "serialNumber": "SERIAL-1",
                    "userPrincipalName": "not-retained@example.invalid",
                    "recoveryKey": "never-retained",
                }
            ]
        },
        poster=lambda **_kwargs: {"access_token": token()},
    )
    page = provider.fetch_page(
        connection(),
        secret="client-secret-value",
        cursor=_encode_cursor({"stage": "devices", "path": "deviceManagement/managedDevices"}),
    )

    assert page.observations[0].safe_projection == {
        "id": "device-1",
        "deviceName": "LAPTOP-1",
        "operatingSystem": "Windows",
        "osVersion": "11.0",
        "complianceState": "compliant",
        "managedDeviceOwnerType": "company",
        "lastSyncDateTime": "2026-09-02T00:00:00Z",
        "manufacturer": "Example",
        "model": "Model 1",
        "serialNumber": "SERIAL-1",
    }
    assert page.complete_types == ("managed_device",)
