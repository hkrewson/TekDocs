from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from .integration_egress import get_provider_json
from .models import IntegrationConnection, IntegrationProvider, NetBoxObjectType


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    remote_type: str
    remote_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ProviderPage:
    observations: tuple[ProviderObservation, ...]
    next_cursor: str


class ProviderAdapter(Protocol):
    key: str
    label: str

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
            observations.append(ProviderObservation(str(remote_type), str(record["id"]), _fingerprint(record)))
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
        parsed.scheme != "https"
        or parsed.hostname != base.hostname
        or parsed.port not in (None, 443)
    ):
        raise ValueError("provider_cursor_invalid")
    path = parsed.path
    if not path.startswith("/"):
        raise ValueError("provider_cursor_invalid")
    return f"{path}?{parsed.query}" if parsed.query else path


PROVIDERS: dict[str, ProviderAdapter] = {str(IntegrationProvider.NETBOX): NetBoxProvider()}


def provider_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": adapter.key,
            "label": adapter.label,
            "direction": "read_only",
            "credential_fields": ["api_token"],
            "capabilities": ["inventory_observations", "reconciliation"],
        }
        for adapter in PROVIDERS.values()
    ]
