import secrets
from datetime import timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.certificate_monitoring import create_certificate_endpoint
from apps.core.domains import DomainInput, create_domain
from apps.core.models import CertificateMonitorRun, DomainMonitorRun, InstallationState
from apps.core.organizations import create_organization
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Monitoring Scale MSP",
        owner_email="monitoring-scale-owner@example.invalid",
        owner_display_name="Monitoring Scale Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.mark.django_db
def test_large_monitoring_histories_are_bounded_and_query_stable(installation):
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Monitoring History Client",
        legal_name="Monitoring History Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(name="history.example", renewal_mode="manual", status="active"),
    )
    endpoint = create_certificate_endpoint(
        scope=workspace.data_scope,
        domain=domain,
        actor_id=installation.owner.id,
        protocol="https",
        hostname_id=None,
    )
    now = timezone.now()
    DomainMonitorRun.objects.bulk_create(
        [
            DomainMonitorRun(
                tenant=installation.tenant,
                workspace=domain.workspace,
                organization=organization,
                domain=domain,
                trigger="scheduled",
                available_at=now + timedelta(seconds=index),
            )
            for index in range(250)
        ]
    )
    CertificateMonitorRun.objects.bulk_create(
        [
            CertificateMonitorRun(
                tenant=installation.tenant,
                workspace=domain.workspace,
                organization=organization,
                endpoint=endpoint,
                trigger="scheduled",
                available_at=now + timedelta(seconds=index),
            )
            for index in range(250)
        ]
    )
    browser = Client()
    browser.force_login(installation.owner)
    domain_url = reverse(
        "organization-domain-monitoring",
        kwargs={"organization_entity_id": organization.entity_id, "domain_entity_id": domain.entity_id},
    )
    certificate_url = reverse(
        "organization-certificate-monitoring",
        kwargs={
            "organization_entity_id": organization.entity_id,
            "domain_entity_id": domain.entity_id,
            "endpoint_entity_id": endpoint.entity_id,
        },
    )
    with CaptureQueriesContext(connection) as domain_queries:
        domain_response = browser.get(domain_url)
    with CaptureQueriesContext(connection) as certificate_queries:
        certificate_response = browser.get(certificate_url)
    assert domain_response.status_code == certificate_response.status_code == 200
    assert len(domain_response.json()["runs"]) == 25
    assert len(certificate_response.json()["runs"]) == 25
    assert len(domain_queries) <= 35
    assert len(certificate_queries) <= 35
