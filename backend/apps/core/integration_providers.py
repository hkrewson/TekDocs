from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from .integration_egress import get_provider_json, post_provider_form, post_provider_form_basic
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
    state: str = "observed"


@dataclass(frozen=True, slots=True)
class ProviderPage:
    observations: tuple[ProviderObservation, ...]
    next_cursor: str
    complete_types: tuple[str, ...] = ()
    complete_id_prefixes: tuple[tuple[str, str], ...] = ()
    configuration_updates: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CredentialField:
    key: str
    label: str
    secret: bool = True
    minimum_length: int = 8
    input_type: str = "password"
    help_text: str = ""


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
    default_base_url: str = ""
    base_url_editable: bool = True
    setup_help_url: str = ""


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
        default_base_url="",
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
        complete = (str(remote_type),) if not next_value else ()
        return ProviderPage(tuple(observations), next_cursor, complete)


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0/"
GRAPH_LOGIN_URL = "https://login.microsoftonline.com/"
GRAPH_AUDIENCES = {"https://graph.microsoft.com", "00000003-0000-0000-c000-000000000000"}
GRAPH_REQUIRED_ROLES = frozenset(
    {
        "Organization.Read.All",
        "User.Read.All",
        "GroupMember.Read.All",
        "LicenseAssignment.Read.All",
        "DeviceManagementManagedDevices.Read.All",
    }
)
GRAPH_FORBIDDEN_ROLE_MARKERS = (
    "mail.",
    "mailbox",
    "files.",
    "sites.",
    "chat.",
    "channelmessage",
    "authenticationmethod",
    "bitlocker",
    "password",
    "readwrite",
)
GRAPH_OBJECT_TYPES = (
    "tenant",
    "domain",
    "user",
    "user_license_assignment",
    "group",
    "group_membership",
    "subscribed_sku",
    "managed_device",
)


def _decode_access_token_claims(token: str) -> dict[str, object]:
    try:
        part = token.split(".")[1]
        payload = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        claims = json.loads(payload)
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("provider_token_invalid") from exc
    if not isinstance(claims, dict):
        raise ValueError("provider_token_invalid")
    return claims


def _cursor(value: str) -> dict[str, object]:
    if not value:
        return {"stage": "tenant", "path": "organization?$select=id,displayName,verifiedDomains"}
    try:
        decoded = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("provider_cursor_invalid") from exc
    if (
        not isinstance(decoded, dict)
        or not isinstance(decoded.get("stage"), str)
        or not isinstance(decoded.get("path"), str)
    ):
        raise ValueError("provider_cursor_invalid")
    return decoded


def _encode_cursor(value: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def _graph_path(value: str) -> str:
    return url_path(value, base_url=GRAPH_BASE_URL).lstrip("/").removeprefix("v1.0/")


def _scalar_projection(record: dict[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {
        key: record[key]
        for key in keys
        if key in record and isinstance(record[key], str | int | float | bool | type(None))
    }


class MicrosoftGraphProvider:
    key = str(IntegrationProvider.MICROSOFT_GRAPH)
    label = "Microsoft 365"
    contract = ProviderContract(
        key=key,
        label=label,
        version="1.0",
        direction="read_only",
        credential_fields=(
            CredentialField(
                "tenant_id", "Microsoft tenant ID", False, 36, "text", "The directory (tenant) ID from Microsoft Entra."
            ),
            CredentialField(
                "client_id", "Application (client) ID", False, 36, "text", "The app registration's application ID."
            ),
            CredentialField(
                "client_secret", "Client secret", True, 8, "password", "Stored encrypted and never shown again."
            ),
        ),
        capabilities=("identity_observations", "license_observations", "managed_device_observations", "reconciliation"),
        object_types=GRAPH_OBJECT_TYPES,
        pagination="opaque_cursor",
        minimum_sync_interval_minutes=15,
        maximum_sync_interval_minutes=10080,
        default_base_url=GRAPH_BASE_URL,
        base_url_editable=False,
        setup_help_url="https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app",
    )

    def __init__(
        self,
        getter: Callable[..., dict[str, object]] = get_provider_json,
        poster: Callable[..., dict[str, object]] = post_provider_form,
    ):
        self._getter = getter
        self._poster = poster

    def _authorize(self, connection: IntegrationConnection, secret: str) -> tuple[str, dict[str, object]]:
        tenant_id = str(connection.configuration.get("tenant_id", ""))
        client_id = str(connection.configuration.get("client_id", ""))
        token_payload = self._poster(
            base_url=GRAPH_LOGIN_URL,
            relative_path=f"{tenant_id}/oauth2/v2.0/token",
            fields={
                "client_id": client_id,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        token = token_payload.get("access_token")
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError("provider_token_invalid")
        claims = _decode_access_token_claims(token)
        roles = claims.get("roles")
        issuer = claims.get("iss")
        application_id = claims.get("azp") or claims.get("appid")
        allowed_issuers = {
            f"https://sts.windows.net/{tenant_id}/",
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        }
        if (
            claims.get("tid") != tenant_id
            or claims.get("aud") not in GRAPH_AUDIENCES
            or issuer not in allowed_issuers
            or application_id != client_id
            or not isinstance(roles, list)
            or any(not isinstance(item, str) for item in roles)
        ):
            raise ValueError("provider_token_invalid")
        role_set = set(roles)
        if GRAPH_REQUIRED_ROLES - role_set:
            raise ValueError("provider_permissions_missing")
        if any(marker in role.casefold() for role in role_set for marker in GRAPH_FORBIDDEN_ROLE_MARKERS):
            raise ValueError("provider_permissions_excessive")
        fingerprint = _fingerprint(sorted(role_set))
        existing = connection.configuration.get("scope_fingerprint")
        if existing and existing != fingerprint:
            raise ValueError("provider_permission_drift")
        return token, {"scope_fingerprint": fingerprint, "validated_tenant_id": tenant_id}

    def fetch_page(self, connection: IntegrationConnection, *, secret: str, cursor: str) -> ProviderPage:
        token, configuration_updates = self._authorize(connection, secret)
        state = _cursor(cursor)
        stage, path = str(state["stage"]), str(state["path"])
        payload = self._getter(base_url=GRAPH_BASE_URL, relative_path=path, authorization=f"Bearer {token}")
        values = payload.get("value")
        if not isinstance(values, list) or len(values) > 1000:
            raise ValueError("provider_response_invalid")
        observations: list[ProviderObservation] = []
        complete: tuple[str, ...] = ()
        complete_prefixes: list[tuple[str, str]] = []
        next_value = payload.get("@odata.nextLink")
        next_path = _graph_path(next_value) if isinstance(next_value, str) else ""
        if next_value is not None and not isinstance(next_value, str):
            raise ValueError("provider_response_invalid")

        if stage == "tenant":
            if len(values) != 1 or not isinstance(values[0], dict) or not isinstance(values[0].get("id"), str):
                raise ValueError("provider_tenant_validation_failed")
            record = values[0]
            if record["id"] != connection.configuration.get("tenant_id"):
                raise ValueError("provider_tenant_validation_failed")
            observations.append(
                ProviderObservation(
                    "tenant", record["id"], _fingerprint(record), _scalar_projection(record, ("id", "displayName"))
                )
            )
            domains = record.get("verifiedDomains", [])
            if not isinstance(domains, list):
                raise ValueError("provider_response_invalid")
            for domain in domains:
                if isinstance(domain, dict) and isinstance(domain.get("name"), str):
                    projection = _scalar_projection(domain, ("name", "isDefault", "isInitial", "type"))
                    observations.append(ProviderObservation("domain", domain["name"], _fingerprint(domain), projection))
            complete = ("tenant", "domain")
            next_cursor = _encode_cursor(
                {
                    "stage": "users",
                    "path": str(
                        connection.configuration.get("users_delta_link")
                        or (
                            "users/delta?$select=id,displayName,userPrincipalName,accountEnabled,"
                            "createdDateTime,assignedLicenses"
                        )
                    ),
                    "incremental": bool(connection.configuration.get("users_delta_link")),
                }
            )
        elif stage == "users":
            incremental = bool(state.get("incremental"))
            for record in values:
                if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                    raise ValueError("provider_response_invalid")
                retired = "@removed" in record
                projection = _scalar_projection(
                    record, ("id", "displayName", "userPrincipalName", "accountEnabled", "createdDateTime")
                )
                assigned = record.get("assignedLicenses")
                complete_prefixes.append(("user_license_assignment", f"{record['id']}:"))
                if isinstance(assigned, list):
                    projection["assignedLicenseCount"] = len(assigned)
                    for license_record in assigned:
                        if not isinstance(license_record, dict) or not isinstance(license_record.get("skuId"), str):
                            raise ValueError("provider_response_invalid")
                        license_projection = {"userId": record["id"], "skuId": license_record["skuId"]}
                        observations.append(
                            ProviderObservation(
                                "user_license_assignment",
                                f"{record['id']}:{license_record['skuId']}",
                                _fingerprint(license_projection),
                                license_projection,
                                state="retired" if retired else "observed",
                            )
                        )
                observations.append(
                    ProviderObservation(
                        "user",
                        record["id"],
                        _fingerprint(record),
                        projection,
                        state="retired" if retired else "observed",
                    )
                )
            delta = payload.get("@odata.deltaLink")
            if next_path:
                next_cursor = _encode_cursor({"stage": "users", "path": next_path, "incremental": incremental})
            elif isinstance(delta, str):
                configuration_updates["users_delta_link"] = _graph_path(delta)
                complete = () if incremental else ("user", "user_license_assignment")
                next_cursor = _encode_cursor(
                    {"stage": "groups", "path": "groups?$top=20&$select=id,displayName,securityEnabled,mailEnabled"}
                )
            else:
                raise ValueError("provider_response_invalid")
        elif stage == "groups":
            group_ids: list[str] = []
            for record in values:
                if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                    raise ValueError("provider_response_invalid")
                group_ids.append(record["id"])
                observations.append(
                    ProviderObservation(
                        "group",
                        record["id"],
                        _fingerprint(record),
                        _scalar_projection(record, ("id", "displayName", "securityEnabled", "mailEnabled")),
                    )
                )
            if group_ids:
                next_cursor = _encode_cursor(
                    {
                        "stage": "members",
                        "path": f"groups/{group_ids[0]}/members?$select=id",
                        "groups": group_ids,
                        "group_index": 0,
                        "groups_next": next_path,
                    }
                )
            elif next_path:
                next_cursor = _encode_cursor({"stage": "groups", "path": next_path})
            else:
                complete = ("group", "group_membership")
                next_cursor = _encode_cursor(
                    {
                        "stage": "skus",
                        "path": "subscribedSkus?$select=id,skuId,skuPartNumber,consumedUnits,prepaidUnits",
                    }
                )
        elif stage == "members":
            groups = state.get("groups")
            group_index = state.get("group_index")
            if (
                not isinstance(groups, list)
                or not all(isinstance(item, str) for item in groups)
                or not isinstance(group_index, int)
                or group_index >= len(groups)
            ):
                raise ValueError("provider_cursor_invalid")
            group_id = groups[group_index]
            for record in values:
                if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                    raise ValueError("provider_response_invalid")
                identity = f"{group_id}:{record['id']}"
                projection = {"groupId": group_id, "memberId": record["id"]}
                observations.append(
                    ProviderObservation("group_membership", identity, _fingerprint(projection), projection)
                )
            if next_path:
                next_cursor = _encode_cursor({**state, "path": next_path})
            elif group_index + 1 < len(groups):
                next_cursor = _encode_cursor(
                    {
                        **state,
                        "path": f"groups/{groups[group_index + 1]}/members?$select=id",
                        "group_index": group_index + 1,
                    }
                )
            elif state.get("groups_next"):
                next_cursor = _encode_cursor({"stage": "groups", "path": state["groups_next"]})
            else:
                complete = ("group", "group_membership")
                next_cursor = _encode_cursor(
                    {
                        "stage": "skus",
                        "path": "subscribedSkus?$select=id,skuId,skuPartNumber,consumedUnits,prepaidUnits",
                    }
                )
        elif stage in {"skus", "devices"}:
            remote_type = "subscribed_sku" if stage == "skus" else "managed_device"
            keys = (
                ("id", "skuId", "skuPartNumber", "consumedUnits")
                if stage == "skus"
                else (
                    "id",
                    "deviceName",
                    "operatingSystem",
                    "osVersion",
                    "complianceState",
                    "managedDeviceOwnerType",
                    "lastSyncDateTime",
                    "manufacturer",
                    "model",
                    "serialNumber",
                )
            )
            for record in values:
                if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                    raise ValueError("provider_response_invalid")
                projection = _scalar_projection(record, keys)
                if stage == "skus" and isinstance(record.get("prepaidUnits"), dict):
                    enabled = record["prepaidUnits"].get("enabled")
                    if isinstance(enabled, int):
                        projection["enabledUnits"] = enabled
                observations.append(ProviderObservation(remote_type, record["id"], _fingerprint(record), projection))
            if next_path:
                next_cursor = _encode_cursor({"stage": stage, "path": next_path})
            elif stage == "skus":
                complete = (remote_type,)
                next_cursor = _encode_cursor(
                    {
                        "stage": "devices",
                        "path": (
                            "deviceManagement/managedDevices?$select=id,deviceName,operatingSystem,osVersion,"
                            "complianceState,managedDeviceOwnerType,lastSyncDateTime,manufacturer,model,serialNumber"
                        ),
                    }
                )
            else:
                complete = (remote_type,)
                next_cursor = ""
        else:
            raise ValueError("provider_cursor_invalid")
        return ProviderPage(
            tuple(observations),
            next_cursor,
            complete,
            tuple(complete_prefixes) if stage == "users" and bool(state.get("incremental")) else (),
            configuration_updates,
        )


HALO_OBJECT_TYPES = ("client", "site", "contact", "contract", "ticket")
HALO_STAGES = (
    ("clients", "Client", "clients", "client"),
    ("sites", "Site", "sites", "site"),
    ("contacts", "Users", "users", "contact"),
    ("contracts", "Agreement", "agreements", "contract"),
    ("tickets", "Tickets", "tickets", "ticket"),
)
HALO_PAGE_SIZE = 100
HALO_CLOSED_TICKET_WINDOW = timedelta(days=90)


def _halo_scalar(record: dict[str, object], *keys: str) -> dict[str, object]:
    return {
        key: record[key]
        for key in keys
        if key in record and isinstance(record[key], str | int | float | bool | type(None))
    }


def _halo_timestamp(record: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _halo_ticket_is_current(record: dict[str, object], *, now: datetime | None = None) -> bool:
    closed = record.get("dateclosed")
    if closed in (None, ""):
        return True
    if not isinstance(closed, str):
        raise ValueError("provider_response_invalid")
    try:
        closed_at = datetime.fromisoformat(closed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("provider_response_invalid") from exc
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=UTC)
    return closed_at >= (now or datetime.now(UTC)) - HALO_CLOSED_TICKET_WINDOW


def _halo_cursor(value: str) -> tuple[int, int]:
    if not value:
        return 0, 1
    try:
        decoded = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("provider_cursor_invalid") from exc
    if (
        not isinstance(decoded, dict)
        or not isinstance(decoded.get("stage"), int)
        or not isinstance(decoded.get("page"), int)
        or decoded["stage"] < 0
        or decoded["stage"] >= len(HALO_STAGES)
        or decoded["page"] < 1
    ):
        raise ValueError("provider_cursor_invalid")
    return decoded["stage"], decoded["page"]


def _halo_encode_cursor(stage: int, page: int) -> str:
    return _encode_cursor({"stage": stage, "page": page})


class HaloPSAProvider:
    key = str(IntegrationProvider.HALOPSA)
    label = "HaloPSA"
    contract = ProviderContract(
        key=key,
        label=label,
        version="1.0",
        direction="read_only",
        credential_fields=(
            CredentialField(
                "client_id",
                "API application client ID",
                False,
                8,
                "text",
                "From Configuration → Integrations → Halo API.",
            ),
            CredentialField(
                "client_secret",
                "API application client secret",
                True,
                8,
                "password",
                "Stored encrypted and never shown again.",
            ),
        ),
        capabilities=("psa_observations", "external_ticket_search", "reconciliation"),
        object_types=HALO_OBJECT_TYPES,
        pagination="opaque_cursor",
        minimum_sync_interval_minutes=15,
        maximum_sync_interval_minutes=10080,
        default_base_url="",
        base_url_editable=True,
        setup_help_url="https://halopsa.com/guides/article/?kbid=1499",
    )

    def __init__(
        self,
        getter: Callable[..., dict[str, object]] = get_provider_json,
        poster: Callable[..., dict[str, object]] = post_provider_form_basic,
    ):
        self._getter = getter
        self._poster = poster

    def _authorize(self, connection: IntegrationConnection, secret: str) -> str:
        payload = self._poster(
            base_url=connection.base_url,
            relative_path="auth/token",
            fields={"grant_type": "client_credentials", "scope": "all"},
            username=str(connection.configuration.get("client_id", "")),
            password=secret,
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not 16 <= len(token) <= 16384:
            raise ValueError("provider_token_invalid")
        token_type = payload.get("token_type", "Bearer")
        if not isinstance(token_type, str) or token_type.casefold() != "bearer":
            raise ValueError("provider_token_invalid")
        return token

    def fetch_page(self, connection: IntegrationConnection, *, secret: str, cursor: str) -> ProviderPage:
        token = self._authorize(connection, secret)
        stage_index, page_number = _halo_cursor(cursor)
        _stage, endpoint, collection_key, remote_type = HALO_STAGES[stage_index]
        payload = self._getter(
            base_url=connection.base_url,
            relative_path=f"api/{endpoint}?page_no={page_number}&page_size={HALO_PAGE_SIZE}&includeinactive=true",
            authorization=f"Bearer {token}",
        )
        values = payload.get(collection_key)
        if not isinstance(values, list) or len(values) > HALO_PAGE_SIZE:
            raise ValueError("provider_response_invalid")
        observations: list[ProviderObservation] = []
        for record in values:
            if not isinstance(record, dict) or not isinstance(record.get("id"), int | str):
                raise ValueError("provider_response_invalid")
            if remote_type == "ticket" and not _halo_ticket_is_current(record):
                continue
            remote_id = str(record["id"])
            if remote_type == "client":
                projection = _halo_scalar(record, "id", "name", "inactive", "toplevel_id")
            elif remote_type == "site":
                projection = _halo_scalar(record, "id", "name", "client_id", "client_name", "inactive")
            elif remote_type == "contact":
                projection = _halo_scalar(
                    record, "id", "name", "emailaddress", "client_id", "client_name", "site_id", "site_name", "inactive"
                )
            elif remote_type == "contract":
                projection = _halo_scalar(
                    record, "id", "name", "reference", "client_id", "client_name", "start_date", "end_date", "status"
                )
            else:
                projection = _halo_scalar(
                    record,
                    "id",
                    "summary",
                    "client_id",
                    "client_name",
                    "site_id",
                    "status_id",
                    "statusname",
                    "priority_id",
                    "priority",
                    "team",
                    "agent_id",
                    "agent_name",
                    "respondbydate",
                    "fixbydate",
                    "dateoccurred",
                    "dateclosed",
                    "lastactiondate",
                )
                projection["external_url"] = f"{connection.base_url.rstrip('/')}/tickets?id={remote_id}"
            observations.append(
                ProviderObservation(
                    remote_type,
                    remote_id,
                    _fingerprint(record),
                    projection,
                    _halo_timestamp(record, "last_modified", "lastactiondate", "dateoccurred"),
                )
            )
        record_count = payload.get("record_count")
        if record_count is not None and not isinstance(record_count, int):
            raise ValueError("provider_response_invalid")
        has_more = len(values) == HALO_PAGE_SIZE and (
            record_count is None or page_number * HALO_PAGE_SIZE < record_count
        )
        if has_more:
            next_cursor = _halo_encode_cursor(stage_index, page_number + 1)
            complete: tuple[str, ...] = ()
        elif stage_index + 1 < len(HALO_STAGES):
            next_cursor = _halo_encode_cursor(stage_index + 1, 1)
            complete = (remote_type,)
        else:
            next_cursor = ""
            complete = (remote_type,)
        return ProviderPage(tuple(observations), next_cursor, complete)


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


PROVIDERS: dict[str, ProviderAdapter] = {
    str(IntegrationProvider.NETBOX): NetBoxProvider(),
    str(IntegrationProvider.MICROSOFT_GRAPH): MicrosoftGraphProvider(),
    str(IntegrationProvider.HALOPSA): HaloPSAProvider(),
}


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

    if not isinstance(page.next_cursor, str) or len(page.next_cursor) > 10000:
        raise ValueError("provider_cursor_invalid")
    if len(page.observations) > 1000:
        raise ValueError("provider_response_invalid")
    if any(
        remote_type not in adapter.contract.object_types or not prefix
        for remote_type, prefix in page.complete_id_prefixes
    ):
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
            or observation.state not in {"observed", "retired"}
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
