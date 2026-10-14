import os
import json
import uuid
from pathlib import Path
from django.db import transaction
from django.conf import settings
from django.test import RequestFactory
from apps.core.models import (
    InstallationState,
    IntegrationConnection,
    WebhookEndpoint,
    WorkspaceRepository,
    ClientAsset,
    CommercialContract,
    NetworkSubnet,
    ContentNode,
    Document,
    DocumentAttachment,
    Organization,
)
from apps.accounts.models import (
    TenantMembership,
    BuiltInRole,
    OrganizationAccessAssignment,
)
from apps.core.rls import bind_local_rls_scope, OrganizationRLSMode, RLSPrincipalMode
from apps.core.scoping import DataScope
from apps.core.repository_service import read_accepted_repository_file
from apps.core.content_authoring import read_authored_content
from apps.core.repository_portal_views import (
    ClientPortalRepositoryPublicationDetailView,
    ClientPortalRepositoryPublicationPDFView,
    ClientPortalRepositoryPublicationAttachmentView,
)

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
    assert a.access_mode == b.access_mode == "assigned_only"
    reader = TenantMembership.objects.get(
        tenant=tenant,
        user__email="reader-a@acceptance.invalid",
        role=BuiltInRole.READ_ONLY,
    )
    assert set(
        OrganizationAccessAssignment.objects.filter(membership=reader).values_list(
            "organization_id", flat=True
        )
    ) == {a.id}
    client_member = TenantMembership.objects.select_related("user").get(
        tenant=tenant,
        user__email="client-a@acceptance.invalid",
        role=BuiltInRole.CLIENT_USER,
        organization=a,
    )
    assert TenantMembership.objects.filter(
        tenant=tenant,
        user__email="reviewer@acceptance.invalid",
        role=BuiltInRole.ADMINISTRATOR,
    ).exists()
    publication = json.loads(Path("/fixture/publication.json").read_text())
    # Call the current read-only portal handlers and their policy checks without
    # creating login sessions, audit writes or modifying the fixture state.
    request = RequestFactory().get("/")
    request.user = client_member.user
    publication_id = uuid.UUID(publication["publication_id"])
    detail = ClientPortalRepositoryPublicationDetailView().get(request, publication_id)
    if detail.status_code != 200:
        raise RuntimeError("Current client publication is unavailable")
    pdf = ClientPortalRepositoryPublicationPDFView().get(request, publication_id)
    if pdf.status_code != 200 or not pdf.content:
        raise RuntimeError("Current retained PDF is unavailable")
    descriptors = [
        *detail.data["attachments"],
        *detail.data["primary_file"]["versions"],
    ]
    if len(detail.data["primary_file"]["versions"]) != 2:
        raise RuntimeError("Expected both retained primary-file versions")
    for descriptor in descriptors:
        download = ClientPortalRepositoryPublicationAttachmentView().get(
            request, publication_id, uuid.UUID(str(descriptor["id"]))
        )
        if download.status_code != 200 or not download.content:
            raise RuntimeError("Current retained file is unavailable")
results = []
for row in manifest["workspaces"]:
    repo = WorkspaceRepository.objects.select_related(
        "workspace__organization", "tenant", "accepted_commit", "indexed_commit"
    ).get(pk=row["repository_id"])
    org = repo.workspace.organization
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.owner(tenant, org),
            organization_mode=OrganizationRLSMode.ORGANIZATION
            if org
            else OrganizationRLSMode.MSP_ONLY,
            actor_user_id=owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        counts = {
            name: model.objects.filter(tenant=tenant, organization=org).count()
            for name, model in [
                ("assets", ClientAsset),
                ("contracts", CommercialContract),
                ("networks", NetworkSubnet),
            ]
        }
        assert all(count == 30 for count in counts.values()), counts
        assert ContentNode.objects.filter(repository=repo).count() == 31
        assert repo.accepted_commit_id == repo.indexed_commit_id
        content = read_authored_content(
            repository=repo, content_id=uuid.UUID(row["document_ids"][0])
        )
        assert read_accepted_repository_file(repository_id=repo.id, path=content.path)
        assert not Document.objects.filter(
            id=row["document_ids"][0], tenant=tenant, organization=org
        ).exists()
        files = DocumentAttachment.objects.filter(owner_workspace=repo.workspace)
        assert files.count() == 32
        for item in files:
            import hashlib

            with item.file.storage.open(item.file.name, "rb") as stored:
                assert hashlib.sha256(stored.read()).hexdigest() == item.checksum
        counts.update(git_documents=30, fragments=1, managed_files=32)
        results.append(
            {
                "workspace": row["name"],
                "counts": counts,
                "git_only": True,
                "accepted_equals_indexed": True,
                "file_checksums": "verified",
            }
        )
report = {
    "status": "fixture technical checks passed",
    "email": "Mailpit only",
    "integration_connections": 0,
    "webhook_endpoints": 0,
    "workspaces": results,
    "pending": [
        "Human MFA enrollment",
        "Interactive operator walkthrough",
        "Imported NetBox provenance fixture",
        "Controlled outage exercise",
    ],
}
Path("/fixture/verification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
