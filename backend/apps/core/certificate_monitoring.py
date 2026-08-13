from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .certificate_monitoring_egress import (
    CertificateCollectionError,
    CollectedCertificateEvidence,
    collect_certificate_evidence,
    protocol_port,
)
from .models import (
    CertificateEndpoint,
    CertificateEndpointProtocol,
    CertificateMonitorAlert,
    CertificateMonitorAlertKind,
    CertificateMonitorRun,
    DomainMonitorRunState,
    DomainMonitorState,
    Entity,
    EntityVisibility,
    ManagedHostname,
    RegisteredDomain,
)
from .monitoring_evidence import canonical_evidence_digest
from .scoping import DataScope

Collector = Callable[[str, str], CollectedCertificateEvidence]
MONITORING_LEASE = timedelta(minutes=15)
EXPIRATION_ALERT_WINDOW = timedelta(days=45)


class CertificateMonitoringError(ValueError):
    pass


def endpoints_for_domain(scope: DataScope, domain_id: UUID) -> QuerySet[CertificateEndpoint]:
    return (
        CertificateEndpoint.scoped.for_scope(scope)
        .filter(domain__entity_id=domain_id, archived_at__isnull=True)
        .select_related("entity", "domain", "hostname")
    )


@transaction.atomic
def create_certificate_endpoint(
    *,
    scope: DataScope,
    domain: RegisteredDomain,
    actor_id: UUID,
    protocol: str,
    hostname_id: UUID | None,
) -> CertificateEndpoint:
    if protocol not in CertificateEndpointProtocol.values:
        raise CertificateMonitoringError("The selected certificate protocol is unavailable.")
    hostname = None
    if hostname_id is not None:
        try:
            hostname = ManagedHostname.scoped.for_scope(scope).get(
                entity_id=hostname_id, domain=domain, archived_at__isnull=True
            )
        except ManagedHostname.DoesNotExist as exc:
            raise CertificateMonitoringError("The selected hostname is unavailable.") from exc
    target_name = hostname.ascii_name if hostname else domain.ascii_name
    if endpoints_for_domain(scope, domain.entity_id).filter(hostname=hostname, protocol=protocol).exists():
        raise CertificateMonitoringError("That certificate endpoint is already monitored.")
    entity = Entity.objects.create(
        tenant=domain.tenant,
        workspace=domain.workspace,
        organization=domain.organization,
        entity_type="certificate_endpoint",
        display_name=f"{protocol}://{target_name}:{protocol_port(protocol)}",
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    return CertificateEndpoint.objects.create(
        tenant=domain.tenant,
        workspace=domain.workspace,
        organization=domain.organization,
        entity=entity,
        domain=domain,
        hostname=hostname,
        protocol=protocol,
        port=protocol_port(protocol),
        created_by_id=actor_id,
    )


@transaction.atomic
def enqueue_certificate_monitoring(
    *, scope: DataScope, endpoint: CertificateEndpoint, requested_by_id: UUID | None, trigger: str
) -> CertificateMonitorRun:
    if trigger not in {"manual", "scheduled"}:
        raise CertificateMonitoringError("Unknown monitoring trigger.")
    endpoint = CertificateEndpoint.objects.select_for_update().get(pk=endpoint.pk)
    existing = (
        CertificateMonitorRun.scoped.for_scope(scope)
        .filter(endpoint=endpoint, state__in=(DomainMonitorRunState.PENDING, DomainMonitorRunState.PROCESSING))
        .order_by("created_at")
        .first()
    )
    if existing is not None:
        return existing
    run = CertificateMonitorRun.objects.create(
        tenant=endpoint.tenant,
        workspace=endpoint.workspace,
        organization=endpoint.organization,
        endpoint=endpoint,
        trigger=trigger,
        requested_by_id=requested_by_id,
    )
    endpoint.monitor_state = DomainMonitorState.QUEUED
    endpoint.monitor_error_code = ""
    endpoint.save(update_fields=("monitor_state", "monitor_error_code", "updated_at"))
    return run


def schedule_due_certificate_monitoring(*, scope: DataScope, now=None, limit: int = 100) -> int:  # type: ignore[no-untyped-def]
    current = now or timezone.now()
    endpoints = list(
        CertificateEndpoint.scoped.for_scope(scope)
        .filter(monitoring_enabled=True, archived_at__isnull=True, next_monitor_at__lte=current)
        .order_by("next_monitor_at", "id")[:limit]
    )
    for endpoint in endpoints:
        enqueue_certificate_monitoring(scope=scope, endpoint=endpoint, requested_by_id=None, trigger="scheduled")
    return len(endpoints)


def _create_alert(
    *,
    run: CertificateMonitorRun,
    kind: str,
    observed: datetime | None = None,
    prior: datetime | None = None,
) -> None:
    CertificateMonitorAlert.objects.get_or_create(
        run=run,
        kind=kind,
        defaults={
            "tenant": run.tenant,
            "workspace": run.workspace,
            "organization": run.organization,
            "endpoint": run.endpoint,
            "observed_not_after": observed,
            "prior_not_after": prior,
        },
    )


def _finish_success(*, run_id: UUID, evidence: CollectedCertificateEvidence, now) -> None:  # type: ignore[no-untyped-def]
    with transaction.atomic():
        run = CertificateMonitorRun.objects.select_for_update().select_related("endpoint").get(pk=run_id)
        endpoint = CertificateEndpoint.objects.select_for_update().get(pk=run.endpoint_id)
        previous = (
            CertificateMonitorRun.objects.filter(endpoint=endpoint, state=DomainMonitorRunState.SUCCEEDED)
            .exclude(pk=run.id)
            .order_by("-finished_at")
            .first()
        )
        run.state = DomainMonitorRunState.SUCCEEDED
        run.locked_at = None
        run.finished_at = now
        run.error_code = ""
        for field in (
            "leaf_sha256",
            "chain_sha256",
            "chain_length",
            "subject_common_name",
            "issuer_common_name",
            "serial_sha256",
            "san_sha256",
            "san_count",
            "not_before",
            "not_after",
            "hostname_valid",
            "trust_valid",
            "tls_version",
            "cipher_name",
        ):
            setattr(run, field, getattr(evidence, field))
        run.evidence_digest = canonical_evidence_digest(
            "certificate_monitor_run",
            {
                "leaf_sha256": run.leaf_sha256,
                "chain_sha256": run.chain_sha256,
                "chain_length": run.chain_length,
                "subject_common_name": run.subject_common_name,
                "issuer_common_name": run.issuer_common_name,
                "serial_sha256": run.serial_sha256,
                "san_sha256": run.san_sha256,
                "san_count": run.san_count,
                "not_before": run.not_before.isoformat() if run.not_before else None,
                "not_after": run.not_after.isoformat() if run.not_after else None,
                "hostname_valid": run.hostname_valid,
                "trust_valid": run.trust_valid,
                "tls_version": run.tls_version,
                "cipher_name": run.cipher_name,
            },
        )
        run.save()
        endpoint.last_monitor_at = now
        endpoint.next_monitor_at = now + timedelta(hours=endpoint.monitor_interval_hours)
        endpoint.monitor_state = DomainMonitorState.CURRENT
        endpoint.monitor_error_code = ""
        endpoint.current_leaf_sha256 = evidence.leaf_sha256
        endpoint.current_not_after = evidence.not_after
        endpoint.current_hostname_valid = evidence.hostname_valid
        endpoint.current_trust_valid = evidence.trust_valid
        endpoint.save(
            update_fields=(
                "last_monitor_at",
                "next_monitor_at",
                "monitor_state",
                "monitor_error_code",
                "current_leaf_sha256",
                "current_not_after",
                "current_hostname_valid",
                "current_trust_valid",
                "updated_at",
            )
        )
        if previous and previous.leaf_sha256 != evidence.leaf_sha256:
            _create_alert(
                run=run,
                kind=CertificateMonitorAlertKind.CERTIFICATE_CHANGED,
                observed=evidence.not_after,
                prior=previous.not_after,
            )
        if evidence.not_after <= now + EXPIRATION_ALERT_WINDOW:
            already_due = CertificateMonitorAlert.objects.filter(
                endpoint=endpoint,
                kind=CertificateMonitorAlertKind.EXPIRATION_DUE,
                observed_not_after=evidence.not_after,
            ).exists()
            if not already_due:
                _create_alert(run=run, kind=CertificateMonitorAlertKind.EXPIRATION_DUE, observed=evidence.not_after)
        if not evidence.hostname_valid or not evidence.trust_valid:
            previously_invalid = previous and (
                previous.leaf_sha256 == evidence.leaf_sha256
                and previous.hostname_valid == evidence.hostname_valid
                and previous.trust_valid == evidence.trust_valid
            )
            if not previously_invalid:
                _create_alert(run=run, kind=CertificateMonitorAlertKind.VALIDATION_FAILED, observed=evidence.not_after)


def _finish_failure(*, run_id: UUID, error_code: str, now) -> None:  # type: ignore[no-untyped-def]
    with transaction.atomic():
        run = CertificateMonitorRun.objects.select_for_update().select_related("endpoint").get(pk=run_id)
        endpoint = CertificateEndpoint.objects.select_for_update().get(pk=run.endpoint_id)
        run.state = DomainMonitorRunState.FAILED
        run.locked_at = None
        run.finished_at = now
        run.error_code = error_code[:64]
        run.save(update_fields=("state", "locked_at", "finished_at", "error_code"))
        endpoint.last_monitor_at = now
        endpoint.next_monitor_at = now + timedelta(hours=min(endpoint.monitor_interval_hours, 24))
        endpoint.monitor_state = DomainMonitorState.FAILED
        endpoint.monitor_error_code = error_code[:64]
        endpoint.save(
            update_fields=("last_monitor_at", "next_monitor_at", "monitor_state", "monitor_error_code", "updated_at")
        )
        _create_alert(run=run, kind=CertificateMonitorAlertKind.COLLECTION_FAILED)


def process_certificate_monitoring_run(
    *, run_id: UUID, collector: Collector = collect_certificate_evidence
) -> bool:
    now = timezone.now()
    with transaction.atomic():
        run = CertificateMonitorRun.objects.select_for_update().get(pk=run_id)
        endpoint = CertificateEndpoint.objects.select_related("hostname", "domain").get(pk=run.endpoint_id)
        if run.state == DomainMonitorRunState.PROCESSING and run.locked_at and run.locked_at > now - MONITORING_LEASE:
            return False
        if run.state not in {DomainMonitorRunState.PENDING, DomainMonitorRunState.PROCESSING}:
            return False
        run.state = DomainMonitorRunState.PROCESSING
        run.locked_at = now
        run.started_at = run.started_at or now
        run.attempts += 1
        run.save(update_fields=("state", "locked_at", "started_at", "attempts"))
        CertificateEndpoint.objects.filter(pk=run.endpoint_id).update(
            monitor_state=DomainMonitorState.RUNNING, monitor_error_code=""
        )
        hostname = endpoint.target_name
        protocol = endpoint.protocol
    try:
        evidence = collector(hostname, protocol)
    except CertificateCollectionError as exc:
        _finish_failure(run_id=run_id, error_code=str(exc) or "certificate_collection_failed", now=timezone.now())
        return False
    except Exception:
        _finish_failure(run_id=run_id, error_code="certificate_collection_failed", now=timezone.now())
        return False
    _finish_success(run_id=run_id, evidence=evidence, now=timezone.now())
    return True
