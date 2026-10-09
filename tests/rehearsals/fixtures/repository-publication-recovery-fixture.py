"""Exercise a released repository publication across encrypted recovery."""

import hashlib
import json
import os
import uuid

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.db import transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.models import Organization, RepositoryStaticPublication
from apps.core.repository_static_delivery import repository_static_delivery_ready
from apps.core.repository_static_publications import verify_repository_static_publication
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


OWNER_EMAIL = "validation-recovery@example.invalid"
ORGANIZATION_NAME = "Validation Recovery Client"
DOCUMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.organization.document")
REVIEWER_EMAIL = "publication-recovery-reviewer@example.invalid"
AUTHORIZER_EMAIL = "publication-recovery-authorizer@example.invalid"
CLIENT_EMAIL = "publication-recovery-client@example.invalid"


def _post(browser, url, value=None):
    response = browser.post(
        url, data=json.dumps(value) if value is not None else None,
        content_type="application/json", secure=True,
    )
    assert response.status_code == 201, (url, response.status_code, response.content)
    return response.json()


def _portal_snapshot(browser, publication_id):
    list_response = browser.get(reverse("client-portal-repository-publication-list"), secure=True)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["results"]] == [str(publication_id)]
    detail = browser.get(reverse("client-portal-repository-publication-detail", args=[publication_id]), secure=True)
    assert detail.status_code == 200
    assert detail["Cache-Control"] == "private, no-store"
    assert "Client enrollment" in detail.json()["rendered_html"]
    assert detail.json()["attachments"] == []
    pdf = browser.get(reverse("client-portal-repository-publication-pdf", args=[publication_id]), secure=True)
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf["Cache-Control"] == "private, no-store"
    return (
        hashlib.sha256(detail.json()["rendered_html"].encode()).hexdigest(),
        hashlib.sha256(pdf.content).hexdigest(),
    )


owner = User.objects.get(email=OWNER_EMAIL)
tenant = owner.tenant_memberships.get(organization__isnull=True).tenant
with transaction.atomic():
    bind_local_rls_scope(
        DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id, principal_mode=RLSPrincipalMode.USER,
    )
    organization = Organization.objects.get(tenant=tenant, entity__display_name=ORGANIZATION_NAME)
mode = os.environ.get("TEKDOCS_RECOVERY_PUBLICATION_MODE")
browser = Client(HTTP_HOST="localhost")

if mode == "create":
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=owner.id, principal_mode=RLSPrincipalMode.USER,
        )
        actors = []
        for email, name in ((REVIEWER_EMAIL, "Reviewer"), (AUTHORIZER_EMAIL, "Authorizer")):
            actor = User.objects.create_user(email=email, display_name=name)
            membership = TenantMembership.objects.create(tenant=tenant, user=actor, role=BuiltInRole.ADMINISTRATOR)
            OrganizationAccessAssignment.objects.create(
                tenant=tenant, organization=organization, membership=membership, created_by=owner
            )
            actors.append(actor)
        client = User.objects.create_user(email=CLIENT_EMAIL, display_name="Client")
        TenantMembership.objects.create(
            tenant=tenant, user=client, role=BuiltInRole.CLIENT_USER, organization=organization
        )
        for actor in (owner, *actors):
            Authenticator.objects.create(
                user=actor, type=Authenticator.Type.TOTP, data={"secret": generate_totp_secret()}
            )
    reviewer, authorizer = actors
    evidence_url = reverse("organization-repository-publication-evidence", args=[organization.entity_id])
    browser.force_login(owner)
    evidence = _post(
        browser, evidence_url, {"content_id": str(DOCUMENT_ID), "audience": "client_visible"}
    )
    evidence_id = evidence["id"]
    decision_url = reverse(
        "organization-repository-publication-evidence-decision", args=[organization.entity_id, evidence_id]
    )
    package_url = reverse(
        "organization-repository-publication-evidence-package", args=[organization.entity_id, evidence_id]
    )
    authorization_url = reverse(
        "organization-repository-publication-evidence-package-authorization",
        args=[organization.entity_id, evidence_id],
    )
    static_url = reverse(
        "organization-repository-publication-evidence-static-publication", args=[organization.entity_id, evidence_id]
    )
    control_url = reverse(
        "organization-repository-publication-evidence-static-control", args=[organization.entity_id, evidence_id]
    )
    delivery_url = reverse(
        "organization-repository-publication-evidence-static-delivery", args=[organization.entity_id, evidence_id]
    )
    browser.force_login(reviewer)
    _post(browser, decision_url, {"outcome": "accepted_for_packaging", "reason": "Recovery fixture review"})
    _post(browser, package_url)
    browser.force_login(authorizer)
    _post(
        browser,
        authorization_url,
        {"outcome": "authorized_for_publication", "reason": "Recovery fixture authorization"},
    )
    browser.force_login(reviewer)
    publication = _post(browser, static_url)
    browser.force_login(authorizer)
    _post(browser, control_url, {"action": "released", "reason": "Recovery fixture release"})
    _post(browser, delivery_url, {"reason": "Recovery fixture delivery"})
    publication_id = uuid.UUID(publication["id"])
    browser.force_login(client)
    html_sha, pdf_sha = _portal_snapshot(browser, publication_id)
    print(f"REPOSITORY_PUBLICATION_ID={publication_id}")
    print(f"REPOSITORY_PUBLICATION_HTML_SHA256={html_sha}")
    print(f"REPOSITORY_PUBLICATION_PDF_SHA256={pdf_sha}")
    print("Released repository publication recovery fixture created")
elif mode == "verify":
    publication_id = uuid.UUID(os.environ["TEKDOCS_RECOVERY_PUBLICATION_ID"])
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(tenant, organization), organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=owner.id, principal_mode=RLSPrincipalMode.USER,
        )
        publication = RepositoryStaticPublication.objects.get(
            pk=publication_id, tenant=tenant, organization=organization,
        )
        assert verify_repository_static_publication(publication)
        assert repository_static_delivery_ready(publication)
    client = User.objects.get(email=CLIENT_EMAIL)
    browser.force_login(client)
    html_sha, pdf_sha = _portal_snapshot(browser, publication_id)
    assert html_sha == os.environ["TEKDOCS_RECOVERY_PUBLICATION_HTML_SHA256"]
    assert pdf_sha == os.environ["TEKDOCS_RECOVERY_PUBLICATION_PDF_SHA256"]
    print("Signed released publication, client HTML, and retained PDF restored")
else:
    raise RuntimeError("TEKDOCS_RECOVERY_PUBLICATION_MODE must be create or verify")
