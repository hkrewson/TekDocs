from dataclasses import dataclass

from allauth.account.models import EmailAddress
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import APIException

from apps.core.models import AuditEvent, InstallationState, Tenant

from .models import User


class BootstrapConflict(APIException):
    status_code = 409
    default_detail = "This installation cannot be bootstrapped."
    default_code = "bootstrap_conflict"


@dataclass(frozen=True)
class BootstrapResult:
    tenant: Tenant
    owner: User


def bootstrap_owner(*, tenant_name: str, owner_email: str, owner_display_name: str, password: str) -> BootstrapResult:
    """Create the installation tenant and owner while holding the singleton row lock."""

    with transaction.atomic():
        try:
            state = InstallationState.objects.select_for_update().get(pk=InstallationState.SINGLETON_ID)
        except InstallationState.DoesNotExist as exc:
            raise BootstrapConflict("Installation state is unavailable; apply database migrations.") from exc

        if state.is_bootstrapped:
            raise BootstrapConflict("This installation has already been bootstrapped.")
        if Tenant.objects.exists() or User.objects.exists():
            raise BootstrapConflict("Bootstrap requires an installation with no existing tenants or users.")

        tenant = Tenant.objects.create(name=tenant_name, slug=slugify(tenant_name)[:80] or "msp")
        owner = User.objects.create_user(
            email=owner_email,
            password=password,
            display_name=owner_display_name,
        )
        EmailAddress.objects.create(user=owner, email=owner.email, primary=True, verified=True)
        state.tenant = tenant
        state.owner = owner
        state.bootstrapped_at = timezone.now()
        state.full_clean()
        state.save(update_fields=["tenant", "owner", "bootstrapped_at"])
        AuditEvent.objects.create(
            tenant=tenant,
            actor=owner,
            action="installation.owner_bootstrapped",
            metadata={"method": "deployment_token"},
        )

    return BootstrapResult(tenant=tenant, owner=owner)
