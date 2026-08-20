import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.documents import create_document
from apps.core.models import (
    AuditEvent,
    DocumentKeyBinding,
    Entity,
    InstallationState,
    Organization,
    OrganizationClassification,
    Tenant,
)

from .network_asset_fixtures import create_network_hardware_asset


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Binding API MSP",
        owner_email=f"binding-api-{uuid.uuid4()}@example.invalid",
        owner_display_name="Binding API Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    client = Client()
    client.force_login(installation.owner)
    return client


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    record = Organization.objects.create(tenant=tenant, entity=anchor)
    OrganizationClassification.objects.create(tenant=tenant, organization=record, kind="client")
    return record


def _document(installation, organization, title, markdown):
    return create_document(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        title=title,
        markdown=markdown,
    )


def _bindings_url(organization, document):
    return reverse(
        "organization-document-key-binding-list-create",
        kwargs={"organization_entity_id": organization.entity_id, "document_entity_id": document.entity_id},
    )


def _keys_url(organization, document):
    return reverse(
        "organization-document-keys",
        kwargs={"organization_entity_id": organization.entity_id, "document_entity_id": document.entity_id},
    )


@pytest.mark.django_db
def test_declaring_a_binding_tells_the_author_which_fields_it_can_resolve(installation, owner_client):
    organization = _organization(installation.tenant, "Authoring client")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Edge firewall")
    document = _document(installation, organization, "Edge runbook", "Serial <tekdocs://key/subject.serial_number>.")

    response = owner_client.post(
        _bindings_url(organization, document),
        {"name": "subject", "target_entity_id": str(asset.entity_id)},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "subject"
    assert body["target_display_name"] == "Edge firewall"
    # The response lists what this binding can address, so an author is not left
    # guessing which field paths exist for the record they just bound.
    assert "serial_number" in body["addressable_fields"]
    assert "model.name" in body["addressable_fields"]
    assert AuditEvent.objects.filter(action="document.key_binding.declared").count() == 1


@pytest.mark.django_db
def test_a_binding_name_is_refused_twice_on_one_document_but_allowed_after_retirement(installation, owner_client):
    organization = _organization(installation.tenant, "Retiring client")
    first = create_network_hardware_asset(installation=installation, organization=organization, name="First firewall")
    second = create_network_hardware_asset(installation=installation, organization=organization, name="Second firewall")
    document = _document(
        installation, organization, "Retiring runbook", "Serial <tekdocs://key/subject.serial_number>."
    )
    url = _bindings_url(organization, document)

    created = owner_client.post(
        url, {"name": "subject", "target_entity_id": str(first.entity_id)}, content_type="application/json"
    )
    assert created.status_code == 201

    conflict = owner_client.post(
        url, {"name": "subject", "target_entity_id": str(second.entity_id)}, content_type="application/json"
    )
    assert conflict.status_code == 409

    archived = owner_client.delete(
        reverse(
            "organization-document-key-binding-detail",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": document.entity_id,
                "binding_id": created.json()["id"],
            },
        )
    )
    assert archived.status_code == 204

    # The retired binding is retained, and the name is free again.
    assert DocumentKeyBinding.objects.filter(archived_at__isnull=False).count() == 1
    reused = owner_client.post(
        url, {"name": "subject", "target_entity_id": str(second.entity_id)}, content_type="application/json"
    )
    assert reused.status_code == 201
    assert owner_client.get(url).json()["count"] == 1


@pytest.mark.django_db
def test_a_binding_cannot_be_declared_against_a_record_the_author_cannot_read(installation, owner_client):
    organization = _organization(installation.tenant, "Bound client")
    other = _organization(installation.tenant, "Other client")
    foreign = create_network_hardware_asset(installation=installation, organization=other, name="Other firewall")
    document = _document(installation, organization, "Bound runbook", "Serial <tekdocs://key/subject.serial_number>.")

    response = owner_client.post(
        _bindings_url(organization, document),
        {"name": "subject", "target_entity_id": str(foreign.entity_id)},
        content_type="application/json",
    )

    # Refused as unavailable rather than created and then permanently withheld.
    assert response.status_code == 404
    assert DocumentKeyBinding.objects.count() == 0


@pytest.mark.django_db
def test_a_binding_is_refused_against_a_record_kind_no_key_can_read(installation, owner_client):
    organization = _organization(installation.tenant, "Unaddressable client")
    document = _document(installation, organization, "Unaddressable runbook", "Text.")

    response = owner_client.post(
        _bindings_url(organization, document),
        {"name": "subject", "target_entity_id": str(document.entity_id)},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "target_not_addressable"


@pytest.mark.django_db
def test_a_binding_name_that_could_never_appear_in_a_key_is_refused_by_the_api(installation, owner_client):
    organization = _organization(installation.tenant, "Grammar client")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Grammar firewall")
    document = _document(installation, organization, "Grammar runbook", "Text.")

    for rejected in ("Subject", "gate-way", "1subject", "subject.gateway"):
        response = owner_client.post(
            _bindings_url(organization, document),
            {"name": rejected, "target_entity_id": str(asset.entity_id)},
            content_type="application/json",
        )
        assert response.status_code == 400, rejected


@pytest.mark.django_db
def test_the_key_report_names_every_key_and_counts_the_unresolved_ones(installation, owner_client):
    organization = _organization(installation.tenant, "Reporting client")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Report firewall")
    hardware = asset.hardware
    hardware.serial_number = "REP-0001"
    hardware.save(update_fields=["serial_number"])
    document = _document(
        installation,
        organization,
        "Report runbook",
        "Serial <tekdocs://key/subject.serial_number>, tag <tekdocs://key/subject.asset_tag>, "
        "absent <tekdocs://key/missing.name>.",
    )
    owner_client.post(
        _bindings_url(organization, document),
        {"name": "subject", "target_entity_id": str(asset.entity_id)},
        content_type="application/json",
    )

    report = owner_client.get(_keys_url(organization, document)).json()

    assert report["count"] == 3
    # The serial resolves; the empty asset tag and the undeclared binding do not.
    assert report["unresolved_count"] == 2
    by_expression = {row["expression"]: row for row in report["results"]}
    assert by_expression["subject.serial_number"]["state"] == "resolved"
    assert by_expression["subject.asset_tag"]["reason"] == "empty"
    assert by_expression["missing.name"]["reason"] == "no_binding"


@pytest.mark.django_db
def test_a_read_only_member_may_list_bindings_but_not_declare_one(installation, owner_client):
    """Declaring a binding changes what the document says, so it needs edit rights."""
    from apps.accounts.models import BuiltInRole, TenantMembership, User

    supplier = _organization(installation.tenant, "Read-only supplier")
    asset = create_network_hardware_asset(installation=installation, organization=None, name="MSP-owned firewall")
    document = _document(installation, None, "MSP runbook", "Text.")
    assert supplier is not None

    reader = User.objects.create_user(email=f"reader-{uuid.uuid4()}@example.invalid", display_name="Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    reader_client = Client()
    reader_client.force_login(reader)

    url = reverse("msp-document-key-binding-list-create", kwargs={"document_entity_id": document.entity_id})
    assert reader_client.get(url).status_code == 200
    assert (
        reader_client.post(
            url, {"name": "subject", "target_entity_id": str(asset.entity_id)}, content_type="application/json"
        ).status_code
        == 403
    )
    # The owner can, on the same route with the same payload.
    assert (
        owner_client.post(
            url, {"name": "subject", "target_entity_id": str(asset.entity_id)}, content_type="application/json"
        ).status_code
        == 201
    )


@pytest.mark.django_db
def test_a_binding_shows_which_other_documents_depend_on_the_same_record(installation, owner_client):
    """Where-used, at the moment the author binds rather than after the fact."""
    organization = _organization(installation.tenant, "Shared-record client")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Core switch")
    first = _document(installation, organization, "Switch runbook", "Serial <tekdocs://key/subject.serial_number>.")
    second = _document(installation, organization, "Escalation guide", "Serial <tekdocs://key/device.serial_number>.")
    third = _document(installation, organization, "Unrelated guide", "No keys.")
    for document, name in ((first, "subject"), (second, "device")):
        assert (
            owner_client.post(
                _bindings_url(organization, document),
                {"name": name, "target_entity_id": str(asset.entity_id)},
                content_type="application/json",
            ).status_code
            == 201
        )

    listed = owner_client.get(_bindings_url(organization, first)).json()["results"][0]

    # The other document that quotes this switch is named; the document doing the
    # asking is not listed against itself, and an unrelated document never appears.
    assert [item["title"] for item in listed["also_bound_by"]] == ["Escalation guide"]
    assert third.entity.display_name not in [item["title"] for item in listed["also_bound_by"]]


@pytest.mark.django_db
def test_the_binding_browser_finds_every_document_that_depends_on_a_record(installation, owner_client):
    organization = _organization(installation.tenant, "Browsing client")
    switch = create_network_hardware_asset(installation=installation, organization=organization, name="Core switch")
    firewall = create_network_hardware_asset(installation=installation, organization=organization, name="Edge firewall")
    switch_document = _document(installation, organization, "Switch runbook", "Text.")
    firewall_document = _document(installation, organization, "Firewall runbook", "Text.")
    for document, target, name in (
        (switch_document, switch, "subject"),
        (firewall_document, firewall, "subject"),
    ):
        owner_client.post(
            _bindings_url(organization, document),
            {"name": name, "target_entity_id": str(target.entity_id)},
            content_type="application/json",
        )

    url = reverse("organization-key-bindings", kwargs={"organization_entity_id": organization.entity_id})
    everything = owner_client.get(url).json()
    assert everything["count"] == 2
    assert everything["has_more"] is False

    # Searching by record name answers "what depends on this switch" in one request.
    filtered = owner_client.get(f"{url}?q=Core switch").json()
    assert [row["document_title"] for row in filtered["results"]] == ["Switch runbook"]
    assert filtered["results"][0]["target_display_name"] == "Core switch"


@pytest.mark.django_db
def test_the_browser_never_lists_a_binding_from_a_document_outside_the_scope(installation, owner_client):
    organization = _organization(installation.tenant, "Scoped client")
    sibling = _organization(installation.tenant, "Sibling client")
    sibling_asset = create_network_hardware_asset(installation=installation, organization=sibling, name="Sibling rack")
    sibling_document = _document(installation, sibling, "Sibling runbook", "Text.")
    assert (
        owner_client.post(
            _bindings_url(sibling, sibling_document),
            {"name": "subject", "target_entity_id": str(sibling_asset.entity_id)},
            content_type="application/json",
        ).status_code
        == 201
    )

    url = reverse("organization-key-bindings", kwargs={"organization_entity_id": organization.entity_id})
    assert owner_client.get(url).json()["results"] == []


@pytest.mark.django_db
def test_a_retired_binding_disappears_from_where_used_and_from_the_browser(installation, owner_client):
    organization = _organization(installation.tenant, "Retiring browser client")
    asset = create_network_hardware_asset(installation=installation, organization=organization, name="Retiring switch")
    first = _document(installation, organization, "First runbook", "Text.")
    second = _document(installation, organization, "Second runbook", "Text.")
    created = [
        owner_client.post(
            _bindings_url(organization, document),
            {"name": "subject", "target_entity_id": str(asset.entity_id)},
            content_type="application/json",
        ).json()
        for document in (first, second)
    ]

    owner_client.delete(
        reverse(
            "organization-document-key-binding-detail",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": second.entity_id,
                "binding_id": created[1]["id"],
            },
        )
    )

    listed = owner_client.get(_bindings_url(organization, first)).json()["results"][0]
    assert listed["also_bound_by"] == []
    browser = reverse("organization-key-bindings", kwargs={"organization_entity_id": organization.entity_id})
    assert owner_client.get(browser).json()["count"] == 1
