from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

from django.db import connection as database_connection
from django.utils import timezone

from .models import IntegrationEntityMapping, IntegrationObservation, IntegrationProvider
from .rls import OrganizationRLSMode, bind_local_rls_scope, system_rls_scope_if_postgresql
from .scoping import DataScope
from .workspaces import ResolvedWorkspace

MAX_TICKET_CANDIDATES = 2_000
MAX_RECENT_TICKETS = 50


def _client_ids(workspace: ResolvedWorkspace) -> dict[object, set[str]]:
    mappings = IntegrationEntityMapping.objects.filter(
        tenant=workspace.member.tenant,
        connection__provider=IntegrationProvider.HALOPSA,
        remote_type="client",
    )
    if workspace.organization is not None:
        mappings = mappings.filter(local_entity_id=workspace.organization.entity_id)
    return {
        connection_id: set(mappings.filter(connection_id=connection_id).values_list("remote_id", flat=True))
        for connection_id in mappings.values_list("connection_id", flat=True).distinct()
    }


def _safe_external_url(base_url: str, value: object) -> str:
    if not isinstance(value, str):
        return ""
    base, target = urlsplit(base_url), urlsplit(value)
    if (
        target.scheme != "https"
        or target.hostname != base.hostname
        or target.port not in (None, 443)
        or target.username
        or target.password
        or target.fragment
    ):
        return ""
    return value


def halo_ticket_summaries(workspace: ResolvedWorkspace) -> list[dict[str, object]]:
    """Return current, mapped Halo ticket projections for MSP staff only."""

    if workspace.member.surface == "client_portal":
        return []
    # Halo connections and their observations belong to the MSP workspace. This
    # narrow, server-side read happens only after the caller has been authorized
    # for the selected organization; the organization mapping below remains the
    # mandatory projection boundary.
    try:
        with system_rls_scope_if_postgresql(
            DataScope.tenant(workspace.member.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
        ):
            client_ids_by_connection = _client_ids(workspace)
            if not client_ids_by_connection:
                return []
            observations = list(
                IntegrationObservation.objects.filter(
                    tenant=workspace.member.tenant,
                    job__connection_id__in=client_ids_by_connection,
                    job__connection__provider=IntegrationProvider.HALOPSA,
                    remote_type="ticket",
                )
                .select_related("job__connection")
                .order_by("-observed_at", "id")[:MAX_TICKET_CANDIDATES]
            )
    finally:
        if database_connection.vendor == "postgresql":
            mode = (
                OrganizationRLSMode.ORGANIZATION if workspace.organization is not None else OrganizationRLSMode.MSP_ONLY
            )
            bind_local_rls_scope(workspace.data_scope, organization_mode=mode)
    current: dict[tuple[object, str], IntegrationObservation] = {}
    for observation in observations:
        key = (observation.job.connection_id, observation.remote_id)
        if key in current:
            continue
        client_id = str(observation.safe_projection.get("client_id", ""))
        if client_id in client_ids_by_connection.get(observation.job.connection_id, set()):
            current[key] = observation
    now = timezone.now()
    results: list[dict[str, object]] = []
    for observation in current.values():
        if observation.state != "observed":
            continue
        projection = observation.safe_projection
        connection = observation.job.connection
        last_sync = connection.last_successful_sync_at
        stale = (
            connection.health_status != "healthy"
            or last_sync is None
            or last_sync < now - timedelta(minutes=connection.sync_interval_minutes * 2)
        )
        results.append(
            {
                "id": observation.id,
                "number": observation.remote_id,
                "title": str(projection.get("summary", "")),
                "status": str(projection.get("statusname", "")),
                "priority": str(projection.get("priority", "")),
                "assigned_team": str(projection.get("team", "")),
                "assigned_agent": str(projection.get("agent_name", "")),
                "respond_by": projection.get("respondbydate") or None,
                "fix_by": projection.get("fixbydate") or None,
                "opened_at": projection.get("dateoccurred") or None,
                "closed_at": projection.get("dateclosed") or None,
                "source_updated_at": observation.source_timestamp or observation.observed_at,
                "source_last_synced_at": last_sync,
                "stale": stale,
                "external_url": _safe_external_url(connection.base_url, projection.get("external_url")),
            }
        )
    results.sort(key=lambda item: (bool(item["closed_at"]), str(item["status"]).casefold(), str(item["number"])))
    return results[:MAX_RECENT_TICKETS]
