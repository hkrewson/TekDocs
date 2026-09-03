import secrets
from types import SimpleNamespace

import pytest

from apps.core.integration_providers import NinjaOneProvider, _ninja_encode_cursor, validate_provider_page


def connection():
    return SimpleNamespace(
        base_url="https://app.ninjarmm.com/",
        configuration={"client_id": "ninjaone-client-id"},
    )


def token(**_kwargs):
    return {"access_token": secrets.token_urlsafe(24), "token_type": "Bearer", "scope": "monitoring"}


def test_ninjaone_uses_monitoring_client_credentials_and_minimizes_device_fields():
    requests = []
    provider_secret = secrets.token_urlsafe(24)
    access_token = secrets.token_urlsafe(24)

    def post(**kwargs):
        requests.append(kwargs)
        return {"access_token": access_token, "token_type": "Bearer", "scope": "monitoring"}

    def get(**kwargs):
        requests.append(kwargs)
        return {
            "results": [
                {
                    "deviceId": 42,
                    "name": "WS-42",
                    "manufacturer": "Framework",
                    "model": "Laptop 13",
                    "serialNumber": "SAFE-SERIAL-42",
                    "domain": "excluded.internal",
                    "totalPhysicalMemory": 1234,
                    "secretCustomField": "never retain",
                    "timestamp": 1_788_447_600_000,
                }
            ],
            "cursor": {"name": "hardware-page", "offset": 0, "count": 1, "expires": 1_788_451_200_000},
        }

    page = NinjaOneProvider(getter=get, poster=post).fetch_page(
        connection(), secret=provider_secret, cursor=_ninja_encode_cursor(3)
    )
    validate_provider_page(NinjaOneProvider(), page)

    assert requests[0]["relative_path"] == "ws/oauth/token"
    assert requests[0]["fields"] == {"grant_type": "client_credentials", "scope": "monitoring"}
    assert requests[0]["username"] == "ninjaone-client-id"
    assert requests[0]["password"] == provider_secret
    assert requests[1]["authorization"] == f"Bearer {access_token}"
    assert page.observations[0].safe_projection == {
        "deviceId": 42,
        "name": "WS-42",
        "manufacturer": "Framework",
        "model": "Laptop 13",
        "serialNumber": "SAFE-SERIAL-42",
    }
    assert "never retain" not in str(page.observations[0].safe_projection)


def test_ninjaone_list_and_query_pagination_are_opaque_and_bounded():
    organizations = [{"id": number, "name": f"Client {number}"} for number in range(1, 101)]
    list_page = NinjaOneProvider(
        getter=lambda **_kwargs: {"items": organizations},
        poster=token,
    ).fetch_page(connection(), secret="secret-value", cursor="")

    assert len(list_page.observations) == 100
    assert list_page.next_cursor == _ninja_encode_cursor(0, "100")

    query_page = NinjaOneProvider(
        getter=lambda **_kwargs: {
            "results": [{"deviceId": 1, "name": "Example", "publisher": "Publisher"}],
            "cursor": {"name": "next-query-page", "offset": 0, "count": 2, "expires": 123},
        },
        poster=token,
    ).fetch_page(connection(), secret="secret-value", cursor=_ninja_encode_cursor(6))

    assert query_page.next_cursor == _ninja_encode_cursor(6, "next-query-page")
    assert query_page.observations[0].remote_id.startswith("1:")


def test_ninjaone_software_projection_excludes_paths_sizes_codes_and_system_flags():
    page = NinjaOneProvider(
        getter=lambda **_kwargs: {
            "results": [
                {
                    "deviceId": 7,
                    "name": "Example Agent",
                    "version": "4.2",
                    "publisher": "Example Publisher",
                    "installDate": "2026-08-01T00:00:00Z",
                    "location": "C:\\Private\\Path",
                    "size": 999,
                    "productCode": "stable-product-code",
                    "isSystemComponent": False,
                }
            ],
            "cursor": {"name": "done", "offset": 0, "count": 1, "expires": 123},
        },
        poster=token,
    ).fetch_page(connection(), secret="secret-value", cursor=_ninja_encode_cursor(6))

    assert page.observations[0].remote_id.startswith("7:")
    assert "stable-product-code" not in page.observations[0].remote_id
    assert page.observations[0].safe_projection == {
        "deviceId": 7,
        "name": "Example Agent",
        "version": "4.2",
        "publisher": "Example Publisher",
        "installDate": "2026-08-01T00:00:00Z",
    }


def test_ninjaone_excluded_fields_do_not_affect_the_retained_fingerprint():
    def fetch(secret_value):
        return NinjaOneProvider(
            getter=lambda **_kwargs: {
                "results": [
                    {
                        "deviceId": 7,
                        "name": "Example Agent",
                        "version": "4.2",
                        "publisher": "Example Publisher",
                        "installDate": "2026-08-01T00:00:00Z",
                        "location": secret_value,
                        "productCode": secret_value,
                    }
                ],
                "cursor": {"name": "done", "offset": 0, "count": 1},
            },
            poster=token,
        ).fetch_page(connection(), secret=secrets.token_urlsafe(24), cursor=_ninja_encode_cursor(6))

    first = fetch("excluded-one")
    second = fetch("excluded-two")
    assert first.observations[0].remote_id == second.observations[0].remote_id
    assert first.observations[0].fingerprint == second.observations[0].fingerprint


@pytest.mark.parametrize(
    "payload",
    [
        {"results": "not-a-list"},
        {"results": [{"name": "missing device identity"}]},
        {"results": [], "cursor": "not-an-object"},
        {"results": [], "cursor": {"name": "x", "offset": "zero", "count": 1}},
    ],
)
def test_ninjaone_rejects_malformed_query_responses(payload):
    provider = NinjaOneProvider(getter=lambda **_kwargs: payload, poster=token)
    with pytest.raises(ValueError, match="provider_response_invalid"):
        provider.fetch_page(connection(), secret="secret-value", cursor=_ninja_encode_cursor(3))


def test_ninjaone_rejects_a_broader_returned_scope():
    provider = NinjaOneProvider(
        getter=lambda **_kwargs: {"items": []},
        poster=lambda **_kwargs: {"access_token": secrets.token_urlsafe(24), "scope": "monitoring management"},
    )
    with pytest.raises(ValueError, match="provider_permissions_excessive"):
        provider.fetch_page(connection(), secret="secret-value", cursor="")
