from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .domain_monitoring_egress import CollectedDomainEvidence, DomainCollectionError, collect_domain_evidence
from .models import (
    DomainDNSObservation,
    DomainMonitorAlert,
    DomainMonitorAlertKind,
    DomainMonitorRun,
    DomainMonitorRunState,
    DomainMonitorState,
    DomainReviewEvent,
    DomainReviewState,
    RegisteredDomain,
)
from .scoping import DataScope

Collector = Callable[[str], CollectedDomainEvidence]
MONITORING_LEASE = timedelta(minutes=15)
EXPIRATION_ALERT_WINDOW = timedelta(days=90)


def monitoring_runs_for_domain(scope: DataScope, domain_id: UUID):  # type: ignore[no-untyped-def]
    return DomainMonitorRun.scoped.for_scope(scope).filter(domain__entity_id=domain_id)


@transaction.atomic
def enqueue_domain_monitoring(
    *, scope: DataScope, domain: RegisteredDomain, requested_by_id: UUID | None, trigger: str
) -> DomainMonitorRun:
    if trigger not in {"manual", "scheduled"}:
        raise ValueError("Unknown monitoring trigger.")
    domain = RegisteredDomain.objects.select_for_update().get(pk=domain.pk)
    existing = (
        DomainMonitorRun.scoped.for_scope(scope)
        .filter(domain=domain, state__in=(DomainMonitorRunState.PENDING, DomainMonitorRunState.PROCESSING))
        .order_by("created_at")
        .first()
    )
    if existing is not None:
        return existing
    run = DomainMonitorRun.objects.create(
        tenant=domain.tenant,
        workspace=domain.workspace,
        organization=domain.organization,
        domain=domain,
        trigger=trigger,
        requested_by_id=requested_by_id,
    )
    domain.monitor_state = DomainMonitorState.QUEUED
    domain.monitor_error_code = ""
    domain.save(update_fields=("monitor_state", "monitor_error_code", "updated_at"))
    return run


def schedule_due_domain_monitoring(*, scope: DataScope, now=None, limit: int = 100) -> int:  # type: ignore[no-untyped-def]
    current = now or timezone.now()
    domains = list(
        RegisteredDomain.scoped.for_scope(scope)
        .filter(monitoring_enabled=True, archived_at__isnull=True, next_monitor_at__lte=current)
        .order_by("next_monitor_at", "id")[:limit]
    )
    for domain in domains:
        enqueue_domain_monitoring(scope=scope, domain=domain, requested_by_id=None, trigger="scheduled")
    return len(domains)


def _review_state(domain: RegisteredDomain, observed: date | None) -> str:
    if observed is None:
        return DomainReviewState.STALE
    if domain.expiration_date is None or domain.expiration_date != observed:
        return DomainReviewState.CONFLICT
    return DomainReviewState.CURRENT


def _create_alert(
    *,
    run: DomainMonitorRun,
    kind: str,
    observed: date | None = None,
    prior: date | None = None,
) -> None:
    if kind == DomainMonitorAlertKind.EXPIRATION_DUE and DomainMonitorAlert.objects.filter(
        domain=run.domain,
        kind=kind,
        observed_expiration_date=observed,
    ).exists():
        return
    if kind == DomainMonitorAlertKind.EXPIRATION_CHANGED and DomainMonitorAlert.objects.filter(
        domain=run.domain,
        kind=kind,
        observed_expiration_date=observed,
        prior_expiration_date=prior,
    ).exists():
        return
    DomainMonitorAlert.objects.get_or_create(
        run=run,
        kind=kind,
        defaults={
            "tenant": run.tenant,
            "workspace": run.workspace,
            "organization": run.organization,
            "domain": run.domain,
            "observed_expiration_date": observed,
            "prior_expiration_date": prior,
        },
    )


def _finish_success(*, run_id: UUID, evidence: CollectedDomainEvidence, now) -> None:  # type: ignore[no-untyped-def]
    with transaction.atomic():
        run = DomainMonitorRun.objects.select_for_update().select_related("domain").get(pk=run_id)
        domain = RegisteredDomain.objects.select_for_update().get(pk=run.domain_id)
        previous = (
            DomainMonitorRun.objects.filter(domain=domain, state=DomainMonitorRunState.SUCCEEDED)
            .exclude(pk=run.id)
            .order_by("-finished_at")
            .first()
        )
        for answer in evidence.dns_answers[:500]:
            digest = hashlib.sha256(f"{answer.record_type}\0{answer.value}\0{answer.ttl or ''}".encode()).hexdigest()
            DomainDNSObservation.objects.create(
                tenant=domain.tenant,
                workspace=domain.workspace,
                organization=domain.organization,
                domain=domain,
                hostname=None,
                record_type=answer.record_type,
                value=answer.value,
                ttl=answer.ttl,
                provenance="discovered",
                source=evidence.dns_source,
                content_digest=digest,
                observed_at=now,
                recorded_by=None,
            )
        state = _review_state(domain, evidence.expiration_date)
        DomainReviewEvent.objects.create(
            tenant=domain.tenant,
            workspace=domain.workspace,
            organization=domain.organization,
            domain=domain,
            state=state,
            entered_expiration_date=domain.expiration_date,
            observed_expiration_date=evidence.expiration_date,
            source=evidence.rdap_source,
            note="",
            reviewed_by=None,
        )
        domain.review_state = state
        domain.observed_expiration_date = evidence.expiration_date
        domain.last_reviewed_at = now
        domain.last_monitor_at = now
        domain.next_monitor_at = now + timedelta(hours=domain.monitor_interval_hours)
        domain.monitor_state = DomainMonitorState.CURRENT
        domain.monitor_error_code = ""
        domain.save(
            update_fields=(
                "review_state",
                "observed_expiration_date",
                "last_reviewed_at",
                "last_monitor_at",
                "next_monitor_at",
                "monitor_state",
                "monitor_error_code",
                "updated_at",
            )
        )
        run.state = DomainMonitorRunState.SUCCEEDED
        run.locked_at = None
        run.finished_at = now
        run.error_code = ""
        run.rdap_source = evidence.rdap_source
        run.rdap_digest = evidence.rdap_digest
        run.observed_expiration_date = evidence.expiration_date
        run.observed_registrar = evidence.registrar
        run.dns_source = evidence.dns_source
        run.dns_digest = evidence.dns_digest
        run.dnssec_validated = evidence.dnssec_validated
        run.dns_record_count = len(evidence.dns_answers)
        run.save(
            update_fields=(
                "state",
                "locked_at",
                "finished_at",
                "error_code",
                "rdap_source",
                "rdap_digest",
                "observed_expiration_date",
                "observed_registrar",
                "dns_source",
                "dns_digest",
                "dnssec_validated",
                "dns_record_count",
            )
        )
        if previous and previous.observed_expiration_date != evidence.expiration_date:
            _create_alert(
                run=run,
                kind=DomainMonitorAlertKind.EXPIRATION_CHANGED,
                observed=evidence.expiration_date,
                prior=previous.observed_expiration_date,
            )
        if evidence.expiration_date and evidence.expiration_date <= (now + EXPIRATION_ALERT_WINDOW).date():
            _create_alert(run=run, kind=DomainMonitorAlertKind.EXPIRATION_DUE, observed=evidence.expiration_date)
        if previous and previous.dns_digest and previous.dns_digest != evidence.dns_digest:
            _create_alert(run=run, kind=DomainMonitorAlertKind.DNS_CHANGED)


def _finish_failure(*, run_id: UUID, error_code: str, now) -> None:  # type: ignore[no-untyped-def]
    with transaction.atomic():
        run = DomainMonitorRun.objects.select_for_update().select_related("domain").get(pk=run_id)
        domain = RegisteredDomain.objects.select_for_update().get(pk=run.domain_id)
        run.state = DomainMonitorRunState.FAILED
        run.locked_at = None
        run.finished_at = now
        run.error_code = error_code[:64]
        run.save(update_fields=("state", "locked_at", "finished_at", "error_code"))
        domain.last_monitor_at = now
        domain.next_monitor_at = now + timedelta(hours=min(domain.monitor_interval_hours, 24))
        domain.monitor_state = DomainMonitorState.FAILED
        domain.monitor_error_code = error_code[:64]
        domain.save(
            update_fields=("last_monitor_at", "next_monitor_at", "monitor_state", "monitor_error_code", "updated_at")
        )
        _create_alert(run=run, kind=DomainMonitorAlertKind.COLLECTION_FAILED)


def process_domain_monitoring_run(*, run_id: UUID, collector: Collector = collect_domain_evidence) -> bool:
    now = timezone.now()
    with transaction.atomic():
        run = DomainMonitorRun.objects.select_for_update().select_related("domain").get(pk=run_id)
        if run.state == DomainMonitorRunState.PROCESSING and run.locked_at and run.locked_at > now - MONITORING_LEASE:
            return False
        if run.state not in {DomainMonitorRunState.PENDING, DomainMonitorRunState.PROCESSING}:
            return False
        run.state = DomainMonitorRunState.PROCESSING
        run.locked_at = now
        run.started_at = run.started_at or now
        run.attempts += 1
        run.save(update_fields=("state", "locked_at", "started_at", "attempts"))
        RegisteredDomain.objects.filter(pk=run.domain_id).update(
            monitor_state=DomainMonitorState.RUNNING, monitor_error_code=""
        )
        ascii_name = run.domain.ascii_name
    try:
        evidence = collector(ascii_name)
    except DomainCollectionError as exc:
        _finish_failure(run_id=run_id, error_code=str(exc) or "collection_failed", now=timezone.now())
        return False
    except Exception:
        _finish_failure(run_id=run_id, error_code="collection_failed", now=timezone.now())
        return False
    _finish_success(run_id=run_id, evidence=evidence, now=timezone.now())
    return True
