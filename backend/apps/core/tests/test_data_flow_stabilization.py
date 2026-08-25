"""Stabilization coverage for the data-flow surfaces (ADR 0088, `0.8.36`).

These tests are adversarial rather than demonstrative: they assert what the surfaces
refuse, what they bound, and what the constrained runtime role cannot reach.
"""

import secrets
import uuid
from xml.etree import ElementTree

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import DataFlow, DataFlowRevision, DataFlowSnapshot, InstallationState
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, bind_local_rls_scope
from apps.core.scoping import DataScope

#: A listing must answer within this many queries however much data sits behind it.
COLLECTION_QUERY_BUDGET = 32


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Flow Stabilization MSP",
        owner_email=f"flow-stab-{uuid.uuid4()}@example.invalid",
        owner_display_name="Flow Stabilization Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client(enforce_csrf_checks=False)
    browser.force_login(installation.owner)
    return browser


def _organization(installation, name):
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )


def _url(organization):
    return reverse("organization-data-flows", kwargs={"organization_entity_id": organization.entity_id})


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
        "source_label": "Vendor",
        "destination_kind": "external",
        "destination_label": "Processor",
        "direction": "one_way",
        "transfer_mechanism": "api",
        "data_classification": "internal",
        "purpose": "Stated purpose.",
        "crosses_trust_boundary": False,
        "protection": "unknown",
        "provenance": "recorded_fact",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("label", "overrides"),
    (
        ("oversized name", {"name": "n" * 241}),
        ("oversized purpose", {"purpose": "p" * 1001}),
        ("oversized label", {"source_label": "s" * 241}),
        ("empty name", {"name": "   "}),
        ("empty purpose", {"purpose": "   "}),
        ("null byte in name", {"name": "\x00Bad"}),
        ("unknown direction", {"direction": "sideways"}),
        ("unknown mechanism", {"transfer_mechanism": "carrier_pigeon"}),
        ("unknown classification", {"data_classification": "cosmic"}),
        ("unknown protection", {"protection": "vibes"}),
        ("unknown provenance", {"provenance": "trust_me"}),
        ("unknown endpoint kind", {"source_kind": "somewhere"}),
        ("malformed review date", {"review_due_on": "the 3rd of never"}),
        ("unexpected field", {"injected": "value"}),
    ),
)
def test_a_flow_is_refused_rather_than_absorbed(installation, owner_client, label, overrides):
    organization = _organization(installation, "Hostile client")

    response = owner_client.post(_url(organization), _payload(**overrides), content_type="application/json")

    assert response.status_code == 400, label
    # A refusal must leave nothing behind: the anchor, the flow and its first revision
    # are written in one transaction or not at all.
    assert not DataFlow.objects.filter(tenant=installation.tenant).exists(), label
    assert not DataFlowRevision.objects.exists(), label


@pytest.mark.django_db
def test_a_malformed_request_body_is_refused_without_echoing_it(installation, owner_client):
    organization = _organization(installation, "Malformed client")
    marker = f"must-not-echo-{secrets.token_hex(8)}"

    response = owner_client.post(_url(organization), f'{{"name":"{marker}"', content_type="application/json")

    assert response.status_code == 400
    assert marker not in response.content.decode()


@pytest.mark.django_db
def test_a_listing_refuses_unbounded_pagination(installation, owner_client):
    organization = _organization(installation, "Paging client")

    assert owner_client.get(_url(organization), {"page_size": 5000}).status_code == 400
    assert owner_client.get(_url(organization), {"page_size": 0}).status_code == 400
    assert owner_client.get(_url(organization), {"page": 0}).status_code == 400


@pytest.mark.django_db
def test_a_snapshot_title_is_bounded(installation, owner_client):
    organization = _organization(installation, "Snapshot bound client")

    long_title = owner_client.post(_snapshot_url(organization), {"title": "t" * 241}, content_type="application/json")
    blank_title = owner_client.post(_snapshot_url(organization), {"title": "   "}, content_type="application/json")
    unexpected = owner_client.post(
        _snapshot_url(organization), {"title": "Fine", "extra": "no"}, content_type="application/json"
    )

    assert long_title.status_code == 400
    assert blank_title.status_code == 400
    assert unexpected.status_code == 400


@pytest.mark.django_db
def test_the_flow_listing_stays_within_its_query_budget_as_flows_accumulate(installation, owner_client):
    organization = _organization(installation, "Budgeted client")
    for index in range(40):
        owner_client.post(_url(organization), _payload(name=f"Flow {index:03d}"), content_type="application/json")

    with CaptureQueriesContext(connection) as queries:
        response = owner_client.get(_url(organization), {"page_size": 50})

    assert response.status_code == 200
    assert response.json()["count"] == 40
    # A per-record query here would make page cost grow with the workspace.
    assert len(queries) <= COLLECTION_QUERY_BUDGET, f"listing used {len(queries)} queries"


@pytest.mark.django_db
def test_a_snapshot_export_reads_the_retained_row_rather_than_the_live_records(installation, owner_client):
    organization = _organization(installation, "Export budget client")
    for index in range(30):
        owner_client.post(_url(organization), _payload(name=f"Flow {index:03d}"), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Budgeted"}, content_type="application/json"
    ).json()["id"]

    for export_format in ("json", "csv", "svg"):
        with CaptureQueriesContext(connection) as queries:
            response = owner_client.get(_export_url(organization, snapshot_id, export_format))
        assert response.status_code == 200, export_format
        assert len(queries) <= COLLECTION_QUERY_BUDGET, f"{export_format} used {len(queries)} queries"


@pytest.mark.django_db
def test_the_diagram_is_bounded_however_many_flows_a_snapshot_holds(installation, owner_client):
    organization = _organization(installation, "Large snapshot client")
    for index in range(70):
        owner_client.post(_url(organization), _payload(name=f"Flow {index:03d}"), content_type="application/json")
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Large"}, content_type="application/json"
    ).json()["id"]

    svg = owner_client.get(_export_url(organization, snapshot_id, "svg"))
    csv_export = owner_client.get(_export_url(organization, snapshot_id, "csv"))

    # The picture is capped and says so; the structured export still carries every row,
    # so the cap costs legibility rather than evidence.
    assert b"further flows are recorded in this snapshot and not drawn" in svg.content
    assert len(csv_export.content.decode().strip().split("\n")) == 71


@pytest.mark.django_db(transaction=True)
def test_the_runtime_role_cannot_read_or_write_another_clients_flows(installation, owner_client, django_runtime_role):
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")
    organization = _organization(installation, "Runtime client")
    sibling = _organization(installation, "Runtime sibling")
    owner_client.post(_url(organization), _payload(), content_type="application/json")
    owner_client.post(_snapshot_url(organization), {"title": "Runtime"}, content_type="application/json")
    selected = DataScope.organization(installation.tenant, organization)
    foreign = DataScope.organization(installation.tenant, sibling)

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(selected, organization_mode=OrganizationRLSMode.ORGANIZATION)
        assert DataFlow.scoped.for_scope(selected).count() == 1
        assert DataFlowSnapshot.scoped.for_scope(selected).count() == 1

        bind_local_rls_scope(foreign, organization_mode=OrganizationRLSMode.ORGANIZATION)
        # Under the constrained role the sibling's rows are not merely filtered by the
        # ORM: the database does not return them, and a write reaches nothing.
        assert not DataFlow.objects.exists()
        assert not DataFlowRevision.objects.exists()
        assert not DataFlowSnapshot.objects.exists()
        assert DataFlow.objects.update(archived_at=None) == 0
        assert DataFlowSnapshot.objects.update(title="Bypassed") == 0


@pytest.mark.django_db
def test_an_adversarial_label_cannot_reach_the_diagram_as_markup(installation, owner_client):
    organization = _organization(installation, "Injection client")
    owner_client.post(
        _url(organization),
        _payload(
            name="</text><script>alert(1)</script>",
            source_label='"><script>alert(2)</script>',
            destination_label="<img src=x onerror=alert(3)>",
        ),
        content_type="application/json",
    )
    snapshot_id = owner_client.post(
        _snapshot_url(organization), {"title": "Injection"}, content_type="application/json"
    ).json()["id"]

    svg = owner_client.get(_export_url(organization, snapshot_id, "svg"))

    assert svg.status_code == 200
    # Parse rather than search for substrings. An escaped payload legitimately contains
    # the word "onerror" as drawn text, so a substring check would either fail on safe
    # output or pass on unsafe output depending on how it was written. The property that
    # matters is structural: what elements and attributes actually exist.
    # S314: the document parsed here is this project's own sanitizer output, produced
    # inside the test process and carrying no DOCTYPE, so there is no external entity
    # to resolve. The hostile part is the label text, which is exactly what is under
    # test. defusedxml is only a transitive dependency here and is not declared.
    document = ElementTree.fromstring(svg.content.decode())  # noqa: S314
    elements = [document, *document.iter()]
    tags = {element.tag.rsplit("}", 1)[-1] for element in elements}
    attributes = {name.lower() for element in elements for name in element.attrib}

    assert "script" not in tags
    assert "img" not in tags
    assert not any(name.startswith("on") for name in attributes)
    assert tags <= {"svg", "rect", "line", "text"}
    # The payload survives as inert text, so nothing is silently discarded either.
    assert "alert(3)" in "".join(element.text or "" for element in elements)
