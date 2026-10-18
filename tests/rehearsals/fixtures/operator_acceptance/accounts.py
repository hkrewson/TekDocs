import os
import json
import secrets
from pathlib import Path
from django.db import transaction
from django.conf import settings
from allauth.account.models import EmailAddress
from apps.accounts.models import (
    User,
    TenantMembership,
    BuiltInRole,
    MembershipWorkspaceScope,
    OrganizationAccessAssignment,
)
from apps.core.models import (
    InstallationState,
    IntegrationConnection,
    WebhookEndpoint,
    Organization,
)
from apps.core.rls import bind_local_rls_scope, OrganizationRLSMode, RLSPrincipalMode
from apps.core.scoping import DataScope

if os.environ.get("TEKDOCS_ACCEPTANCE_FIXTURE") != "isolated-disposable":
    raise RuntimeError("Acceptance fixtures require the isolated preparation command")
assert settings.TEKDOCS_PUBLIC_URL == os.environ["TEKDOCS_ACCEPTANCE_URL"]
manifest = json.loads(Path("/fixture/manifest.json").read_text())
state = InstallationState.objects.get()
tenant, owner = state.tenant, state.owner
assert tenant.name == "Acceptance MSP"
assert settings.EMAIL_HOST == "mailpit"
assert IntegrationConnection.objects.count() == 0
assert WebhookEndpoint.objects.count() == 0
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.tenant(tenant),
        organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )
    a = Organization.objects.get(tenant=tenant, entity__display_name="Acceptance A")
    b = Organization.objects.get(tenant=tenant, entity__display_name="Acceptance B")
    for org in (a, b):
        org.access_mode = "assigned_only"
        org.full_clean()
        org.save(update_fields=["access_mode"])
    for email, name, role, organization in [
        (
            "reviewer@acceptance.invalid",
            "Acceptance Reviewer",
            BuiltInRole.ADMINISTRATOR,
            None,
        ),
        (
            "reader-a@acceptance.invalid",
            "Acceptance A Reader",
            BuiltInRole.READ_ONLY,
            None,
        ),
        (
            "client-a@acceptance.invalid",
            "Acceptance A Client",
            BuiltInRole.CLIENT_USER,
            a,
        ),
    ]:
        if User.objects.filter(email=email).exists():
            continue
        password = secrets.token_urlsafe(28)
        user = User.objects.create_user(
            email=email, password=password, display_name=name
        )
        EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
        member = TenantMembership.objects.create(
            tenant=tenant,
            user=user,
            role=role,
            organization=organization,
            workspace_scope=(
                MembershipWorkspaceScope.ASSIGNED_ORGANIZATIONS
                if email == "reader-a@acceptance.invalid"
                else MembershipWorkspaceScope.TENANT
            ),
        )
        if role == BuiltInRole.READ_ONLY:
            OrganizationAccessAssignment.objects.create(
                tenant=tenant, organization=a, membership=member, created_by=owner
            )
        with Path("/fixture/access.txt").open("a") as f:
            f.write(f"\n{name}\nEmail: {email}\nPassword: {password}\n")
