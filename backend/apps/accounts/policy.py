from dataclasses import dataclass

from rest_framework.exceptions import APIException, PermissionDenied

from apps.core.models import InstallationState, Tenant

from .models import User


class InstallationContextUnavailable(APIException):
    status_code = 503
    default_detail = "The authenticated installation context is unavailable."
    default_code = "authentication_context_unavailable"


@dataclass(frozen=True)
class InstallationOwnerContext:
    state: InstallationState
    tenant: Tenant


def require_installation_owner(user: User) -> InstallationOwnerContext:
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    try:
        state = InstallationState.objects.select_related("tenant", "owner").get(
            pk=InstallationState.SINGLETON_ID,
            bootstrapped_at__isnull=False,
        )
    except InstallationState.DoesNotExist as exc:
        raise InstallationContextUnavailable() from exc
    if state.tenant is None or state.owner_id != user.pk:
        raise PermissionDenied("Installation ownership is required.")
    return InstallationOwnerContext(state=state, tenant=state.tenant)
