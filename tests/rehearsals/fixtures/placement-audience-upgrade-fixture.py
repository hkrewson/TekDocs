import os


def organization_workspace(user, organization):  # type: ignore[no-untyped-def]
    from apps.accounts.policy import require_installation_member
    from apps.core.scoping import DataScope
    from apps.core.workspaces import ResolvedWorkspace

    member = require_installation_member(user)
    return ResolvedWorkspace(
        member=member,
        kind="organization",
        id=organization.entity_id,
        name=organization.entity.display_name,
        data_scope=DataScope.organization(member.tenant, organization),
        classifications=("client",),
        capabilities=("documentation",),
        organization=organization,
    )


def create_fixture():
    from apps.accounts.bootstrap import bootstrap_owner
    from apps.core.documents import create_document
    from apps.core.organizations import create_organization
    from apps.core.publications import publish_document, verify_publication
    from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, system_rls_scope
    from apps.core.scoping import DataScope

    result = bootstrap_owner(
        tenant_name="Placement Audience Upgrade MSP",
        owner_email="placement-audience-upgrade@example.invalid",
        owner_display_name="Placement Audience Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with system_rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Exact 0.8.39 Audience Client",
            legal_name="Exact 0.8.39 Audience Client, LLC",
            website="",
            classifications=["client"],
        )
        workspace = organization_workspace(result.owner, client)
        bind_local_rls_scope(
            DataScope.organization(result.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        document = create_document(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Audience upgrade runbook",
            markdown="Shared before upgrade.",
        )
        publication = publish_document(
            workspace=workspace,
            document=document,
            actor_id=result.owner.id,
            reason="Retain exact 0.8.39 evidence",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v3"
        assert all(verify_publication(publication).values())
        print("Exact 0.8.39 placement and signed publication fixture created")


def verify_fixture():
    from apps.core.documents import create_document_block
    from apps.core.models import Document, DocumentPublication, InstallationState, Organization
    from apps.core.publications import publish_document, verify_publication
    from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, system_rls_scope
    from apps.core.scoping import DataScope

    state = InstallationState.objects.select_related("tenant", "owner").get(pk=1)
    with system_rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = Organization.objects.get(entity__display_name="Exact 0.8.39 Audience Client")
        workspace = organization_workspace(state.owner, client)
        bind_local_rls_scope(
            DataScope.organization(state.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        document = Document.objects.get(entity__display_name="Audience upgrade runbook")
        primary = document.placements.get(parent__isnull=True, position=0)
        assert primary.audience_profile == "shared"

        retained = DocumentPublication.objects.get(reason="Retain exact 0.8.39 evidence")
        assert retained.manifest["format"] == "tekdocs-static-publication/v3"
        assert all(verify_publication(retained).values())

        internal = create_document_block(
            document=document,
            actor_id=state.owner.id,
            markdown="MSP-UPGRADE-SENTINEL",
            kind="rich_text",
            name="MSP-only upgrade section",
            parent_id=None,
            position=None,
            audience_profile="msp_internal",
        )
        client_only = create_document_block(
            document=document,
            actor_id=state.owner.id,
            markdown="CLIENT-UPGRADE-SENTINEL",
            kind="rich_text",
            name="Client-only upgrade section",
            parent_id=None,
            position=None,
            audience_profile="client_visible",
        )
        client_publication = publish_document(
            workspace=workspace,
            document=document,
            actor_id=state.owner.id,
            reason="Client audience after upgrade",
            audience="client_visible",
            retention="permanent",
            retention_review_on=None,
        )
        msp_publication = publish_document(
            workspace=workspace,
            document=document,
            actor_id=state.owner.id,
            reason="MSP audience after upgrade",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert client_publication.manifest["format"] == "tekdocs-static-publication/v4"
        assert msp_publication.manifest["format"] == "tekdocs-static-publication/v4"
        assert "MSP-UPGRADE-SENTINEL" not in client_publication.canonical_markdown
        assert str(internal.id) not in str(client_publication.manifest)
        assert "CLIENT-UPGRADE-SENTINEL" not in msp_publication.canonical_markdown
        assert str(client_only.id) not in str(msp_publication.manifest)
        assert all(verify_publication(client_publication).values())
        assert all(verify_publication(msp_publication).values())
        print("0.8.39 evidence and 0.8.40 audience isolation survived the 0.8.41 production-image upgrade")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
