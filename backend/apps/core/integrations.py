from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.policy import PermissionKey, require_permission

from .integration_egress import validate_integration_base_url
from .integration_providers import PROVIDERS, ProviderAdapter
from .integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from .models import (
    AuditEvent,
    IntegrationConflict,
    IntegrationConflictStatus,
    IntegrationConnection,
    IntegrationJobState,
    IntegrationLogEvent,
    IntegrationObservation,
    IntegrationProvider,
    IntegrationSyncJob,
    NetBoxReference,
    Tenant,
    workspace_for_owner,
)
from .scoping import DataScope
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace

MAX_CONNECTIONS_PER_WORKSPACE = 20
MAX_JOB_ATTEMPTS = 8
JOB_LEASE = timedelta(minutes=10)
LOG_RETENTION = timedelta(days=30)
ALLOWED_LOG_CODES = frozenset(
    {"sync_started", "sync_page_succeeded", "sync_retry_scheduled", "sync_dead_lettered", "sync_completed"}
)


def _validate_provider_secret(value: str) -> bytes:
    encoded = value.encode()
    contains_control_character = any(ord(character) < 32 or ord(character) == 127 for character in value)
    if len(encoded) < 8 or len(encoded) > 4096 or contains_control_character:
        raise ValidationError({"api_token": "Enter a valid provider API token without control characters."})
    return encoded


def resolve_integration_workspace(
    user: Any, *, organization_entity_id: UUID | None, permission: PermissionKey
) -> ResolvedWorkspace:
    workspace = (
        resolve_organization_workspace(user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(user)
    )
    require_permission(user, permission, organization=workspace.organization)
    return workspace


def _recent_session(request: Any) -> None:
    if getattr(request, "auth", None) is not None or getattr(request, "api_token", None) is not None:
        raise PermissionDenied("API tokens cannot set or rotate provider credentials.")
    if not did_recently_authenticate(request._request):
        raise PermissionDenied("Recent password or MFA reauthentication is required.")


def connections_for_workspace(workspace: ResolvedWorkspace) -> QuerySet[IntegrationConnection]:
    return IntegrationConnection.scoped.for_scope(workspace.data_scope).filter(
        workspace_id=workspace.data_scope.workspace_id
    )


@transaction.atomic
def create_connection(
    *,
    request: Any,
    organization_entity_id: UUID | None,
    provider: str,
    name: str,
    base_url: str,
    api_token: str,
    sync_interval_minutes: int,
) -> IntegrationConnection:
    _recent_session(request)
    resolved = resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=PermissionKey.INTEGRATIONS_MANAGE
    )
    if provider not in PROVIDERS:
        raise ValidationError({"provider": "That integration provider is not supported."})
    if connections_for_workspace(resolved).count() >= MAX_CONNECTIONS_PER_WORKSPACE:
        raise ValidationError({"connection": "This Workspace has reached the integration connection limit."})
    normalized_name = " ".join(name.split())
    if not normalized_name or any(ord(character) < 32 for character in normalized_name):
        raise ValidationError({"name": "Enter a visible connection name without control characters."})
    encoded_token = _validate_provider_secret(api_token)
    connection_id = uuid4()
    connection = IntegrationConnection(
        id=connection_id,
        tenant=resolved.member.tenant,
        workspace=workspace_for_owner(tenant=resolved.member.tenant, organization=resolved.organization),
        organization=resolved.organization,
        provider=provider,
        name=normalized_name,
        base_url=validate_integration_base_url(base_url),
        configuration={},
        secret_envelope=encrypt_integration_secret(
            secret=encoded_token, tenant_id=resolved.member.tenant.id, connection_id=connection_id, generation=1
        ),
        sync_interval_minutes=sync_interval_minutes,
        created_by=request.user,
    )
    connection.full_clean()
    connection.save()
    AuditEvent.objects.create(
        tenant=resolved.member.tenant,
        actor=request.user,
        action="integration_connection.created",
        entity_id=connection.id,
        request_id=getattr(request, "request_id", None),
        metadata={"provider": provider},
    )
    return connection


@transaction.atomic
def update_connection(
    *, request: Any, organization_entity_id: UUID | None, connection_id: UUID, active: bool, sync_interval_minutes: int
) -> IntegrationConnection:
    resolved = resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=PermissionKey.INTEGRATIONS_MANAGE
    )
    try:
        connection = connections_for_workspace(resolved).select_for_update().get(pk=connection_id)
    except IntegrationConnection.DoesNotExist as exc:
        raise NotFound("The integration connection is unavailable.") from exc
    connection.active = active
    connection.health_status = "unknown" if active else "paused"
    connection.sync_interval_minutes = sync_interval_minutes
    connection.full_clean()
    connection.save(update_fields=("active", "health_status", "sync_interval_minutes", "updated_at"))
    AuditEvent.objects.create(
        tenant=resolved.member.tenant,
        actor=request.user,
        action="integration_connection.updated",
        entity_id=connection.id,
        request_id=getattr(request, "request_id", None),
        metadata={"active": active},
    )
    return connection


@transaction.atomic
def rotate_connection_secret(
    *, request: Any, organization_entity_id: UUID | None, connection_id: UUID, api_token: str
) -> IntegrationConnection:
    _recent_session(request)
    resolved = resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=PermissionKey.INTEGRATIONS_MANAGE
    )
    try:
        connection = connections_for_workspace(resolved).select_for_update().get(pk=connection_id)
    except IntegrationConnection.DoesNotExist as exc:
        raise NotFound("The integration connection is unavailable.") from exc
    encoded_token = _validate_provider_secret(api_token)
    connection.secret_generation += 1
    connection.secret_envelope = encrypt_integration_secret(
        secret=encoded_token,
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        generation=connection.secret_generation,
    )
    connection.save(update_fields=("secret_envelope", "secret_generation", "updated_at"))
    AuditEvent.objects.create(
        tenant=resolved.member.tenant,
        actor=request.user,
        action="integration_connection.credential_rotated",
        entity_id=connection.id,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
    return connection


def _job_key(connection: IntegrationConnection, *, now: Any) -> str:
    interval = connection.sync_interval_minutes * 60
    return f"scheduled:{int(now.timestamp()) // interval}"


@transaction.atomic
def enqueue_sync(
    *,
    connection: IntegrationConnection,
    trigger: str,
    requested_by_id: UUID | None = None,
    idempotency_key: str = "",
    cursor: str = "",
    now: Any = None,
) -> IntegrationSyncJob:
    now = now or timezone.now()
    key = idempotency_key or _job_key(connection, now=now)
    job, _created = IntegrationSyncJob.objects.get_or_create(
        connection=connection,
        idempotency_key=key,
        defaults={
            "tenant": connection.tenant,
            "workspace": connection.workspace,
            "organization": connection.organization,
            "trigger": trigger,
            "cursor_before": cursor,
            "requested_by_id": requested_by_id,
            "available_at": now,
        },
    )
    return job


def schedule_due_connections(*, tenant: Tenant, scope: DataScope, now: Any = None) -> int:
    now = now or timezone.now()
    count = 0
    for connection in IntegrationConnection.scoped.for_scope(scope).filter(active=True, next_sync_at__lte=now):
        enqueue_sync(connection=connection, trigger="scheduled", now=now)
        count += 1
    return count


def _safe_log(*, job: IntegrationSyncJob, level: str, code: str, metrics: dict[str, int] | None = None) -> None:
    if code not in ALLOWED_LOG_CODES or level not in {"info", "warning", "error"}:
        raise ValueError("Integration log metadata is not allowlisted")
    normalized = metrics or {}
    if any(not isinstance(value, int) or value < 0 for value in normalized.values()):
        raise ValueError("Integration metrics must be non-negative integers")
    IntegrationLogEvent.objects.create(
        tenant=job.tenant,
        workspace=job.workspace,
        organization=job.organization,
        connection=job.connection,
        job=job,
        level=level,
        code=code,
        metrics=normalized,
    )


def _conflicts_for_observations(job: IntegrationSyncJob, observations: list[IntegrationObservation]) -> None:
    if job.connection.provider != IntegrationProvider.NETBOX:
        return
    references = {
        (item.object_type, str(item.object_id)): item
        for item in NetBoxReference.scoped.for_scope(
            DataScope(job.tenant_id, job.workspace_id, job.organization_id)
        ).filter(workspace=job.workspace, archived_at__isnull=True)
    }
    for observation in observations:
        key = (observation.remote_type, observation.remote_id)
        reference = references.get(key)
        difference = (
            "unmatched"
            if reference is None
            else ("changed" if reference.observed_fingerprint != observation.fingerprint else "")
        )
        if not difference:
            continue
        IntegrationConflict.objects.update_or_create(
            connection=job.connection,
            remote_type=observation.remote_type,
            remote_id=observation.remote_id,
            status=IntegrationConflictStatus.OPEN,
            defaults={
                "tenant": job.tenant,
                "workspace": job.workspace,
                "organization": job.organization,
                "observation": observation,
                "local_entity": reference.entity if reference else None,
                "difference": difference,
                "remote_fingerprint": observation.fingerprint,
                "local_fingerprint": reference.observed_fingerprint if reference else "",
            },
        )


@transaction.atomic
def process_sync_job(*, job_id: UUID, adapter: ProviderAdapter | None = None, now: Any = None) -> IntegrationSyncJob:
    now = now or timezone.now()
    try:
        job = IntegrationSyncJob.objects.select_for_update().select_related("connection").get(pk=job_id)
    except IntegrationSyncJob.DoesNotExist as exc:
        raise NotFound("The integration job is unavailable.") from exc
    if job.state == IntegrationJobState.SUCCEEDED or job.state == IntegrationJobState.DEAD_LETTER:
        return job
    if job.locked_at and job.locked_at > now - JOB_LEASE:
        return job
    job.state = IntegrationJobState.PROCESSING
    job.locked_at = now
    job.started_at = job.started_at or now
    job.attempts += 1
    job.last_error_code = ""
    job.save(update_fields=("state", "locked_at", "started_at", "attempts", "last_error_code"))
    _safe_log(job=job, level="info", code="sync_started", metrics={"attempt": job.attempts})
    try:
        secret = decrypt_integration_secret(
            envelope_payload=job.connection.secret_envelope,
            tenant_id=job.tenant_id,
            connection_id=job.connection_id,
            generation=job.connection.secret_generation,
        ).decode()
        selected = adapter or PROVIDERS[job.connection.provider]
        page = selected.fetch_page(job.connection, secret=secret, cursor=job.cursor_before)
        # A handled finalization failure must roll back the whole provider page before scheduling a retry.
        with transaction.atomic():
            records = [
                IntegrationObservation(
                    tenant=job.tenant,
                    workspace=job.workspace,
                    organization=job.organization,
                    job=job,
                    remote_type=item.remote_type,
                    remote_id=item.remote_id,
                    fingerprint=item.fingerprint,
                    schema_version=item.schema_version,
                    safe_projection=item.safe_projection,
                    source_timestamp=item.source_timestamp,
                    provenance=item.provenance,
                )
                for item in page.observations
            ]
            IntegrationObservation.objects.bulk_create(records, ignore_conflicts=True)
            created = list(IntegrationObservation.objects.filter(job=job))
            _conflicts_for_observations(job, created)
            job.cursor_after = page.next_cursor
            job.state = IntegrationJobState.SUCCEEDED
            job.locked_at = None
            job.finished_at = now
            job.result_counts = {"observations": len(created)}
            job.save(update_fields=("cursor_after", "state", "locked_at", "finished_at", "result_counts"))
            _safe_log(job=job, level="info", code="sync_page_succeeded", metrics={"observations": len(created)})
            if page.next_cursor:
                enqueue_sync(
                    connection=job.connection,
                    trigger=job.trigger,
                    requested_by_id=job.requested_by_id,
                    idempotency_key=f"continuation:{job.id}",
                    cursor=page.next_cursor,
                    now=now,
                )
            else:
                job.connection.next_sync_at = now + timedelta(minutes=job.connection.sync_interval_minutes)
                job.connection.health_status = "healthy"
                job.connection.last_successful_sync_at = now
                job.connection.last_error_code = ""
                job.connection.reconciliation_counts = {
                    "observations": len(created),
                    "review_required": IntegrationConflict.objects.filter(
                        connection=job.connection, status=IntegrationConflictStatus.OPEN
                    ).count(),
                }
                job.connection.save(
                    update_fields=(
                        "next_sync_at",
                        "health_status",
                        "last_successful_sync_at",
                        "last_error_code",
                        "reconciliation_counts",
                        "updated_at",
                    )
                )
                _safe_log(job=job, level="info", code="sync_completed", metrics={"observations": len(created)})
        return job
    except Exception as exc:
        code = (
            str(exc)
            if str(exc)
            in {
                "provider_cursor_invalid",
                "provider_response_invalid",
                "provider_http_error",
                "provider_content_type_invalid",
                "provider_response_too_large",
                "provider_connection_failed",
                "destination_not_public",
                "dns_unavailable",
            }
            else "provider_failure"
        )
        job.state = IntegrationJobState.DEAD_LETTER if job.attempts >= MAX_JOB_ATTEMPTS else IntegrationJobState.PENDING
        job.locked_at = None
        job.last_error_code = code
        job.finished_at = now if job.state == IntegrationJobState.DEAD_LETTER else None
        job.available_at = now + timedelta(minutes=min(2**job.attempts, 60))
        job.save(update_fields=("state", "locked_at", "last_error_code", "finished_at", "available_at"))
        job.connection.health_status = "failing" if job.state == IntegrationJobState.DEAD_LETTER else "degraded"
        job.connection.last_error_code = code
        job.connection.save(update_fields=("health_status", "last_error_code", "updated_at"))
        _safe_log(
            job=job,
            level="error" if job.state == IntegrationJobState.DEAD_LETTER else "warning",
            code="sync_dead_lettered" if job.state == IntegrationJobState.DEAD_LETTER else "sync_retry_scheduled",
            metrics={"attempt": job.attempts},
        )
        return job


def purge_integration_logs(*, tenant: Tenant, now: Any = None) -> int:
    cutoff = (now or timezone.now()) - LOG_RETENTION
    deleted, _ = IntegrationLogEvent.objects.filter(tenant=tenant, occurred_at__lt=cutoff).delete()
    return deleted


@transaction.atomic
def resolve_conflict(
    *, workspace: ResolvedWorkspace, conflict_id: UUID, actor: Any, resolution: str
) -> IntegrationConflict:
    if resolution not in {
        IntegrationConflictStatus.KEEP_LOCAL,
        IntegrationConflictStatus.ACCEPT_REMOTE,
        IntegrationConflictStatus.IGNORED,
    }:
        raise ValidationError({"resolution": "Select a supported reconciliation action."})
    try:
        conflict = (
            IntegrationConflict.scoped.for_scope(workspace.data_scope)
            .select_for_update()
            .get(workspace_id=workspace.data_scope.workspace_id, pk=conflict_id, status=IntegrationConflictStatus.OPEN)
        )
    except IntegrationConflict.DoesNotExist as exc:
        raise NotFound("The integration conflict is unavailable.") from exc
    # Accepting remote acknowledges only the external identity fingerprint. Domain records remain canonical.
    if resolution == IntegrationConflictStatus.ACCEPT_REMOTE and conflict.local_entity_id:
        reference = (
            NetBoxReference.scoped.for_scope(workspace.data_scope)
            .select_for_update()
            .filter(
                workspace_id=workspace.data_scope.workspace_id,
                entity_id=conflict.local_entity_id,
                object_type=conflict.remote_type,
                object_id=int(conflict.remote_id),
                archived_at__isnull=True,
            )
            .first()
        )
        if reference:
            reference.observed_fingerprint = conflict.remote_fingerprint
            reference.last_observed_at = timezone.now()
            reference.save(update_fields=("observed_fingerprint", "last_observed_at", "updated_at"))
    conflict.status = resolution
    conflict.resolved_by = actor
    conflict.resolved_at = timezone.now()
    conflict.save(update_fields=("status", "resolved_by", "resolved_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="integration_conflict.resolved",
        entity_id=conflict.id,
        metadata={"resolution": resolution},
    )
    return conflict
