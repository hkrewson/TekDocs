import secrets

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.documents import create_document
from apps.core.models import (
    DocumentPublicationControlEvent,
    Entity,
    EntityVisibility,
    InstallationState,
    PublicationAudience,
    PublicationControlAction,
    PublicationRetention,
)
from apps.core.organizations import create_organization
from apps.core.publications import PublicationConflict, approve_publication, publish_document, withdraw_publication
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def portal_publications(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Portal Documents MSP",
        owner_email="portal-doc-owner@example.invalid",
        owner_display_name="Portal Document Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Published Client",
            legal_name="Published Client, LLC",
            website="",
            classifications=["client"],
        )
        sibling = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Sibling Client",
            legal_name="Sibling Client, LLC",
            website="",
            classifications=["client"],
        )
        portal_user = User.objects.create_user(email="reader@example.invalid", display_name="Client Reader")
        TenantMembership.objects.create(
            tenant=result.tenant,
            user=portal_user,
            role=BuiltInRole.CLIENT_USER,
            organization=organization,
        )
        approver = User.objects.create_user(email="approver@example.invalid", display_name="Approver")
        TenantMembership.objects.create(tenant=result.tenant, user=approver, role=BuiltInRole.ADMINISTRATOR)

    def publication_for(target, title: str):  # type: ignore[no-untyped-def]
        with rls_scope(
            DataScope.organization(result.tenant, target),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        ):
            document = create_document(
                tenant=result.tenant,
                organization=target,
                actor_id=result.owner.id,
                title=title,
                markdown=f"# {title}\n\nApproved client content.",
            )
            return publish_document(
                workspace=resolve_organization_workspace(result.owner, entity_id=target.entity_id),
                document=document,
                actor_id=result.owner.id,
                reason="Client distribution",
                audience=PublicationAudience.CLIENT_VISIBLE,
                retention=PublicationRetention.PERMANENT,
                retention_review_on=None,
            )

    available = publication_for(organization, "Available guide")
    pending = publication_for(organization, "Pending guide")
    withdrawn = publication_for(organization, "Withdrawn guide")
    sibling_publication = publication_for(sibling, "Sibling secret")
    with rls_scope(
        DataScope.organization(result.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        private_entity = Entity.objects.create(
            tenant=result.tenant,
            workspace=organization.ownership_workspace,
            organization=organization,
            entity_type="network_device",
            display_name="Private infrastructure",
            visibility=EntityVisibility.MSP_PRIVATE,
        )
        unsafe_document = create_document(
            tenant=result.tenant,
            organization=organization,
            actor_id=result.owner.id,
            title="Unsafe reference guide",
            markdown=f"[Private infrastructure](tekdocs://entity/{private_entity.id})",
        )
        unsafe = publish_document(
            workspace=resolve_organization_workspace(result.owner, entity_id=organization.entity_id),
            document=unsafe_document,
            actor_id=result.owner.id,
            reason="Contains a private projection",
            audience=PublicationAudience.CLIENT_VISIBLE,
            retention=PublicationRetention.PERMANENT,
            retention_review_on=None,
        )
    with rls_scope(
        DataScope.organization(result.tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        approve_publication(publication=available, actor_id=approver.id, reason="Approved for client")
        with pytest.raises(PublicationConflict, match="client-visible records"):
            approve_publication(publication=unsafe, actor_id=approver.id, reason="Unsafe projection")
        DocumentPublicationControlEvent.objects.create(
            tenant=result.tenant,
            organization=organization,
            publication=unsafe,
            action=PublicationControlAction.APPROVED,
            actor=approver,
            reason="Simulated historical approval before the portal projection gate",
        )
        approve_publication(publication=withdrawn, actor_id=approver.id, reason="Approved then withdrawn")
        withdraw_publication(publication=withdrawn, actor_id=approver.id, reason="No longer current")
    with rls_scope(
        DataScope.organization(result.tenant, sibling),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        approve_publication(publication=sibling_publication, actor_id=approver.id, reason="Sibling approval")
    return result, organization, portal_user, available, pending, withdrawn, sibling_publication, unsafe


@pytest.mark.django_db
def test_portal_lists_only_current_approved_exact_client_publications(portal_publications):  # type: ignore[no-untyped-def]
    result, _organization, portal_user, available, pending, withdrawn, sibling, unsafe = portal_publications
    client = Client()
    client.force_login(portal_user)

    listing = client.get(reverse("client-portal-document-list"))
    assert listing.status_code == 200
    assert [record["title"] for record in listing.json()["results"]] == ["Available guide"]
    assert listing.json()["results"][0]["visibility"] == "client_visible"

    detail = client.get(reverse("client-portal-document-detail", kwargs={"publication_entity_id": available.entity_id}))
    assert detail.status_code == 200
    assert "Approved client content" in detail.json()["sanitized_html"]
    artifact = detail.json()["artifacts"][0]
    downloaded = client.get(
        reverse(
            "client-portal-document-artifact-download",
            kwargs={"publication_entity_id": available.entity_id, "artifact_entity_id": artifact["id"]},
        )
    )
    assert downloaded.status_code == 200
    assert downloaded["Cache-Control"] == "private, no-store"
    assert downloaded["Content-Type"] == "application/octet-stream"

    for hidden in (pending, withdrawn, sibling, unsafe):
        assert (
            client.get(
                reverse("client-portal-document-detail", kwargs={"publication_entity_id": hidden.entity_id})
            ).status_code
            == 404
        )

    msp = Client()
    msp.force_login(result.owner)
    assert msp.get(reverse("client-portal-document-list")).status_code == 403
