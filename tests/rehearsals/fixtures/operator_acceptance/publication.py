"""Create local-only retained client evidence through the normal workflow API."""

import os
import json
import secrets
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.test import Client
from django.urls import reverse
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from apps.accounts.models import (
    User,
    TenantMembership,
    OrganizationAccessAssignment,
    BuiltInRole,
)
from apps.core.models import (
    InstallationState,
    Organization,
    RepositoryStaticPublication,
)
from apps.core.rls import bind_local_rls_scope, OrganizationRLSMode, RLSPrincipalMode
from apps.core.scoping import DataScope

if os.environ.get("TEKDOCS_ACCEPTANCE_FIXTURE") != "isolated-disposable":
    raise RuntimeError("Acceptance fixtures require the isolated preparation command")
assert settings.TEKDOCS_PUBLIC_URL == os.environ["TEKDOCS_ACCEPTANCE_URL"]
manifest = json.loads(Path("/fixture/manifest.json").read_text())
row = manifest["workspaces"][1]
state = InstallationState.objects.get()
assert state.tenant.name == "Acceptance MSP"
assert not RepositoryStaticPublication.objects.exists(), (
    "Do not duplicate the retained fixture"
)
org = Organization.objects.get(entity_id=row["organization_entity_id"])
password = secrets.token_urlsafe(32)
actors = []
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.tenant(state.tenant),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=state.owner_id,
        principal_mode=RLSPrincipalMode.USER,
    )
    for name in ("publisher", "reviewer", "authorizer"):
        user = User.objects.create_user(
            email=f"fixture-{name}@acceptance.invalid",
            password=password,
            display_name=f"Fixture {name} (automated preparation only)",
        )
        member = TenantMembership.objects.create(
            tenant=state.tenant, user=user, role=BuiltInRole.ADMINISTRATOR
        )
        OrganizationAccessAssignment.objects.create(
            tenant=state.tenant,
            organization=org,
            membership=member,
            created_by=state.owner,
        )
        TOTP.activate(user, generate_totp_secret())
        actors.append(user)
browser = Client(HTTP_HOST="localhost")


def post(name, args, value=None):
    response = browser.post(
        reverse(name, args=args),
        data=json.dumps(value or {}),
        content_type="application/json",
    )
    assert response.status_code == 201, (
        name,
        response.status_code,
        "Fixture request failed; response body withheld",
    )
    return response.json()


browser.force_login(actors[0])
evidence = post(
    "organization-repository-publication-evidence",
    [org.entity_id],
    {"content_id": row["document_ids"][0], "audience": "client_visible"},
)
args = [org.entity_id, evidence["id"]]
browser.force_login(actors[1])
post(
    "organization-repository-publication-evidence-decision",
    args,
    {"outcome": "accepted_for_packaging", "reason": "Local acceptance fixture review"},
)
post("organization-repository-publication-evidence-package", args)
browser.force_login(actors[2])
post(
    "organization-repository-publication-evidence-package-authorization",
    args,
    {
        "outcome": "authorized_for_publication",
        "reason": "Local acceptance fixture authorization",
    },
)
browser.force_login(actors[1])
publication = post(
    "organization-repository-publication-evidence-static-publication", args
)
browser.force_login(actors[2])
post(
    "organization-repository-publication-evidence-static-control",
    args,
    {"action": "released", "reason": "Local acceptance fixture release"},
)
response = browser.post(
    "/_allauth/browser/v1/auth/reauthenticate",
    data=json.dumps({"password": password}),
    content_type="application/json",
)
assert response.status_code == 200, response.status_code
post(
    "organization-repository-publication-evidence-static-delivery",
    args,
    {"reason": "Local acceptance portal fixture; no outbound delivery workers"},
)
browser.force_login(User.objects.get(email="client-a@acceptance.invalid"))
detail = browser.get(
    reverse("client-portal-repository-publication-detail", args=[publication["id"]])
)
assert detail.status_code == 200, detail.status_code
pdf = browser.get(
    reverse("client-portal-repository-publication-pdf", args=[publication["id"]])
)
assert pdf.status_code == 200, pdf.status_code
Path("/fixture/publication.json").write_text(
    json.dumps(
        {
            "publication_id": publication["id"],
            "evidence_id": evidence["id"],
            "document": "Acceptance A Runbook 01",
            "client_detail_status": detail.status_code,
            "client_pdf_status": pdf.status_code,
            "prepared_through": "normal workflow APIs; distinct fixture actors; real password reauthentication",
        },
        indent=2,
    )
    + "\n"
)
print(
    "Retained A publication released and authorized locally; A client detail and PDF passed."
)
