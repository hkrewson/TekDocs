import csv
import io
import json
import secrets
import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    AuditEvent,
    DataFlow,
    DataFlowRevision,
    DataFlowSnapshot,
    Entity,
    EntityVisibility,
    InstallationState,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core.sites import create_site


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Data Flow MSP",
        owner_email=f"data-flow-{uuid.uuid4()}@example.invalid",
        owner_display_name="Data Flow Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name, classification="client"):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=[classification],
    )


def _url(organization, name="organization-data-flows"):
    return reverse(name, kwargs={"organization_entity_id": organization.entity_id})


def _detail_url(organization, flow_id, suffix=""):
    return reverse(
        f"organization-data-flow-{suffix or 'detail'}",
        kwargs={"organization_entity_id": organization.entity_id, "data_flow_entity_id": flow_id},
    )


def _snapshot_url(organization):
    return reverse("organization-data-flow-snapshots", kwargs={"organization_entity_id": organization.entity_id})


def _export_url(organization, snapshot_id, export_format):
    return reverse(
        "organization-data-flow-snapshot-export",
        kwargs={
            "organization_entity_id": organization.entity_id,
            "snapshot_id": snapshot_id,
            "export_format": export_format,
        },
    )


def _payload(**overrides):
    payload = {
        "name": "Billing export",
        "source_kind": "external",
        "source_label": "Practice management vendor",
        "destination_kind": "external",
        "destination_label": "Payment processor",
        "direction": "one_way",
        "transfer_mechanism": "api",
        "data_classification": "personal_data",
        "purpose": "Transmit patient billing records for settlement.",
        "crosses_trust_boundary": True,
        "protection": "in_transit_and_at_rest",
        "provenance": "recorded_fact",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_a_declared_flow_records_its_first_revision_and_carries_it_as_current(installation, owner_client):
    organization = _organization(installation, "Flow client")

    response = owner_client.post(_url(organization), _payload(), content_type="application/json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Billing export"
    assert body["revision_count"] == 1
    current = body["current_revision"]
    assert current["revision_number"] == 1
    assert current["data_classification"] == "personal_data"
    assert current["crosses_trust_boundary"] is True
    # An external endpoint reads back under the same display name an internal one would,
    # so a view never has to branch on endpoint kind to render a label.
    assert current["source_display_name"] == "Practice management vendor"
    assert current["destination_display_name"] == "Payment processor"
    assert AuditEvent.objects.filter(action="data_flow.created").count() == 1


@pytest.mark.django_db
def test_revising_a_flow_appends_and_leaves_the_earlier_statement_readable(installation, owner_client):
    organization = _organization(installation, "Revision client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    revised = owner_client.patch(
        _detail_url(organization, created["id"]),
        _payload(protection="none", provenance="unverified_draft"),
        content_type="application/json",
    )

    assert revised.status_code == 200
    assert revised.json()["current_revision"]["revision_number"] == 2
    history = owner_client.get(_detail_url(organization, created["id"], "revisions")).json()
    assert history["count"] == 2
    # The superseded statement keeps the posture it asserted. Evidence that silently
    # adopts the newest values is not evidence.
    superseded = next(row for row in history["results"] if row["revision_number"] == 1)
    assert superseded["protection"] == "in_transit_and_at_rest"
    assert superseded["provenance"] == "recorded_fact"


@pytest.mark.django_db
def test_an_unchanged_submission_does_not_consume_a_revision_number(installation, owner_client):
    organization = _organization(installation, "Idempotent client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    again = owner_client.patch(_detail_url(organization, created["id"]), _payload(), content_type="application/json")

    assert again.status_code == 200
    assert again.json()["current_revision"]["revision_number"] == 1
    assert again.json()["revision_count"] == 1


@pytest.mark.django_db
def test_an_endpoint_is_a_record_or_a_name_but_never_both_and_never_neither(installation, owner_client):
    organization = _organization(installation, "Endpoint client")
    site = create_site(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        name="Main surgery",
        code="",
        address_line_1="1 Example Way",
        address_line_2="",
        city="Example",
        region="EX",
        postal_code="00000",
        country_code="US",
        timezone="UTC",
        phone="",
    )

    both = owner_client.post(
        _url(organization),
        _payload(source_kind="internal", source_entity_id=str(site.entity_id), source_label="Also named"),
        content_type="application/json",
    )
    neither = owner_client.post(
        _url(organization), _payload(source_kind="external", source_label=""), content_type="application/json"
    )
    internal = owner_client.post(
        _url(organization),
        _payload(source_kind="internal", source_entity_id=str(site.entity_id), source_label=""),
        content_type="application/json",
    )

    assert both.status_code == 400
    assert neither.status_code == 400
    assert internal.status_code == 201
    assert internal.json()["current_revision"]["source_display_name"] == "Main surgery"


@pytest.mark.django_db
def test_a_flow_cannot_name_a_record_belonging_to_another_client(installation, owner_client):
    organization = _organization(installation, "Naming client")
    sibling = _organization(installation, "Sibling client")
    sibling_site = create_site(
        tenant=installation.tenant,
        organization=sibling,
        actor_id=installation.owner.id,
        name="Sibling surgery",
        code="",
        address_line_1="1 Example Way",
        address_line_2="",
        city="Example",
        region="EX",
        postal_code="00000",
        country_code="US",
        timezone="UTC",
        phone="",
    )

    response = owner_client.post(
        _url(organization),
        _payload(source_kind="internal", source_entity_id=str(sibling_site.entity_id), source_label=""),
        content_type="application/json",
    )

    assert response.status_code == 400
    # The refusal names the problem rather than reporting a generic invalid request.
    assert "unavailable" in response.json()["error"]["fields"]["detail"][0]


@pytest.mark.django_db
def test_a_flow_declared_for_one_client_is_invisible_to_a_sibling(installation, owner_client):
    organization = _organization(installation, "Visible client")
    sibling = _organization(installation, "Blind client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    assert owner_client.get(_url(sibling)).json()["results"] == []
    hidden = owner_client.get(_detail_url(sibling, created["id"]))
    assert hidden.status_code == 404
    # An MSP-workspace listing is not the union of its clients.
    assert owner_client.get(reverse("msp-data-flows")).json()["results"] == []


@pytest.mark.django_db
def test_archiving_a_flow_removes_it_from_the_listing_and_retains_its_revisions(installation, owner_client):
    organization = _organization(installation, "Archiving client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    assert owner_client.delete(_detail_url(organization, created["id"])).status_code == 204

    assert owner_client.get(_url(organization)).json()["results"] == []
    assert DataFlowRevision.objects.filter(data_flow__entity_id=created["id"]).count() == 1
    assert AuditEvent.objects.filter(action="data_flow.archived").count() == 1


@pytest.mark.django_db
def test_the_listing_states_whether_this_member_may_author(installation, owner_client):
    organization = _organization(installation, "Authoring client")

    assert owner_client.get(_url(organization)).json()["can_manage"] is True


@pytest.mark.django_db
def test_the_choice_vocabulary_is_served_rather_than_assumed_by_the_browser(installation, owner_client):
    organization = _organization(installation, "Vocabulary client")

    body = owner_client.get(_url(organization, "organization-data-flow-choices")).json()

    assert {"value": "unverified_draft", "label": "Unverified draft"} in body["provenance_states"]
    assert {row["value"] for row in body["endpoint_kinds"]} == {"internal", "external"}
    assert len(body["transfer_mechanisms"]) >= 5


@pytest.mark.django_db
def test_revisions_are_immutable_through_the_orm(installation, owner_client):
    organization = _organization(installation, "Immutable client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()
    revision = DataFlowRevision.objects.get(data_flow__entity_id=created["id"])

    revision.purpose = "Rewritten"
    with pytest.raises(ValidationError):
        revision.save()
    with pytest.raises(ValidationError):
        revision.delete()


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_a_direct_revision_rewrite(installation, owner_client):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    organization = _organization(installation, "Trigger client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    # The ORM guard is a courtesy. The record must survive a writer that never loads it.
    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowRevision.objects.filter(data_flow__entity_id=created["id"]).update(purpose="Rewritten")
    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowRevision.objects.filter(data_flow__entity_id=created["id"]).delete()


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_a_direct_cross_workspace_endpoint(installation, owner_client):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    organization = _organization(installation, "Guarded client")
    sibling = _organization(installation, "Foreign client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()
    flow = DataFlow.objects.get(entity_id=created["id"])
    foreign = Entity.objects.create_owned(
        tenant=installation.tenant,
        organization=sibling,
        entity_type="site",
        display_name="Foreign site",
        visibility=EntityVisibility.MSP_PRIVATE,
    )

    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowRevision.objects.create(
            tenant=flow.tenant,
            workspace=flow.workspace,
            organization=flow.organization,
            data_flow=flow,
            revision_number=2,
            source_kind="internal",
            source_entity=foreign,
            source_label="",
            destination_kind="external",
            destination_label="Payment processor",
            direction="one_way",
            transfer_mechanism="api",
            data_classification="personal_data",
            purpose="Forged.",
            crosses_trust_boundary=True,
            protection="none",
            provenance="recorded_fact",
            content_digest="0" * 64,
            created_by=installation.owner,
        )


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_a_revision_number_that_skips_the_chain(installation, owner_client):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    organization = _organization(installation, "Chain client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()
    flow = DataFlow.objects.get(entity_id=created["id"])

    # A gap would make "revision 4" unreadable: a reader cannot tell whether 2 and 3
    # were never written or were removed.
    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowRevision.objects.create(
            tenant=flow.tenant,
            workspace=flow.workspace,
            organization=flow.organization,
            data_flow=flow,
            revision_number=4,
            source_kind="external",
            source_label="Vendor",
            destination_kind="external",
            destination_label="Processor",
            direction="one_way",
            transfer_mechanism="api",
            data_classification="internal",
            purpose="Skipped.",
            crosses_trust_boundary=False,
            protection="unknown",
            provenance="recorded_fact",
            content_digest="0" * 64,
            created_by=installation.owner,
        )


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_an_anchor_from_the_wrong_workspace(installation, owner_client):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    organization = _organization(installation, "Anchored client")
    msp_anchor = Entity.objects.create(
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=None),
        organization=None,
        entity_type="data_flow",
        display_name="MSP anchor",
        visibility=EntityVisibility.MSP_PRIVATE,
    )

    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlow.objects.create(
            tenant=installation.tenant,
            workspace=workspace_for_owner(tenant=installation.tenant, organization=organization),
            organization=organization,
            entity=msp_anchor,
            created_by=installation.owner,
        )


@pytest.mark.django_db
def test_a_snapshot_retains_what_a_flow_said_even_after_it_is_revised(installation, owner_client):
    organization = _organization(installation, "Snapshot client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    snapshot = owner_client.post(
        _snapshot_url(organization),
        {"title": "Q3 review", "reason": "Quarterly data-flow review."},
        content_type="application/json",
    )
    assert snapshot.status_code == 201
    owner_client.patch(
        _detail_url(organization, created["id"]),
        _payload(protection="none", data_classification="public"),
        content_type="application/json",
    )

    retained = DataFlowSnapshot.objects.get(id=snapshot.json()["id"])
    flow = retained.flows["flows"][0]
    # The whole reason a snapshot exists: the later revision does not reach back.
    assert flow["protection"] == "in_transit_and_at_rest"
    assert flow["data_classification"] == "personal_data"
    assert flow["revision_number"] == 1
    assert retained.flow_count == 1
    assert AuditEvent.objects.filter(action="data_flow.snapshot.created").count() == 1


@pytest.mark.django_db
def test_a_snapshot_is_immutable_in_python_and_in_postgres(installation, owner_client):
    organization = _organization(installation, "Immutable snapshot client")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Retained"}, content_type="application/json"
    ).json()["id"]

    retained = DataFlowSnapshot.objects.get(id=snapshot_id)
    retained.title = "Rewritten"
    with pytest.raises(ValidationError):
        retained.save()
    with pytest.raises(ValidationError):
        retained.delete()


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_a_direct_snapshot_rewrite(installation, owner_client):
    if transaction.get_connection().vendor != "postgresql":
        pytest.skip("PostgreSQL trigger coverage")
    organization = _organization(installation, "Guarded snapshot client")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Retained"}, content_type="application/json"
    ).json()["id"]

    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowSnapshot.objects.filter(id=snapshot_id).update(title="Rewritten")
    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowSnapshot.objects.filter(id=snapshot_id).delete()


@pytest.mark.django_db
def test_every_export_of_one_snapshot_is_byte_identical_on_repetition(installation, owner_client):
    organization = _organization(installation, "Export client")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    owner_client.post(_url(organization), _payload(name="Second flow"), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Deterministic"}, content_type="application/json"
    ).json()["id"]

    for export_format, media_type in (("json", "application/json"), ("csv", "text/csv"), ("svg", "image/svg+xml")):
        first = owner_client.get(_export_url(organization, snapshot_id, export_format))
        second = owner_client.get(_export_url(organization, snapshot_id, export_format))
        assert first.status_code == 200, export_format
        # A retained export that differs run to run cannot be compared, which is the
        # only thing anyone wants a retained export for.
        assert first.content == second.content, export_format
        assert first["Content-Type"].startswith(media_type)
        assert first["X-Content-Type-Options"] == "nosniff"
        assert f"data-flows-{snapshot_id}.{export_format}" in first["Content-Disposition"]


@pytest.mark.django_db
def test_the_structured_exports_carry_the_asserted_values(installation, owner_client):
    organization = _organization(installation, "Structured client")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Structured"}, content_type="application/json"
    ).json()["id"]

    body = json.loads(owner_client.get(_export_url(organization, snapshot_id, "json")).content)
    rows = list(
        csv.reader(io.StringIO(owner_client.get(_export_url(organization, snapshot_id, "csv")).content.decode()))
    )

    assert body["content_digest"] == body["payload"]["digest"]
    assert body["payload"]["flows"][0]["source"] == "Practice management vendor"
    assert rows[0][:3] == ["name", "source", "destination"]
    assert rows[1][1] == "Practice management vendor"
    assert "personal_data" in rows[1]


@pytest.mark.django_db
def test_the_diagram_survives_a_label_that_would_trip_the_shared_sanitizer(installation, owner_client):
    organization = _organization(installation, "Diagram client")
    # A vendor named after its endpoint is ordinary, and the shared SVG sanitizer
    # rejects any URL scheme. The export must still succeed.
    owner_client.post(
        _url(organization),
        _payload(source_label="https://vendor.example/api"),
        content_type="application/json",
    )
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Diagram"}, content_type="application/json"
    ).json()["id"]

    svg = owner_client.get(_export_url(organization, snapshot_id, "svg"))

    assert svg.status_code == 200
    assert svg.content.startswith(b"<svg")
    assert b"<script" not in svg.content
    assert b"https:" not in svg.content
    # Rects survive sanitization where circles would not: the shared allowlist admits
    # no cx/cy/r, so the geometry has to be rectangular to reach the reader at all.
    assert b"<rect" in svg.content


@pytest.mark.django_db
def test_a_snapshot_belongs_to_one_workspace_only(installation, owner_client):
    organization = _organization(installation, "Owning client")
    sibling = _organization(installation, "Other client")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Owned"}, content_type="application/json"
    ).json()["id"]

    assert owner_client.get(_snapshot_url(sibling)).json()["results"] == []
    assert owner_client.get(_export_url(sibling, snapshot_id, "json")).status_code == 404


@pytest.mark.django_db
def test_an_unknown_export_format_is_refused(installation, owner_client):
    organization = _organization(installation, "Format client")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Formats"}, content_type="application/json"
    ).json()["id"]

    assert owner_client.get(_export_url(organization, snapshot_id, "pdf")).status_code == 404


@pytest.mark.django_db
def test_a_flow_can_be_cited_as_compliance_evidence(installation, owner_client):
    organization = _organization(installation, "Evidence client")
    created = owner_client.post(_url(organization), _payload(), content_type="application/json").json()

    evidence = owner_client.post(
        reverse(
            "organization-compliance-evidence-list-create",
            kwargs={"organization_entity_id": organization.entity_id},
        ),
        {"title": "Billing export flow", "kind": "entity", "source_entity_id": created["id"]},
        content_type="application/json",
    )

    # A data flow is a first-class citable record, gated by its own permission rather
    # than by compliance's, so citing one cannot widen who may read it.
    assert evidence.status_code == 201, evidence.content
    assert evidence.json()["source_entity_id"] == created["id"]
