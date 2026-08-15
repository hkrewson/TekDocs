import os
from datetime import timedelta


def create_fixture():
    from apps.accounts.bootstrap import bootstrap_owner
    from apps.accounts.models import Invitation, TenantMembership
    from django.utils import timezone

    result = bootstrap_owner(
        tenant_name="Portal Upgrade MSP",
        owner_email="portal-upgrade@example.invalid",
        owner_display_name="Portal Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    membership = TenantMembership.objects.get(tenant=result.tenant, user=result.owner)
    invitation = Invitation.objects.create(
        tenant=result.tenant,
        email="retained-staff-invite@example.invalid",
        token_digest=Invitation.digest_token("retained-upgrade-token"),
        invited_by=result.owner,
        expires_at=timezone.now() + timedelta(days=1),
    )
    print(membership.id, invitation.id)


def verify_fixture():
    from apps.accounts.models import BuiltInRole, Invitation, TenantMembership

    membership = TenantMembership.objects.get(user__email="portal-upgrade@example.invalid")
    invitation = Invitation.objects.get(email="retained-staff-invite@example.invalid")
    assert membership.organization_id is None
    assert invitation.organization_id is None
    assert invitation.role == BuiltInRole.READ_ONLY
    print("Historical MSP membership and invitation retained without client scope")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
