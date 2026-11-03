"""The document library includes newly authored Git content without legacy rows."""

import uuid

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.content_authoring import author_content
from apps.core.documents import create_document
from apps.core.tests.test_content_authoring import _create
from apps.core.tests.test_content_authoring import authoring_context as _authoring_context

discovery_context = _authoring_context

pytestmark = pytest.mark.django_db(transaction=True)


def test_library_lists_legacy_and_native_documents_without_fragments(discovery_context):
    installation, repository = discovery_context
    old = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Zulu older instructions", markdown="Retained original instructions.\n",
    )
    native = _create(installation, repository, title="Alpha native instructions")
    repository.refresh_from_db()
    fragment_id = uuid.uuid4()
    author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="create", content_id=fragment_id, base_commit=repository.accepted_commit.object_id,
        base_blob=None, kind="fragment", path=None, title="Independent fragment",
        markdown="Not a document.\n", metadata_patch={},
    )
    browser = Client()
    browser.force_login(installation.owner)
    for route in ("msp-document-search", "msp-document-list-create"):
        response = browser.get(reverse(route))
        assert response.status_code == 200, response.content
        assert response.json()["count"] == 2
        assert [row["title"] for row in response.json()["results"]] == [
            "Alpha native instructions", "Zulu older instructions",
        ]
        rows = {row["content_id"]: row for row in response.json()["results"]}
        assert set(rows) == {str(old.id), str(native.content_id)}
        assert rows[str(native.content_id)]["repository_native"] is True
        assert rows[str(native.content_id)]["content_authority"] == "repository"
        assert rows[str(native.content_id)]["title"] == "Alpha native instructions"
        assert rows[str(old.id)]["id"] == str(old.entity_id)


def test_native_search_filters_facets_and_pagination(discovery_context):
    installation, repository = discovery_context
    native = _create(installation, repository, title="Native zulu")
    repository.refresh_from_db()
    author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=native.content_id, base_commit=native.accepted_commit,
        base_blob=native.source_blob, kind=None, path=None, title=None,
        markdown="Distinctive repair instructions.\n", metadata_patch={
            "properties": {"category": "runbook", "collection": "Repairs", "tags": ["native"]},
        },
    )
    _create(installation, repository, title="Native alpha")
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-document-search")
    page = browser.get(url, {"page_size": 1}).json()
    assert page["count"] == 2 and page["has_more"] is True
    assert page["results"][0]["title"] == "Native alpha"
    second = browser.get(url, {"page_size": 1, "page": 2}).json()
    assert second["results"][0]["content_id"] == str(native.content_id)
    assert second["has_more"] is False
    for filters in ({"q": "Distinctive repair"}, {"collection": "repairs"}, {"tag": "native"}):
        data = browser.get(url, filters).json()
        assert data["count"] == 1
        assert data["results"][0]["content_id"] == str(native.content_id)
        assert data["collections"] == [{"value": "Repairs", "count": 1}]
        assert data["tags"] == [{"value": "native", "count": 1}]
    for filters in ({"owner_id": str(installation.owner.id)}, {"review_state": "approved"},
                    {"exclude_document": str(native.content_id), "q": "Distinctive"}):
        assert browser.get(url, filters).json()["count"] == 0


def test_native_discovery_refuses_stale_projection(discovery_context):
    installation, repository = discovery_context
    _create(installation, repository)
    repository.refresh_from_db()
    repository.indexed_commit = None
    repository.save(update_fields=("indexed_commit",))
    browser = Client()
    browser.force_login(installation.owner)
    for route in ("msp-document-search", "msp-document-list-create"):
        assert browser.get(reverse(route)).status_code == 409


def test_native_discovery_is_scoped_and_not_client_publication(discovery_context, django_runtime_role):
    from apps.accounts.models import BuiltInRole, TenantMembership, User
    from apps.core import repository_storage
    from apps.core.models import Tenant, Workspace
    from apps.core.organizations import create_organization

    installation, repository = discovery_context
    _create(installation, repository, title="MSP private guide")
    organizations = [create_organization(
        tenant=installation.tenant, actor_id=installation.owner.id, name=name,
        legal_name=name, website="", classifications=["client"],
    ) for name in ("Selected audit client", "Sibling audit client")]
    for organization in organizations:
        owned = repository_storage.ensure_workspace_repository(
            Workspace.objects.get(organization=organization)
        ).repository
        _create(installation, owned, title=organization.entity.display_name)
    browser = Client()
    browser.force_login(installation.owner)
    with django_runtime_role():
        assert browser.get(reverse("msp-document-search")).json()["count"] == 1
        for organization in organizations:
            url = reverse("organization-document-search", kwargs={"organization_entity_id": organization.entity_id})
            response = browser.get(url)
            assert response.status_code == 200
            assert [row["title"] for row in response.json()["results"]] == [organization.entity.display_name]
    selected = organizations[0]
    portal = User.objects.create_user(email=f"reader-{uuid.uuid4()}@example.invalid", display_name="Client reader")
    TenantMembership.objects.create(
        tenant=installation.tenant, user=portal, role=BuiltInRole.CLIENT_USER, organization=selected,
    )
    browser.force_login(portal)
    own_url = reverse("organization-document-search", kwargs={"organization_entity_id": selected.entity_id})
    response = browser.get(own_url)
    assert response.status_code == 403 or (response.status_code == 200 and response.json()["count"] == 0)
    foreign = Tenant.objects.create(name="Other audit tenant", slug=f"other-{uuid.uuid4()}")
    user = User.objects.create_user(email=f"foreign-{uuid.uuid4()}@example.invalid", display_name="Foreign reader")
    TenantMembership.objects.create(tenant=foreign, user=user, role=BuiltInRole.ADMINISTRATOR)
    browser.force_login(user)
    assert browser.get(own_url).status_code in (403, 404)
    assert Client().get(own_url).status_code in (401, 403)


def test_archived_legacy_shadow_is_not_discovered_as_native(discovery_context):
    from django.utils import timezone

    from apps.core import repository_service
    from apps.core.content_index import index_repository_content
    from apps.core.models import ContentNode
    from apps.core.tests.test_content_read import _content

    installation, repository = discovery_context
    old = create_document(
        tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
        title="Archived guide", markdown="Retained archived instructions.\n",
    )
    repository_service.commit_repository_files(
        repository_id=repository.id,
        expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
        changes={"docs/shadow.md": _content(content_id=old.id, title="Archived guide", body="Retained text\n")},
        message="Prepare synthetic shadow",
    )
    index_repository_content(repository_id=repository.id)
    old.archived_at = timezone.now()
    old.save(update_fields=("archived_at",))
    browser = Client()
    browser.force_login(installation.owner)
    assert browser.get(reverse("msp-document-search")).json()["count"] == 0
    graph = browser.get(reverse("msp-content-documents")).json()
    assert graph["results"][0]["repository_native"] is False
    assert ContentNode.objects.filter(content_id=old.id).exists()


def test_native_modified_order_ignores_unrelated_repository_changes(discovery_context):
    installation, repository = discovery_context
    first = _create(installation, repository, title="Zulu modified guide")
    _create(installation, repository, title="Alpha other guide")
    repository.refresh_from_db()
    changed = author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=first.content_id, base_commit=first.accepted_commit,
        base_blob=first.source_blob, kind=None, path=None, title=None,
        markdown="Actually revised instructions.\n", metadata_patch={},
    )
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-document-search")
    before = browser.get(url, {"ordering": "-updated_at"}).json()
    assert before["results"][0]["content_id"] == str(first.content_id)
    repository.refresh_from_db()
    author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="create", content_id=uuid.uuid4(), base_commit=changed.accepted_commit,
        base_blob=None, kind="fragment", path="fragments/é[1].md", title="Unrelated fragment",
        markdown="Separate text.\n", metadata_patch={},
    )
    after = browser.get(url, {"ordering": "-updated_at"}).json()
    assert [(row["content_id"], row["updated_at"]) for row in after["results"]] == [
        (row["content_id"], row["updated_at"]) for row in before["results"]
    ]


@pytest.mark.parametrize("organization_scope", [False, True])
def test_legacy_library_works_with_a_new_unindexed_empty_repository(discovery_context, organization_scope):
    from apps.core import repository_storage
    from apps.core.models import Workspace
    from apps.core.organizations import create_organization

    installation, repository = discovery_context
    organization = None
    if organization_scope:
        organization = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Fresh supplier",
            legal_name="Fresh supplier", website="", classifications=["vendor"],
        )
        repository = repository_storage.ensure_workspace_repository(
            Workspace.objects.get(organization=organization)
        ).repository
    old = create_document(
        tenant=installation.tenant, organization=organization, actor_id=installation.owner.id,
        title="Supplier installation guide", markdown="Retained supplier instructions.\n",
    )
    browser = Client()
    browser.force_login(installation.owner)
    repository.refresh_from_db()
    assert repository.accepted_commit_id != repository.indexed_commit_id
    scope = {"organization_entity_id": organization.entity_id} if organization else {}
    for route in ("document-search", "document-list-create"):
        response = browser.get(reverse(("organization-" if organization else "msp-") + route, kwargs=scope))
        assert response.status_code == 200, response.content
        assert [row["id"] for row in response.json()["results"]] == [str(old.entity_id)]


def test_unindexed_first_git_document_is_not_mistaken_for_an_empty_repository(discovery_context):
    from apps.core import repository_service
    from apps.core.tests.test_content_read import _content

    installation, repository = discovery_context
    repository.refresh_from_db()
    repository_service.commit_repository_files(
        repository_id=repository.id, expected_base=repository.accepted_commit.object_id,
        changes={"docs/unindexed.md": _content(content_id=uuid.uuid4(), title="Pending native", body="Pending text\n")},
        message="Prepare unindexed synthetic content",
    )
    browser = Client()
    browser.force_login(installation.owner)
    for route in ("msp-document-search", "msp-document-list-create"):
        assert browser.get(reverse(route)).status_code == 409
