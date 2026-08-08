from dataclasses import dataclass

from allauth.mfa.models import Authenticator
from rest_framework.exceptions import APIException, PermissionDenied

from apps.core.models import InstallationState, Tenant
from apps.core.scoping import DataScope

from .models import TenantMembership, User


class InstallationContextUnavailable(APIException):
    status_code = 503
    default_detail = "The authenticated installation context is unavailable."
    default_code = "authentication_context_unavailable"


class PrivilegedMFARequired(PermissionDenied):
    default_detail = "Two-factor authentication is required for privileged actions."
    default_code = "privileged_mfa_required"


@dataclass(frozen=True)
class InstallationMemberContext:
    state: InstallationState
    tenant: Tenant
    is_owner: bool

    @property
    def data_scope(self) -> DataScope:
        return DataScope.tenant(self.tenant)


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
    if not is_owner and not TenantMembership.scoped.for_tenant(state.tenant).filter(user=user).exists():
        raise PermissionDenied("Installation membership is required.")
    return InstallationMemberContext(state=state, tenant=state.tenant, is_owner=is_owner)


def require_installation_owner(user: User) -> InstallationMemberContext:
    context = require_installation_member(user)
    if not context.is_owner:
        raise PermissionDenied("Installation ownership is required.")
    if not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
        raise PrivilegedMFARequired()
    return context
