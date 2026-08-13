import hashlib
import os
from datetime import timedelta

from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.certificate_monitoring import create_certificate_endpoint
from apps.core.domains import DomainInput, create_domain
from apps.core.models import (
    CertificateMonitorRun,
    DomainMonitorRun,
    InstallationState,
    Organization,
)
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace


OWNER_EMAIL = "monitoring-recovery@example.invalid"
ORGANIZATION_NAME = "Monitoring Recovery Client"
DOMAIN_NAME = "monitoring-recovery.example"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def _has_field(model, name):
    return any(field.name == name for field in model._meta.get_fields())


def create_fixture():
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Monitoring Recovery MSP",
        owner_email=OWNER_EMAIL,
        owner_display_name="Monitoring Recovery Owner",
        password=os.environ["TEKDOCS_FIXTURE_PASSWORD"],
    )
    with rls_scope(DataScope.tenant(result.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = create_organization(
            tenant=result.tenant,
            actor_id=result.owner.id,
            name=ORGANIZATION_NAME,
            legal_name=f"{ORGANIZATION_NAME}, LLC",
            website="",
            classifications=["client"],
        )
        workspace = resolve_organization_workspace(result.owner, entity_id=organization.entity_id)
    scope = workspace.data_scope
    with rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION):
        domain = create_domain(
            workspace=workspace,
            actor_id=result.owner.id,
            value=DomainInput(name=DOMAIN_NAME, renewal_mode="manual", status="active"),
        )
        endpoint = create_certificate_endpoint(
            scope=scope,
            domain=domain,
            actor_id=result.owner.id,
            protocol="https",
            hostname_id=None,
        )
        now = timezone.now()
        domain_run = DomainMonitorRun.objects.create(
            tenant=result.tenant,
            workspace=domain.workspace,
            organization=organization,
            domain=domain,
            trigger="scheduled",
        )
        domain_values = {
            "state": "succeeded",
            "finished_at": now,
            "rdap_source": "rdap.example",
            "rdap_digest": HEX_A,
            "observed_expiration_date": (now + timedelta(days=180)).date(),
            "observed_registrar": "Recovery Registrar",
            "dns_source": "resolver.example",
            "dns_digest": HEX_B,
            "dnssec_validated": True,
            "dns_record_count": 4,
        }
        if _has_field(DomainMonitorRun, "caa_digest"):
            domain_values.update(
                caa_digest=hashlib.sha256(b"[]").hexdigest(),
                caa_record_count=0,
                evidence_digest=HEX_C,
            )
        DomainMonitorRun.objects.filter(pk=domain_run.pk).update(**domain_values)

        certificate_run = CertificateMonitorRun.objects.create(
            tenant=result.tenant,
            workspace=domain.workspace,
            organization=organization,
            endpoint=endpoint,
            trigger="scheduled",
        )
        certificate_values = {
            "state": "succeeded",
            "finished_at": now,
            "leaf_sha256": HEX_A,
            "chain_sha256": HEX_B,
            "chain_length": 2,
            "subject_common_name": DOMAIN_NAME,
            "issuer_common_name": "Recovery CA",
            "serial_sha256": HEX_C,
            "san_sha256": HEX_A,
            "san_count": 1,
            "not_before": now - timedelta(days=1),
            "not_after": now + timedelta(days=90),
            "hostname_valid": True,
            "trust_valid": True,
            "tls_version": "TLSv1.3",
            "cipher_name": "TLS_AES_256_GCM_SHA384",
        }
        if _has_field(CertificateMonitorRun, "evidence_digest"):
            certificate_values["evidence_digest"] = HEX_C
        CertificateMonitorRun.objects.filter(pk=certificate_run.pk).update(**certificate_values)
    print("monitoring stabilization fixture created")


def verify_fixture():
    owner = User.objects.get(email=OWNER_EMAIL)
    tenant = owner.tenant_memberships.get().tenant
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
        organization = Organization.objects.get(tenant=tenant, entity__display_name=ORGANIZATION_NAME)
        workspace = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    scope = workspace.data_scope
    with rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION):
        domain_run = DomainMonitorRun.objects.get(domain__ascii_name=DOMAIN_NAME, state="succeeded")
        certificate_run = CertificateMonitorRun.objects.get(
            endpoint__domain__ascii_name=DOMAIN_NAME,
            state="succeeded",
        )
        assert len(domain_run.evidence_digest) == 64
        assert len(domain_run.caa_digest) == 64
        assert domain_run.caa_record_count == 0
        assert domain_run.dnssec_validated is True
        assert len(certificate_run.evidence_digest) == 64
        assert certificate_run.hostname_valid is True
        assert certificate_run.trust_valid is True
    print("monitoring stabilization fixture verified")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
