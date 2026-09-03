from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4
from uuid import UUID as UUIDValue

from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.policy import PermissionKey, require_permission

from .integration_egress import ProviderRateLimited, validate_integration_base_url
from .integration_providers import PROVIDERS, ProviderAdapter, validate_provider_adapter, validate_provider_page
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
    {
        "sync_started",
        "sync_page_succeeded",
        "sync_retry_scheduled",
        "sync_dead_lettered",
        "sync_completed",
    }
)


def _validate_provider_secret(value: str, *, field: str = "api_token") -> bytes:
    encoded = value.encode()
    contains_control_character = any(ord(character) < 32 or ord(character) == 127 for character in value)
    if len(encoded) < 8 or len(encoded) > 4096 or contains_control_character:
        raise ValidationError({field: "Enter a valid credential without control characters."})
    return encoded


def _provider_credentials(
    provider: str, values: dict[str, str], legacy_token: str = ""
) -> tuple[bytes, dict[str, object]]:
    adapter = PROVIDERS[provider]
    supplied = dict(values)
    if legacy_token and provider == IntegrationProvider.NETBOX:
        supplied["api_token"] = legacy_token
    expected = {field.key for field in adapter.contract.credential_fields}
    if set(supplied) != expected:
        raise ValidationError({"credentials": "Provide every credential field shown for this provider."})
    configuration: dict[str, object] = {}
    secrets: dict[str, str] = {}
    for field in adapter.contract.credential_fields:
        value = supplied[field.key]
        if not isinstance(value, str) or len(value) < field.minimum_length or len(value) > 4096:
            raise ValidationError({"credentials": f"Enter a valid {field.label.lower()}."})
        _validate_provider_secret(value, field="credentials")
        if not field.secret:
            try:
                normalized = str(UUIDValue(value))
            except ValueError as exc:
                raise ValidationError({"credentials": f"{field.label} must be a UUID."}) from exc
            configuration[field.key] = normalized
        else:
            secrets[field.key] = value
    if provider == IntegrationProvider.NETBOX:
        return secrets["api_token"].encode(), configuration
    return json.dumps(secrets, sort_keys=True, separators=(",", ":")).encode(), configuration


def _secret_for_provider(connection: IntegrationConnection, payload: bytes) -> str:
    decoded = payload.decode()
    if connection.provider == IntegrationProvider.NETBOX:
        return decoded
    try:
        values = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError("provider_credential_invalid") from exc
    if not isinstance(values, dict):
        raise ValueError("provider_credential_invalid")
    client_secret = values.get("client_secret")
    if not isinstance(client_secret, str):
        raise ValueError("provider_credential_invalid")
    return client_secret


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
    base_url: str = "",
    credentials: dict[str, str] | None = None,
    api_token: str = "",
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
    encoded_token, configuration = _provider_credentials(provider, credentials or {}, api_token)
    adapter = PROVIDERS[provider]
    if not (
        adapter.contract.minimum_sync_interval_minutes
        <= sync_interval_minutes
        <= adapter.contract.maximum_sync_interval_minutes
    ):
        raise ValidationError({"sync_interval_minutes": "Choose an interval allowed by this provider."})
    selected_base_url = adapter.contract.default_base_url if not adapter.contract.base_url_editable else base_url
    if not selected_base_url:
        raise ValidationError({"base_url": "Enter the provider API base URL."})
    connection_id = uuid4()
    connection = IntegrationConnection(
        id=connection_id,
        tenant=resolved.member.tenant,
        workspace=workspace_for_owner(tenant=resolved.member.tenant, organization=resolved.organization),
        organization=resolved.organization,
        provider=provider,
        name=normalized_name,
        base_url=validate_integration_base_url(selected_base_url),
        configuration=configuration,
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
    adapter = PROVIDERS[connection.provider]
    if not (
        adapter.contract.minimum_sync_interval_minutes
        <= sync_interval_minutes
        <= adapter.contract.maximum_sync_interval_minutes
    ):
        raise ValidationError({"sync_interval_minutes": "Choose an interval allowed by this provider."})
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
    *,
    request: Any,
    organization_entity_id: UUID | None,
    connection_id: UUID,
    credentials: dict[str, str] | None = None,
    api_token: str = "",
) -> IntegrationConnection:
    _recent_session(request)
    resolved = resolve_integration_workspace(
        request.user, organization_entity_id=organization_entity_id, permission=PermissionKey.INTEGRATIONS_MANAGE
    )
    try:
        connection = connections_for_workspace(resolved).select_for_update().get(pk=connection_id)
    except IntegrationConnection.DoesNotExist as exc:
        raise NotFound("The integration connection is unavailable.") from exc
    encoded_token, configuration = _provider_credentials(connection.provider, credentials or {}, api_token)
    connection.configuration = {**connection.configuration, **configuration}
    if connection.provider == IntegrationProvider.MICROSOFT_GRAPH:
        connection.configuration.pop("scope_fingerprint", None)
        connection.configuration.pop("validated_tenant_id", None)
    connection.secret_generation += 1
    connection.secret_envelope = encrypt_integration_secret(
        secret=encoded_token,
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        generation=connection.secret_generation,
    )
    connection.health_status = "unknown"
    connection.last_error_code = ""
    connection.save(
        update_fields=(
            "secret_envelope",
            "secret_generation",
            "configuration",
            "health_status",
            "last_error_code",
            "updated_at",
        )
    )
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
    sync_run_id: UUID | None = None,
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
            "sync_run_id": sync_run_id or uuid4(),
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
            "retired_remote"
            if observation.state == "retired"
            else (
                "unmatched"
                if reference is None
                else ("changed" if reference.observed_fingerprint != observation.fingerprint else "")
            )
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


def _retired_observations(job: IntegrationSyncJob, complete_types: tuple[str, ...]) -> list[IntegrationObservation]:
    if not complete_types:
        return []
    current_keys = set(
        IntegrationObservation.objects.filter(
            job__connection=job.connection, job__sync_run_id=job.sync_run_id
        ).values_list("remote_type", "remote_id")
    )
    latest = (
        IntegrationObservation.objects.filter(job__connection=job.connection, remote_type__in=complete_types)
        .exclude(job__sync_run_id=job.sync_run_id)
        .order_by("remote_type", "remote_id", "-observed_at")
        .distinct("remote_type", "remote_id")
    )
    return [
        IntegrationObservation(
            tenant=job.tenant,
            workspace=job.workspace,
            organization=job.organization,
            job=job,
            remote_type=item.remote_type,
            remote_id=item.remote_id,
            fingerprint=item.fingerprint,
            schema_version=item.schema_version,
            safe_projection={},
            provenance="provider_absence",
            state="retired",
        )
        for item in latest
        if item.state == "observed" and (item.remote_type, item.remote_id) not in current_keys
    ]


def _retired_prefix_observations(
    job: IntegrationSyncJob, complete_id_prefixes: tuple[tuple[str, str], ...]
) -> list[IntegrationObservation]:
    retired: list[IntegrationObservation] = []
    for remote_type, prefix in complete_id_prefixes:
        current_keys = set(
            IntegrationObservation.objects.filter(
                job__connection=job.connection,
                job__sync_run_id=job.sync_run_id,
                remote_type=remote_type,
                remote_id__startswith=prefix,
            ).values_list("remote_id", flat=True)
        )
        latest = (
            IntegrationObservation.objects.filter(
                job__connection=job.connection,
                remote_type=remote_type,
                remote_id__startswith=prefix,
            )
            .exclude(job__sync_run_id=job.sync_run_id)
            .order_by("remote_id", "-observed_at")
            .distinct("remote_id")
        )
        retired.extend(
            IntegrationObservation(
                tenant=job.tenant,
                workspace=job.workspace,
                organization=job.organization,
                job=job,
                remote_type=item.remote_type,
                remote_id=item.remote_id,
                fingerprint=item.fingerprint,
                schema_version=item.schema_version,
                safe_projection={},
                provenance="provider_delta_absence",
                state="retired",
            )
            for item in latest
            if item.state == "observed" and item.remote_id not in current_keys
        )
    return retired


@transaction.atomic
def cancel_sync_job(*, workspace: ResolvedWorkspace, job_id: UUID, actor: Any) -> IntegrationSyncJob:
    try:
        job = (
            IntegrationSyncJob.scoped.for_scope(workspace.data_scope)
            .select_for_update()
            .select_related("connection")
            .get(workspace_id=workspace.data_scope.workspace_id, pk=job_id)
        )
    except IntegrationSyncJob.DoesNotExist as exc:
        raise NotFound("The integration job is unavailable.") from exc
    if job.state in {IntegrationJobState.SUCCEEDED, IntegrationJobState.DEAD_LETTER, IntegrationJobState.CANCELLED}:
        return job
    now = timezone.now()
    job.state = IntegrationJobState.CANCELLED
    job.finished_at = now
    job.locked_at = None
    job.save(update_fields=("state", "finished_at", "locked_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="integration_sync.cancel_requested",
        entity_id=job.id,
        metadata={},
    )
    return job


def process_sync_job(*, job_id: UUID, adapter: ProviderAdapter | None = None, now: Any = None) -> IntegrationSyncJob:
    now = now or timezone.now()
    with transaction.atomic():
        try:
            job = IntegrationSyncJob.objects.select_for_update().select_related("connection").get(pk=job_id)
        except IntegrationSyncJob.DoesNotExist as exc:
            raise NotFound("The integration job is unavailable.") from exc
        if job.state in {IntegrationJobState.SUCCEEDED, IntegrationJobState.DEAD_LETTER, IntegrationJobState.CANCELLED}:
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
        secret_payload = decrypt_integration_secret(
            envelope_payload=job.connection.secret_envelope,
            tenant_id=job.tenant_id,
            connection_id=job.connection_id,
            generation=job.connection.secret_generation,
        )
        secret = _secret_for_provider(job.connection, secret_payload)
        selected = adapter or PROVIDERS[job.connection.provider]
        validate_provider_adapter(selected)
        page = selected.fetch_page(job.connection, secret=secret, cursor=job.cursor_before)
        validate_provider_page(selected, page)
        with transaction.atomic():
            job = IntegrationSyncJob.objects.select_for_update().select_related("connection").get(pk=job_id)
            if job.state == IntegrationJobState.CANCELLED:
                return job
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
                    state=item.state,
                )
                for item in page.observations
            ]
            IntegrationObservation.objects.bulk_create(records, ignore_conflicts=True)
            created = list(IntegrationObservation.objects.filter(job=job))
            if page.complete_types:
                retired = _retired_observations(job, page.complete_types)
                IntegrationObservation.objects.bulk_create(retired, ignore_conflicts=True)
                created = list(IntegrationObservation.objects.filter(job=job))
            if page.complete_id_prefixes:
                retired = _retired_prefix_observations(job, page.complete_id_prefixes)
                IntegrationObservation.objects.bulk_create(retired, ignore_conflicts=True)
                created = list(IntegrationObservation.objects.filter(job=job))
            if page.configuration_updates:
                allowed_updates = {"scope_fingerprint", "validated_tenant_id", "users_delta_link"}
                if set(page.configuration_updates) - allowed_updates:
                    raise ValueError("provider_configuration_invalid")
                job.connection.configuration = {**job.connection.configuration, **page.configuration_updates}
                job.connection.save(update_fields=("configuration", "updated_at"))
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
                    sync_run_id=job.sync_run_id,
                    now=now,
                )
            else:
                run_observations = IntegrationObservation.objects.filter(
                    job__connection=job.connection, job__sync_run_id=job.sync_run_id
                )
                observation_count = run_observations.count()
                type_counts = {
                    f"{row['remote_type']}_count": row["count"]
                    for row in run_observations.values("remote_type").annotate(count=Count("id"))
                }
                job.connection.next_sync_at = now + timedelta(minutes=job.connection.sync_interval_minutes)
                job.connection.health_status = "healthy"
                job.connection.last_successful_sync_at = now
                job.connection.last_error_code = ""
                job.connection.rate_limit_reset_at = None
                job.connection.reconciliation_counts = {
                    "observations": observation_count,
                    "review_required": IntegrationConflict.objects.filter(
                        connection=job.connection, status=IntegrationConflictStatus.OPEN
                    ).count(),
                    **type_counts,
                }
                job.connection.save(
                    update_fields=(
                        "next_sync_at",
                        "health_status",
                        "last_successful_sync_at",
                        "last_error_code",
                        "rate_limit_reset_at",
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
                "provider_authentication_failed",
                "provider_cursor_expired",
                "provider_token_invalid",
                "provider_credential_invalid",
                "provider_permissions_missing",
                "provider_permissions_excessive",
                "provider_permission_drift",
                "provider_tenant_validation_failed",
                "provider_configuration_invalid",
                "provider_rate_limited",
                "destination_not_public",
                "dns_unavailable",
            }
            else "provider_failure"
        )
        with transaction.atomic():
            job = IntegrationSyncJob.objects.select_for_update().select_related("connection").get(pk=job_id)
            if job.state == IntegrationJobState.CANCELLED:
                return job
            job.state = (
                IntegrationJobState.DEAD_LETTER if job.attempts >= MAX_JOB_ATTEMPTS else IntegrationJobState.PENDING
            )
            job.locked_at = None
            job.last_error_code = code
            job.finished_at = now if job.state == IntegrationJobState.DEAD_LETTER else None
            job.available_at = (
                exc.retry_at
                if isinstance(exc, ProviderRateLimited)
                else now + timedelta(minutes=min(2**job.attempts, 60))
            )
            if code == "provider_cursor_expired" and job.connection.provider == IntegrationProvider.MICROSOFT_GRAPH:
                job.cursor_before = ""
                job.connection.configuration.pop("users_delta_link", None)
            job.save(
                update_fields=(
                    "state",
                    "locked_at",
                    "last_error_code",
                    "finished_at",
                    "available_at",
                    "cursor_before",
                )
            )
            job.connection.health_status = "failing" if job.state == IntegrationJobState.DEAD_LETTER else "degraded"
            job.connection.last_error_code = code
            job.connection.rate_limit_reset_at = exc.retry_at if isinstance(exc, ProviderRateLimited) else None
            job.connection.save(
                update_fields=("health_status", "last_error_code", "rate_limit_reset_at", "configuration", "updated_at")
            )
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
