from __future__ import annotations

import uuid

import pytest
from django.db import transaction
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import content_composition, repository_service, repository_storage
from apps.core.content_composition import ContentCompositionError, ContentCompositionResolver
from apps.core.content_index import ContentIndexValidationError, content_graph_projection, index_repository_content
from apps.core.content_profile import parse_content
from apps.core.models import (
    ContentInclude,
    ContentNode,
    ContentTemplateSource,
    InstallationState,
    Tenant,
    Workspace,
    WorkspaceKind,
)
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope

pytestmark = pytest.mark.django_db(transaction=True)


def _content(
    *,
    content_id: uuid.UUID,
    title: str,
    body: str,
    kind: str = "document",
    metadata: str = "",
) -> bytes:
    return (
        f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: {kind}\ntitle: {title}\n{metadata}---\n{body}"
    ).encode()


def _include(*, content_id: uuid.UUID, mode: str, audience: str, commit: str = "") -> str:
    value = f"  - id: {content_id}\n    mode: {mode}\n    audience: {audience}\n"
    return value + (f"    commit: {commit}\n" if commit else "")


@pytest.fixture
def composition_repository(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Composition MSP",
            owner_email="composition-owner@example.invalid",
            owner_display_name="Composition Owner",
            password="CompositionPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        yield installation, workspace, repository


def _accepted(repository) -> str | None:  # type: ignore[no-untyped-def]
    repository.refresh_from_db()
    return repository.accepted_commit.object_id if repository.accepted_commit_id else None


def test_file_backed_composition_preserves_pins_audiences_copy_provenance_and_template_preview(
    composition_repository, django_runtime_role,
):
    installation, _workspace, repository = composition_repository
    source_id = uuid.uuid4()
    nested_id = uuid.uuid4()
    internal_id = uuid.uuid4()
    client_id = uuid.uuid4()
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "fragments/source.md": _content(
                content_id=source_id,
                title="Source fragment",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="shared"),
                body="Pinned source v1.\n",
            ),
            "fragments/nested.md": _content(
                content_id=nested_id,
                title="Nested fragment",
                kind="fragment",
                body="Nested v1.\n",
            ),
            "fragments/internal.md": _content(
                content_id=internal_id, title="Internal", kind="fragment", body="Internal only.\n"
            ),
            "fragments/client.md": _content(
                content_id=client_id, title="Client", kind="fragment", body="Client only.\n"
            ),
        },
        message="Add reusable fragment sources",
    )

    document_id = uuid.uuid4()
    audience_document_id = uuid.uuid4()
    copied_id = uuid.uuid4()
    template_id = uuid.uuid4()
    second = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "fragments/source.md": _content(
                content_id=source_id,
                title="Source fragment",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=nested_id, mode="live", audience="shared"),
                body="Live source v2.\n",
            ),
            "docs/pinned-guide.md": _content(
                content_id=document_id,
                title="Pinned guide",
                metadata=(
                    "includes:\n"
                    + _include(content_id=source_id, mode="pinned", audience="shared", commit=first.object_id)
                ),
                body="Guide introduction.\n",
            ),
            "docs/audience-guide.md": _content(
                content_id=audience_document_id,
                title="Audience guide",
                metadata=(
                    "includes:\n"
                    + _include(content_id=internal_id, mode="live", audience="msp_internal")
                    + _include(content_id=client_id, mode="live", audience="client_visible")
                ),
                body="Shared introduction.\n",
            ),
            "fragments/copied.md": _content(
                content_id=copied_id,
                title="Independent copy",
                kind="fragment",
                metadata=f"derived_from:\n  id: {source_id}\n  commit: {first.object_id}\n",
                body="Customized independent copy.\n",
            ),
            "docs/template.md": _content(
                content_id=template_id,
                title="Template",
                metadata=f"template_sources:\n  - id: {source_id}\n    commit: {first.object_id}\n",
                body="Template introduction.\n",
            ),
        },
        message="Compose reusable fragments",
    )

    result = index_repository_content(repository_id=repository.id)
    repository.refresh_from_db()
    projection = content_graph_projection(repository=repository)

    assert result.object_id == second.object_id
    pinned = next(node for node in projection["nodes"] if node["id"] == str(document_id))
    assert pinned["composition"]["markdown"] == "Guide introduction.\n\nPinned source v1.\n\nNested v1.\n"
    assert pinned["includes"][0]["resolved_commit"] == first.object_id
    assert pinned["includes"][0]["mode"] == "pinned"
    source = next(node for node in projection["nodes"] if node["id"] == str(source_id))
    assert source["included_by"] == [str(document_id)]
    copied = next(node for node in projection["nodes"] if node["id"] == str(copied_id))
    assert copied["derived_from"] == {"id": str(source_id), "commit": first.object_id}
    assert "Pinned source v1." not in copied["composition"]["markdown"]
    template = next(node for node in projection["nodes"] if node["id"] == str(template_id))
    assert template["template_sources"][0]["state"] == "changed"
    assert "Pinned source v1." in template["template_sources"][0]["change_preview"]
    assert "Live source v2." in template["template_sources"][0]["change_preview"]
    assert ContentTemplateSource.objects.get(template__content_id=template_id).current_content_digest
    assert ContentInclude.objects.get(source__content_id=document_id).resolved_content_digest

    foreign_tenant = Tenant.objects.create(name="Other composition MSP", slug=f"other-{uuid.uuid4()}")
    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(installation.tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
        )
        assert ContentInclude.objects.count() > 0
        assert ContentTemplateSource.objects.count() == 1
        bind_local_rls_scope(DataScope.tenant(foreign_tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)
        assert ContentInclude.objects.count() == 0
        assert ContentTemplateSource.objects.count() == 0

    browser = Client()
    browser.force_login(installation.owner)
    internal_response = browser.get(reverse("msp-content-graph"), {"audience": "msp_internal"})
    client_response = browser.get(reverse("msp-content-graph"), {"audience": "client_visible"})
    internal = next(node for node in internal_response.json()["nodes"] if node["id"] == str(audience_document_id))
    client = next(node for node in client_response.json()["nodes"] if node["id"] == str(audience_document_id))
    assert internal["composition"]["markdown"] == "Shared introduction.\n\nInternal only.\n"
    assert client["composition"]["markdown"] == "Shared introduction.\n\nClient only.\n"

    rebuilt = index_repository_content(repository_id=repository.id, force=True)
    repository.refresh_from_db()
    assert rebuilt.projection_digest == result.projection_digest
    assert content_graph_projection(repository=repository) == projection


def test_cycle_rejection_retains_the_last_known_good_composition(composition_repository):
    _installation, _workspace, repository = composition_repository
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    document_id = uuid.uuid4()
    valid = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                metadata="includes:\n" + _include(content_id=first_id, mode="live", audience="shared"),
                body="Guide.\n",
            ),
            "fragments/first.md": _content(content_id=first_id, title="First", kind="fragment", body="First.\n"),
            "fragments/second.md": _content(content_id=second_id, title="Second", kind="fragment", body="Second.\n"),
        },
        message="Add valid composition",
    )
    index_repository_content(repository_id=repository.id)
    before = ContentNode.objects.get(repository=repository, content_id=document_id).composition_variants
    invalid = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=valid.object_id,
        changes={
            "fragments/first.md": _content(
                content_id=first_id,
                title="First",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=second_id, mode="live", audience="shared"),
                body="First.\n",
            ),
            "fragments/second.md": _content(
                content_id=second_id,
                title="Second",
                kind="fragment",
                metadata="includes:\n" + _include(content_id=first_id, mode="live", audience="shared"),
                body="Second.\n",
            ),
        },
        message="Introduce a composition cycle",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)

    repository.refresh_from_db()
    assert repository.indexed_commit.object_id == valid.object_id
    assert ContentNode.objects.get(repository=repository, content_id=document_id).composition_variants == before
    assert {item["code"] for item in captured.value.diagnostics} == {"include.cycle"}
    assert invalid.object_id not in str(captured.value.diagnostics)


def test_composition_limits_reject_excessive_depth_and_expanded_size(monkeypatch):
    ids = [uuid.uuid4() for _ in range(4)]
    sources = {}
    for index, content_id in enumerate(ids):
        metadata = ""
        if index + 1 < len(ids):
            metadata = "includes:\n" + _include(content_id=ids[index + 1], mode="live", audience="shared")
        sources[content_id] = parse_content(
            _content(content_id=content_id, title=f"Fragment {index}", kind="fragment", metadata=metadata, body="x\n")
        )
    resolver = ContentCompositionResolver(accepted_object_id="a" * 40, accepted=sources, loader=lambda _value: {})
    monkeypatch.setattr(content_composition, "MAX_COMPOSITION_DEPTH", 2)
    with pytest.raises(ContentCompositionError, match="depth") as depth:
        resolver.resolve(content_id=ids[0], audience=None)
    assert depth.value.code == "include.depth"

    target_id = uuid.uuid4()
    document_id = uuid.uuid4()
    target = parse_content(_content(content_id=target_id, title="Large", kind="fragment", body="x" * 40))
    document = parse_content(
        _content(
            content_id=document_id,
            title="Repeated",
            metadata=(
                "includes:\n"
                + _include(content_id=target_id, mode="live", audience="shared")
                + _include(content_id=target_id, mode="live", audience="shared")
            ),
            body="root\n",
        )
    )
    monkeypatch.setattr(content_composition, "MAX_COMPOSITION_DEPTH", 12)
    monkeypatch.setattr(content_composition, "MAX_EXPANDED_BYTES", 64)
    size_resolver = ContentCompositionResolver(
        accepted_object_id="a" * 40,
        accepted={document_id: document, target_id: target},
        loader=lambda _value: {},
    )
    with pytest.raises(ContentCompositionError, match="size") as size:
        size_resolver.resolve(content_id=document_id, audience=None)
    assert size.value.code == "include.size"


def test_rollback_is_a_new_commit_that_restores_the_prior_composition(composition_repository):
    _installation, _workspace, repository = composition_repository
    fragment_id = uuid.uuid4()
    document_id = uuid.uuid4()
    original_document = _content(
        content_id=document_id,
        title="Guide",
        metadata="includes:\n" + _include(content_id=fragment_id, mode="live", audience="shared"),
        body="Introduction.\n",
    )
    first = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": original_document,
            "fragments/steps.md": _content(
                content_id=fragment_id, title="Steps", kind="fragment", body="Original steps.\n"
            ),
        },
        message="Add original composition",
    )
    index_repository_content(repository_id=repository.id)
    original_digest = ContentNode.objects.get(content_id=document_id).composition_variants["all"]["digest"]
    changed = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=first.object_id,
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                body="Temporary standalone content.\n",
            )
        },
        message="Temporarily remove reuse",
    )
    index_repository_content(repository_id=repository.id)
    rollback = repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=changed.object_id,
        changes={"docs/guide.md": original_document},
        message="Restore prior composition",
    )
    index_repository_content(repository_id=repository.id)

    restored = ContentNode.objects.get(content_id=document_id).composition_variants["all"]
    assert rollback.object_id not in {first.object_id, changed.object_id}
    assert restored["digest"] != original_digest
    assert restored["markdown"] == "Introduction.\n\nOriginal steps.\n"
    assert restored["manifest"][0]["commit"] == rollback.object_id


def test_pinned_include_cannot_resolve_a_commit_from_another_repository(composition_repository):
    _installation, _workspace, repository = composition_repository
    foreign_tenant = Tenant.objects.create(name="Foreign MSP", slug=f"foreign-{uuid.uuid4()}")
    foreign_workspace = Workspace.objects.get(tenant=foreign_tenant, kind=WorkspaceKind.MSP)
    foreign_repository = repository_storage.ensure_workspace_repository(foreign_workspace).repository
    foreign_id = uuid.uuid4()
    foreign = repository_service.commit_repository_files(
        repository_id=foreign_repository.id,
        expected_base=_accepted(foreign_repository),
        changes={
            "fragments/private.md": _content(
                content_id=foreign_id,
                title="Private foreign fragment",
                kind="fragment",
                body="Foreign private content.\n",
            )
        },
        message="Add foreign fragment",
    )
    document_id = uuid.uuid4()
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/guide.md": _content(
                content_id=document_id,
                title="Guide",
                metadata=(
                    "includes:\n"
                    + _include(
                        content_id=foreign_id,
                        mode="pinned",
                        audience="shared",
                        commit=foreign.object_id,
                    )
                ),
                body="Guide.\n",
            )
        },
        message="Attempt foreign reuse",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)

    diagnostics = list(captured.value.diagnostics)
    assert diagnostics[0]["code"] == "include.commit.unavailable"
    assert "Private foreign fragment" not in str(diagnostics)
    assert "Foreign private content" not in str(diagnostics)
    assert foreign.object_id not in str(diagnostics)


def test_fragment_identity_requires_the_reserved_repository_directory(composition_repository):
    _installation, _workspace, repository = composition_repository
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=_accepted(repository),
        changes={
            "docs/misplaced.md": _content(
                content_id=uuid.uuid4(),
                title="Misplaced fragment",
                kind="fragment",
                body="Fragment content.\n",
            )
        },
        message="Add misplaced fragment",
    )

    with pytest.raises(ContentIndexValidationError) as captured:
        index_repository_content(repository_id=repository.id)
    assert any(item["code"] == "content.path.fragment" for item in captured.value.diagnostics)


def test_client_portal_cannot_read_raw_repository_content_or_internal_fragments(composition_repository):
    installation, _workspace, _repository = composition_repository
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Composition Client",
        legal_name="Composition Client LLC",
        website="",
        classifications=["client"],
    )
    client_user = User.objects.create_user(
        email="composition-client@example.invalid", display_name="Composition Client Reader"
    )
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=client_user,
        role=BuiltInRole.CLIENT_USER,
        organization=organization,
    )
    browser = Client()
    browser.force_login(client_user)
    url = reverse("organization-content-graph", args=[organization.entity_id])

    for audience in ("all", "msp_internal", "client_visible"):
        response = browser.get(url, {"audience": audience})
        assert response.status_code == 403
        assert b"composition" not in response.content
    assert browser.post(url, data={"force": True}, content_type="application/json").status_code == 403
