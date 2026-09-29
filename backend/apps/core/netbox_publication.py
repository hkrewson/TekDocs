from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from .integration_egress import get_provider_json, send_provider_json
from .integration_providers import netbox_api_base_url, netbox_authorization
from .integration_secrets import decrypt_integration_secret
from .models import AuditEvent, IntegrationConnection, IntegrationObservation, IntegrationProvider
from .workspaces import ResolvedWorkspace


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _connection(workspace: ResolvedWorkspace, connection_id: UUID) -> IntegrationConnection:
    try:
        return IntegrationConnection.scoped.for_scope(workspace.data_scope).get(
            pk=connection_id,
            workspace_id=workspace.data_scope.workspace_id,
            provider=IntegrationProvider.NETBOX,
            active=True,
        )
    except IntegrationConnection.DoesNotExist as exc:
        raise NotFound("The active NetBox publishing connection is unavailable.") from exc


def _source(workspace: ResolvedWorkspace, observation_id: UUID) -> IntegrationObservation:
    try:
        observation = (
            IntegrationObservation.scoped.for_scope(workspace.data_scope)
            .select_related("job__connection")
            .get(
                pk=observation_id,
                workspace_id=workspace.data_scope.workspace_id,
                job__connection__provider=IntegrationProvider.UNIFI,
                state="observed",
            )
        )
    except IntegrationObservation.DoesNotExist as exc:
        raise NotFound("The UniFi source record is unavailable.") from exc
    latest = (
        IntegrationObservation.objects.filter(
            job__connection=observation.job.connection,
            remote_type=observation.remote_type,
            remote_id=observation.remote_id,
            state="observed",
        )
        .order_by("-observed_at", "-id")
        .first()
    )
    if latest is None or latest.id != observation.id:
        raise ValidationError({"source_observation_id": "The UniFi source changed. Preview it again."})
    if observation.remote_type not in {"unifi.network", "unifi.device"}:
        raise ValidationError({"source_observation_id": "Only UniFi networks and adopted devices can be published."})
    return observation


def _read_secret(connection: IntegrationConnection) -> str:
    return decrypt_integration_secret(
        envelope_payload=connection.secret_envelope,
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        generation=connection.secret_generation,
    ).decode()


def _write_secret(connection: IntegrationConnection) -> str:
    if not connection.write_secret_envelope:
        raise ValidationError({"connection_id": "Configure a separate NetBox write token before publishing."})
    return decrypt_integration_secret(
        envelope_payload=connection.write_secret_envelope,
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        generation=connection.write_secret_generation,
    ).decode()


def _require_write_secret(connection: IntegrationConnection) -> None:
    if not connection.write_secret_envelope:
        raise ValidationError({"connection_id": "Configure a separate NetBox write token before publishing."})


def _matches(payload: dict[str, Any]) -> list[dict[str, object]]:
    results = payload.get("results")
    if not isinstance(results, list) or len(results) > 2 or any(not isinstance(item, dict) for item in results):
        raise ValidationError({"connection_id": "NetBox returned an unexpected lookup response."})
    return results


def preview_netbox_publication(
    *,
    workspace: ResolvedWorkspace,
    source_observation_id: UUID,
    connection_id: UUID,
    fetcher: Callable[..., dict[str, Any]] = get_provider_json,
) -> dict[str, object]:
    source = _source(workspace, source_observation_id)
    target = _connection(workspace, connection_id)
    _require_write_secret(target)
    authorization = netbox_authorization(_read_secret(target))
    values = source.safe_projection
    if source.remote_type == "unifi.network":
        cidr = values.get("cidr")
        if not isinstance(cidr, str) or not cidr:
            raise ValidationError({"source_observation_id": "This UniFi network has no publishable CIDR."})
        matches = _matches(
            fetcher(
                base_url=netbox_api_base_url(target.base_url),
                relative_path=f"ipam/prefixes/?{urlencode({'prefix': cidr})}",
                authorization=authorization,
            )
        )
        if len(matches) > 1:
            raise ValidationError({"connection_id": "More than one NetBox prefix matched this CIDR."})
        remote_id = matches[0].get("id") if matches else None
        if remote_id is not None and not isinstance(remote_id, int):
            raise ValidationError({"connection_id": "The matched NetBox prefix has an invalid identity."})
        proposal = {
            "source_observation_id": str(source.id),
            "source_type": source.remote_type,
            "source_fingerprint": source.fingerprint,
            "connection_id": str(target.id),
            "action": "update" if remote_id is not None else "create",
            "endpoint": f"ipam/prefixes/{remote_id}/" if remote_id is not None else "ipam/prefixes/",
            "fields": {"prefix": cidr, "description": "Observed by TekDocs from UniFi Network."},
            "target_fingerprint": _digest(matches[0]) if matches else "",
        }
    else:
        name = values.get("name")
        if not isinstance(name, str) or not name:
            raise ValidationError({"source_observation_id": "This UniFi device has no publishable name."})
        matches = _matches(
            fetcher(
                base_url=netbox_api_base_url(target.base_url),
                relative_path=f"dcim/devices/?{urlencode({'name': name})}",
                authorization=authorization,
            )
        )
        if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
            raise ValidationError(
                {
                    "connection_id": (
                        "Publishing a device requires one existing NetBox device with the same name. "
                        "Device creation remains in NetBox."
                    )
                }
            )
        remote_id = matches[0]["id"]
        fields = {"name": name}
        serial = values.get("serial")
        if isinstance(serial, str) and serial:
            fields["serial"] = serial
        proposal = {
            "source_observation_id": str(source.id),
            "source_type": source.remote_type,
            "source_fingerprint": source.fingerprint,
            "connection_id": str(target.id),
            "action": "update",
            "endpoint": f"dcim/devices/{remote_id}/",
            "fields": fields,
            "target_fingerprint": _digest(matches[0]),
        }
    return {**proposal, "proposal_digest": _digest(proposal)}


def publish_netbox_proposal(
    *,
    workspace: ResolvedWorkspace,
    actor_id: UUID,
    source_observation_id: UUID,
    connection_id: UUID,
    proposal_digest: str,
    request_id: str | None = None,
    fetcher: Callable[..., dict[str, Any]] = get_provider_json,
    sender: Callable[..., dict[str, Any]] = send_provider_json,
) -> dict[str, object]:
    proposal = preview_netbox_publication(
        workspace=workspace,
        source_observation_id=source_observation_id,
        connection_id=connection_id,
        fetcher=fetcher,
    )
    if proposal.get("proposal_digest") != proposal_digest:
        raise ValidationError({"proposal_digest": "The source or NetBox target changed. Review a fresh proposal."})
    target = _connection(workspace, connection_id)
    fields = proposal["fields"]
    if not isinstance(fields, dict):
        raise ValidationError({"proposal_digest": "The publication proposal is invalid."})
    result = sender(
        base_url=netbox_api_base_url(target.base_url),
        relative_path=str(proposal["endpoint"]),
        method="POST" if proposal["action"] == "create" else "PATCH",
        authorization=netbox_authorization(_write_secret(target)),
        values=fields,
    )
    remote_id = result.get("id")
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor_id=actor_id,
        action="integration_netbox.publication_completed",
        entity_id=target.id,
        request_id=request_id,
        metadata={
            "source_observation_id": str(source_observation_id),
            "source_type": str(proposal["source_type"]),
            "target_action": str(proposal["action"]),
            "target_id": remote_id if isinstance(remote_id, int) else None,
            "proposal_digest": proposal_digest,
        },
    )
    return {"status": "published", "target_id": remote_id, "proposal_digest": proposal_digest}
