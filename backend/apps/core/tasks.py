from celery import shared_task

from .models import InstallationState
from .notification_email import dispatch_due_notification_emails
from .outbox import dispatch_due_outbox_events
from .rls import OrganizationRLSMode, rls_scope
from .scoping import DataScope
from .webhooks import dispatch_due_webhooks


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_outbox_events() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_outbox_events(tenant=installation.tenant)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_notification_emails() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_notification_emails(tenant=installation.tenant)


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_webhook_deliveries() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_webhooks(tenant=installation.tenant)
