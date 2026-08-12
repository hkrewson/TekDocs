from celery import shared_task

from .models import InstallationState
from .outbox import dispatch_due_outbox_events
from .rls import OrganizationRLSMode, rls_scope
from .scoping import DataScope


@shared_task(ignore_result=True)  # type: ignore[untyped-decorator]
def dispatch_outbox_events() -> int:
    installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
    if installation.tenant is None:
        return 0
    with rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        return dispatch_due_outbox_events(tenant=installation.tenant)
