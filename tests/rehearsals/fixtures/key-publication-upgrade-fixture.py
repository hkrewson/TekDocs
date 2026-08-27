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
    from apps.core.models import (
        DocumentKeyBinding,
        PublicationAudience,
        PublicationRetention,
        workspace_for_owner,
    )
    from apps.core.organizations import create_organization
    from apps.core.publications import publish_document, verify_publication
    from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, system_rls_scope
    from apps.core.scoping import DataScope

    result = bootstrap_owner(
        tenant_name="Key Publication Upgrade MSP",
        owner_email="key-publication-upgrade@example.invalid",
        owner_display_name="Key Publication Upgrade Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with system_rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name="Exact 0.8.38 Client",
            legal_name="Exact 0.8.38 Client, LLC",
            website="",
            classifications=["client"],
        )
        workspace = organization_workspace(result.owner, client)
        bind_local_rls_scope(
            DataScope.organization(result.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        retained = create_document(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Retained 0.8.38 publication",
            markdown="# Retained publication\n\nCreated by 0.8.38.\n",
        )
        publication = publish_document(
            workspace=workspace,
            document=retained,
            actor_id=result.owner.id,
            reason="Retain exact-prior signed evidence",
            audience=PublicationAudience.MSP_INTERNAL,
            retention=PublicationRetention.PERMANENT,
            retention_review_on=None,
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v2"
        assert all(verify_publication(publication).values())

        keyed = create_document(
            tenant=result.tenant,
            organization=client,
            actor_id=result.owner.id,
            title="Upgrade key runbook",
            markdown="Before upgrade.\n\n<tekdocs://key/procedure.content>\n",
        )
        source_block = retained.placements.get(parent__isnull=True).block
        DocumentKeyBinding.objects.create(
            tenant=result.tenant,
            workspace=workspace_for_owner(tenant=result.tenant, organization=client),
            organization=client,
            document=keyed,
            name="procedure",
            target_entity=source_block.entity,
            created_by=result.owner,
        )
        print("Exact 0.8.38 fixture created")


def verify_fixture():
    from apps.core.document_exports import (
        export_bundle,
        export_docx,
        export_html,
        export_pdf,
        resolve_export_snapshot,
    )
    from apps.core.models import Document, DocumentPublication, InstallationState, Organization
    from apps.core.publications import publish_document, verify_publication
    from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope, system_rls_scope
    from apps.core.scoping import DataScope

    state = InstallationState.objects.select_related("tenant", "owner").get(pk=1)
    with system_rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        client = Organization.objects.get(entity__display_name="Exact 0.8.38 Client")
        workspace = organization_workspace(state.owner, client)
        bind_local_rls_scope(
            DataScope.organization(state.tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
        )
        retained = DocumentPublication.objects.get(title="Retained 0.8.38 publication")
        assert retained.manifest["format"] == "tekdocs-static-publication/v2"
        assert all(verify_publication(retained).values())

        document = Document.objects.get(entity__display_name="Upgrade key runbook")
        snapshot = resolve_export_snapshot(workspace=workspace, document=document)
        assert "<tekdocs://key/" not in snapshot.markdown
        assert "# Retained publication" in snapshot.markdown
        assert "Created by 0.8.38." in snapshot.markdown
        assert snapshot.manifest["format"] == "tekdocs-portable-document/v2"
        assert snapshot.manifest["key_resolutions"][0]["value"] == (
            "# Retained publication\n\nCreated by 0.8.38.\n"
        )
        assert b"Created by 0.8.38." in export_html(
            title=snapshot.title,
            markdown=snapshot.markdown,
            retained_html=snapshot.sanitized_html,
        )
        assert export_pdf(title=snapshot.title, markdown=snapshot.markdown).startswith(b"%PDF-")
        assert export_docx(title=snapshot.title, markdown=snapshot.markdown).startswith(b"PK")
        assert export_bundle(snapshot).startswith(b"PK")

        publication = publish_document(
            workspace=workspace,
            document=document,
            actor_id=state.owner.id,
            reason="Prove key freeze after exact-prior upgrade",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v3"
        assert publication.canonical_markdown == snapshot.markdown
        assert publication.manifest["key_resolutions"][0]["kind"] == "content"
        assert all(verify_publication(publication).values())
        print("Prior v2 evidence and new v3 resolved output survived the production-image upgrade")


mode = os.environ.get("TEKDOCS_FIXTURE_MODE")
if mode == "create":
    create_fixture()
elif mode == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
