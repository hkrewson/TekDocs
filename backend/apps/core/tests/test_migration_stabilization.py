import secrets
import uuid
from datetime import date
from decimal import Decimal
from importlib import import_module

import psycopg
import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from psycopg import sql

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import (
    CustomRole,
    CustomRolePermission,
    CustomRoleScope,
    ScopedRoleAssignment,
    TenantMembership,
    User,
)
from apps.core.custom_fields import create_definition
from apps.core.data_flows import DataFlowInput, create_data_flow, create_data_flow_snapshot
from apps.core.documents import create_document
from apps.core.invoicing import create_invoice, create_line
from apps.core.models import (
    AuditEvent,
    BlockRevision,
    CustomFieldDefinition,
    DataFlowRevision,
    DataFlowSnapshot,
    DocumentPublication,
    Entity,
    EntityLink,
    InstallationState,
    Invoice,
    InvoiceLine,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    Site,
    TaxRate,
    Tenant,
    TenantBillingProfile,
    Workspace,
)
from apps.core.organizations import create_organization
from apps.core.people import create_person
from apps.core.publications import publish_document, verify_publication
from apps.core.rls_contract import RLS_TABLES
from apps.core.scoping import DataScope
from apps.core.sites import archive_site, create_location, create_site
from apps.core.workspaces import resolve_organization_workspace

legacy_scope_helper_migration = import_module("apps.core.migrations.0109_restrict_legacy_scope_helpers")
LEGACY_SCOPE_FUNCTIONS = legacy_scope_helper_migration.LEGACY_SCOPE_FUNCTIONS
LEGACY_SCOPE_HELPERS_FORWARD_SQL = legacy_scope_helper_migration.FORWARD_SQL
LEGACY_SCOPE_HELPERS_REVERSE_SQL = legacy_scope_helper_migration.REVERSE_SQL

DOCUMENT_RLS_TABLES = {
    "core_webhookinboundreceipt",
    "core_webhookoutbounddelivery",
    "core_block",
    "core_blockrevision",
    "core_document",
    "core_documentationlistingreference",
    "core_documentplacement",
    "core_documentattachment",
    "core_documentpublication",
    "core_documentpublicationartifact",
    "core_documentpublicationcontrolevent",
    "core_documenttemplaterevision",
    "core_documenttemplateenrollment",
    "core_documentremotesource",
    "core_documentremoteobservation",
    "core_credentialreference",
    "core_catalogproduct",
    "core_catalogmodel",
    "core_catalogspecificationdefinition",
    "core_catalogspecificationdefinitionversion",
    "core_catalogmodelrevision",
    "core_catalogproductdocument",
    "core_clientasset",
    "core_clientassetdocumentprovenance",
    "core_clienthardwareasset",
    "core_clientassetlifecycleevent",
    "core_clientsoftwareinstallation",
    "core_softwarelicense",
    "core_softwarelicenseinstallation",
    "core_softwarelicenseseat",
    "core_softwarelicenseevent",
    "core_commercialcontract",
    "core_contractcost",
    "core_invoice",
    "core_invoiceartifact",
    "core_invoiceline",
    "core_invoicenumberseries",
    "core_servicerate",
    "core_networkrack",
    "core_networkdevice",
    "core_networkvrf",
    "core_networkvlan",
    "core_networksubnet",
    "core_networkinterface",
    "core_networkipaddress",
    "core_networkmacaddress",
    "core_wirelessnetwork",
    "core_dnszone",
    "core_dnsrecord",
    "core_networkcircuit",
    "core_networkcircuithandoff",
    "core_netboxreference",
    "core_outboxevent",
    "core_outboxdeliveryreceipt",
    "core_inboxnotification",
    "core_notificationpreference",
    "core_notificationemaildelivery",
    "core_integrationconnection",
    "core_integrationsyncjob",
    "core_integrationobservation",
    "core_integrationlogevent",
    "core_integrationconflict",
    "core_gitexportbundle",
    "core_complianceframework",
    "core_compliancecatalogrevision",
    "core_compliancecontrol",
    "core_compliancecontrolrevision",
    "core_compliancecatalogentry",
    "core_compliancecontrolassignment",
    "core_complianceassignmentreview",
    "core_complianceevidence",
    "core_complianceevidencelink",
    "core_complianceevidencereview",
    "core_compliancerisk",
    "core_complianceriskevent",
    "core_complianceevidencebundle",
    "core_reminderschedule",
    "core_registereddomain",
    "core_managedhostname",
    "core_domaindnsobservation",
    "core_domainreviewevent",
    "core_domainmonitorrun",
    "core_domainmonitoralert",
    "core_certificateendpoint",
    "core_certificatemonitorrun",
    "core_certificatemonitoralert",
    "core_relationshipgraphview",
    "core_relationshipgraphsnapshot",
    "core_documentkeybinding",
    "core_dataflow",
    "core_dataflowrevision",
    "core_dataflowsnapshot",
    "core_tenantbillingprofile",
    "core_taxrate",
    "core_importbatch",
    "core_importrow",
    "core_importexternalkey",
    "core_documentationmap",
    "core_documentationmaprevision",
    "core_documentationmapentry",
    "core_documentationmapbaseline",
}


@pytest.mark.django_db(transaction=True)
def test_billing_foundation_upgrades_from_document_operations(migration_head_restored):
    if connection.vendor != "postgresql":
        pytest.skip("Billing-foundation upgrade validation requires PostgreSQL")

    call_command("migrate", "core", "0126", verbosity=0, interactive=False)
    tenant = Tenant.objects.create(name="Billing upgrade MSP", slug=f"billing-upgrade-{uuid.uuid4()}")

    call_command("migrate", "core", verbosity=0, interactive=False)

    profile = TenantBillingProfile.objects.create(tenant=tenant, legal_name="Preserved issuer")
    rate = TaxRate.objects.create(
        tenant=tenant,
        name="Upgrade tax",
        rate=Decimal("0.082500"),
        inclusive=False,
        effective_from=date(2026, 1, 1),
    )
    assert Tenant.objects.filter(pk=tenant.pk).exists()
    assert profile.tenant_id == tenant.id
    assert rate.tenant_id == tenant.id

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            [["core_tenantbillingprofile", "core_taxrate"]],
        )
        assert {row[0] for row in cursor.fetchall()} == {"core_tenantbillingprofile", "core_taxrate"}
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY(%s)",
            [["core_billingprofile_validate", "core_taxrate_immutable"]],
        )
        assert {row[0] for row in cursor.fetchall()} == {
            "core_billingprofile_validate",
            "core_taxrate_immutable",
        }


@pytest.mark.django_db(transaction=True)
def test_invoice_issue_upgrades_an_exact_prior_draft_without_allocating_a_number(migration_head_restored):
    if connection.vendor != "postgresql":
        pytest.skip("Invoice-issue upgrade validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Invoice issue upgrade MSP",
        owner_email=f"invoice-upgrade-{uuid.uuid4()}@example.invalid",
        owner_display_name="Invoice Upgrade Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Invoice Upgrade Client",
        legal_name="Invoice Upgrade Client, LLC",
        website="https://example.invalid",
        classifications=["client"],
    )
    invoice = create_invoice(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        currency="USD",
        invoice_date=date(2026, 8, 29),
        due_date=date(2026, 9, 28),
        reference="UPGRADE-1",
    )
    line = create_line(
        invoice=invoice,
        actor_id=result.owner.id,
        values={"description": "Preserved draft line", "quantity": "2.000", "unit_amount": "15.00"},
    )

    call_command("migrate", "core", "0128_invoice_drafts", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, reference FROM core_invoice WHERE id=%s", [invoice.id])
        assert cursor.fetchone() == ("draft", "UPGRADE-1")
        cursor.execute("SELECT description FROM core_invoiceline WHERE id=%s", [line.id])
        assert cursor.fetchone() == ("Preserved draft line",)

    call_command("migrate", "core", verbosity=0, interactive=False)
    upgraded = Invoice.objects.get(pk=invoice.id)
    assert upgraded.state == "draft"
    assert upgraded.number == ""
    assert upgraded.number_series_id is None
    assert upgraded.subtotal_amount is None
    assert upgraded.delivered_at is None
    assert upgraded.delivery_count == 0
    assert InvoiceLine.objects.get(pk=line.id).description == "Preserved draft line"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            [["core_invoiceartifact", "core_invoicenumberseries"]],
        )
        assert {row[0] for row in cursor.fetchall()} == {"core_invoiceartifact", "core_invoicenumberseries"}


@pytest.fixture
def migration_head_restored(transactional_db):
    """Return the shared test database to migration head however the test ends.

    A reversal test downgrades the schema of the database every later test in the
    session shares. Restoring it only on the success path means one failed assertion
    between the downgrade and the restore leaves the whole session on a stale schema,
    which then surfaces as unrelated ``UndefinedColumn`` errors far from the real
    failure. Requesting ``transactional_db`` here orders this teardown ahead of the
    flush pytest-django performs when the test finishes.

    Reversing and reapplying the whole migration set dirties thousands of relation
    files. Left to PostgreSQL's own timing, that checkpoint lands in the middle of a
    later test and stalls one request long enough to fail a latency budget that has
    nothing to do with migrations. Forcing the checkpoint here pays that cost inside
    the test that caused it.
    """
    try:
        yield
    finally:
        call_command("migrate", "core", verbosity=0, interactive=False)
        call_command("migrate", "accounts", verbosity=0, interactive=False)
        if connection.vendor == "postgresql":
            try:
                with connection.cursor() as cursor:
                    cursor.execute("CHECKPOINT")
            except DatabaseError:  # pragma: no cover - requires a non-superuser test role
                pass


@pytest.mark.django_db(transaction=True)
def test_latest_isolation_migration_reverses_and_reapplies_without_data_loss(migration_head_restored):
    if connection.vendor != "postgresql":
        pytest.skip("Migration-cycle validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Migration Cycle MSP",
        owner_email="migration-cycle-owner@example.invalid",
        owner_display_name="Migration Cycle Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Migration Cycle Client",
        legal_name="Migration Cycle Client, LLC",
        website="https://migration-cycle.example.invalid",
        classifications=["client"],
    )
    site = create_site(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        name="Primary Site",
        code="PRIMARY",
        address_line_1="1 Test Lane",
        address_line_2="",
        city="Madison",
        region="WI",
        postal_code="53703",
        country_code="US",
        timezone="America/Chicago",
        phone="",
    )
    location = create_location(
        scope=DataScope.organization(result.tenant, organization),
        site=site,
        actor_id=result.owner.id,
        name="Office 101",
        kind="office",
        code="101",
        parent_id=None,
    )
    association = create_person(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        full_name="Migration Contact",
        preferred_name="Contact",
        kind="contact",
        role="Technical contact",
        responsibility="Migration evidence",
        location="",
        office="",
        site=site,
        structured_location=location,
        phone="",
        email="migration-contact@example.invalid",
    )
    definition = create_definition(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        key="migration_evidence",
        entity_type="site",
        label="Migration evidence",
        description="",
        required=False,
        field_type="text",
        display_order=0,
        options=[],
    )
    endpoints = sorted((organization.entity, site.entity), key=lambda entity: entity.id.int)
    link = EntityLink.objects.create(
        tenant=result.tenant,
        source=endpoints[0],
        target=endpoints[1],
        link_type="related_to",
    )
    member = User.objects.create_user(
        email="migration-cycle-member@example.invalid",
        display_name="Migration Cycle Member",
    )
    membership = TenantMembership.objects.create(tenant=result.tenant, user=member)
    role = CustomRole.objects.create(
        tenant=result.tenant,
        name="Migration reviewer",
        scope=CustomRoleScope.ORGANIZATION,
        created_by=result.owner,
    )
    CustomRolePermission.objects.create(
        tenant=result.tenant,
        role=role,
        permission="documents.view",
    )
    assignment = ScopedRoleAssignment.objects.create(
        tenant=result.tenant,
        membership=membership,
        role=role,
        organization=organization,
        created_by=result.owner,
    )
    archived = create_site(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        name="Archived Site",
        code="ARCHIVED",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="",
        timezone="",
        phone="",
    )
    archive_site(site=archived, actor_id=result.owner.id)
    document = create_document(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        title="Migration runbook",
        markdown="# Preserved revision\n",
    )
    block = document.placements.get(parent__isnull=True, position=0).block

    stable_entity_ids = {
        organization.entity_id,
        site.entity_id,
        location.entity_id,
        association.person.entity_id,
        archived.entity_id,
    }
    counts = {
        "entities": Entity.objects.filter(tenant=result.tenant).count(),
        "organizations": Organization.objects.filter(tenant=result.tenant).count(),
        "classifications": OrganizationClassification.objects.filter(tenant=result.tenant).count(),
        "audits": AuditEvent.objects.filter(tenant=result.tenant).count(),
        "workspaces": Workspace.objects.filter(tenant=result.tenant).count(),
    }
    workspace_ids = set(Workspace.objects.filter(tenant=result.tenant).values_list("id", flat=True))

    call_command("migrate", "accounts", "0011", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('accounts_tenant_membership_guard', 'accounts_invitation_scope_guard', "
            "'accounts_organization_access_assignment_actor_guard', 'accounts_custom_role_creator_guard', "
            "'accounts_access_collection_creator_guard', 'accounts_service_account_guard', "
            "'accounts_api_token_guard', 'accounts_api_token_permission_guard')"
        )
        assert cursor.fetchone() == (0,)
    call_command("migrate", "accounts", "0019", verbosity=0, interactive=False)
    assert TenantMembership.objects.filter(id=membership.id, tenant=result.tenant, user=member).exists()
    assert ScopedRoleAssignment.objects.filter(id=assignment.id).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('accounts_tenant_membership_guard', 'accounts_invitation_scope_guard', "
            "'accounts_organization_access_assignment_actor_guard', 'accounts_custom_role_creator_guard', "
            "'accounts_access_collection_creator_guard', 'accounts_service_account_guard', "
            "'accounts_api_token_guard', 'accounts_api_token_permission_guard')"
        )
        assert cursor.fetchone() == (8,)

    call_command("migrate", "core", "0021", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT markdown FROM core_block WHERE id = %s", [block.id])
        assert cursor.fetchone() == ("# Preserved revision\n",)
    call_command("migrate", "core", "0049", verbosity=0, interactive=False)
    preserved_revision = BlockRevision.objects.get(block_id=block.id)
    assert preserved_revision.markdown == "# Preserved revision\n"
    assert preserved_revision.checksum
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_revision_id FROM core_block WHERE id = %s", [block.id])
        assert cursor.fetchone() == (preserved_revision.id,)
        cursor.execute(
            "SELECT resolution_mode FROM core_documentplacement "
            "WHERE document_id = %s AND parent_id IS NULL AND position = 0",
            [document.id],
        )
        assert cursor.fetchone() == ("live",)

    call_command("migrate", "core", "0019", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            [list(RLS_TABLES)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(RLS_TABLES) - DOCUMENT_RLS_TABLES

    # Restore to the current head of both apps so the assertions below observe the
    # round trip. Never name an explicit target here: a pinned revision silently
    # strands the session on a stale schema as soon as a new migration lands.
    call_command("migrate", "core", verbosity=0, interactive=False)
    call_command("migrate", "accounts", verbosity=0, interactive=False)

    assert set(Entity.objects.filter(id__in=stable_entity_ids).values_list("id", flat=True)) == stable_entity_ids
    assert Organization.objects.filter(tenant=result.tenant).count() == counts["organizations"]
    assert OrganizationClassification.objects.filter(tenant=result.tenant).count() == counts["classifications"]
    assert Entity.objects.filter(tenant=result.tenant).count() == counts["entities"]
    assert AuditEvent.objects.filter(tenant=result.tenant).count() == counts["audits"]
    assert Entity.objects.get(id=archived.entity_id).archived_at is not None
    assert Person.objects.filter(entity_id=association.person.entity_id).exists()
    assert Site.objects.filter(entity_id=site.entity_id).exists()
    assert Location.objects.filter(entity_id=location.entity_id, site=site).exists()
    assert CustomFieldDefinition.objects.filter(id=definition.id).exists()
    assert EntityLink.objects.filter(id=link.id).exists()
    assert ScopedRoleAssignment.objects.filter(id=assignment.id).exists()
    assert CustomRolePermission.objects.filter(role=role, permission="documents.view").exists()
    assert Workspace.objects.filter(tenant=result.tenant).count() == counts["workspaces"]
    assert set(Workspace.objects.filter(tenant=result.tenant).values_list("id", flat=True)) == workspace_ids
    assert not Entity.objects.filter(tenant=result.tenant, workspace__isnull=True).exists()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            [list(RLS_TABLES)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(RLS_TABLES)
        with pytest.raises(DatabaseError), transaction.atomic():
            cursor.execute(
                "UPDATE core_auditevent SET occurred_at = %s WHERE tenant_id = %s",
                [timezone.now(), result.tenant.id],
            )


def _legacy_scope_helper_privileges(role_name: str) -> tuple[dict[str, bool], dict[str, bool]]:
    role_privileges: dict[str, bool] = {}
    public_privileges: dict[str, bool] = {}
    with connection.cursor() as cursor:
        for signature in LEGACY_SCOPE_FUNCTIONS:
            cursor.execute(
                """
                SELECT
                    has_function_privilege(%s, %s, 'EXECUTE'),
                    EXISTS (
                        SELECT 1
                        FROM pg_proc function_record
                        CROSS JOIN LATERAL aclexplode(
                            COALESCE(
                                function_record.proacl,
                                acldefault('f', function_record.proowner)
                            )
                        ) function_acl
                        WHERE function_record.oid = to_regprocedure(%s)
                          AND function_acl.grantee = 0
                          AND function_acl.privilege_type = 'EXECUTE'
                    )
                """,
                [role_name, signature, signature],
            )
            role_allowed, public_allowed = cursor.fetchone()
            role_privileges[signature] = role_allowed
            public_privileges[signature] = public_allowed
    return role_privileges, public_privileges


def _unrelated_role_connection(role_name: str, password: str):  # type: ignore[no-untyped-def]
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=role_name,
        password=password,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
        autocommit=True,
    )


@pytest.mark.django_db(transaction=True)
def test_legacy_scope_helper_privileges_reverse_and_reapply():
    if connection.vendor != "postgresql":
        pytest.skip("Scope-helper privilege validation requires PostgreSQL")

    role_name = f"tekdocs_unrelated_{secrets.token_hex(6)}"
    password = f"{secrets.token_urlsafe(32)}Aa7!"
    calls = (
        "SELECT tekdocs_current_tenant_id()",
        "SELECT tekdocs_current_organization_id()",
        "SELECT tekdocs_current_workspace_id()",
        "SELECT tekdocs_scope_matches(NULL::uuid, NULL::uuid)",
    )

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %s"
            ).format(sql.Identifier(role_name)),
            [password],
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(connection.settings_dict["NAME"]),
                sql.Identifier(role_name),
            )
        )
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name)))

    try:
        runtime_privileges, public_privileges = _legacy_scope_helper_privileges("tekdocs_runtime")
        unrelated_privileges, _ = _legacy_scope_helper_privileges(role_name)
        assert all(runtime_privileges.values())
        assert not any(public_privileges.values())
        assert not any(unrelated_privileges.values())
        with _unrelated_role_connection(role_name, password) as unrelated:
            for statement in calls:
                with unrelated.cursor() as cursor, pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(statement)

        with connection.cursor() as cursor:
            cursor.execute(LEGACY_SCOPE_HELPERS_REVERSE_SQL)
        runtime_privileges, public_privileges = _legacy_scope_helper_privileges("tekdocs_runtime")
        unrelated_privileges, _ = _legacy_scope_helper_privileges(role_name)
        assert all(runtime_privileges.values())
        assert all(public_privileges.values())
        assert all(unrelated_privileges.values())
        with _unrelated_role_connection(role_name, password) as unrelated:
            for statement in calls:
                with unrelated.cursor() as cursor:
                    cursor.execute(statement)
                    cursor.fetchone()

        with connection.cursor() as cursor:
            cursor.execute(LEGACY_SCOPE_HELPERS_FORWARD_SQL)
        runtime_privileges, public_privileges = _legacy_scope_helper_privileges("tekdocs_runtime")
        unrelated_privileges, _ = _legacy_scope_helper_privileges(role_name)
        assert all(runtime_privileges.values())
        assert not any(public_privileges.values())
        assert not any(unrelated_privileges.values())
        with _unrelated_role_connection(role_name, password) as unrelated:
            for statement in calls:
                with unrelated.cursor() as cursor, pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(statement)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(LEGACY_SCOPE_HELPERS_FORWARD_SQL)
            cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name)))
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))


@pytest.mark.django_db(transaction=True)
def test_the_newest_guard_migration_reverses_and_reapplies_without_losing_retained_evidence(
    migration_head_restored,
):
    """Reverse only the newest guard migration, not the whole history.

    The deep reversal above targets `core 0019`, which predates the data-flow tables, so
    it drops them by design and can say nothing about their contents. What can be
    proven — and is the operationally relevant case, since it is what a failed upgrade
    actually rolls back — is that un-applying the newest guard migration and reapplying
    it leaves retained evidence byte-identical and its protections restored.
    """

    if connection.vendor != "postgresql":
        pytest.skip("Migration guard validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Guard Cycle MSP",
        owner_email=f"guard-cycle-{uuid.uuid4()}@example.invalid",
        owner_display_name="Guard Cycle Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Guard Cycle Client",
        legal_name="Guard Cycle Client, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(result.owner, entity_id=organization.entity_id)
    flow = create_data_flow(
        workspace=workspace,
        actor_id=result.owner.id,
        value=DataFlowInput(
            name="Guarded billing export",
            source_kind="external",
            source_label="Practice vendor",
            destination_kind="external",
            destination_label="Payment processor",
            direction="one_way",
            transfer_mechanism="api",
            data_classification="personal_data",
            purpose="Settle billing.",
            crosses_trust_boundary=True,
            protection="in_transit_and_at_rest",
            provenance="recorded_fact",
        ),
    )
    snapshot = create_data_flow_snapshot(workspace=workspace, actor_id=result.owner.id, title="Guarded snapshot")
    retained = {
        "revision_digest": DataFlowRevision.objects.get(data_flow=flow).content_digest,
        "snapshot_digest": snapshot.content_digest,
        "snapshot_flows": snapshot.flows,
    }

    call_command("migrate", "core", "0122_data_flow_snapshots", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'core_dataflowsnap_validate'",
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'core_dataflowsnapshot'",
        )
        # Both flags, not just one: `DISABLE ROW LEVEL SECURITY` alone leaves FORCE set,
        # which is drift a fresh install at this revision would not carry.
        assert cursor.fetchone() == (False, False)

    call_command("migrate", "core", verbosity=0, interactive=False)

    preserved_revision = DataFlowRevision.objects.get(data_flow__entity_id=flow.entity_id)
    preserved_snapshot = DataFlowSnapshot.objects.get(id=snapshot.id)
    assert preserved_revision.content_digest == retained["revision_digest"]
    assert preserved_revision.data_classification == "personal_data"
    assert preserved_revision.protection == "in_transit_and_at_rest"
    assert preserved_revision.crosses_trust_boundary is True
    # A snapshot that survives with a digest no longer matching its payload is worse
    # than one that is missing: it still reads as authoritative.
    assert preserved_snapshot.content_digest == retained["snapshot_digest"]
    assert preserved_snapshot.flows == retained["snapshot_flows"]

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname = 'core_dataflowsnap_validate'")
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'core_dataflowsnapshot'"
        )
        assert cursor.fetchone() == (True,)
    with pytest.raises(DatabaseError), transaction.atomic():
        DataFlowSnapshot.objects.filter(id=snapshot.id).update(title="Rewritten after reapply")


@pytest.mark.django_db(transaction=True)
def test_publication_manifest_v3_guard_reverses_and_reapplies_without_rewriting_evidence(
    migration_head_restored,
):
    if connection.vendor != "postgresql":
        pytest.skip("Migration guard validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Publication Guard MSP",
        owner_email=f"publication-guard-{uuid.uuid4()}@example.invalid",
        owner_display_name="Publication Guard Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = create_organization(
        tenant=result.tenant,
        actor_id=result.owner.id,
        name="Publication Guard Client",
        legal_name="Publication Guard Client, Inc.",
        website="https://example.invalid",
        classifications=["client"],
    )
    document = create_document(
        tenant=result.tenant,
        organization=organization,
        actor_id=result.owner.id,
        title="Guarded publication",
        markdown="Retained publication content.",
    )
    publication = publish_document(
        workspace=resolve_organization_workspace(result.owner, entity_id=organization.entity_id),
        document=document,
        actor_id=result.owner.id,
        reason="Exercise the manifest guard migration",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    retained_digest = publication.content_digest
    assert publication.manifest["format"] == "tekdocs-static-publication/v4"

    call_command("migrate", "core", "0123_data_flow_snapshot_guards", verbosity=0, interactive=False)
    retained = DocumentPublication.objects.get(pk=publication.pk)
    assert retained.content_digest == retained_digest
    assert retained.manifest["format"] == "tekdocs-static-publication/v4"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication'::regproc)")
        assert "tekdocs-static-publication/v2" in cursor.fetchone()[0]

    call_command("migrate", "core", verbosity=0, interactive=False)
    retained = DocumentPublication.objects.get(pk=publication.pk)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('tekdocs_validate_document_publication'::regproc)")
        guard = cursor.fetchone()[0]
    assert "tekdocs-static-publication/v4" in guard
    assert "key_resolutions" in guard
    assert "audience_profile" in guard
    assert retained.content_digest == retained_digest
    assert all(verify_publication(retained).values())
