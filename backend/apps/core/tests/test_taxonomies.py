import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from zipfile import ZipFile

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.models import (
    DocumentTaxonomyTerm,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    Taxonomy,
    TaxonomyTerm,
    TaxonomyVersion,
)
from apps.core.taxonomies import revise_taxonomy


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Taxonomy MSP",
        owner_email="taxonomy-owner@example.invalid",
        owner_display_name="Taxonomy Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def taxonomy_payload():
    return {
        "key": "technology",
        "binding": "document_tags",
        "label": "Technology",
        "description": "Products and platforms used by the document.",
        "allow_local_terms": False,
        "terms": [
            {
                "stable_key": "microsoft",
                "label": "Microsoft",
                "description": "Microsoft products and services.",
                "aliases": ["MSFT"],
                "sort_order": 0,
            },
            {
                "stable_key": "entra-id",
                "label": "Entra ID",
                "description": "Microsoft Entra identity services.",
                "parent_key": "microsoft",
                "aliases": ["Azure AD"],
                "sort_order": 1,
            },
        ],
    }


def create_document(client: Client, title="Identity recovery"):
    response = client.post(
        reverse("msp-document-list-create"),
        {"title": title, "markdown": "Recover the directory."},
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


def create_organization(installation, name="Client One"):
    entity = Entity.objects.create_owned(tenant=installation.tenant, entity_type="organization", display_name=name)
    organization = Organization.objects.create(tenant=installation.tenant, entity=entity)
    OrganizationClassification.objects.create(tenant=installation.tenant, organization=organization, kind="client")
    return organization


@pytest.mark.django_db
def test_taxonomy_versions_drive_document_picker_alias_search_and_portable_manifest(owner_client):
    created_taxonomy = owner_client.post(
        reverse("msp-taxonomy-list-create"), taxonomy_payload(), content_type="application/json"
    )
    assert created_taxonomy.status_code == 201
    taxonomy = created_taxonomy.json()
    assert taxonomy["current_version"]["version"] == 1
    assert taxonomy["current_version"]["terms"][1]["parent_key"] == "microsoft"

    document = create_document(owner_client)
    entra = next(term for term in taxonomy["current_version"]["terms"] if term["stable_key"] == "entra-id")
    updated = owner_client.put(
        reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]}),
        {"collection": "Runbooks", "tags": [], "taxonomy_term_ids": [entra["id"]]},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["Entra ID"]
    assert updated.json()["taxonomy_terms"][0]["stable_key"] == "entra-id"
    refreshed = owner_client.get(reverse("msp-taxonomy-list-create")).json()["results"]
    impact = next(item for item in refreshed if item["id"] == taxonomy["id"])["current_version"]["terms"]
    assert next(term for term in impact if term["stable_key"] == "entra-id")["impact"] == {
        "documents": 1,
        "templates": 0,
    }

    alias_result = owner_client.get(reverse("msp-document-search"), {"tag": "azure ad"})
    assert alias_result.status_code == 200
    assert [item["id"] for item in alias_result.json()["results"]] == [document["id"]]

    exported = owner_client.get(
        reverse("msp-document-export", kwargs={"document_entity_id": document["id"]}),
        {"export_format": "bundle"},
    )
    assert exported.status_code == 200
    with ZipFile(BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["taxonomies"] == [
        {
            "taxonomy_key": "technology",
            "taxonomy_version": 1,
            "label": "Technology",
            "terms": [{"key": "entra-id", "label": "Entra ID"}],
        }
    ]


@pytest.mark.django_db
def test_exact_legacy_tag_migration_never_guesses(owner_client):
    document = create_document(owner_client)
    operations = reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]})
    assert (
        owner_client.put(
            operations,
            {"collection": "", "tags": ["Azure AD", "directory"]},
            content_type="application/json",
        ).status_code
        == 200
    )
    assert (
        owner_client.post(
            reverse("msp-taxonomy-list-create"), taxonomy_payload(), content_type="application/json"
        ).status_code
        == 201
    )

    preview = owner_client.post(reverse("msp-taxonomy-migration"), {"apply": False}, content_type="application/json")
    assert preview.status_code == 200
    assert preview.json()["counts"] == {"matched": 1, "unmatched": 1, "ambiguous": 0}
    applied = owner_client.post(reverse("msp-taxonomy-migration"), {"apply": True}, content_type="application/json")
    assert applied.status_code == 200
    assert applied.json()["counts"] == {"matched": 0, "unmatched": 1, "ambiguous": 0}
    detail = owner_client.get(reverse("msp-document-detail", kwargs={"document_entity_id": document["id"]})).json()
    assert detail["tags"] == ["directory", "Entra ID"]


@pytest.mark.django_db
def test_cycle_undefined_terms_and_read_only_management_are_rejected(owner_client, installation):
    malformed = taxonomy_payload()
    malformed["terms"][0]["parent_key"] = "entra-id"
    malformed["terms"][1]["parent_key"] = "microsoft"
    assert (
        owner_client.post(reverse("msp-taxonomy-list-create"), malformed, content_type="application/json").status_code
        == 400
    )

    taxonomy = owner_client.post(
        reverse("msp-taxonomy-list-create"), taxonomy_payload(), content_type="application/json"
    ).json()
    removed = taxonomy_payload()
    removed["terms"] = removed["terms"][:1]
    assert (
        owner_client.patch(
            reverse("msp-taxonomy-detail", kwargs={"taxonomy_id": taxonomy["id"]}),
            {key: removed[key] for key in ("label", "description", "allow_local_terms", "terms")},
            content_type="application/json",
        ).status_code
        == 400
    )
    document = create_document(owner_client)
    undefined = owner_client.put(
        reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]}),
        {"collection": "", "tags": ["misspelled"]},
        content_type="application/json",
    )
    assert undefined.status_code == 400

    original_entra = next(
        term for term in taxonomy["current_version"]["terms"] if term["stable_key"] == "entra-id"
    )
    assert (
        owner_client.put(
            reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]}),
            {"collection": "", "tags": [], "taxonomy_term_ids": [original_entra["id"]]},
            content_type="application/json",
        ).status_code
        == 200
    )
    retired = taxonomy_payload()
    retired["terms"][1]["status"] = "retired"
    retired["terms"][1]["replacement_key"] = "microsoft"
    assert (
        owner_client.patch(
            reverse("msp-taxonomy-detail", kwargs={"taxonomy_id": taxonomy["id"]}),
            {key: retired[key] for key in ("label", "description", "allow_local_terms", "terms")},
            content_type="application/json",
        ).status_code
        == 200
    )
    preserved = owner_client.put(
        reverse("msp-document-operations", kwargs={"document_entity_id": document["id"]}),
        {"collection": "Retained", "tags": [], "taxonomy_term_ids": [original_entra["id"]]},
        content_type="application/json",
    )
    assert preserved.status_code == 200
    assert preserved.json()["tags"] == ["Entra ID"]

    reader = User.objects.create_user(
        email="taxonomy-reader@example.invalid", password=f"{secrets.token_urlsafe(24)}Aa7!", display_name="Reader"
    )
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    client = Client()
    client.force_login(reader)
    assert client.get(reverse("msp-taxonomy-list-create")).status_code == 200
    assert (
        client.patch(
            reverse("msp-taxonomy-detail", kwargs={"taxonomy_id": taxonomy["id"]}),
            taxonomy_payload(),
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
def test_database_rejects_cross_taxonomy_term_assignment(owner_client):
    first = owner_client.post(
        reverse("msp-taxonomy-list-create"), taxonomy_payload(), content_type="application/json"
    ).json()
    second_payload = taxonomy_payload()
    second_payload["key"] = "platform"
    second_payload["label"] = "Platform"
    second = owner_client.post(
        reverse("msp-taxonomy-list-create"), second_payload, content_type="application/json"
    ).json()
    document = create_document(owner_client)
    record_id = owner_client.get(reverse("msp-document-detail", kwargs={"document_entity_id": document["id"]})).json()[
        "id"
    ]
    from apps.core.models import Document

    record = Document.objects.get(entity_id=record_id)
    wrong_term = TaxonomyTerm.objects.get(id=second["current_version"]["terms"][0]["id"])
    first_taxonomy = Taxonomy.objects.get(id=first["id"])
    with pytest.raises(DatabaseError, match="document taxonomy term mismatch"), transaction.atomic():
        DocumentTaxonomyTerm.objects.create(
            tenant=record.tenant,
            organization=record.organization,
            document=record,
            taxonomy=first_taxonomy,
            term=wrong_term,
        )


@pytest.mark.django_db
def test_client_local_terms_require_permission_and_remain_client_scoped(owner_client, installation):
    payload = taxonomy_payload()
    payload["allow_local_terms"] = True
    taxonomy = owner_client.post(reverse("msp-taxonomy-list-create"), payload, content_type="application/json").json()
    organization = create_organization(installation)
    local = owner_client.post(
        reverse(
            "organization-taxonomy-local-term-create",
            kwargs={"organization_entity_id": organization.entity_id, "taxonomy_id": taxonomy["id"]},
        ),
        {
            "stable_key": "client-app",
            "label": "Client App",
            "description": "Application used only by this client.",
            "aliases": ["Legacy Client App"],
        },
        content_type="application/json",
    )
    assert local.status_code == 201
    local_term = next(term for term in local.json()["current_version"]["terms"] if term["local"])

    created = owner_client.post(
        reverse(
            "organization-document-list-create",
            kwargs={"organization_entity_id": organization.entity_id},
        ),
        {"title": "Client application", "markdown": "Client-only notes."},
        content_type="application/json",
    )
    assert created.status_code == 201
    updated = owner_client.put(
        reverse(
            "organization-document-operations",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": created.json()["id"],
            },
        ),
        {"collection": "Applications", "tags": [], "taxonomy_term_ids": [local_term["id"]]},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["Client App"]

    other = create_organization(installation, "Client Two")
    other_catalog = owner_client.get(
        reverse("organization-taxonomy-list", kwargs={"organization_entity_id": other.entity_id})
    )
    assert all(not term["local"] for term in other_catalog.json()["results"][0]["current_version"]["terms"])
    other_document = owner_client.post(
        reverse("organization-document-list-create", kwargs={"organization_entity_id": other.entity_id}),
        {"title": "Other client", "markdown": "Other notes."},
        content_type="application/json",
    ).json()
    rejected = owner_client.put(
        reverse(
            "organization-document-operations",
            kwargs={"organization_entity_id": other.entity_id, "document_entity_id": other_document["id"]},
        ),
        {"collection": "", "tags": [], "taxonomy_term_ids": [local_term["id"]]},
        content_type="application/json",
    )
    assert rejected.status_code == 400

    template = owner_client.post(
        reverse("msp-document-list-create"),
        {
            "title": "Identity baseline",
            "markdown": "Use the approved identity platform.",
            "is_template": True,
            "library_visible": True,
        },
        content_type="application/json",
    ).json()
    entra = next(term for term in taxonomy["current_version"]["terms"] if term["stable_key"] == "entra-id")
    assert (
        owner_client.put(
            reverse("msp-document-operations", kwargs={"document_entity_id": template["id"]}),
            {"collection": "Baselines", "tags": [], "taxonomy_term_ids": [entra["id"]]},
            content_type="application/json",
        ).status_code
        == 200
    )
    instantiated = owner_client.post(
        reverse(
            "organization-document-template-instantiate",
            kwargs={"organization_entity_id": organization.entity_id},
        ),
        {
            "source_document_id": template["id"],
            "title": "Client identity baseline",
            "category": "guide",
            "placement_rules": {},
        },
        content_type="application/json",
    )
    assert instantiated.status_code == 201
    assert instantiated.json()["tags"] == ["Entra ID"]

    revision_payload = taxonomy_payload()
    revised = owner_client.patch(
        reverse("msp-taxonomy-detail", kwargs={"taxonomy_id": taxonomy["id"]}),
        {
            "label": revision_payload["label"],
            "description": revision_payload["description"],
            "allow_local_terms": True,
            "terms": revision_payload["terms"],
        },
        content_type="application/json",
    ).json()
    microsoft = next(term for term in revised["current_version"]["terms"] if term["stable_key"] == "microsoft")
    assert (
        owner_client.put(
            reverse("msp-document-operations", kwargs={"document_entity_id": template["id"]}),
            {"collection": "Baselines", "tags": [], "taxonomy_term_ids": [microsoft["id"]]},
            content_type="application/json",
        ).status_code
        == 200
    )
    preview = owner_client.post(
        reverse(
            "organization-document-template-rollout-preview",
            kwargs={"organization_entity_id": organization.entity_id},
        ),
        {"enrollment_id": instantiated.json()["template_enrollment_id"]},
        content_type="application/json",
    ).json()
    assert preview["up_to_date"] is False
    applied = owner_client.post(
        reverse(
            "organization-document-template-rollout-apply",
            kwargs={"organization_entity_id": organization.entity_id},
        ),
        {
            "enrollment_id": instantiated.json()["template_enrollment_id"],
            "expected_applied_revision_id": preview["applied_revision_id"],
            "placement_rules": {},
        },
        content_type="application/json",
    )
    assert applied.status_code == 200
    destination = owner_client.get(
        reverse(
            "organization-document-detail",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": instantiated.json()["id"],
            },
        )
    )
    assert destination.json()["tags"] == ["Microsoft"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_taxonomy_revisions_allocate_distinct_append_only_versions(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Taxonomy revision concurrency validation requires PostgreSQL")
    created = owner_client.post(
        reverse("msp-taxonomy-list-create"), taxonomy_payload(), content_type="application/json"
    ).json()
    barrier = threading.Barrier(2)

    def revise(label: str) -> int:
        close_old_connections()
        try:
            taxonomy = Taxonomy.objects.get(id=created["id"])
            barrier.wait(timeout=5)
            revised = revise_taxonomy(
                taxonomy=taxonomy,
                actor_id=installation.owner.id,
                label=label,
                description="Concurrent controlled revision.",
                allow_local_terms=False,
                terms=taxonomy_payload()["terms"],
            )
            return revised.current_version.version
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        observed = sorted(executor.map(revise, ("Technology A", "Technology B")))

    assert observed == [2, 3]
    assert list(
        TaxonomyVersion.objects.filter(taxonomy_id=created["id"]).order_by("version").values_list("version", flat=True)
    ) == [1, 2, 3]
