from django.http import HttpRequest

from apps.core.models import AuditEvent, InstallationState

from .models import TenantMembership, User


def record_auth_event(*, action: str, request: HttpRequest | None = None, user: User | None = None) -> AuditEvent:
    """Record an authentication event without credentials or client identifiers."""

    state = InstallationState.objects.select_related("tenant", "owner").filter(
        pk=InstallationState.SINGLETON_ID,
        bootstrapped_at__isnull=False,
    ).first()
    tenant = None
    actor = None
    if state is not None and state.tenant is not None:
        tenant = state.tenant
        if user is not None and (
            state.owner_id == user.pk or TenantMembership.scoped.for_tenant(tenant).filter(user=user).exists()
        ):
            actor = user
    return AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        action=action,
        request_id=getattr(request, "request_id", None),
        metadata={},
    )
