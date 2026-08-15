import hashlib
import os
from datetime import timedelta

from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import User
from apps.core.certificate_monitoring import create_certificate_endpoint
from apps.core.compliance_bundles import create_bundle, verify_bundle
from apps.core.compliance_catalogs import ControlInput, create_framework
from apps.core.compliance_evidence import EvidenceInput, create_evidence, link_evidence, review_evidence
from apps.core.compliance_operations import AssignmentInput, record_assignment_review
from apps.core.compliance_risks import RiskInput, create_risk
from apps.core.domains import DomainInput, create_domain
from apps.core.models import (
    CertificateMonitorRun,
    ComplianceEvidenceBundle,
    DomainMonitorRun,
    InstallationState,
    Organization,
    ReminderSchedule,
)
from apps.core.organizations import create_organization
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope, rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace


OWNER_EMAIL = "validation-recovery@example.invalid"
ORGANIZATION_NAME = "Validation Recovery Client"
DOMAIN_NAME = "validation-recovery.example"
FRAMEWORK_NAME = "Validation Recovery Baseline"
BUNDLE_TITLE = "Validation Recovery Evidence"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def create_fixture():
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Validation Recovery MSP",
        owner_email=OWNER_EMAIL,
        owner_display_name="Validation Recovery Owner",
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
        bind_local_rls_scope(
            DataScope.tenant(result.tenant),
            organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
            actor_user_id=result.owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        workspace = resolve_organization_workspace(result.owner, entity_id=organization.entity_id)

    scope = workspace.data_scope
    now = timezone.now()
    with rls_scope(scope, organization_mode=OrganizationRLSMode.ORGANIZATION):
        framework = create_framework(
            tenant=result.tenant,
            organization=organization,
            actor_id=result.owner.id,
            name=FRAMEWORK_NAME,
            version_label="2026.1",
            description="Retained validation fixture.",
            source_url="",
            controls=[
                ControlInput(
                    identifier="CERT-1",
                    title="Monitor managed domains",
                    description="Retain scoped domain and certificate evidence.",
                    guidance="Review evidence before acceptance.",
                )
            ],
        )
        assignment = record_assignment_review(
            framework=framework,
            control_entity_id=framework.controls.get().entity_id,
            actor_id=result.owner.id,
            value=AssignmentInput(
                applicability="applicable",
                implementation_status="implemented",
                owner_id=result.owner.id,
                review_due_date=(now + timedelta(days=90)).date(),
                decision="Monitoring boundary reviewed",
            ),
        )
        evidence = create_evidence(
            workspace=workspace,
            actor_id=result.owner.id,
            value=EvidenceInput(
                title="Monitoring review record",
                kind="note",
                summary="Domain and certificate evidence reviewed for validation.",
                collection_start=now.date(),
                collection_end=now.date(),
            ),
        )
        review_evidence(
            evidence=evidence,
            actor_id=result.owner.id,
            status="accepted",
            decision="Evidence accepted",
        )
        link_evidence(assignment=assignment, evidence=evidence, actor_id=result.owner.id)
        create_risk(
            workspace=workspace,
            actor_id=result.owner.id,
            value=RiskInput(
                title="Monitoring evidence drift",
                description="Observed state can change after collection.",
                likelihood=2,
                impact=3,
                status="monitoring",
                treatment="mitigate",
                treatment_plan="Retain recurring checks and review changes.",
                assignment_id=assignment.id,
                owner_id=result.owner.id,
                due_date=(now + timedelta(days=30)).date(),
                decision="Track residual drift risk",
            ),
        )
        bundle = create_bundle(
            workspace=workspace,
            actor_id=result.owner.id,
            title=BUNDLE_TITLE,
            reason="Exact-prior upgrade and independent restore validation",
            audience="msp_internal",
        )
        assert verify_bundle(bundle)

        domain = create_domain(
            workspace=workspace,
            actor_id=result.owner.id,
            value=DomainInput(
                name=DOMAIN_NAME,
                renewal_mode="manual",
                status="active",
                expiration_date=(now + timedelta(days=180)).date(),
            ),
        )
        endpoint = create_certificate_endpoint(
            scope=scope,
            domain=domain,
            actor_id=result.owner.id,
            protocol="https",
            hostname_id=None,
        )
        domain_run = DomainMonitorRun.objects.create(
            tenant=result.tenant,
            workspace=domain.workspace,
            organization=organization,
            domain=domain,
            trigger="scheduled",
        )
        DomainMonitorRun.objects.filter(pk=domain_run.pk).update(
            state="succeeded",
            finished_at=now,
            rdap_source="rdap.example",
            rdap_digest=HEX_A,
            observed_expiration_date=(now + timedelta(days=180)).date(),
            observed_registrar="Validation Registrar",
            dns_source="resolver.example",
            dns_digest=HEX_B,
            dnssec_validated=True,
            dns_record_count=4,
            caa_digest=hashlib.sha256(b"[]").hexdigest(),
            caa_record_count=0,
            evidence_digest=HEX_C,
        )
        certificate_run = CertificateMonitorRun.objects.create(
            tenant=result.tenant,
            workspace=domain.workspace,
            organization=organization,
            endpoint=endpoint,
            trigger="scheduled",
        )
        CertificateMonitorRun.objects.filter(pk=certificate_run.pk).update(
            state="succeeded",
            finished_at=now,
            leaf_sha256=HEX_A,
            chain_sha256=HEX_B,
            chain_length=2,
            subject_common_name=DOMAIN_NAME,
            issuer_common_name="Validation CA",
            serial_sha256=HEX_C,
            san_sha256=HEX_A,
            san_count=1,
            not_before=now - timedelta(days=1),
            not_after=now + timedelta(days=90),
            hostname_valid=True,
            trust_valid=True,
            tls_version="TLSv1.3",
            cipher_name="TLS_AES_256_GCM_SHA384",
            evidence_digest=HEX_C,
        )
    print("compliance and monitoring validation fixture created")


def verify_fixture():
    owner = User.objects.get(email=OWNER_EMAIL)
    tenant = owner.tenant_memberships.get().tenant
    with rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED):
        bind_local_rls_scope(
            DataScope.tenant(tenant),
            organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
            actor_user_id=owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        organization = Organization.objects.get(tenant=tenant, entity__display_name=ORGANIZATION_NAME)
        workspace = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    with rls_scope(workspace.data_scope, organization_mode=OrganizationRLSMode.ORGANIZATION):
        bundle = ComplianceEvidenceBundle.objects.get(entity__display_name=BUNDLE_TITLE)
        assert verify_bundle(bundle)
        assert len(bundle.manifest["assignments"]) == 1
        assert len(bundle.manifest["evidence"]) == 1
        assert len(bundle.manifest["risks"]) == 1
        domain_run = DomainMonitorRun.objects.get(domain__ascii_name=DOMAIN_NAME, state="succeeded")
        certificate_run = CertificateMonitorRun.objects.get(
            endpoint__domain__ascii_name=DOMAIN_NAME,
            state="succeeded",
        )
        assert len(domain_run.evidence_digest) == 64
        assert domain_run.dnssec_validated is True
        assert len(certificate_run.evidence_digest) == 64
        assert certificate_run.hostname_valid is True
        assert certificate_run.trust_valid is True
        assert ReminderSchedule.objects.get(source_entity=domain_run.domain.entity).domain == "domain"
    print("compliance and monitoring validation fixture verified")


if os.environ.get("TEKDOCS_FIXTURE_MODE") == "create":
    create_fixture()
elif os.environ.get("TEKDOCS_FIXTURE_MODE") == "verify":
    verify_fixture()
else:
    raise RuntimeError("TEKDOCS_FIXTURE_MODE must be create or verify")
