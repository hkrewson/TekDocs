import json
from types import SimpleNamespace

import pytest

from apps.core.integration_providers import HaloPSAProvider, _halo_encode_cursor, validate_provider_page


def connection():
    return SimpleNamespace(
        base_url="https://support.example.invalid/",
        configuration={"client_id": "halopsa-client-id"},
    )


def test_halopsa_authenticates_with_client_credentials_and_minimizes_ticket_projection():
    requests = []

    def post(**kwargs):
        requests.append(kwargs)
        return {"access_token": "safe-access-token-value", "token_type": "Bearer"}

    def get(**kwargs):
        requests.append(kwargs)
        return {
            "tickets": [
                {
                    "id": 1042,
                    "summary": "Printer queue unavailable",
                    "client_id": 24,
                    "statusname": "In progress",
                    "priority": "High",
                    "team": "Service desk",
                    "agent_name": "Taylor",
                    "fixbydate": "2026-09-03T18:00:00Z",
                    "lastactiondate": "2026-09-03T15:00:00Z",
                    "details": "ticket body must not be retained",
                    "private_notes": [{"note": "never retain"}],
                    "attachments": [{"name": "never-retain.txt"}],
                    "customfields": [{"name": "password", "value": "never retain"}],
                }
            ],
            "record_count": 1,
        }

    provider = HaloPSAProvider(getter=get, poster=post)
    page = provider.fetch_page(
        connection(), secret="halopsa-client-secret", cursor=_halo_encode_cursor(4, 1)
    )
    validate_provider_page(provider, page)

    assert requests[0] == {
        "base_url": "https://support.example.invalid/",
        "relative_path": "auth/token",
        "fields": {"grant_type": "client_credentials", "scope": "all"},
        "username": "halopsa-client-id",
        "password": "halopsa-client-secret",
    }
    assert "page_no=1&page_size=100" in requests[1]["relative_path"]
    assert requests[1]["authorization"] == "Bearer safe-access-token-value"
    observation = page.observations[0]
    assert observation.remote_type == "ticket"
    assert observation.remote_id == "1042"
    assert observation.source_timestamp == "2026-09-03T15:00:00Z"
    assert observation.safe_projection == {
        "id": 1042,
        "summary": "Printer queue unavailable",
        "client_id": 24,
        "statusname": "In progress",
        "priority": "High",
        "team": "Service desk",
        "agent_name": "Taylor",
        "fixbydate": "2026-09-03T18:00:00Z",
        "lastactiondate": "2026-09-03T15:00:00Z",
        "external_url": "https://support.example.invalid/tickets?id=1042",
    }
    assert not {"details", "private_notes", "attachments", "customfields"} & set(observation.safe_projection)
    assert "never retain" not in json.dumps(observation.safe_projection)
    assert page.next_cursor == ""
    assert page.complete_types == ("ticket",)


def test_halopsa_pagination_is_opaque_and_advances_between_collections():
    full_page = [{"id": number, "name": f"Client {number}"} for number in range(100)]
    provider = HaloPSAProvider(
        getter=lambda **_kwargs: {"clients": full_page, "record_count": 101},
        poster=lambda **_kwargs: {"access_token": "safe-access-token-value"},
    )
    first = provider.fetch_page(connection(), secret="client-secret", cursor="")
    assert first.next_cursor == _halo_encode_cursor(0, 2)
    assert first.complete_types == ()

    provider = HaloPSAProvider(
        getter=lambda **_kwargs: {"clients": [{"id": 101, "name": "Last client"}], "record_count": 101},
        poster=lambda **_kwargs: {"access_token": "safe-access-token-value"},
    )
    last = provider.fetch_page(connection(), secret="client-secret", cursor=_halo_encode_cursor(0, 2))
    assert last.next_cursor == _halo_encode_cursor(1, 1)
    assert last.complete_types == ("client",)


def test_halopsa_retains_open_and_recently_closed_tickets_only():
    provider = HaloPSAProvider(
        getter=lambda **_kwargs: {
            "tickets": [
                {"id": 1, "summary": "Open ticket", "dateclosed": None},
                {"id": 2, "summary": "Recent ticket", "dateclosed": "2026-08-15T12:00:00Z"},
                {"id": 3, "summary": "Old ticket", "dateclosed": "2025-01-01T12:00:00Z"},
            ],
            "record_count": 3,
        },
        poster=lambda **_kwargs: {"access_token": "safe-access-token-value"},
    )

    page = provider.fetch_page(connection(), secret="client-secret", cursor=_halo_encode_cursor(4, 1))

    assert [item.remote_id for item in page.observations] == ["1", "2"]


@pytest.mark.parametrize(
    "payload",
    [
        {"tickets": "not-a-list"},
        {"tickets": [{"summary": "missing identity"}]},
        {"tickets": [], "record_count": "many"},
    ],
)
def test_halopsa_rejects_malformed_responses(payload):
    provider = HaloPSAProvider(
        getter=lambda **_kwargs: payload,
        poster=lambda **_kwargs: {"access_token": "safe-access-token-value"},
    )
    with pytest.raises(ValueError, match="provider_response_invalid"):
        provider.fetch_page(connection(), secret="client-secret", cursor=_halo_encode_cursor(4, 1))
