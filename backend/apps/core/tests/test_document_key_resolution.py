import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, cast

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.accounts.policy import DataAudience, InstallationMemberContext, require_installation_member
from apps.core.document_key_fields import RESOLVABLE_RECORDS
from apps.core.document_key_resolution import (
    ResolutionState,
    UnresolvableReason,
    ValueProvenance,
    audience_for,
    resolve_markdown_keys,
)
from apps.core.document_keys import KEY_TARGET_SCHEME, MAXIMUM_KEYS_PER_DOCUMENT
from apps.core.documents import create_document
from apps.core.models import (
    AuditEvent,
    DocumentKeyBinding,
    Entity,
    EntityVisibility,
    InstallationState,
    NetBoxReference,
    Organization,
    OrganizationClassification,
    Tenant,
    workspace_for_owner,
)
from apps.core.rendering import render_markdown
from apps.core.workspaces import resolve_organization_workspace

from .network_asset_fixtures import create_network_hardware_asset


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Resolution MSP",
        owner_email=f"resolution-{uuid.uuid4()}@example.invalid",
        owner_display_name="Resolution Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


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


def _bind(installation, *, document, target, organization, name="subject"):
    return DocumentKeyBinding.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
        organization=organization,
        document=document,
        name=name,
        target_entity=target,
        created_by=installation.owner,
    )


def _asset_with_serial(installation, organization, *, name, serial, visibility=None):
    asset = create_network_hardware_asset(installation=installation, organization=organization, name=name)
    hardware = asset.hardware
    hardware.serial_number = serial
    hardware.save(update_fields=["serial_number"])
    if visibility is not None:
        Entity.objects.filter(pk=asset.entity_id).update(visibility=visibility)
        asset.entity.refresh_from_db()
    return asset


def _resolve(installation, *, document, markdown, audience, organization, user=None):
    context = require_installation_member(user or installation.owner)
    return resolve_markdown_keys(
        markdown,
        context=context,
        document=document,
        audience=audience,
        organization=organization,
    )


# ---------------------------------------------------------------------------
# The registry is an allowlist, so its entries must describe real reads.
# ---------------------------------------------------------------------------


def test_every_registered_field_names_a_real_attribute_chain():
    """A registry entry that does not resolve would fail silently as "empty".

    The registry is expected to grow, and a mistyped accessor produces an
    unresolvable key rather than an error, so the mistake would look like missing
    data. Walking the model metadata here turns that into a failing test instead.
    """
    from django.db.models import Model

    from apps.core.models import Entity as EntityModel

    for entity_type, record in RESOLVABLE_RECORDS.items():
        relation = EntityModel._meta.get_field(record.record_accessor)
        model = relation.related_model
        assert isinstance(model, type) and issubclass(model, Model), entity_type

        for path, field in record.fields.items():
            owner = model
            *hops, attribute = field.accessor
            for hop in hops:
                related = owner._meta.get_field(hop).related_model
                assert related is not None, f"{entity_type}.{path}: {hop} is not a relation"
                owner = related
            assert owner._meta.get_field(attribute) is not None, f"{entity_type}.{path}: {attribute} is missing"

        for related_path in record.select_related:
            owner = model
            for hop in related_path.split("__"):
                related = owner._meta.get_field(hop).related_model
                assert related is not None, f"{entity_type}: select_related {related_path} is not a relation"
                owner = related


# ---------------------------------------------------------------------------
# Authorization parity.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_key_resolves_exactly_what_a_direct_read_of_the_field_returns(installation):
    client = _organization(installation.tenant, "Resolving client")
    asset = _asset_with_serial(installation, client, name="Edge firewall", serial="FGT-60F-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number> on <tekdocs://key/subject.name>."
    document = _document(installation, client, "Firewall runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolutions = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=client,
    )

    serial = resolutions[f"{KEY_TARGET_SCHEME}subject.serial_number"]
    assert serial.state == ResolutionState.RESOLVED
    # Parity: the key returns the stored value, not a copy that could drift.
    assert serial.value == asset.hardware.serial_number == "FGT-60F-0001"
    assert serial.provenance == ValueProvenance.LOCAL
    assert serial.source_entity_id == asset.entity_id
    assert resolutions[f"{KEY_TARGET_SCHEME}subject.name"].value == asset.entity.display_name


@pytest.mark.django_db
def test_a_reader_denied_the_record_is_told_nothing_more_than_a_direct_denial_would_tell(installation):
    client = _organization(installation.tenant, "Portal client")
    asset = _asset_with_serial(installation, client, name="Private firewall", serial="SECRET-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Portal runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    withheld = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.CLIENT_PORTAL,
        organization=client,
    )[f"{KEY_TARGET_SCHEME}subject.serial_number"]

    assert withheld.state == ResolutionState.WITHHELD
    assert withheld.value == ""
    assert withheld.source_entity_id is None
    # The marker names the key the author wrote, never the field label, because the
    # label would disclose what kind of record the binding points at.
    assert withheld.label == "subject.serial_number"
    assert "SECRET" not in withheld.label


@pytest.mark.django_db
def test_a_client_visible_record_resolves_for_the_portal_audience(installation):
    client = _organization(installation.tenant, "Shared client")
    asset = _asset_with_serial(
        installation,
        client,
        name="Shared firewall",
        serial="SHARED-0001",
        visibility=EntityVisibility.CLIENT_VISIBLE,
    )
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Shared runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolved = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.CLIENT_PORTAL,
        organization=client,
    )[f"{KEY_TARGET_SCHEME}subject.serial_number"]

    assert resolved.state == ResolutionState.RESOLVED
    assert resolved.value == "SHARED-0001"


@pytest.mark.django_db
def test_the_audience_decides_resolution_not_the_author(installation):
    """The same key, same document, same binding — two audiences, two outcomes."""
    client = _organization(installation.tenant, "Audience client")
    asset = _asset_with_serial(installation, client, name="Audience firewall", serial="AUD-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Audience runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    def state_for(audience):
        return _resolve(
            installation,
            document=document,
            markdown=markdown,
            audience=audience,
            organization=client,
        )[f"{KEY_TARGET_SCHEME}subject.serial_number"].state

    assert state_for(DataAudience.MSP_STAFF) == ResolutionState.RESOLVED
    assert state_for(DataAudience.CLIENT_PORTAL) == ResolutionState.WITHHELD


@pytest.mark.django_db
def test_a_reader_without_access_to_the_organization_is_withheld(installation):
    client = _organization(installation.tenant, "Scoped client")
    asset = _asset_with_serial(installation, client, name="Scoped firewall", serial="SCOPE-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Scoped runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    reader = User.objects.create_user(email=f"reader-{uuid.uuid4()}@example.invalid", display_name="Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)

    # Resolving against a sibling organization the binding does not belong to must
    # not leak the value, even though the reader is a legitimate tenant member.
    sibling = _organization(installation.tenant, "Sibling client")
    withheld = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=sibling,
        user=reader,
    )[f"{KEY_TARGET_SCHEME}subject.serial_number"]

    assert withheld.state == ResolutionState.WITHHELD


# ---------------------------------------------------------------------------
# Unresolvable keys are reported, never blank and never stale.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unresolvable_keys_each_report_their_own_reason(installation):
    client = _organization(installation.tenant, "Reporting client")
    asset = _asset_with_serial(installation, client, name="Reporting firewall", serial="")
    markdown = (
        "Missing binding <tekdocs://key/absent.name>, "
        "unregistered field <tekdocs://key/subject.disposal_reason>, "
        "empty value <tekdocs://key/subject.serial_number>, "
        "malformed <tekdocs://key/subject>."
    )
    document = _document(installation, client, "Reporting runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolutions = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=client,
    )

    reasons = {target: result.reason for target, result in resolutions.items()}
    assert reasons[f"{KEY_TARGET_SCHEME}absent.name"] == UnresolvableReason.NO_BINDING
    assert reasons[f"{KEY_TARGET_SCHEME}subject.disposal_reason"] == UnresolvableReason.NOT_ADDRESSABLE
    assert reasons[f"{KEY_TARGET_SCHEME}subject.serial_number"] == UnresolvableReason.EMPTY
    assert reasons[f"{KEY_TARGET_SCHEME}subject"] == UnresolvableReason.NOT_ADDRESSABLE
    assert all(result.state == ResolutionState.UNRESOLVABLE for result in resolutions.values())
    assert all(result.value == "" for result in resolutions.values())


@pytest.mark.django_db
def test_a_record_reconciled_against_a_provider_resolves_as_observed(installation):
    client = _organization(installation.tenant, "Observed client")
    asset = _asset_with_serial(installation, client, name="Observed firewall", serial="OBS-0001")
    NetBoxReference.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=client),
        organization=client,
        entity=asset.entity,
        object_type="dcim.device",
        object_id="41",
        observed_fingerprint="a" * 64,
    )
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Observed runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolved = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=client,
    )[f"{KEY_TARGET_SCHEME}subject.serial_number"]

    assert resolved.provenance == ValueProvenance.OBSERVED


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_key_ever_reaches_the_reader_as_raw_syntax(installation):
    """Even with no resolutions at all, the rendered output contains no key target.

    ``tekdocs`` is an allowed URL scheme, so a key link that fell through the
    transform would survive the sanitizer as a live link exposing the expression.
    """
    client = _organization(installation.tenant, "Rendering client")
    asset = _asset_with_serial(installation, client, name="Rendering firewall", serial="REN-0001")
    markdown = (
        "Serial <tekdocs://key/subject.serial_number>, unknown <tekdocs://key/absent.name>, "
        "malformed <tekdocs://key/subject>."
    )
    document = _document(installation, client, "Rendering runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    assert KEY_TARGET_SCHEME not in render_markdown(markdown)

    resolutions = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=client,
    )
    rendered = render_markdown(
        markdown,
        key_resolutions={
            target: {
                "state": result.state.value,
                "label": result.label,
                "value": result.value,
                "provenance": result.provenance.value if result.provenance else "",
            }
            for target, result in resolutions.items()
        },
    )

    assert KEY_TARGET_SCHEME not in rendered
    assert "REN-0001" in rendered
    assert 'data-key-state="unresolvable"' in rendered


@pytest.mark.django_db
def test_a_withheld_value_is_absent_from_the_rendered_output(installation):
    client = _organization(installation.tenant, "Leak client")
    asset = _asset_with_serial(installation, client, name="Leak firewall", serial="LEAK-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, client, "Leak runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolutions = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.CLIENT_PORTAL,
        organization=client,
    )
    rendered = render_markdown(
        markdown,
        key_resolutions={
            target: {"state": result.state.value, "label": result.label, "value": result.value}
            for target, result in resolutions.items()
        },
    )

    assert "LEAK-0001" not in rendered
    assert 'data-key-state="withheld"' in rendered
    assert "Withheld" in rendered


# ---------------------------------------------------------------------------
# Cost.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_many_keys_on_one_record_read_that_record_once(installation, django_assert_num_queries):
    """Live rendering costs per distinct record, not per key.

    ADR 0089 makes this a requirement rather than an optimisation: resolution must
    be batched per document and must not introduce a cross-scope cache, so the only
    remaining lever is reading each bound record once.
    """
    client = _organization(installation.tenant, "Batching client")
    asset = _asset_with_serial(installation, client, name="Batching firewall", serial="BAT-0001")
    markdown = " ".join(
        f"<tekdocs://key/subject.{path}>"
        for path in ("name", "serial_number", "asset_tag", "model.name", "supplier.name", "lifecycle_state")
    )
    document = _document(installation, client, "Batching runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)
    context = require_installation_member(installation.owner)

    # Bindings, the asset record with its relations pre-joined, and the provenance
    # lookup. Six keys, three queries — and the count does not grow with keys.
    with django_assert_num_queries(3):
        resolve_markdown_keys(
            markdown,
            context=context,
            document=document,
            audience=DataAudience.MSP_STAFF,
            organization=client,
        )


@pytest.mark.django_db
def test_many_content_keys_read_their_block_revisions_in_one_batch(installation, django_assert_num_queries):
    client = _organization(installation.tenant, "Content batching client")
    document = _document(installation, client, "Content batching runbook", "Initial content.")
    targets = []
    for index in range(8):
        source = _document(installation, client, f"Shared procedure {index}", f"Procedure {index}.")
        block = source.placements.get(parent__isnull=True).block
        name = f"procedure_{index}"
        _bind(
            installation,
            document=document,
            target=block.entity,
            organization=client,
            name=name,
        )
        targets.append(f"<tekdocs://key/{name}.content>")
    markdown = "\n\n".join(targets)
    context = require_installation_member(installation.owner)

    # Binding targets, every block/current revision in one batch, and provenance.
    # The query count stays fixed as distinct content keys are added.
    with django_assert_num_queries(3):
        resolutions = resolve_markdown_keys(
            markdown,
            context=context,
            document=document,
            audience=DataAudience.MSP_STAFF,
            organization=client,
        )

    assert {resolution.value for resolution in resolutions.values()} == {
        f"Procedure {index}." for index in range(8)
    }


@pytest.mark.django_db
def test_a_binding_declared_on_another_document_does_not_resolve(installation):
    """Bindings are per document, so the same name means different things elsewhere."""
    client = _organization(installation.tenant, "Namespace client")
    asset = _asset_with_serial(installation, client, name="Namespace firewall", serial="NS-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    bound = _document(installation, client, "Bound runbook", markdown)
    unbound = _document(installation, client, "Unbound runbook", markdown)
    _bind(installation, document=bound, target=asset.entity, organization=client)

    def reason_for(document):
        return _resolve(
            installation,
            document=document,
            markdown=markdown,
            audience=DataAudience.MSP_STAFF,
            organization=client,
        )[f"{KEY_TARGET_SCHEME}subject.serial_number"]

    assert reason_for(bound).value == "NS-0001"
    assert reason_for(unbound).reason == UnresolvableReason.NO_BINDING


@pytest.mark.django_db
def test_a_document_beyond_the_key_limit_reports_the_excess_rather_than_dropping_it(installation):
    """The bound exists so one generated revision cannot fan out into record reads.

    Truncating silently would make the limit invisible: the document would render
    with values simply missing. Each excess key is marked instead.
    """
    client = _organization(installation.tenant, "Limit client")
    asset = _asset_with_serial(installation, client, name="Limit firewall", serial="LIM-0001")
    paths = [f"subject.field_{index}" for index in range(MAXIMUM_KEYS_PER_DOCUMENT + 5)]
    markdown = " ".join(f"<{KEY_TARGET_SCHEME}{path}>" for path in paths)
    document = _document(installation, client, "Limit runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=client)

    resolutions = _resolve(
        installation,
        document=document,
        markdown=markdown,
        audience=DataAudience.MSP_STAFF,
        organization=client,
    )

    assert len(resolutions) == len(paths)
    excess = [result for result in resolutions.values() if result.reason == UnresolvableReason.LIMIT_EXCEEDED]
    assert len(excess) == 5
    assert all(result.state == ResolutionState.UNRESOLVABLE for result in excess)


# ---------------------------------------------------------------------------
# The live read paths resolve dynamically; evidence paths freeze one exact result.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_preview_endpoint_resolves_a_key_for_the_requesting_member(installation, client):
    organization = _organization(installation.tenant, "Preview client")
    asset = _asset_with_serial(installation, organization, name="Preview firewall", serial="PRE-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Preview runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)
    client.force_login(installation.owner)

    response = client.post(
        reverse("markdown-render"),
        {
            "markdown": markdown,
            "organization_id": str(organization.entity_id),
            "document_id": str(document.entity_id),
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    html = response.json()["html"]
    assert "PRE-0001" in html
    assert KEY_TARGET_SCHEME not in html


@pytest.mark.django_db
def test_a_preview_without_a_document_cannot_borrow_another_documents_bindings(installation, client):
    organization = _organization(installation.tenant, "Scratch client")
    asset = _asset_with_serial(installation, organization, name="Scratch firewall", serial="SCR-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Scratch runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)
    client.force_login(installation.owner)

    # The same markdown, previewed with no document: bindings belong to a document, so
    # a scratch buffer resolves nothing rather than picking up a nearby binding.
    response = client.post(
        reverse("markdown-render"),
        {"markdown": markdown, "organization_id": str(organization.entity_id)},
        content_type="application/json",
    )

    assert response.status_code == 200
    html = response.json()["html"]
    assert "SCR-0001" not in html
    assert 'data-key-state="unresolvable"' in html


@pytest.mark.django_db
def test_publication_freezes_a_resolved_key_and_its_provenance(installation):
    from apps.core.publications import publish_document, verify_publication

    organization = _organization(installation.tenant, "Publishing client")
    asset = _asset_with_serial(installation, organization, name="Publishing firewall", serial="PUB-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Publishing runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)

    publication = publish_document(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
        actor_id=installation.owner.pk,
        reason="Freeze the resolved key",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )

    assert publication.manifest["format"] == "tekdocs-static-publication/v4"
    assert KEY_TARGET_SCHEME not in publication.canonical_markdown
    assert publication.canonical_markdown == "Serial PUB\\-0001.\n"
    assert "PUB-0001" in publication.sanitized_html
    assert publication.manifest["key_resolutions"] == [
        {
            "kind": "field",
            "expression": "subject.serial_number",
            "value": "PUB-0001",
            "source_entity_id": str(asset.entity_id),
            "source_entity_type": "client_asset",
            "source_fingerprint": publication.manifest["key_resolutions"][0]["source_fingerprint"],
            "provenance": "local",
            "resolved_at": publication.manifest["published_at"],
            "source_revision_id": None,
            "source_revision_number": None,
            "dependency_chain": [],
        }
    ]
    assert len(publication.manifest["key_resolutions"][0]["source_fingerprint"]) == 64
    assert all(verify_publication(publication).values())

    # Authored immutable source remains unresolved; only retained evidence freezes it.
    source = document.placements.get(parent__isnull=True).block.current_revision
    assert source is not None
    assert KEY_TARGET_SCHEME in source.markdown

    asset.hardware.serial_number = "PUB-CHANGED"
    asset.hardware.save(update_fields=["serial_number"])
    publication.refresh_from_db()
    assert publication.canonical_markdown == "Serial PUB\\-0001.\n"
    assert "PUB-CHANGED" not in publication.canonical_markdown
    assert all(verify_publication(publication).values())


@pytest.mark.django_db
def test_publication_only_freezes_keys_outside_markdown_code(installation):
    from apps.core.publications import publish_document

    organization = _organization(installation.tenant, "Key example client")
    asset = _asset_with_serial(installation, organization, name="Example firewall", serial="EX-0001")
    target = "<tekdocs://key/subject.serial_number>"
    markdown = f"Example: `{target}`\n\nResolved: {target}."
    document = _document(installation, organization, "Key example", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)

    publication = publish_document(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
        actor_id=installation.owner.pk,
        reason="Preserve the authored key example",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )

    assert f"`{target}`" in publication.canonical_markdown
    assert "Resolved: EX\\-0001." in publication.canonical_markdown
    assert publication.manifest["key_resolutions"][0]["expression"] == "subject.serial_number"


@pytest.mark.django_db
def test_export_freezes_the_same_resolved_key_and_provenance(installation):
    from apps.core.document_exports import resolve_export_snapshot

    organization = _organization(installation.tenant, "Exporting client")
    asset = _asset_with_serial(installation, organization, name="Exporting firewall", serial="EXP-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Exporting runbook", markdown)
    binding = _bind(installation, document=document, target=asset.entity, organization=organization)

    snapshot = resolve_export_snapshot(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
    )
    repeated = resolve_export_snapshot(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
    )

    assert KEY_TARGET_SCHEME not in snapshot.markdown
    assert snapshot.markdown == "Serial EXP\\-0001.\n"
    assert "EXP-0001" in snapshot.sanitized_html
    assert snapshot.manifest["key_resolutions"][0]["expression"] == "subject.serial_number"
    assert snapshot.manifest["key_resolutions"][0]["value"] == "EXP-0001"
    assert snapshot.manifest["key_resolutions"][0]["source_entity_id"] == str(asset.entity_id)
    assert snapshot.manifest["key_resolutions"] == repeated.manifest["key_resolutions"]
    assert snapshot.manifest["key_resolutions"][0]["resolved_at"] == max(
        document.updated_at,
        binding.updated_at,
        asset.entity.updated_at,
        asset.hardware.updated_at,
    ).isoformat()


@pytest.mark.django_db
def test_export_refusal_creates_neither_output_audit_nor_partial_evidence(installation, client):
    organization = _organization(installation.tenant, "Unresolved export client")
    document = _document(
        installation,
        organization,
        "Unresolved export runbook",
        "Serial <tekdocs://key/missing.serial_number>.",
    )
    client.force_login(installation.owner)

    response = client.get(
        reverse(
            "organization-document-export",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": document.entity_id,
            },
        ),
        {"export_format": "bundle"},
    )

    assert response.status_code == 409
    assert response.content == b"One or more document keys could not be resolved for the selected audience."
    assert document.publications.count() == 0
    assert not AuditEvent.objects.filter(action="document.exported", entity_id=document.entity_id).exists()


@pytest.mark.django_db(transaction=True)
def test_export_holds_resolved_field_rows_until_the_snapshot_is_complete(installation, monkeypatch):
    from apps.core import document_exports

    organization = _organization(installation.tenant, "Concurrent field client")
    asset = _asset_with_serial(installation, organization, name="Concurrent firewall", serial="OLD-0001")
    document = _document(
        installation,
        organization,
        "Concurrent field runbook",
        "Serial <tekdocs://key/subject.serial_number>.",
    )
    _bind(installation, document=document, target=asset.entity, organization=organization)
    route = reverse(
        "organization-document-export",
        kwargs={
            "organization_entity_id": organization.entity_id,
            "document_entity_id": document.entity_id,
        },
    )
    snapshot_holds_source = threading.Event()
    release_snapshot = threading.Event()
    original_freeze = document_exports.freeze_document_keys

    def paused_freeze(**kwargs):  # type: ignore[no-untyped-def]
        frozen = original_freeze(**kwargs)
        snapshot_holds_source.set()
        assert release_snapshot.wait(timeout=10)
        return frozen

    monkeypatch.setattr("apps.core.document_exports.freeze_document_keys", paused_freeze)
    results: dict[str, Any] = {}

    def run_export() -> None:
        close_old_connections()
        worker = Client()
        worker.force_login(installation.owner)
        results["export"] = worker.get(route, {"export_format": "md"})
        close_old_connections()

    def run_source_edit() -> None:
        close_old_connections()
        hardware_type = type(asset.hardware)
        results["updated"] = hardware_type.objects.filter(pk=asset.hardware.pk).update(serial_number="NEW-0002")
        close_old_connections()

    export_thread = threading.Thread(target=run_export)
    edit_thread = threading.Thread(target=run_source_edit)
    export_thread.start()
    assert snapshot_holds_source.wait(timeout=10)
    edit_thread.start()
    time.sleep(0.2)
    try:
        assert edit_thread.is_alive()
    finally:
        release_snapshot.set()
    export_thread.join(timeout=10)
    edit_thread.join(timeout=10)

    assert not export_thread.is_alive()
    assert not edit_thread.is_alive()
    assert results["export"].status_code == 200
    assert results["export"].content == b"Serial OLD\\-0001.\n"
    assert results["updated"] == 1


@pytest.mark.django_db
def test_client_visible_publication_refuses_a_key_withheld_from_that_audience(installation):
    from apps.core.publications import PublicationConflict, publish_document

    organization = _organization(installation.tenant, "Withheld publishing client")
    asset = _asset_with_serial(installation, organization, name="Private firewall", serial="PRIVATE-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Client runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)

    with pytest.raises(PublicationConflict, match="could not be resolved for the selected audience"):
        publish_document(
            workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
            document=document,
            actor_id=installation.owner.pk,
            reason="Must not use publisher authority",
            audience="client_visible",
            retention="permanent",
            retention_review_on=None,
        )

    assert document.publications.count() == 0


@pytest.mark.django_db
def test_publication_freezes_a_content_key_to_one_exact_block_revision(installation):
    from apps.core.document_exports import resolve_export_snapshot
    from apps.core.publications import publish_document, verify_publication

    organization = _organization(installation.tenant, "Content publishing client")
    source = _document(
        installation,
        organization,
        "Shared restart procedure",
        "## Restart safely\n\nUse **maintenance mode** before restarting.",
    )
    source_block = source.placements.get(parent__isnull=True).block
    source_revision = source_block.current_revision
    assert source_revision is not None
    markdown = "Before.\n\n<tekdocs://key/procedure.content>\n\nAfter."
    document = _document(installation, organization, "Content-key runbook", markdown)
    _bind(
        installation,
        document=document,
        target=source_block.entity,
        organization=organization,
        name="procedure",
    )

    publication = publish_document(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
        actor_id=installation.owner.pk,
        reason="Freeze shared content",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )

    assert KEY_TARGET_SCHEME not in publication.canonical_markdown
    assert "## Restart safely" in publication.canonical_markdown
    assert "<strong>maintenance mode</strong>" in publication.sanitized_html
    resolution = publication.manifest["key_resolutions"][0]
    assert resolution["kind"] == "content"
    assert resolution["expression"] == "procedure.content"
    assert resolution["source_entity_id"] == str(source_block.entity_id)
    assert resolution["source_revision_id"] == str(source_revision.id)
    assert resolution["source_revision_number"] == source_revision.revision_number
    assert resolution["source_fingerprint"] == source_revision.checksum
    assert resolution["dependency_chain"] == [str(source_block.entity_id)]
    assert all(verify_publication(publication).values())

    exported = resolve_export_snapshot(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
    )
    assert "## Restart safely" in exported.markdown
    assert "<strong>maintenance mode</strong>" in exported.sanitized_html
    assert exported.manifest["key_resolutions"][0]["source_revision_id"] == str(source_revision.id)


@pytest.mark.django_db
def test_client_visible_publication_resolves_only_explicitly_client_visible_content(installation):
    from apps.core.publications import PublicationConflict, publish_document

    organization = _organization(installation.tenant, "Client content audience")
    source = _document(installation, organization, "Client recovery step", "Use the client recovery vault.")
    source_block = source.placements.get(parent__isnull=True).block
    document = _document(
        installation,
        organization,
        "Client recovery runbook",
        "<tekdocs://key/recovery.content>",
    )
    _bind(
        installation,
        document=document,
        target=source_block.entity,
        organization=organization,
        name="recovery",
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)

    with pytest.raises(PublicationConflict, match="could not be resolved for the selected audience"):
        publish_document(
            workspace=workspace,
            document=document,
            actor_id=installation.owner.pk,
            reason="Private source must remain withheld",
            audience="client_visible",
            retention="permanent",
            retention_review_on=None,
        )

    source_block.entity.visibility = EntityVisibility.CLIENT_VISIBLE
    source_block.entity.save(update_fields=("visibility", "updated_at"))
    publication = publish_document(
        workspace=workspace,
        document=document,
        actor_id=installation.owner.pk,
        reason="Publish authorized client content",
        audience="client_visible",
        retention="permanent",
        retention_review_on=None,
    )

    assert publication.lifecycle_state == "pending_approval"
    assert publication.canonical_markdown == "Use the client recovery vault.\n"
    assert publication.manifest["key_resolutions"][0]["kind"] == "content"


@pytest.mark.django_db
def test_content_key_cycles_and_inline_expansion_fail_before_publication(installation):
    from apps.core.publications import PublicationConflict, publish_document

    organization = _organization(installation.tenant, "Content refusal client")
    cyclic_source = _document(
        installation,
        organization,
        "Cyclic shared content",
        "<tekdocs://key/procedure.content>",
    )
    source_block = cyclic_source.placements.get(parent__isnull=True).block

    safe_source = _document(installation, organization, "Safe shared content", "Restart safely.")
    safe_source_block = safe_source.placements.get(parent__isnull=True).block
    for title, markdown, message, target in (
        (
            "Cyclic runbook",
            "<tekdocs://key/procedure.content>",
            "Circular content-key expansion",
            source_block.entity,
        ),
        (
            "Inline runbook",
            "Before <tekdocs://key/procedure.content> after.",
            "Content keys must appear on a line by themselves",
            safe_source_block.entity,
        ),
    ):
        document = _document(installation, organization, title, markdown)
        _bind(
            installation,
            document=document,
            target=target,
            organization=organization,
            name="procedure",
        )
        with pytest.raises(PublicationConflict, match=message):
            publish_document(
                workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
                document=document,
                actor_id=installation.owner.pk,
                reason="Exercise content-key refusal",
                audience="msp_internal",
                retention="permanent",
                retention_review_on=None,
            )
        assert document.publications.count() == 0


@pytest.mark.django_db
def test_content_key_depth_and_resolved_size_limits_fail_before_publication(installation, monkeypatch):
    from apps.core.publications import PublicationConflict, publish_document

    organization = _organization(installation.tenant, "Bounded content client")
    leaf = _document(installation, organization, "Leaf content", "Leaf procedure.")
    leaf_block = leaf.placements.get(parent__isnull=True).block
    parent = _document(
        installation,
        organization,
        "Parent content",
        "<tekdocs://key/leaf.content>",
    )
    parent_block = parent.placements.get(parent__isnull=True).block
    destination = _document(
        installation,
        organization,
        "Depth-limited runbook",
        "<tekdocs://key/parent.content>",
    )
    _bind(installation, document=destination, target=parent_block.entity, organization=organization, name="parent")
    _bind(installation, document=destination, target=leaf_block.entity, organization=organization, name="leaf")
    workspace = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)

    monkeypatch.setattr("apps.core.document_key_freeze.MAXIMUM_CONTENT_KEY_DEPTH", 2)
    with pytest.raises(PublicationConflict, match="2-level expansion limit"):
        publish_document(
            workspace=workspace,
            document=destination,
            actor_id=installation.owner.pk,
            reason="Exercise the content depth bound",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert destination.publications.count() == 0

    sized = _document(installation, organization, "Size-limited runbook", "<tekdocs://key/leaf.content>")
    _bind(installation, document=sized, target=leaf_block.entity, organization=organization, name="leaf")
    monkeypatch.setattr("apps.core.document_key_freeze.MAXIMUM_CONTENT_KEY_DEPTH", 32)
    monkeypatch.setattr("apps.core.document_key_freeze.MAXIMUM_FROZEN_MARKDOWN_BYTES", 8)
    with pytest.raises(PublicationConflict, match="2 MiB rendering limit"):
        publish_document(
            workspace=workspace,
            document=sized,
            actor_id=installation.owner.pk,
            reason="Exercise the content size bound",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
    assert sized.publications.count() == 0


@pytest.mark.django_db
def test_live_preview_expands_a_standalone_content_key_through_the_markdown_pipeline(installation, client):
    organization = _organization(installation.tenant, "Live content client")
    source = _document(
        installation,
        organization,
        "Live shared content",
        "## Shared heading\n\nUse **safe mode**.",
    )
    source_block = source.placements.get(parent__isnull=True).block
    markdown = "Before.\n\n<tekdocs://key/shared.content>\n\nAfter."
    document = _document(installation, organization, "Live content runbook", markdown)
    _bind(
        installation,
        document=document,
        target=source_block.entity,
        organization=organization,
        name="shared",
    )
    client.force_login(installation.owner)

    response = client.post(
        reverse("markdown-render"),
        {
            "markdown": markdown,
            "organization_id": str(organization.entity_id),
            "document_id": str(document.entity_id),
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    html = response.json()["html"]
    assert "<h2>Shared heading</h2>" in html
    assert "<strong>safe mode</strong>" in html
    assert KEY_TARGET_SCHEME not in html

    detail = client.get(
        reverse(
            "organization-document-detail",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": document.entity_id,
            },
        )
    )
    assert detail.status_code == 200
    placement_html = " ".join(item["resolved_html"] for item in detail.json()["placements"])
    assert "<h2>Shared heading</h2>" in placement_html
    assert "<strong>safe mode</strong>" in placement_html


@pytest.mark.django_db
def test_a_document_without_keys_still_publishes(installation):
    from apps.core.publications import publish_document

    organization = _organization(installation.tenant, "Ordinary client")
    document = _document(installation, organization, "Ordinary runbook", "No keys in this document.")

    publication = publish_document(
        workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
        document=document,
        actor_id=installation.owner.pk,
        reason="Unchanged behaviour for documents without keys",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )

    assert publication is not None


def test_the_audience_follows_the_members_own_surface():
    """A reader's surface decides the audience, so the author's cannot leak into it.

    Live document reads are MSP-staff-only today: the client portal is served
    publications, not live compositions. This mapping is what makes the portal branch
    correct in advance of the portal reaching a live path, rather than an untested
    assumption discovered later.
    """

    @dataclass
    class _Surface:
        surface: str

    assert audience_for(cast(InstallationMemberContext, _Surface("msp"))) == DataAudience.MSP_STAFF
    assert audience_for(cast(InstallationMemberContext, _Surface("client_portal"))) == DataAudience.CLIENT_PORTAL


@pytest.mark.django_db
def test_the_document_api_returns_a_resolved_value_in_its_rendered_html(installation, client):
    organization = _organization(installation.tenant, "API client")
    asset = _asset_with_serial(installation, organization, name="API firewall", serial="API-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "API runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)
    client.force_login(installation.owner)

    response = client.get(
        reverse(
            "organization-document-detail",
            kwargs={
                "organization_entity_id": organization.entity_id,
                "document_entity_id": document.entity_id,
            },
        )
    )

    assert response.status_code == 200
    html = " ".join(placement["resolved_html"] for placement in response.json()["placements"])
    assert "API-0001" in html
    assert KEY_TARGET_SCHEME not in html
    # The stored source is untouched: only the rendered projection carries the value.
    assert "<tekdocs://key/subject.serial_number>" in response.json()["resolved_markdown"]
