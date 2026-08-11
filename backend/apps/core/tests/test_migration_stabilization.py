import secrets

import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

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
from apps.core.documents import create_document
from apps.core.models import (
    AuditEvent,
    BlockRevision,
    CustomFieldDefinition,
    Entity,
    EntityLink,
    InstallationState,
    Location,
    Organization,
    OrganizationClassification,
    Person,
    Site,
    Workspace,
)
from apps.core.organizations import create_organization
from apps.core.people import create_person
from apps.core.rls_contract import RLS_TABLES
from apps.core.scoping import DataScope
from apps.core.sites import archive_site, create_location, create_site

DOCUMENT_RLS_TABLES = {
    "core_block",
    "core_blockrevision",
    "core_document",
    "core_documentationlistingreference",
    "core_documentplacement",
    "core_documentattachment",
    "core_documentpublication",
    "core_documentpublicationartifact",
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
    "core_networkrack",
    "core_networkdevice",
    "core_networkvrf",
    "core_networkvlan",
    "core_networksubnet",
    "core_networkinterface",
    "core_networkipaddress",
    "core_networkmacaddress",
}


@pytest.mark.django_db(transaction=True)
def test_latest_isolation_migration_reverses_and_reapplies_without_data_loss():
    if connection.vendor != "postgresql":
        pytest.skip("Migration-cycle certification requires PostgreSQL")

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
            "'accounts_access_collection_creator_guard')"
        )
        assert cursor.fetchone() == (0,)
    call_command("migrate", "accounts", "0013", verbosity=0, interactive=False)
    assert TenantMembership.objects.filter(id=membership.id, tenant=result.tenant, user=member).exists()
    assert ScopedRoleAssignment.objects.filter(id=assignment.id).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('accounts_tenant_membership_guard', 'accounts_invitation_scope_guard', "
            "'accounts_organization_access_assignment_actor_guard', 'accounts_custom_role_creator_guard', "
            "'accounts_access_collection_creator_guard')"
        )
        assert cursor.fetchone() == (5,)

    call_command("migrate", "core", "0021", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT markdown FROM core_block WHERE id = %s", [block.id])
        assert cursor.fetchone() == ("# Preserved revision\n",)
    call_command("migrate", "core", "0049", verbosity=0, interactive=False)
    preserved_revision = BlockRevision.objects.get(block_id=block.id)
    assert preserved_revision.markdown == "# Preserved revision\n"
    assert preserved_revision.checksum
    block.refresh_from_db()
    assert document.placements.get(parent__isnull=True, position=0).resolution_mode == "live"

    call_command("migrate", "core", "0019", verbosity=0, interactive=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            [list(RLS_TABLES)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(RLS_TABLES) - DOCUMENT_RLS_TABLES

    call_command("migrate", "core", "0053", verbosity=0, interactive=False)

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
