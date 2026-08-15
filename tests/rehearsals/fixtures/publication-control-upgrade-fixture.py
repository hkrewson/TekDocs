import os


def create_fixture():
    from apps.accounts.bootstrap import bootstrap_owner
    from apps.core.documents import create_document
    from apps.core.models import PublicationAudience, PublicationRetention
    from apps.core.organizations import create_organization
    from apps.core.publications import publish_document
    from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, rls_scope
    from apps.core.scoping import DataScope
    from apps.core.workspaces import resolve_organization_workspace

    result = bootstrap_owner(
        tenant_name="Publication Upgrade MSP",
        owner_email="publication-upgrade@example.invalid",
        owner_display_name="Publication Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Publication Upgrade Client",
            legal_name="Publication Upgrade Client, LLC",
            website="",
            classifications=["client"],
        )
        bind_local_rls_scope(
            DataScope.organization(result.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        document = create_document(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Retained client publication",
            markdown="# Retained publication\n\nApproved before 0.5.1.\n",
        )
        publication = publish_document(
            workspace=resolve_organization_workspace(result.owner, entity_id=client.entity_id),
            document=document,
            actor_id=result.owner.id,
            reason="Historical client distribution",
            audience=PublicationAudience.CLIENT_VISIBLE,
            retention=PublicationRetention.PERMANENT,
            retention_review_on=None,
        )
        print(publication.entity_id)


def verify_fixture():
    from apps.core.models import (
        DocumentPublication,
        DocumentPublicationControlEvent,
        InstallationState,
        Organization,
    )
    from apps.core.rls import OrganizationRLSMode, rls_scope
    from apps.core.scoping import DataScope
    from apps.core.serializers import DocumentPublicationSerializer

    tenant = InstallationState.objects.select_related("tenant").get(pk=1).tenant
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = Organization.objects.get(entity__display_name="Publication Upgrade Client")
    with rls_scope(
        DataScope.organization(tenant, client),
        organization_mode=OrganizationRLSMode.ORGANIZATION,
    ):
        publication = DocumentPublication.objects.get(title="Retained client publication")
        events = list(
            DocumentPublicationControlEvent.objects.filter(publication=publication)
            .order_by("occurred_at", "id")
            .values_list("action", flat=True)
        )
        assert events == ["submitted", "approved"]
        assert publication.lifecycle_state == "published"
        projection = DocumentPublicationSerializer(publication).data["audience_projections"]
        assert projection[1] == {
            "audience": "client_portal",
            "available": True,
            "state": "available",
        }
        assert publication.control_events.count() == 2
        print("Historical publication retained approved audience availability")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
