import secrets
from hashlib import sha256

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    BuiltInRole,
    CustomRole,
    CustomRolePermission,
    CustomRoleScope,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)
from apps.core.models import (
    Block,
    BlockRevision,
    Document,
    DocumentationListingReference,
    DocumentPlacement,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
)


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Example MSP",
        owner_email="documents-owner@example.com",
        owner_display_name="Primary Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def organization(tenant, name):  # type: ignore[no-untyped-def]
    entity = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


@pytest.mark.django_db
def test_document_persists_from_msp_and_client_browser_routes(owner_client, installation):
    client_org = organization(installation.tenant, "Acme Dental")
    msp_url = reverse("msp-document-list-create")
    org_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": client_org.entity_id})

    msp_created = owner_client.post(
        msp_url,
        {"title": "Firewall standard", "markdown": "# Firewall\n\nUse **MFA**."},
        content_type="application/json",
    )
    org_created = owner_client.post(
        org_url, {"title": "Acme onboarding", "markdown": "- Call the client"}, content_type="application/json"
    )

    assert msp_created.status_code == 201
    assert org_created.status_code == 201
    assert msp_created.json()["block_id"]
    assert org_created.json()["owner_organization_id"] == str(client_org.entity_id)
    assert Document.objects.count() == 2
    assert Block.objects.count() == 2
    assert DocumentPlacement.objects.values_list("position", flat=True).order_by("position").first() == 0

    detail = reverse("msp-document-detail", kwargs={"document_entity_id": msp_created.json()["id"]})
    updated = owner_client.put(
        detail,
        {
            "title": "Firewall baseline",
            "markdown": "Updated from the browser.",
            "base_revision_id": msp_created.json()["current_revision_id"],
        },
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Firewall baseline"
    assert updated.json()["markdown"] == "Updated from the browser."
    assert updated.json()["revision_number"] == 2
    revisions = list(
        BlockRevision.objects.filter(block__entity_id=msp_created.json()["block_id"]).order_by("revision_number")
    )
    assert [item.markdown for item in revisions] == ["# Firewall\n\nUse **MFA**.", "Updated from the browser."]
    assert revisions[1].parent == revisions[0]
    assert revisions[1].checksum == sha256(b"Updated from the browser.").hexdigest()


@pytest.mark.django_db
def test_msp_document_reference_cross_lists_without_copying_or_lateral_disclosure(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Shared response guide", "markdown": "One canonical block."},
        content_type="application/json",
    ).json()
    references_url = reverse("msp-document-reference-list-create", kwargs={"document_entity_id": created["id"]})
    added = owner_client.post(references_url, {"organization_id": str(acme.entity_id)}, content_type="application/json")
    assert added.status_code == 201
    assert Document.objects.count() == 1
    assert Block.objects.count() == 1
    assert DocumentationListingReference.objects.count() == 1

    acme_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    beta_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": beta.entity_id})
    assert owner_client.get(acme_url).json()["results"][0]["is_reference"] is True
    assert owner_client.get(acme_url).json()["results"][0]["title"] == "Shared response guide"
    assert owner_client.get(beta_url).json()["count"] == 0

    removed = owner_client.delete(
        reverse(
            "msp-document-reference-detail",
            kwargs={"document_entity_id": created["id"], "reference_id": added.json()["id"]},
        )
    )
    assert removed.status_code == 204
    assert owner_client.get(acme_url).json()["count"] == 0


@pytest.mark.django_db
def test_document_route_scope_returns_not_found_for_another_client(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    acme_url = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    created = owner_client.post(
        acme_url, {"title": "Acme private", "markdown": "Never disclose laterally."}, content_type="application/json"
    ).json()
    beta_detail = reverse(
        "organization-document-detail",
        kwargs={"organization_entity_id": beta.entity_id, "document_entity_id": created["id"]},
    )
    assert owner_client.get(beta_detail).status_code == 404
    assert (
        owner_client.put(
            beta_detail,
            {"title": "Changed", "markdown": "Bad", "base_revision_id": created["current_revision_id"]},
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_stale_document_update_returns_diff_without_overwriting_draft(owner_client, installation):
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Runbook", "markdown": "line one\nline two\n"},
        content_type="application/json",
    ).json()
    detail = reverse("msp-document-detail", kwargs={"document_entity_id": created["id"]})
    first = owner_client.put(
        detail,
        {"title": "Runbook", "markdown": "line one\nserver edit\n", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    ).json()
    stale = owner_client.put(
        detail,
        {"title": "Runbook", "markdown": "line one\nmy draft\n", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"
    assert stale.json()["current_revision"]["id"] == first["current_revision_id"]
    assert "+server edit" in stale.json()["diff"]
    assert owner_client.get(detail).json()["markdown"] == "line one\nserver edit\n"
    assert BlockRevision.objects.count() == 2


@pytest.mark.django_db
def test_revision_history_is_scoped_and_noop_content_does_not_add_revision(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    collection = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    created = owner_client.post(
        collection, {"title": "Access guide", "markdown": "First"}, content_type="application/json"
    ).json()
    detail = reverse(
        "organization-document-detail",
        kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": created["id"]},
    )
    renamed = owner_client.put(
        detail,
        {"title": "Access procedure", "markdown": "First", "base_revision_id": created["current_revision_id"]},
        content_type="application/json",
    ).json()
    assert renamed["revision_number"] == 1
    history_url = reverse(
        "organization-document-revision-list",
        kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": created["id"]},
    )
    history = owner_client.get(history_url)
    assert history.status_code == 200
    assert history.json()["count"] == 1
    revision_url = reverse(
        "organization-document-revision-detail",
        kwargs={
            "organization_entity_id": acme.entity_id,
            "document_entity_id": created["id"],
            "revision_id": created["current_revision_id"],
        },
    )
    assert owner_client.get(revision_url).json()["markdown"] == "First"
    beta_history = reverse(
        "organization-document-revision-list",
        kwargs={"organization_entity_id": beta.entity_id, "document_entity_id": created["id"]},
    )
    assert owner_client.get(beta_history).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_block_revisions_are_append_only_in_application_and_postgresql(owner_client, installation):
    created = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Immutable runbook", "markdown": "Original"},
        content_type="application/json",
    ).json()
    revision = BlockRevision.objects.get(id=created["current_revision_id"])
    revision.markdown = "Mutated"
    with pytest.raises(ValidationError):
        revision.save()
    if connection.vendor == "postgresql":
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE core_blockrevision SET markdown = %s WHERE id = %s", ["Mutated", revision.id])
    revision.refresh_from_db()
    assert revision.markdown == "Original"


@pytest.mark.django_db
def test_live_and_pinned_transclusions_resolve_deterministically(owner_client, installation):
    collection = reverse("msp-document-list-create")
    source = owner_client.post(
        collection, {"title": "Shared checklist", "markdown": "Shared revision one"}, content_type="application/json"
    ).json()
    live_document = owner_client.post(
        collection, {"title": "Live composition", "markdown": "Live introduction"}, content_type="application/json"
    ).json()
    pinned_document = owner_client.post(
        collection, {"title": "Pinned composition", "markdown": "Pinned introduction"}, content_type="application/json"
    ).json()

    live_added = owner_client.post(
        reverse("msp-document-placement-list-create", kwargs={"document_entity_id": live_document["id"]}),
        {"source_document_id": source["id"], "resolution_mode": "live"},
        content_type="application/json",
    )
    pinned_added = owner_client.post(
        reverse("msp-document-placement-list-create", kwargs={"document_entity_id": pinned_document["id"]}),
        {
            "source_document_id": source["id"],
            "resolution_mode": "pinned",
            "pinned_revision_id": source["current_revision_id"],
        },
        content_type="application/json",
    )
    assert live_added.status_code == 200
    assert pinned_added.status_code == 200
    assert live_added.json()["resolved_markdown"] == "Live introduction\n\nShared revision one\n"
    assert pinned_added.json()["resolved_markdown"] == "Pinned introduction\n\nShared revision one\n"

    owner_client.put(
        reverse("msp-document-detail", kwargs={"document_entity_id": source["id"]}),
        {
            "title": source["title"],
            "markdown": "Shared revision two",
            "base_revision_id": source["current_revision_id"],
        },
        content_type="application/json",
    )
    live_reloaded = owner_client.get(
        reverse("msp-document-detail", kwargs={"document_entity_id": live_document["id"]})
    ).json()
    pinned_reloaded = owner_client.get(
        reverse("msp-document-detail", kwargs={"document_entity_id": pinned_document["id"]})
    ).json()
    assert live_reloaded["resolved_markdown"].endswith("Shared revision two\n")
    assert pinned_reloaded["resolved_markdown"].endswith("Shared revision one\n")
    assert live_reloaded["placements"][1]["resolved_revision_number"] == 2
    assert pinned_reloaded["placements"][1]["resolved_revision_number"] == 1


@pytest.mark.django_db
def test_nested_transclusion_is_depth_first_and_rejects_ancestor_cycle(owner_client, installation):
    collection = reverse("msp-document-list-create")
    destination = owner_client.post(
        collection, {"title": "Composition", "markdown": "A"}, content_type="application/json"
    ).json()
    source_b = owner_client.post(collection, {"title": "B", "markdown": "B"}, content_type="application/json").json()
    source_c = owner_client.post(collection, {"title": "C", "markdown": "C"}, content_type="application/json").json()
    placements_url = reverse("msp-document-placement-list-create", kwargs={"document_entity_id": destination["id"]})
    added_b = owner_client.post(
        placements_url,
        {"source_document_id": source_b["id"], "resolution_mode": "live"},
        content_type="application/json",
    ).json()
    b_placement = added_b["placements"][1]
    added_c = owner_client.post(
        placements_url,
        {
            "source_document_id": source_c["id"],
            "resolution_mode": "live",
            "parent_id": b_placement["id"],
        },
        content_type="application/json",
    )
    assert added_c.status_code == 200
    assert added_c.json()["resolved_markdown"] == "A\n\nB\n\nC\n"
    assert [item["depth"] for item in added_c.json()["placements"]] == [0, 0, 1]

    cycle = owner_client.post(
        placements_url,
        {
            "source_document_id": source_b["id"],
            "resolution_mode": "live",
            "parent_id": b_placement["id"],
        },
        content_type="application/json",
    )
    assert cycle.status_code == 409
    assert cycle.json()["code"] == "placement_conflict"
    assert "Circular" in cycle.json()["detail"]


@pytest.mark.django_db
def test_transclusion_source_must_be_visible_in_destination_workspace(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    acme_collection = reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id})
    beta_collection = reverse("organization-document-list-create", kwargs={"organization_entity_id": beta.entity_id})
    destination = owner_client.post(
        acme_collection, {"title": "Acme composition", "markdown": "Acme"}, content_type="application/json"
    ).json()
    sibling_source = owner_client.post(
        beta_collection, {"title": "Beta private", "markdown": "Beta"}, content_type="application/json"
    ).json()
    response = owner_client.post(
        reverse(
            "organization-document-placement-list-create",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        ),
        {"source_document_id": sibling_source["id"], "resolution_mode": "live"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_referenced_msp_block_can_be_transcluded_but_reference_cannot_be_revoked_while_used(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    source = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "MSP standard", "markdown": "Shared standard"},
        content_type="application/json",
    ).json()
    reference = owner_client.post(
        reverse("msp-document-reference-list-create", kwargs={"document_entity_id": source["id"]}),
        {"organization_id": str(acme.entity_id)},
        content_type="application/json",
    ).json()
    destination = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id}),
        {"title": "Client runbook", "markdown": "Client introduction"},
        content_type="application/json",
    ).json()
    added = owner_client.post(
        reverse(
            "organization-document-placement-list-create",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        ),
        {"source_document_id": source["id"], "resolution_mode": "live"},
        content_type="application/json",
    )
    assert added.status_code == 200
    assert added.json()["resolved_markdown"] == "Client introduction\n\nShared standard\n"

    revoked = owner_client.delete(
        reverse(
            "msp-document-reference-detail",
            kwargs={"document_entity_id": source["id"], "reference_id": reference["id"]},
        )
    )
    assert revoked.status_code == 409
    assert revoked.json()["code"] == "placement_conflict"
    archived = owner_client.delete(reverse("msp-document-detail", kwargs={"document_entity_id": source["id"]}))
    assert archived.status_code == 409
    assert Document.objects.get(entity_id=source["id"]).archived_at is None


@pytest.mark.django_db(transaction=True)
def test_postgresql_rejects_raw_placement_cycle_and_cross_client_block(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Placement database guards require PostgreSQL")
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    destination = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id}),
        {"title": "Acme composition", "markdown": "A"},
        content_type="application/json",
    ).json()
    beta_source = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": beta.entity_id}),
        {"title": "Beta source", "markdown": "B"},
        content_type="application/json",
    ).json()
    destination_record = Document.objects.get(entity_id=destination["id"])
    root = destination_record.placements.get(parent__isnull=True, position=0)
    beta_block = Block.objects.get(entity_id=beta_source["block_id"])
    with pytest.raises(DatabaseError), transaction.atomic():
        DocumentPlacement.objects.create(
            tenant=installation.tenant,
            organization=acme,
            document=destination_record,
            block=beta_block,
            position=1,
        )

    source = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id}),
        {"title": "Acme source", "markdown": "B"},
        content_type="application/json",
    ).json()
    added = owner_client.post(
        reverse(
            "organization-document-placement-list-create",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        ),
        {"source_document_id": source["id"], "resolution_mode": "live", "parent_id": str(root.id)},
        content_type="application/json",
    ).json()
    child = DocumentPlacement.objects.get(id=added["placements"][1]["id"])
    with pytest.raises(DatabaseError), transaction.atomic():
        DocumentPlacement.objects.filter(id=root.id).update(parent=child)
    with pytest.raises(DatabaseError), transaction.atomic():
        DocumentPlacement.objects.filter(id=root.id).update(
            resolution_mode="pinned", pinned_revision_id=root.block.current_revision_id
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        DocumentPlacement.objects.filter(id=root.id).delete()


@pytest.mark.django_db
def test_reuse_impact_shared_update_and_detach_preserve_live_and_local_semantics(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    source = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "Shared standard", "markdown": "Revision one"},
        content_type="application/json",
    ).json()
    owner_client.post(
        reverse("msp-document-reference-list-create", kwargs={"document_entity_id": source["id"]}),
        {"organization_id": str(acme.entity_id)},
        content_type="application/json",
    )
    destination = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id}),
        {"title": "Acme runbook", "markdown": "Introduction"},
        content_type="application/json",
    ).json()
    composed = owner_client.post(
        reverse(
            "organization-document-placement-list-create",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        ),
        {"source_document_id": source["id"], "resolution_mode": "live"},
        content_type="application/json",
    ).json()
    placement = composed["placements"][1]
    reuse_url = reverse(
        "organization-document-placement-reuse",
        kwargs={
            "organization_entity_id": acme.entity_id,
            "document_entity_id": destination["id"],
            "placement_id": placement["id"],
        },
    )

    impact = owner_client.get(reuse_url)
    assert impact.status_code == 200
    assert impact.json()["can_edit_shared"] is True
    assert impact.json()["can_detach"] is True
    assert impact.json()["live_audience_count"] == 3
    assert {item["relationship"] for item in impact.json()["audiences"]} == {"source", "listing", "placement"}

    updated = owner_client.put(
        reuse_url,
        {"markdown": "Revision two", "base_revision_id": source["current_revision_id"]},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["resolved_markdown"].endswith("Revision two\n")
    assert BlockRevision.objects.filter(block__entity_id=source["block_id"]).count() == 2

    detached = owner_client.post(
        reverse(
            "organization-document-placement-detach",
            kwargs={
                "organization_entity_id": acme.entity_id,
                "document_entity_id": destination["id"],
                "placement_id": placement["id"],
            },
        )
    )
    assert detached.status_code == 200
    assert detached.json()["placements"][1]["block_id"] != source["block_id"]

    owner_client.put(
        reverse("msp-document-detail", kwargs={"document_entity_id": source["id"]}),
        {
            "title": source["title"],
            "markdown": "Revision three",
            "base_revision_id": updated.json()["placements"][1]["resolved_revision_id"],
        },
        content_type="application/json",
    )
    reloaded = owner_client.get(
        reverse(
            "organization-document-detail",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        )
    ).json()
    assert reloaded["resolved_markdown"].endswith("Revision two\n")


@pytest.mark.django_db
def test_entity_mentions_search_and_render_are_workspace_scoped(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    beta = organization(installation.tenant, "Beta")
    acme_router = Entity.objects.create(
        tenant=installation.tenant,
        organization=acme,
        entity_type="hardware_asset",
        display_name="Acme Core Router",
        visibility="client_visible",
    )
    beta_router = Entity.objects.create(
        tenant=installation.tenant,
        organization=beta,
        entity_type="hardware_asset",
        display_name="Beta Core Router",
        visibility="client_visible",
    )
    search = owner_client.get(
        reverse("organization-document-mention-search", kwargs={"organization_entity_id": acme.entity_id}),
        {"q": "Core Router"},
    )
    assert search.status_code == 200
    assert [item["id"] for item in search.json()["results"]] == [str(acme_router.id)]

    markdown = (
        f"[authored](tekdocs://entity/{acme_router.id}) [secret authored label](tekdocs://entity/{beta_router.id})"
    )
    preview = owner_client.post(
        reverse("markdown-render"),
        {"markdown": markdown, "organization_id": str(acme.entity_id)},
        content_type="application/json",
    )
    assert preview.status_code == 200
    assert "Acme Core Router · hardware asset · Acme" in preview.json()["html"]
    assert "Unavailable reference" in preview.json()["html"]
    assert "secret authored label" not in preview.json()["html"]


@pytest.mark.django_db
def test_client_editor_cannot_change_msp_shared_block_but_can_detach(owner_client, installation):
    acme = organization(installation.tenant, "Acme")
    source = owner_client.post(
        reverse("msp-document-list-create"),
        {"title": "MSP standard", "markdown": "Canonical"},
        content_type="application/json",
    ).json()
    owner_client.post(
        reverse("msp-document-reference-list-create", kwargs={"document_entity_id": source["id"]}),
        {"organization_id": str(acme.entity_id)},
        content_type="application/json",
    )
    destination = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": acme.entity_id}),
        {"title": "Client guide", "markdown": "Local"},
        content_type="application/json",
    ).json()
    composed = owner_client.post(
        reverse(
            "organization-document-placement-list-create",
            kwargs={"organization_entity_id": acme.entity_id, "document_entity_id": destination["id"]},
        ),
        {"source_document_id": source["id"], "resolution_mode": "live"},
        content_type="application/json",
    ).json()
    placement = composed["placements"][1]

    editor = User.objects.create_user(email="client-editor@example.com", display_name="Client Editor")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=editor,
        role=BuiltInRole.READ_ONLY,
    )
    role = CustomRole.objects.create(
        tenant=installation.tenant,
        name="Client document editor",
        scope=CustomRoleScope.ORGANIZATION,
        created_by=installation.owner,
    )
    CustomRolePermission.objects.create(
        tenant=installation.tenant,
        role=role,
        permission="documents.edit",
    )
    ScopedRoleAssignment.objects.create(
        tenant=installation.tenant,
        membership=membership,
        role=role,
        organization=acme,
        created_by=installation.owner,
    )
    TOTP.activate(editor, generate_totp_secret())
    editor_client = Client()
    editor_client.force_login(editor)
    route_kwargs = {
        "organization_entity_id": acme.entity_id,
        "document_entity_id": destination["id"],
        "placement_id": placement["id"],
    }
    reuse_url = reverse("organization-document-placement-reuse", kwargs=route_kwargs)
    impact = editor_client.get(reuse_url)
    assert impact.status_code == 200
    assert impact.json()["can_edit_shared"] is False
    assert impact.json()["can_detach"] is True
    denied = editor_client.put(
        reuse_url,
        {"markdown": "Unauthorized", "base_revision_id": source["current_revision_id"]},
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert BlockRevision.objects.filter(block__entity_id=source["block_id"]).count() == 1
    assert editor_client.post(reverse("organization-document-placement-detach", kwargs=route_kwargs)).status_code == 200
