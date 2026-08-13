import secrets
from datetime import UTC, datetime, timedelta

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.certificate_monitoring import process_certificate_monitoring_run
from apps.core.certificate_monitoring_egress import CollectedCertificateEvidence
from apps.core.domains import DomainInput, create_domain
from apps.core.models import CertificateEndpoint, CertificateMonitorAlert, CertificateMonitorRun, InstallationState
from apps.core.organizations import create_organization
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Certificate MSP",
        owner_email="certificate-owner@example.invalid",
        owner_display_name="Certificate Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


def _evidence(*, leaf: str = "a", trusted: bool = True, hostname_valid: bool = True):
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    return CollectedCertificateEvidence(
        leaf_sha256=leaf * 64,
        chain_sha256="b" * 64,
        chain_length=2,
        subject_common_name="www.example.com",
        issuer_common_name="Example CA",
        serial_sha256="c" * 64,
        san_sha256="d" * 64,
        san_count=2,
        not_before=now - timedelta(days=1),
        not_after=now + timedelta(days=30),
        hostname_valid=hostname_valid,
        trust_valid=trusted,
        tls_version="TLSv1.3",
        cipher_name="TLS_AES_256_GCM_SHA384",
    )


@pytest.mark.django_db
def test_certificate_endpoint_scan_retains_validation_and_change_evidence(installation):
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Certificate Client",
        legal_name="Certificate Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=organization.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(name="example.com", renewal_mode="auto", status="active"),
    )
    browser = Client()
    browser.force_login(installation.owner)
    list_url = reverse(
        "organization-certificate-endpoint-list-create",
        kwargs={"organization_entity_id": organization.entity_id, "domain_entity_id": domain.entity_id},
    )
    response = browser.post(list_url, {"protocol": "https", "hostname_id": None}, content_type="application/json")
    assert response.status_code == 201
    endpoint = CertificateEndpoint.objects.get(entity_id=response.json()["id"])
    scan_url = reverse(
        "organization-certificate-monitoring",
        kwargs={
            "organization_entity_id": organization.entity_id,
            "domain_entity_id": domain.entity_id,
            "endpoint_entity_id": endpoint.entity_id,
        },
    )
    assert browser.post(scan_url, {}, content_type="application/json").status_code == 202
    run = CertificateMonitorRun.objects.get(endpoint=endpoint)
    assert process_certificate_monitoring_run(run_id=run.id, collector=lambda *_args: _evidence())
    endpoint.refresh_from_db()
    assert endpoint.current_trust_valid is True
    assert endpoint.current_hostname_valid is True
    assert endpoint.current_not_after is not None
    assert CertificateMonitorAlert.objects.filter(run=run, kind="expiration_due").exists()

    assert browser.post(scan_url, {}, content_type="application/json").status_code == 202
    changed = CertificateMonitorRun.objects.exclude(pk=run.pk).get(endpoint=endpoint)
    assert process_certificate_monitoring_run(
        run_id=changed.id, collector=lambda *_args: _evidence(leaf="e", trusted=False)
    )
    assert set(CertificateMonitorAlert.objects.filter(run=changed).values_list("kind", flat=True)) == {
        "certificate_changed",
        "validation_failed",
    }
    history = browser.get(scan_url)
    assert history.status_code == 200
    assert len(history.json()["runs"]) == 2

    if connection.vendor == "postgresql":
        with pytest.raises(DatabaseError, match="identity is immutable"), transaction.atomic():
            CertificateEndpoint.objects.filter(pk=endpoint.pk).update(protocol="smtps", port=465)
        with pytest.raises(DatabaseError, match="terminal evidence is immutable"), transaction.atomic():
            CertificateMonitorRun.objects.filter(pk=run.pk).update(error_code="rewritten")
        with pytest.raises(DatabaseError, match="runs are retained"), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM core_certificatemonitorrun WHERE id = %s", [run.pk])
        alert = CertificateMonitorAlert.objects.filter(run=run).first()
        assert alert is not None
        with pytest.raises(DatabaseError, match="alerts are immutable"), transaction.atomic():
            CertificateMonitorAlert.objects.filter(pk=alert.pk).delete()


@pytest.mark.django_db
def test_certificate_endpoint_api_does_not_cross_organization_scope(installation):
    first = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="First Certificate Client",
        legal_name="First Certificate Client LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Certificate Client",
        legal_name="Sibling Certificate Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=first.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(name="scoped.example", renewal_mode="manual", status="active"),
    )
    browser = Client()
    browser.force_login(installation.owner)
    sibling_url = reverse(
        "organization-certificate-endpoint-list-create",
        kwargs={"organization_entity_id": sibling.entity_id, "domain_entity_id": domain.entity_id},
    )
    assert browser.get(sibling_url).status_code == 400
