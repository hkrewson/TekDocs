import secrets
from datetime import UTC, datetime

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.domain_hierarchy import HostnameInput, create_hostname, record_dns_observation
from apps.core.domain_monitoring import enqueue_domain_monitoring, process_domain_monitoring_run
from apps.core.domain_monitoring_egress import CollectedDomainEvidence, DNSAnswer
from apps.core.domains import DomainInput, create_domain, normalize_domain_name, review_domain
from apps.core.models import DomainMonitorAlert, DomainMonitorRunState, InstallationState, ReminderSchedule
from apps.core.organizations import create_organization
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Domain MSP",
        owner_email="domain-owner@example.invalid",
        owner_display_name="Domain Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.mark.django_db
def test_registered_domain_is_normalized_and_exact_workspace_scoped(installation):
    first = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="First Client",
        legal_name="First Client LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Client",
        legal_name="Sibling Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=first.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(
            name="EXAMPLE.COM.", renewal_mode="auto", status="active", expiration_date=datetime(2027, 8, 12).date()
        ),
    )
    assert domain.ascii_name == "example.com"
    assert normalize_domain_name("bücher.example") == "xn--bcher-kva.example"
    assert ReminderSchedule.objects.get(source_entity=domain.entity).due_on.isoformat() == "2027-08-12"
    reviewed = review_domain(
        domain=domain,
        actor_id=installation.owner.id,
        state="conflict",
        observed_expiration_date=datetime(2027, 8, 13).date(),
        source="registrar export",
        note="Verify before renewal.",
    )
    assert reviewed.review_state == "conflict"
    assert reviewed.review_events.count() == 1

    browser = Client()
    browser.force_login(installation.owner)
    first_url = reverse("organization-domain-list-create", kwargs={"organization_entity_id": first.entity_id})
    sibling_url = reverse("organization-domain-list-create", kwargs={"organization_entity_id": sibling.entity_id})
    assert browser.get(first_url).json()[0]["id"] == str(domain.entity_id)
    assert browser.get(sibling_url).json() == []

    hostname = create_hostname(
        workspace=workspace,
        domain=domain,
        actor_id=installation.owner.id,
        value=HostnameInput(name="www.example.com", provenance="entered", source="operator"),
    )
    observation = record_dns_observation(
        hostname=hostname,
        actor_id=installation.owner.id,
        record_type="A",
        value="192.0.2.10",
        ttl=300,
        provenance="entered",
        source="operator",
        observed_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    assert len(observation.content_digest) == 64


@pytest.mark.django_db
def test_domain_monitoring_retains_remote_evidence_and_change_notifications(installation):
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Monitored Client",
        legal_name="Monitored Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(
            name="monitor.example",
            renewal_mode="manual",
            status="active",
            expiration_date=datetime(2027, 8, 12).date(),
        ),
    )
    run = enqueue_domain_monitoring(
        scope=workspace.data_scope,
        domain=domain,
        requested_by_id=installation.owner.id,
        trigger="manual",
    )
    evidence = CollectedDomainEvidence(
        rdap_source="rdap.example.invalid",
        rdap_digest="a" * 64,
        expiration_date=datetime(2027, 8, 13).date(),
        registrar="Example Registrar",
        dns_source="doh.example.invalid",
        dns_digest="b" * 64,
        dnssec_validated=True,
        dns_answers=(DNSAnswer("NS", "ns1.example.invalid.", 3600),),
    )

    assert process_domain_monitoring_run(run_id=run.id, collector=lambda _name: evidence)
    run.refresh_from_db()
    domain.refresh_from_db()
    assert run.state == DomainMonitorRunState.SUCCEEDED
    assert run.dns_record_count == 1
    assert domain.review_state == "conflict"
    assert domain.observed_expiration_date.isoformat() == "2027-08-13"
    assert domain.dns_observations.get().recorded_by is None

    second = enqueue_domain_monitoring(
        scope=workspace.data_scope,
        domain=domain,
        requested_by_id=None,
        trigger="scheduled",
    )
    changed = CollectedDomainEvidence(
        rdap_source=evidence.rdap_source,
        rdap_digest="c" * 64,
        expiration_date=datetime(2028, 8, 13).date(),
        registrar=evidence.registrar,
        dns_source=evidence.dns_source,
        dns_digest="d" * 64,
        dnssec_validated=False,
        dns_answers=(DNSAnswer("NS", "ns2.example.invalid.", 3600),),
    )
    assert process_domain_monitoring_run(run_id=second.id, collector=lambda _name: changed)
    assert set(DomainMonitorAlert.objects.filter(run=second).values_list("kind", flat=True)) == {
        "expiration_changed",
        "dns_changed",
    }


@pytest.mark.django_db
def test_domain_monitoring_api_does_not_cross_organization_scope(installation):
    first = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Monitor First",
        legal_name="Monitor First LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Monitor Sibling",
        legal_name="Monitor Sibling LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=first.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(name="scoped.example", renewal_mode="auto", status="active"),
    )
    browser = Client()
    browser.force_login(installation.owner)
    first_url = reverse(
        "organization-domain-monitoring",
        kwargs={"organization_entity_id": first.entity_id, "domain_entity_id": domain.entity_id},
    )
    sibling_url = reverse(
        "organization-domain-monitoring",
        kwargs={"organization_entity_id": sibling.entity_id, "domain_entity_id": domain.entity_id},
    )
    assert browser.post(first_url, data={}, content_type="application/json").status_code == 202
    assert browser.get(first_url).status_code == 200
    assert browser.get(sibling_url).status_code == 400
