from dataclasses import dataclass

from rest_framework.exceptions import APIException, PermissionDenied

from apps.core.models import InstallationState, Tenant

from .models import TenantMembership, User


class InstallationContextUnavailable(APIException):
    status_code = 503
    default_detail = "The authenticated installation context is unavailable."
    default_code = "authentication_context_unavailable"


@dataclass(frozen=True)
class InstallationMemberContext:
    state: InstallationState
    tenant: Tenant
    is_owner: bool


def require_installation_member(user: User) -> InstallationMemberContext:
    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    try:
        state = InstallationState.objects.select_related("tenant", "owner").get(
            pk=InstallationState.SINGLETON_ID,
            bootstrapped_at__isnull=False,
        )
    except InstallationState.DoesNotExist as exc:
        raise InstallationContextUnavailable() from exc
    if state.tenant is None:
        raise InstallationContextUnavailable()
    is_owner = state.owner_id == user.pk
    if not is_owner and not TenantMembership.objects.filter(tenant=state.tenant, user=user).exists():
        raise PermissionDenied("Installation membership is required.")
    return InstallationMemberContext(state=state, tenant=state.tenant, is_owner=is_owner)


def require_installation_owner(user: User) -> InstallationMemberContext:
    context = require_installation_member(user)
    if not context.is_owner:
        raise PermissionDenied("Installation ownership is required.")
    return context
