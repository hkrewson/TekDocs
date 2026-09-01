from datetime import timedelta
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from .certificate_monitoring import process_certificate_monitoring_run, schedule_due_certificate_monitoring
from .document_sources import fetch_remote_document
from .domain_monitoring import process_domain_monitoring_run, schedule_due_domain_monitoring
from .imports import purge_expired_import_staging
from .integrations import process_sync_job, purge_integration_logs, schedule_due_connections
from .models import (
    CertificateMonitorRun,
    DocumentRemoteSource,
    DomainMonitorRun,
    DomainMonitorRunState,
    InstallationState,
    IntegrationJobState,
    IntegrationSyncJob,
    Workspace,
)
from .notification_email import dispatch_due_notification_emails
from .outbox import dispatch_due_outbox_events
from .rls import OrganizationRLSMode, system_rls_scope
from .scoping import DataScope
from .webhooks import dispatch_due_webhooks

INTEGRATION_DISPATCH_LEASE = timedelta(minutes=2)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def process_remote_document_source(
    source_id: str, tenant_id: str, workspace_id: str, organization_id: str | None
) -> None:
    scope = DataScope(UUID(tenant_id), UUID(workspace_id), UUID(organization_id) if organization_id else None)
    mode = OrganizationRLSMode.ORGANIZATION if scope.organization_id else OrganizationRLSMode.MSP_ONLY
    with system_rls_scope(scope, organization_mode=mode):
        fetch_remote_document(DocumentRemoteSource.scoped.for_scope(scope).get(id=UUID(source_id), enabled=True))


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def schedule_remote_document_sources() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            source_ids = list(
                DocumentRemoteSource.scoped.for_scope(scope)
                .filter(enabled=True, archived_at__isnull=True, next_check_at__lte=timezone.now())
                .order_by("next_check_at", "id")
                .values_list("id", flat=True)[:25]
            )
            DocumentRemoteSource.scoped.for_scope(scope).filter(id__in=source_ids).update(
                next_check_at=timezone.now() + INTEGRATION_DISPATCH_LEASE
            )
            for source_id in source_ids:
                process_remote_document_source.delay(
                    str(source_id),
                    str(scope.tenant_id),
                    str(scope.workspace_id),
                    str(scope.organization_id) if scope.organization_id else None,
                )
                total += 1
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_outbox_events() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with system_rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_outbox_events(tenant=installation.tenant)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_notification_emails() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with system_rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_notification_emails(tenant=installation.tenant)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_webhook_deliveries() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with system_rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_webhooks(tenant=installation.tenant)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def schedule_integration_syncs() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            total += schedule_due_connections(tenant=installation.tenant, scope=scope)
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def process_integration_sync_job(job_id: str, tenant_id: str, workspace_id: str, organization_id: str | None) -> None:
    scope = DataScope(
        tenant_id=UUID(tenant_id),
        workspace_id=UUID(workspace_id),
        organization_id=UUID(organization_id) if organization_id else None,
    )
    mode = OrganizationRLSMode.ORGANIZATION if scope.organization_id else OrganizationRLSMode.MSP_ONLY
    with system_rls_scope(scope, organization_mode=mode):
        process_sync_job(job_id=UUID(job_id))


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_integration_syncs() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            now = timezone.now()
            job_ids = list(
                IntegrationSyncJob.scoped.for_scope(scope)
                .filter(state=IntegrationJobState.PENDING, available_at__lte=now)
                .order_by("available_at", "created_at")
                .values_list("id", flat=True)[:25]
            )
            IntegrationSyncJob.scoped.for_scope(scope).filter(id__in=job_ids).update(
                available_at=now + INTEGRATION_DISPATCH_LEASE
            )
            for job_id in job_ids:
                process_integration_sync_job.delay(
                    str(job_id),
                    str(scope.tenant_id),
                    str(scope.workspace_id),
                    str(scope.organization_id) if scope.organization_id else None,
                )
                total += 1
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def purge_expired_integration_logs() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            total += purge_integration_logs(tenant=installation.tenant)
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def purge_expired_import_rows() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            total += purge_expired_import_staging()
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def schedule_domain_monitoring() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            total += schedule_due_domain_monitoring(scope=scope)
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def process_domain_monitoring(run_id: str, tenant_id: str, workspace_id: str, organization_id: str | None) -> None:
    scope = DataScope(UUID(tenant_id), UUID(workspace_id), UUID(organization_id) if organization_id else None)
    mode = OrganizationRLSMode.ORGANIZATION if scope.organization_id else OrganizationRLSMode.MSP_ONLY
    with system_rls_scope(scope, organization_mode=mode):
        process_domain_monitoring_run(run_id=UUID(run_id))


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_domain_monitoring() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            run_ids = list(
                DomainMonitorRun.scoped.for_scope(scope)
                .filter(state=DomainMonitorRunState.PENDING, available_at__lte=timezone.now())
                .order_by("available_at", "created_at")
                .values_list("id", flat=True)[:25]
            )
            DomainMonitorRun.scoped.for_scope(scope).filter(id__in=run_ids).update(
                available_at=timezone.now() + INTEGRATION_DISPATCH_LEASE
            )
            for run_id in run_ids:
                process_domain_monitoring.delay(
                    str(run_id),
                    str(scope.tenant_id),
                    str(scope.workspace_id),
                    str(scope.organization_id) if scope.organization_id else None,
                )
                total += 1
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def schedule_certificate_monitoring() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            total += schedule_due_certificate_monitoring(scope=scope)
    return total


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def process_certificate_monitoring(run_id: str, tenant_id: str, workspace_id: str, organization_id: str | None) -> None:
    scope = DataScope(UUID(tenant_id), UUID(workspace_id), UUID(organization_id) if organization_id else None)
    mode = OrganizationRLSMode.ORGANIZATION if scope.organization_id else OrganizationRLSMode.MSP_ONLY
    with system_rls_scope(scope, organization_mode=mode):
        process_certificate_monitoring_run(run_id=UUID(run_id))


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_certificate_monitoring() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    total = 0
    for workspace in Workspace.objects.filter(tenant=installation.tenant).order_by("id"):
        scope = DataScope(installation.tenant.id, workspace.id, workspace.organization_id)
        mode = OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
        with system_rls_scope(scope, organization_mode=mode):
            run_ids = list(
                CertificateMonitorRun.scoped.for_scope(scope)
                .filter(state=DomainMonitorRunState.PENDING, available_at__lte=timezone.now())
                .order_by("available_at", "created_at")
                .values_list("id", flat=True)[:25]
            )
            CertificateMonitorRun.scoped.for_scope(scope).filter(id__in=run_ids).update(
                available_at=timezone.now() + INTEGRATION_DISPATCH_LEASE
            )
            for run_id in run_ids:
                process_certificate_monitoring.delay(
                    str(run_id),
                    str(scope.tenant_id),
                    str(scope.workspace_id),
                    str(scope.organization_id) if scope.organization_id else None,
                )
                total += 1
    return total
