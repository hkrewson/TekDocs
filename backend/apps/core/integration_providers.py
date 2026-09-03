from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from .integration_egress import get_provider_json
from .models import IntegrationConnection, IntegrationProvider, NetBoxObjectType


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    remote_type: str
    remote_id: str
    fingerprint: str
    safe_projection: dict[str, object] = field(default_factory=dict)
    source_timestamp: str | None = None
    provenance: str = "provider_api"
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class ProviderPage:
    observations: tuple[ProviderObservation, ...]
    next_cursor: str


@dataclass(frozen=True, slots=True)
class CredentialField:
    key: str
    label: str
    secret: bool = True
    minimum_length: int = 8


@dataclass(frozen=True, slots=True)
class ProviderContract:
    key: str
    label: str
    version: str
    direction: str
    credential_fields: tuple[CredentialField, ...]
    capabilities: tuple[str, ...]
    object_types: tuple[str, ...]
    pagination: str
    minimum_sync_interval_minutes: int
    maximum_sync_interval_minutes: int
    health_states: tuple[str, ...] = ("unknown", "healthy", "degraded", "failing", "paused")
    observation_schema_version: int = 1


class ProviderAdapter(Protocol):
    key: str
    label: str
    contract: ProviderContract

    def fetch_page(self, connection: IntegrationConnection, *, secret: str, cursor: str) -> ProviderPage: ...


NETBOX_ENDPOINTS = (
    (NetBoxObjectType.RACK, "dcim/racks/"),
    (NetBoxObjectType.DEVICE, "dcim/devices/"),
    (NetBoxObjectType.MAC_ADDRESS, "dcim/mac-addresses/"),
    (NetBoxObjectType.VLAN, "ipam/vlans/"),
    (NetBoxObjectType.PREFIX, "ipam/prefixes/"),
    (NetBoxObjectType.IP_ADDRESS, "ipam/ip-addresses/"),
)


def _fingerprint(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(serialized).hexdigest()


class NetBoxProvider:
    key: str = str(IntegrationProvider.NETBOX)
    label = "NetBox"
    contract = ProviderContract(
        key=key,
        label=label,
        version="1.0",
        direction="read_only",
        credential_fields=(CredentialField("api_token", "API token"),),
        capabilities=("inventory_observations", "reconciliation"),
        object_types=tuple(str(item[0]) for item in NETBOX_ENDPOINTS),
        pagination="opaque_cursor",
        minimum_sync_interval_minutes=5,
        maximum_sync_interval_minutes=10080,
    )

    def __init__(self, fetcher: Callable[..., dict[str, object]] = get_provider_json):
        self._fetcher = fetcher

    def fetch_page(self, connection: IntegrationConnection, *, secret: str, cursor: str) -> ProviderPage:
        index_text, _, path = cursor.partition("|")
        index = int(index_text) if index_text else 0
        if index < 0 or index >= len(NETBOX_ENDPOINTS):
            raise ValueError("provider_cursor_invalid")
        remote_type, default_path = NETBOX_ENDPOINTS[index]
        payload = self._fetcher(
            base_url=connection.base_url,
            relative_path=path or default_path,
            authorization=f"Token {secret}",
        )
        results = payload.get("results")
        if not isinstance(results, list) or len(results) > 1000:
            raise ValueError("provider_response_invalid")
        observations: list[ProviderObservation] = []
        for record in results:
            if not isinstance(record, dict) or not isinstance(record.get("id"), int):
                raise ValueError("provider_response_invalid")
            # The digest covers the provider record, but only the digest and identity leave this boundary.
            projection = {
                key: record[key]
                for key in ("id", "name", "display", "url")
                if key in record and isinstance(record[key], str | int | float | bool | type(None))
            }
            observations.append(
                ProviderObservation(str(remote_type), str(record["id"]), _fingerprint(record), projection)
            )
        next_value = payload.get("next")
        if next_value is not None and not isinstance(next_value, str):
            raise ValueError("provider_response_invalid")
        if next_value:
            next_path = url_path(next_value, base_url=connection.base_url)
            next_cursor = f"{index}|{next_path}"
        elif index + 1 < len(NETBOX_ENDPOINTS):
            next_cursor = f"{index + 1}|{NETBOX_ENDPOINTS[index + 1][1]}"
        else:
            next_cursor = ""
        return ProviderPage(tuple(observations), next_cursor)


def url_path(value: str, *, base_url: str) -> str:
    parsed = urlsplit(value)
    base = urlsplit(base_url)
    if parsed.fragment or parsed.username or parsed.password:
        raise ValueError("provider_cursor_invalid")
    if parsed.netloc and (
        parsed.scheme != "https" or parsed.hostname != base.hostname or parsed.port not in (None, 443)
    ):
        raise ValueError("provider_cursor_invalid")
    path = parsed.path
    if not path.startswith("/"):
        raise ValueError("provider_cursor_invalid")
    return f"{path}?{parsed.query}" if parsed.query else path


PROVIDERS: dict[str, ProviderAdapter] = {str(IntegrationProvider.NETBOX): NetBoxProvider()}


def validate_provider_adapter(adapter: ProviderAdapter) -> None:
    contract = adapter.contract
    if adapter.key != contract.key or adapter.label != contract.label:
        raise ValueError("provider_contract_identity_invalid")
    if contract.direction != "read_only" or not contract.version or not contract.object_types:
        raise ValueError("provider_contract_invalid")
    if contract.pagination != "opaque_cursor":
        raise ValueError("provider_contract_pagination_invalid")
    if not 5 <= contract.minimum_sync_interval_minutes <= contract.maximum_sync_interval_minutes <= 10080:
        raise ValueError("provider_contract_schedule_invalid")
    if contract.observation_schema_version < 1 or not contract.credential_fields:
        raise ValueError("provider_contract_schema_invalid")


def validate_provider_page(adapter: ProviderAdapter, page: ProviderPage) -> None:
    """Enforce the same bounded observation contract for every provider adapter."""

    if not isinstance(page.next_cursor, str) or len(page.next_cursor) > 500:
        raise ValueError("provider_cursor_invalid")
    if len(page.observations) > 1000:
        raise ValueError("provider_response_invalid")
    identities: dict[tuple[str, str], str] = {}
    for observation in page.observations:
        identity = (observation.remote_type, observation.remote_id)
        if (
            observation.remote_type not in adapter.contract.object_types
            or not observation.remote_id
            or len(observation.remote_id) > 160
            or (identity in identities and identities[identity] != observation.fingerprint)
            or len(observation.fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in observation.fingerprint)
            or observation.schema_version != adapter.contract.observation_schema_version
            or not isinstance(observation.safe_projection, dict)
            or any(
                not isinstance(value, str | int | float | bool | type(None))
                for value in observation.safe_projection.values()
            )
        ):
            raise ValueError("provider_response_invalid")
        identities[identity] = observation.fingerprint


for registered_provider in PROVIDERS.values():
    validate_provider_adapter(registered_provider)


def provider_catalog() -> list[dict[str, object]]:
    return [json.loads(json.dumps(asdict(adapter.contract))) for adapter in PROVIDERS.values()]
