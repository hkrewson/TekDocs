import secrets
import uuid
from dataclasses import dataclass
from typing import cast

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
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
# The live read paths resolve; the evidence paths refuse.
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
def test_publication_refuses_a_document_whose_keys_cannot_yet_be_frozen(installation):
    from apps.core.publications import PublicationConflict, publish_document

    organization = _organization(installation.tenant, "Publishing client")
    asset = _asset_with_serial(installation, organization, name="Publishing firewall", serial="PUB-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Publishing runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)

    with pytest.raises(PublicationConflict, match="subject.serial_number"):
        publish_document(
            workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
            document=document,
            actor_id=installation.owner.pk,
            reason="Key freeze is not implemented yet",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )

    # Nothing partial is retained: the refusal happens before any artifact exists.
    assert document.publications.count() == 0


@pytest.mark.django_db
def test_export_refuses_a_document_whose_keys_cannot_yet_be_frozen(installation):
    from apps.core.document_exports import ExportConflict, resolve_export_snapshot

    organization = _organization(installation.tenant, "Exporting client")
    asset = _asset_with_serial(installation, organization, name="Exporting firewall", serial="EXP-0001")
    markdown = "Serial <tekdocs://key/subject.serial_number>."
    document = _document(installation, organization, "Exporting runbook", markdown)
    _bind(installation, document=document, target=asset.entity, organization=organization)

    with pytest.raises(ExportConflict, match="subject.serial_number"):
        resolve_export_snapshot(
            workspace=resolve_organization_workspace(installation.owner, entity_id=organization.entity_id),
            document=document,
        )


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
