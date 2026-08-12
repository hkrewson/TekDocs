import secrets
from datetime import timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.compliance_catalogs import ControlInput, create_catalog_version, create_framework, frameworks_for_scope
from apps.core.compliance_evidence import EvidenceInput, create_evidence, link_evidence, review_evidence
from apps.core.compliance_operations import AssignmentInput, record_assignment_review
from apps.core.compliance_risks import RiskInput, create_risk, review_risk, risk_summary
from apps.core.models import (
    ComplianceCatalogEntry,
    ComplianceCatalogRevision,
    ComplianceRiskEvent,
    InstallationState,
)
from apps.core.organizations import create_organization
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_msp_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Compliance MSP",
        owner_email="compliance-owner@example.invalid",
        owner_display_name="Compliance Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client()
    browser.force_login(installation.owner)
    return browser


def control(identifier: str, title: str, *, control_id=None, guidance=""):
    return ControlInput(
        identifier=identifier,
        title=title,
        description="Control description",
        guidance=guidance,
        control_id=control_id,
    )


@pytest.mark.django_db
def test_catalog_versions_pin_exact_control_revisions_and_preserve_history(installation):
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="TekDocs Baseline",
        version_label="2026.1",
        description="Initial baseline",
        source_url="https://example.invalid/baseline",
        controls=[control("TD-1", "Inventory"), control("TD-2", "Recovery")],
    )
    framework = frameworks_for_scope(DataScope.tenant(installation.tenant)).get(pk=framework.pk)
    first = framework.current_revision
    first_entries = list(first.entries.all())
    unchanged = first_entries[0].control_revision
    changing = first_entries[1].control_revision

    second = create_catalog_version(
        framework=framework,
        actor_id=installation.owner.id,
        version_label="2026.2",
        description="Recovery guidance clarified",
        source_url="https://example.invalid/baseline",
        controls=[
            control("TD-1", "Inventory", control_id=unchanged.control.entity_id),
            control("TD-2", "Recovery", control_id=changing.control.entity_id, guidance="Test restores quarterly."),
        ],
    )
    second_entries = list(second.entries.select_related("control_revision__control").order_by("position"))

    assert second_entries[0].control_revision_id == unchanged.id
    assert second_entries[1].control_revision.control_id == changing.control_id
    assert second_entries[1].control_revision.revision_number == 2
    first.refresh_from_db()
    assert first.entries.get(position=1).control_revision_id == changing.id
    assert first.content_digest != second.content_digest
    assert ComplianceCatalogRevision.objects.filter(framework=framework).count() == 2
    with pytest.raises(ValidationError):
        first.delete()
    with pytest.raises(ValidationError):
        first.version_label = "rewritten"
        first.save()


@pytest.mark.django_db
def test_compliance_api_is_workspace_scoped_and_revisions_are_addressable(owner_client, installation):
    client = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Scoped Client",
        legal_name="Scoped Client LLC",
        website="https://client.example.invalid",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Client",
        legal_name="Sibling Client LLC",
        website="https://sibling.example.invalid",
        classifications=["client"],
    )
    collection = reverse(
        "organization-compliance-framework-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    created = owner_client.post(
        collection,
        {
            "name": "Client Security Standard",
            "version_label": "v1",
            "description": "Client-owned catalog",
            "controls": [{"identifier": "CS-1", "title": "Asset inventory"}],
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["current_revision"]["entries"][0]["control"]["identifier"] == "CS-1"
    assert owner_client.get(collection).json()["count"] == 1
    assert owner_client.get(reverse("msp-compliance-framework-list-create")).json()["count"] == 0
    assert (
        owner_client.get(
            reverse(
                "organization-compliance-framework-detail",
                kwargs={"organization_entity_id": sibling.entity_id, "framework_entity_id": body["id"]},
            )
        ).status_code
        == 404
    )

    revisions_url = reverse(
        "organization-compliance-catalog-revision-list-create",
        kwargs={"organization_entity_id": client.entity_id, "framework_entity_id": body["id"]},
    )
    revised = owner_client.post(
        revisions_url,
        {
            "version_label": "v2",
            "controls": [
                {
                    "control_id": body["current_revision"]["entries"][0]["control"]["control_id"],
                    "identifier": "CS-1",
                    "title": "Asset inventory",
                    "guidance": "Review quarterly.",
                }
            ],
        },
        content_type="application/json",
    )
    assert revised.status_code == 201
    assert revised.json()["revision_number"] == 2
    assert len(owner_client.get(revisions_url).json()) == 2
    first = owner_client.get(
        reverse(
            "organization-compliance-catalog-revision-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "framework_entity_id": body["id"],
                "revision_number": 1,
            },
        )
    )
    assert first.status_code == 200
    assert first.json()["entries"][0]["control"]["guidance"] == ""


@pytest.mark.django_db
def test_catalog_input_is_strict_and_rejects_duplicate_control_identity(owner_client, installation):
    url = reverse("msp-compliance-framework-list-create")
    assert (
        owner_client.post(
            url,
            {"name": "Bad", "version_label": "v1", "unexpected": "value"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        owner_client.post(
            url,
            {
                "name": "Duplicates",
                "version_label": "v1",
                "controls": [
                    {"identifier": "A-1", "title": "First"},
                    {"identifier": "a-1", "title": "Duplicate"},
                ],
            },
            content_type="application/json",
        ).status_code
        == 400
    )
    assert ComplianceCatalogRevision.objects.count() == 0
    assert ComplianceCatalogEntry.objects.count() == 0


@pytest.mark.django_db
def test_assignments_pin_current_control_revision_and_retain_review_history(installation):
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="Review baseline",
        version_label="v1",
        description="",
        source_url="",
        controls=[control("R-1", "Review me")],
    )
    control_record = framework.controls.get()
    first = record_assignment_review(
        framework=framework,
        control_entity_id=control_record.entity_id,
        actor_id=installation.owner.id,
        value=AssignmentInput(applicability="applicable", implementation_status="planned", decision="Accepted"),
    )
    second = record_assignment_review(
        framework=framework,
        control_entity_id=control_record.entity_id,
        actor_id=installation.owner.id,
        value=AssignmentInput(applicability="applicable", implementation_status="implemented", decision="Verified"),
    )
    assert first.pk == second.pk
    assert list(second.reviews.values_list("decision", flat=True)) == ["Verified", "Accepted"]
    with pytest.raises(ValidationError):
        second.reviews.first().delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        second.reviews.filter(decision="Accepted").update(decision="Rewritten")


@pytest.mark.django_db
def test_assignment_api_is_exact_workspace_scoped(owner_client, installation):
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="API baseline",
        version_label="v1",
        description="",
        source_url="",
        controls=[control("A-1", "API control")],
    )
    control_record = framework.controls.get()
    url = reverse(
        "msp-compliance-assignment-review",
        kwargs={
            "framework_entity_id": framework.entity_id,
            "control_entity_id": control_record.entity_id,
        },
    )
    response = owner_client.post(
        url,
        {
            "applicability": "applicable",
            "implementation_status": "in_progress",
            "decision": "Work started",
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["control_id"] == str(control_record.entity_id)
    listing = owner_client.get(
        reverse("msp-compliance-assignment-list", kwargs={"framework_entity_id": framework.entity_id})
    )
    assert listing.status_code == 200
    assert listing.json()["results"][0]["reviews"][0]["decision"] == "Work started"
    assert listing.json()["owner_choices"][0]["display_name"] == installation.owner.display_name
    denied = owner_client.post(
        url,
        {
            "applicability": "applicable",
            "implementation_status": "implemented",
            "owner_id": "00000000-0000-4000-8000-000000000099",
            "decision": "Invalid owner",
        },
        content_type="application/json",
    )
    assert denied.status_code == 400


@pytest.mark.django_db
def test_evidence_is_reused_with_exact_revision_links_and_retained_reviews(installation):
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="Evidence baseline",
        version_label="v1",
        description="",
        source_url="",
        controls=[control("E-1", "First"), control("E-2", "Second")],
    )
    assignments = [
        record_assignment_review(
            framework=framework,
            control_entity_id=item.entity_id,
            actor_id=installation.owner.id,
            value=AssignmentInput(
                applicability="applicable",
                implementation_status="implemented",
                decision="In scope",
            ),
        )
        for item in framework.controls.all()
    ]
    evidence = create_evidence(
        workspace=resolve_msp_workspace(installation.owner),
        actor_id=installation.owner.id,
        value=EvidenceInput(title="Quarterly access review", kind="note", summary="Reviewed **quarterly**."),
    )
    review = review_evidence(
        evidence=evidence,
        actor_id=installation.owner.id,
        status="accepted",
        decision="Current",
    )
    links = [link_evidence(assignment=item, evidence=evidence, actor_id=installation.owner.id) for item in assignments]
    assert {item.control_revision_id for item in links} == {item.control_revision_id for item in assignments}
    assert evidence.control_links.count() == 2
    with pytest.raises(DatabaseError), transaction.atomic():
        evidence.reviews.filter(pk=review.pk).update(decision="Rewritten")


@pytest.mark.django_db
def test_evidence_api_creates_reviews_and_links_in_the_msp_workspace(owner_client, installation):
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="Evidence API",
        version_label="v1",
        description="",
        source_url="",
        controls=[control("EA-1", "API evidence")],
    )
    assignment = record_assignment_review(
        framework=framework,
        control_entity_id=framework.controls.get().entity_id,
        actor_id=installation.owner.id,
        value=AssignmentInput(applicability="applicable", implementation_status="implemented", decision="Implemented"),
    )
    created = owner_client.post(
        reverse("msp-compliance-evidence-list-create"),
        {"title": "Configuration export", "kind": "url", "source_url": "https://example.invalid/evidence"},
        content_type="application/json",
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]
    reviewed = owner_client.post(
        reverse("msp-compliance-evidence-review", kwargs={"evidence_entity_id": evidence_id}),
        {"status": "accepted", "decision": "Verified"},
        content_type="application/json",
    )
    assert reviewed.status_code == 201
    linked = owner_client.post(
        reverse("msp-compliance-assignment-evidence-link", kwargs={"assignment_id": assignment.pk}),
        {"evidence_id": evidence_id},
        content_type="application/json",
    )
    assert linked.status_code == 201
    listing = owner_client.get(reverse("msp-compliance-evidence-list-create"))
    assert listing.json()["results"][0]["control_links"][0]["control_id"] == str(assignment.control.entity_id)


@pytest.mark.django_db(transaction=True)
def test_database_guards_retain_catalog_evidence_and_reject_scope_retargeting(installation):
    if connection.vendor != "postgresql":
        pytest.skip("Compliance database guards require PostgreSQL")
    framework = create_framework(
        tenant=installation.tenant,
        organization=None,
        actor_id=installation.owner.id,
        name="Guarded Baseline",
        version_label="v1",
        description="",
        source_url="",
        controls=[control("G-1", "Guarded control")],
    )
    revision = ComplianceCatalogRevision.objects.get(framework=framework)
    entry = ComplianceCatalogEntry.objects.get(catalog_revision=revision)
    with pytest.raises(DatabaseError), transaction.atomic():
        ComplianceCatalogRevision.objects.filter(pk=revision.pk).update(version_label="rewritten")
    with pytest.raises(DatabaseError), transaction.atomic():
        ComplianceCatalogEntry.objects.filter(pk=entry.pk).delete()


@pytest.mark.django_db
def test_risks_score_treatment_acceptance_deadlines_and_retained_decisions(installation):
    workspace = resolve_msp_workspace(installation.owner)
    risk = create_risk(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=RiskInput(
            title="Unsupported firewall",
            description="The perimeter appliance is end of support.",
            likelihood=4,
            impact=5,
            status="open",
            treatment="mitigate",
            treatment_plan="Replace the appliance.",
            due_date=timezone.localdate() - timedelta(days=1),
            owner_id=installation.owner.id,
            decision="Added to register",
        ),
    )
    assert risk.score == 20
    assert risk.reporting_band == "critical"
    assert risk_summary(workspace.data_scope)["overdue"] == 1

    accepted = review_risk(
        risk=risk,
        workspace=workspace,
        actor_id=installation.owner.id,
        value=RiskInput(
            title="Unsupported firewall",
            description=risk.description,
            likelihood=2,
            impact=3,
            status="accepted",
            treatment="accept",
            treatment_plan="Replacement is scheduled next quarter.",
            due_date=None,
            owner_id=installation.owner.id,
            decision="Residual risk accepted",
        ),
    )
    assert accepted.accepted_by_id == installation.owner.id
    assert accepted.accepted_at is not None
    assert accepted.events.count() == 2
    assert risk_summary(workspace.data_scope)["by_status"] == {"accepted": 1}
    event = accepted.events.first()
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        ComplianceRiskEvent.objects.filter(pk=event.pk).update(decision="Rewritten")


@pytest.mark.django_db
def test_risk_api_reports_exact_workspace_and_requires_explicit_acceptance(owner_client, installation):
    url = reverse("msp-compliance-risk-list-create")
    created = owner_client.post(
        url,
        {
            "title": "Recovery gap",
            "description": "Restore evidence is incomplete.",
            "likelihood": 3,
            "impact": 4,
            "status": "monitoring",
            "treatment": "mitigate",
            "treatment_plan": "Complete a restore test.",
            "owner_id": str(installation.owner.id),
            "decision": "Track this quarter",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["score"] == 12
    assert created.json()["reporting_band"] == "high"
    listing = owner_client.get(url).json()
    assert listing["summary"]["total"] == 1
    assert listing["owner_choices"][0]["id"] == str(installation.owner.id)

    invalid = owner_client.post(
        reverse("msp-compliance-risk-review", kwargs={"risk_entity_id": created.json()["id"]}),
        {
            "title": "Recovery gap",
            "description": "Restore evidence is incomplete.",
            "likelihood": 2,
            "impact": 3,
            "status": "accepted",
            "treatment": "mitigate",
            "decision": "Invalid acceptance",
        },
        content_type="application/json",
    )
    assert invalid.status_code == 400
