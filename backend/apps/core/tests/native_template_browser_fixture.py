"""Git-only source files for the real native template enrollment journey."""

import uuid

from apps.accounts.policy import require_installation_member
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_read import document_detail
from apps.core.models import Block, Document, Workspace
from apps.core.native_template_models import RepositoryTemplateEnrollment
from apps.core.organizations import create_organization
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.workspaces import resolve_organization_workspace


def prepare_native_template_browser_fixture(owner):
    member = require_installation_member(owner)
    organization = create_organization(
        tenant=member.tenant, actor_id=owner.id, name="Native template acceptance client",
        legal_name="", website="", classifications=["client"],
    )
    repository = ensure_workspace_repository(Workspace.objects.get(
        tenant=member.tenant, organization__isnull=True,
    )).repository
    fragments = {}
    for mode in ("copy", "live", "pinned"):
        repository.refresh_from_db()
        content_id = uuid.uuid4()
        source = author_content(
            repository=repository, actor_id=owner.id, request_id=None, operation="create",
            content_id=content_id, base_commit=repository.accepted_commit.object_id,
            base_blob=None, kind="fragment", path=f"fragments/native-template-{mode}.md",
            title=f"Native template {mode} section", markdown=f"Native {mode} original.\n",
            metadata_patch={},
        )
        fragments[mode] = {"id": str(source.content_id), "title": source.title}
    repository.refresh_from_db()
    source = author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation="create",
        content_id=uuid.uuid4(), base_commit=repository.accepted_commit.object_id,
        base_blob=None, kind="document", path="docs/native-template-browser.md",
        title="Native browser template", markdown="Native template introduction.\n",
        metadata_patch={"includes": [
            {"id": item["id"], "mode": "live", "audience": "shared"} for item in fragments.values()
        ]},
    )
    ids = [source.content_id, *(uuid.UUID(item["id"]) for item in fragments.values())]
    assert not Document.objects.filter(pk__in=ids).exists()
    assert not Block.objects.filter(pk__in=ids).exists()
    return {"organization_id": str(organization.entity_id), "source_id": str(source.content_id),
            "fragments": fragments}


def verify_native_template_browser_fixture(fixture, owner):
    member = require_installation_member(owner)
    reader = resolve_organization_workspace(owner, entity_id=uuid.UUID(fixture['organization_id']))
    workspace = Workspace.objects.get(tenant=member.tenant, organization=reader.organization)
    enrollment = RepositoryTemplateEnrollment.objects.select_related('repository').get(
        tenant=member.tenant, workspace=workspace,
    )
    root = read_authored_content(repository=enrollment.repository, content_id=enrollment.content_id)
    assert root.title == 'Native browser enrolled document'
    assert root.markdown == 'Native enrolled local introduction.\n'
    assert [item['mode'] for item in enrollment.placement_map] == ['copy', 'copy', 'pinned']
    assert not Document.objects.filter(tenant=member.tenant, pk=enrollment.content_id).exists()
    local_ids = [item['local_id'] for item in enrollment.placement_map if item['mode'] == 'copy']
    assert not Block.objects.filter(tenant=member.tenant, pk__in=local_ids).exists()
    html = document_detail(workspace=reader, content_id=enrollment.content_id, audience='all')['sanitized_html']
    for retained in ('Native enrolled local introduction.', 'Native copied local edit.',
                     'Native live updated.', 'Native pinned newest.'):
        assert retained in html
    assert 'Native live after detach.' not in html and 'Native copy updated.' not in html
