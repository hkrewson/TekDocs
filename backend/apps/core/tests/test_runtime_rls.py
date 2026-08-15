import secrets
import uuid
from datetime import timedelta
from hashlib import sha256

import psycopg
import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, Invitation, OrganizationAccessAssignment, TenantMembership, User
from apps.core.models import (
    Block,
    BlockRevision,
    CredentialReference,
    Document,
    DocumentationListingReference,
    DocumentAttachment,
    DocumentPlacement,
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    Entity,
    InboxNotification,
    InstallationState,
    Organization,
    OrganizationAccessMode,
    OrganizationClassification,
    OutboxEvent,
    OutboxEventState,
    Person,
    PersonAssociation,
    Tenant,
)
from apps.core.outbox import OutboxTopic, dispatch_due_outbox_events
from apps.core.rls import (
    OrganizationRLSMode,
    RLSPrincipalMode,
    bind_local_rls_scope,
    system_rls_scope,
)
from apps.core.rls_contract import RLS_TABLES, RUNTIME_ROLE
from apps.core.scoping import DataScope
from apps.core.validation import CONTROL_PLANE_GUARD_TRIGGERS


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    return Organization.objects.create(tenant=tenant, entity=anchor)


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def _bind(cursor, tenant_id, mode, organization_id=None, user_id=None, principal_mode=None):
    cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(tenant_id)])
    cursor.execute(
        "SELECT id FROM core_workspace WHERE tenant_id = %s AND organization_id IS NOT DISTINCT FROM %s",
        [tenant_id, organization_id],
    )
    workspace_id = cursor.fetchone()[0]
    cursor.execute("SELECT set_config('tekdocs.workspace_id', %s, true)", [str(workspace_id)])
    cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(organization_id or "")])
    cursor.execute("SELECT set_config('tekdocs.organization_mode', %s, true)", [mode])
    cursor.execute("SELECT set_config('tekdocs.user_id', %s, true)", [str(user_id or "")])
    cursor.execute(
        "SELECT set_config('tekdocs.principal_mode', %s, true)",
        [principal_mode if principal_mode is not None else ("user" if user_id else "system")],
    )


@pytest.mark.django_db(transaction=True)
def test_runtime_credential_references_are_forced_to_the_selected_workspace():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    tenant = Tenant.objects.create(name="Credential RLS tenant", slug=f"credential-{uuid.uuid4()}")
    first_org = _organization(tenant, "First credential client")
    sibling_org = _organization(tenant, "Sibling credential client")
    entity = Entity.objects.create_owned(
        tenant=tenant,
        organization=first_org,
        entity_type="credential_reference",
        display_name="Firewall administrator",
    )
    reference = CredentialReference.objects.create(
        tenant=tenant,
        organization=first_org,
        entity=entity,
        provider="onepassword",
        reference_url=(
            "https://start.1password.com/open/i?"
            "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
            "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
        ),
    )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, tenant.id, "organization", first_org.id)
        cursor.execute("SELECT id FROM core_credentialreference")
        assert cursor.fetchall() == [(reference.id,)]
        runtime.commit()

        _bind(cursor, tenant.id, "organization", sibling_org.id)
        cursor.execute("SELECT id FROM core_credentialreference")
        assert cursor.fetchall() == []
        cursor.execute(
            "UPDATE core_credentialreference SET organization_id = %s WHERE id = %s",
            [sibling_org.id, reference.id],
        )
        assert cursor.rowcount == 0


@pytest.mark.django_db(transaction=True)
def test_runtime_organization_scope_requires_system_principal_to_stage_tenant_person_identity():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    tenant = Tenant.objects.create(name="Person identity tenant", slug=f"person-{uuid.uuid4()}")
    organization = _organization(tenant, "Person identity client")
    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, tenant.id, "organization", organization.id, principal_mode="")
        cursor.execute(
            "SELECT id FROM core_workspace WHERE tenant_id = %s AND kind = 'msp'",
            [tenant.id],
        )
        msp_workspace_id = cursor.fetchone()[0]
        untrusted_entity_id = uuid.uuid4()
        cursor.execute(
            "INSERT INTO core_entity "
            "(id, tenant_id, workspace_id, organization_id, entity_type, display_name, custom_fields, "
            "visibility, archived_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, NULL, 'person', 'Runtime person', '{}'::jsonb, "
            "'msp_private', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            [untrusted_entity_id, tenant.id, msp_workspace_id],
        )
        assert cursor.rowcount == 1
        cursor.execute("SELECT id FROM core_entity WHERE id = %s", [untrusted_entity_id])
        assert cursor.fetchone() is None
        runtime.rollback()

        _bind(cursor, tenant.id, "organization", organization.id, principal_mode="system")
        trusted_entity_id = uuid.uuid4()
        cursor.execute(
            "INSERT INTO core_entity "
            "(id, tenant_id, workspace_id, organization_id, entity_type, display_name, custom_fields, "
            "visibility, archived_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, NULL, 'person', 'Runtime system person', '{}'::jsonb, "
            "'msp_private', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            [trusted_entity_id, tenant.id, msp_workspace_id],
        )
        cursor.execute("SELECT id FROM core_entity WHERE id = %s", [trusted_entity_id])
        assert cursor.fetchone() == (trusted_entity_id,)


@pytest.mark.django_db(transaction=True)
def test_runtime_role_request_enforces_assigned_only_entity_search_and_mentions(django_runtime_role):  # type: ignore[no-untyped-def]
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Runtime request MSP",
        owner_email="runtime-request-owner@example.invalid",
        owner_display_name="Runtime Request Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    assigned = _organization(installation.tenant, "Runtime Assigned Client")
    restricted = _organization(installation.tenant, "Runtime Restricted Client")
    reader = User.objects.create_user(email="runtime-reader@example.invalid", display_name="Runtime Reader")
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=reader,
        role=BuiltInRole.READ_ONLY,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=assigned,
        membership=membership,
        created_by=installation.owner,
    )
    for organization, name in (
        (assigned, "Runtime Visible Contact"),
        (restricted, "Runtime Hidden Contact"),
    ):
        entity = Entity.objects.create_owned(
            tenant=installation.tenant,
            entity_type="person",
            display_name=name,
        )
        person = Person.objects.create(tenant=installation.tenant, entity=entity)
        PersonAssociation.objects.create(
            tenant=installation.tenant,
            organization=organization,
            person=person,
            kind="contact",
        )
    OrganizationClassification.objects.bulk_create(
        [
            OrganizationClassification(tenant=installation.tenant, organization=assigned, kind="client"),
            OrganizationClassification(tenant=installation.tenant, organization=restricted, kind="client"),
        ]
    )
    browser = Client()
    browser.force_login(reader)

    with django_runtime_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == (RUNTIME_ROLE,)
        organizations = browser.get(reverse("msp-entity-search"), {"entity_type": "organization"})
        people = browser.get(reverse("msp-entity-search"), {"entity_type": "person"})
        mentions = browser.get(reverse("msp-document-mention-search"))

    assert organizations.status_code == 200
    assert [item["display_name"] for item in organizations.json()["results"]] == ["Runtime Assigned Client"]
    assert people.status_code == 200
    assert people.json()["results"] == []
    mention_names = {item["display_name"] for item in mentions.json()["results"]}
    assert "Runtime Restricted Client" not in mention_names
    assert "Runtime Hidden Contact" not in mention_names


@pytest.mark.django_db(transaction=True)
def test_runtime_role_administrator_can_create_and_reopen_fail_closed_organization(
    django_runtime_role,  # type: ignore[no-untyped-def]
):
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Runtime organization creation MSP",
        owner_email="runtime-organization-owner@example.invalid",
        owner_display_name="Runtime Organization Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    administrator = User.objects.create_user(
        email="runtime-organization-administrator@example.invalid",
        display_name="Runtime Organization Administrator",
    )
    membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=administrator,
        role=BuiltInRole.ADMINISTRATOR,
    )
    TOTP.activate(administrator, generate_totp_secret())
    browser = Client()
    browser.force_login(administrator)

    with django_runtime_role():
        created = browser.post(
            reverse("organization-list-create"),
            {
                "name": "Runtime Created Client",
                "legal_name": "Runtime Created Client, LLC",
                "website": "https://runtime-created.example.invalid",
                "classifications": ["client"],
            },
            content_type="application/json",
        )
        listed = browser.get(reverse("organization-list-create"))
        person_created = browser.post(
            reverse(
                "organization-people-list-create",
                kwargs={"organization_entity_id": created.json()["id"]},
            ),
            {
                "full_name": "Runtime Created Contact",
                "preferred_name": "Runtime Contact",
                "kind": "contact",
                "role": "Technical contact",
                "responsibility": "Runtime RLS regression",
                "location": "",
                "office": "",
                "phone": "",
                "email": "runtime-created-contact@example.invalid",
            },
            content_type="application/json",
        )

    assert created.status_code == 201
    assert person_created.status_code == 201
    assert created.json()["access_mode"] == OrganizationAccessMode.ASSIGNED_ONLY
    assert [item["name"] for item in listed.json()] == ["Runtime Created Client"]
    organization = Organization.objects.get(entity_id=created.json()["id"])
    assert organization.entity.organization_id is None
    assert OrganizationAccessAssignment.objects.filter(
        tenant=installation.tenant,
        organization=organization,
        membership=membership,
        created_by=administrator,
    ).exists()
    association = PersonAssociation.objects.get(person__entity_id=person_created.json()["id"])
    assert association.organization == organization


@pytest.mark.django_db(transaction=True)
def test_runtime_role_preserves_request_actor_and_system_outbox_principal(django_runtime_role):  # type: ignore[no-untyped-def]
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Runtime notification MSP",
        owner_email="runtime-notification-owner@example.invalid",
        owner_display_name="Runtime Notification Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = _organization(installation.tenant, "Runtime Notification Client")
    OrganizationClassification.objects.create(
        tenant=installation.tenant,
        organization=organization,
        kind="client",
    )
    invitation = Invitation.objects.create(
        tenant=installation.tenant,
        organization=organization,
        role=BuiltInRole.CLIENT_USER,
        email="runtime-invitee@example.invalid",
        token_digest="a" * 64,
        invited_by=installation.owner,
        expires_at=timezone.now() + timedelta(days=1),
    )
    event = OutboxEvent.objects.create(
        tenant=installation.tenant,
        organization=organization,
        topic=OutboxTopic.INVITATION_ISSUED,
        subject_id=invitation.id,
        idempotency_key="runtime-notification-invitation",
        payload={"role": BuiltInRole.CLIENT_USER},
    )
    browser = Client()
    browser.force_login(installation.owner)

    with django_runtime_role():
        with system_rls_scope(DataScope.tenant(installation.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
            assert dispatch_due_outbox_events(tenant=installation.tenant) == 1
        response = browser.get(reverse("notification-list"))

    event.refresh_from_db()
    assert event.state == OutboxEventState.DELIVERED
    assert InboxNotification.objects.filter(event=event, recipient=installation.owner).exists()
    assert response.status_code == 200
    assert response.json()["results"][0]["message"] == (
        "A client user invitation for Runtime Notification Client was issued."
    )


@pytest.mark.django_db(transaction=True)
def test_runtime_client_member_sees_only_its_organization_anchor_and_system_scope_restores_actor(
    django_runtime_role,  # type: ignore[no-untyped-def]
):
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    tenant = Tenant.objects.create(name="Runtime client tenant", slug=f"runtime-client-{uuid.uuid4()}")
    client = _organization(tenant, "Runtime Portal Client")
    sibling = _organization(tenant, "Runtime Portal Sibling")
    user = User.objects.create_user(email="runtime-portal@example.invalid", display_name="Runtime Portal User")
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=BuiltInRole.CLIENT_USER,
        organization=client,
    )

    with django_runtime_role(), transaction.atomic():
        bind_local_rls_scope(
            DataScope.organization(tenant, client),
            organization_mode=OrganizationRLSMode.ORGANIZATION,
            actor_user_id=user.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        assert Entity.objects.filter(id=client.entity_id).exists()
        assert not Entity.objects.filter(id=sibling.entity_id).exists()
        with system_rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('tekdocs.principal_mode', true)")
                assert cursor.fetchone() == ("system",)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('tekdocs.principal_mode', true), current_setting('tekdocs.user_id', true)"
            )
            assert cursor.fetchone() == ("user", str(user.id))


@pytest.mark.django_db(transaction=True)
def test_runtime_entity_anchors_require_entitled_user_or_explicit_system_principal():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Runtime anchor principal MSP",
        owner_email="runtime-anchor-owner@example.invalid",
        owner_display_name="Runtime Anchor Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    assigned = _organization(installation.tenant, "Runtime Principal Assigned")
    restricted = _organization(installation.tenant, "Runtime Principal Restricted")
    all_authorized = _organization(installation.tenant, "Runtime Principal All Authorized")
    all_authorized.access_mode = OrganizationAccessMode.ALL_AUTHORIZED
    all_authorized.save(update_fields=("access_mode", "updated_at"))

    staff = User.objects.create_user(
        email="runtime-principal-staff@example.invalid",
        display_name="Runtime Principal Staff",
    )
    staff_membership = TenantMembership.objects.create(
        tenant=installation.tenant,
        user=staff,
        role=BuiltInRole.READ_ONLY,
    )
    OrganizationAccessAssignment.objects.create(
        tenant=installation.tenant,
        organization=assigned,
        membership=staff_membership,
        created_by=installation.owner,
    )
    portal_user = User.objects.create_user(
        email="runtime-principal-portal@example.invalid",
        display_name="Runtime Principal Portal",
    )
    TenantMembership.objects.create(
        tenant=installation.tenant,
        user=portal_user,
        role=BuiltInRole.CLIENT_USER,
        organization=restricted,
    )
    stranger = User.objects.create_user(
        email="runtime-principal-stranger@example.invalid",
        display_name="Runtime Principal Stranger",
    )

    def person(name: str, organization: Organization | None) -> None:
        entity = Entity.objects.create_owned(
            tenant=installation.tenant,
            entity_type="person",
            display_name=name,
        )
        record = Person.objects.create(tenant=installation.tenant, entity=entity)
        PersonAssociation.objects.create(
            tenant=installation.tenant,
            organization=organization,
            person=record,
            kind="employee" if organization is None else "contact",
        )

    person("Runtime Principal MSP Person", None)
    person("Runtime Principal Assigned Person", assigned)
    person("Runtime Principal Restricted Person", restricted)

    def names(cursor, entity_type: str) -> set[str]:  # type: ignore[no-untyped-def]
        cursor.execute(
            "SELECT display_name FROM core_entity WHERE entity_type = %s ORDER BY display_name",
            [entity_type],
        )
        return {row[0] for row in cursor.fetchall()}

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, installation.tenant.id, "msp", principal_mode="")
        assert names(cursor, "organization") == set()
        assert names(cursor, "person") == set()
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "msp", user_id=stranger.id)
        assert names(cursor, "organization") == set()
        assert names(cursor, "person") == set()
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "msp", user_id=staff.id)
        assert names(cursor, "organization") == {
            "Runtime Principal Assigned",
            "Runtime Principal All Authorized",
        }
        assert names(cursor, "person") == {"Runtime Principal MSP Person"}
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "organization", restricted.id, staff.id)
        assert "Runtime Principal Restricted" not in names(cursor, "organization")
        assert "Runtime Principal Restricted Person" not in names(cursor, "person")
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "organization", restricted.id, portal_user.id)
        assert names(cursor, "organization") == {"Runtime Principal Restricted"}
        assert names(cursor, "person") == {"Runtime Principal Restricted Person"}
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "msp", user_id=installation.owner.id)
        assert names(cursor, "organization") == {
            "Runtime Principal Assigned",
            "Runtime Principal All Authorized",
            "Runtime Principal Restricted",
        }
        assert names(cursor, "person") == {"Runtime Principal MSP Person"}
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "msp")
        assert names(cursor, "organization") == {
            "Runtime Principal Assigned",
            "Runtime Principal All Authorized",
            "Runtime Principal Restricted",
        }
        assert names(cursor, "person") == {"Runtime Principal MSP Person"}
        runtime.rollback()

        _bind(cursor, installation.tenant.id, "organization", restricted.id)
        assert names(cursor, "organization") == {"Runtime Principal Restricted"}
        assert names(cursor, "person") == {"Runtime Principal Restricted Person"}
        runtime.rollback()


@pytest.mark.django_db(transaction=True)
def test_runtime_role_is_constrained_and_forced_rls_inventory_is_complete():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        assert cursor.fetchone() == (RUNTIME_ROLE, False, False, False, False)
        cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        assert cursor.fetchone() == (False,)
        cursor.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND c.relrowsecurity AND c.relforcerowsecurity",
            [list(RLS_TABLES)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(RLS_TABLES)
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY(%s)",
            [list(CONTROL_PLANE_GUARD_TRIGGERS)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(CONTROL_PLANE_GUARD_TRIGGERS)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("CREATE TABLE runtime_role_escape (id integer)")
        runtime.rollback()


@pytest.mark.django_db(transaction=True)
def test_runtime_outbox_is_tenant_isolated_and_event_payload_is_immutable():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    first = Tenant.objects.create(name="First outbox tenant", slug=f"outbox-first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second outbox tenant", slug=f"outbox-second-{uuid.uuid4()}")
    first_org = _organization(first, "First outbox client")
    second_org = _organization(second, "Second outbox client")
    first_event = OutboxEvent.objects.create(
        tenant=first,
        organization=first_org,
        topic="document_publication.available",
        subject_id=uuid.uuid4(),
        idempotency_key="first-event",
        payload={"audience": "client_visible"},
    )
    OutboxEvent.objects.create(
        tenant=second,
        organization=second_org,
        topic="document_publication.available",
        subject_id=uuid.uuid4(),
        idempotency_key="second-event",
        payload={"audience": "client_visible"},
    )
    with pytest.raises(DatabaseError, match="payload contract mismatch"), transaction.atomic():
        OutboxEvent.objects.create(
            tenant=first,
            organization=first_org,
            topic="document_publication.available",
            subject_id=uuid.uuid4(),
            idempotency_key="unsafe-event",
            payload={"audience": "client_visible", "password": "must-not-persist"},
        )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, first.id, "msp")
        cursor.execute("SELECT id FROM core_outboxevent")
        assert cursor.fetchall() == [(first_event.id,)]
        with pytest.raises(psycopg.errors.RaiseException, match="payload are immutable"):
            cursor.execute(
                'UPDATE core_outboxevent SET payload=\'{"audience": "msp_internal"}\'::jsonb WHERE id=%s',
                [first_event.id],
            )
        runtime.rollback()


@pytest.mark.django_db(transaction=True)
def test_runtime_raw_sql_denies_missing_cross_tenant_sibling_write_and_all_mode():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    first = Tenant.objects.create(name="First runtime tenant", slug=f"first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second runtime tenant", slug=f"second-{uuid.uuid4()}")
    first_org = _organization(first, "First client")
    sibling_org = _organization(first, "Sibling client")
    foreign_org = _organization(second, "Foreign client")
    msp = Entity.objects.create_owned(tenant=first, entity_type="document", display_name="MSP runbook")
    selected = Entity.objects.create_owned(
        tenant=first,
        organization=first_org,
        entity_type="document",
        display_name="Selected client runbook",
    )
    Entity.objects.create_owned(
        tenant=first,
        organization=sibling_org,
        entity_type="document",
        display_name="Sibling client runbook",
    )
    Entity.objects.create_owned(
        tenant=second,
        organization=foreign_org,
        entity_type="document",
        display_name="Foreign client runbook",
    )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM core_entity")
        assert cursor.fetchone() == (0,)

        _bind(cursor, first.id, "msp")
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert {row[0] for row in cursor.fetchall()} == {msp.id}
        runtime.commit()

        cursor.execute("SELECT COALESCE(current_setting('tekdocs.tenant_id', true), '')")
        assert cursor.fetchone() == ("",)
        _bind(cursor, first.id, "organization", first_org.id)
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert {row[0] for row in cursor.fetchall()} == {selected.id}
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.CheckViolation)):
            cursor.execute(
                "UPDATE core_entity SET organization_id = %s WHERE id = %s",
                [sibling_org.id, selected.id],
            )
        runtime.rollback()

        _bind(cursor, first.id, "all")
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert cursor.fetchall() == []


@pytest.mark.django_db(transaction=True)
def test_runtime_document_projection_exposes_only_the_referenced_client():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role validation requires PostgreSQL")

    tenant = Tenant.objects.create(name="Document RLS tenant", slug=f"documents-{uuid.uuid4()}")
    selected_org = _organization(tenant, "Selected client")
    sibling_org = _organization(tenant, "Sibling client")
    document_entity = Entity.objects.create_owned(tenant=tenant, entity_type="document", display_name="Shared runbook")
    document = Document.objects.create(tenant=tenant, entity=document_entity)
    block_entity = Entity.objects.create_owned(tenant=tenant, entity_type="document_block", display_name="Shared block")
    block = Block.objects.create(tenant=tenant, entity=block_entity)
    revision = BlockRevision.objects.create(
        tenant=tenant,
        block=block,
        revision_number=1,
        markdown="Reference content",
        checksum=sha256(b"Reference content").hexdigest(),
    )
    block.current_revision = revision
    block.save(update_fields=("current_revision", "updated_at"))
    placement = DocumentPlacement.objects.create(tenant=tenant, document=document, block=block, position=0)
    reference = DocumentationListingReference.objects.create(
        tenant=tenant, organization=selected_org, document=document
    )
    attachment_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_attachment",
        display_name="reference.txt",
    )
    attachment = DocumentAttachment.objects.create(
        tenant=tenant,
        document=document,
        entity=attachment_entity,
        file="document-attachments/fixture",
        original_filename="reference.txt",
        media_type="text/plain",
        size=1,
        checksum=sha256(b"x").hexdigest(),
    )
    publication_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_publication",
        display_name="Shared runbook STATIC",
    )
    publication_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    artifact_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_publication_artifact",
        display_name="Shared runbook STATIC.pdf",
    )
    artifact_checksum = sha256(b"%PDF-fixture").hexdigest()
    with transaction.atomic():
        publication = DocumentPublication.objects.create(
            id=publication_id,
            tenant=tenant,
            document=document,
            entity=publication_entity,
            title="Shared runbook",
            category="reference",
            reason="RLS fixture",
            audience="msp_internal",
            retention="permanent",
            canonical_markdown="Reference content\n",
            sanitized_html="<p>Reference content</p>",
            manifest={
                "format": "tekdocs-static-publication/v2",
                "publication_id": str(publication_id),
                "publication_entity_id": str(publication_entity.id),
                "source_document_id": str(document.entity_id),
                "workspace": {"kind": "msp", "id": None},
                "reason": "RLS fixture",
                "audience": "msp_internal",
                "retention": "permanent",
                "retention_review_on": None,
                "supersedes_id": None,
                "artifacts": [
                    {
                        "id": str(artifact_id),
                        "entity_id": str(artifact_entity.id),
                        "kind": "pdf",
                        "filename": "shared-runbook-static.pdf",
                        "media_type": "application/pdf",
                        "size": 12,
                        "checksum": artifact_checksum,
                        "source_attachment_id": None,
                    }
                ],
            },
            content_digest="a" * 64,
            signature="fixture",
            public_key="fixture",
            key_fingerprint="b" * 64,
            published_at="2026-08-09T12:00:00Z",
        )
        artifact = DocumentPublicationArtifact.objects.create(
            id=artifact_id,
            tenant=tenant,
            publication=publication,
            entity=artifact_entity,
            kind="pdf",
            file="publication-artifacts/fixture",
            original_filename="shared-runbook-static.pdf",
            media_type="application/pdf",
            size=12,
            checksum=artifact_checksum,
            created_at="2026-08-09T12:00:00Z",
        )
        control_event = DocumentPublicationControlEvent.objects.create(
            tenant=tenant,
            publication=publication,
            action="submitted",
            reason="RLS fixture",
            occurred_at="2026-08-09T12:00:00Z",
        )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, tenant.id, "organization", selected_org.id)
        cursor.execute("SELECT id FROM core_document")
        assert cursor.fetchall() == [(document.id,)]
        cursor.execute("SELECT id FROM core_block")
        assert cursor.fetchall() == [(block.id,)]
        cursor.execute("SELECT id FROM core_blockrevision")
        assert cursor.fetchall() == [(revision.id,)]
        cursor.execute("SELECT id FROM core_documentplacement")
        assert cursor.fetchall() == [(placement.id,)]
        cursor.execute("SELECT id FROM core_documentationlistingreference")
        assert cursor.fetchall() == [(reference.id,)]
        cursor.execute("SELECT id FROM core_documentattachment")
        assert cursor.fetchall() == [(attachment.id,)]
        cursor.execute("SELECT id FROM core_documentpublication")
        assert cursor.fetchall() == [(publication.id,)]
        cursor.execute("SELECT id FROM core_documentpublicationartifact")
        assert cursor.fetchall() == [(artifact.id,)]
        cursor.execute("SELECT id FROM core_documentpublicationcontrolevent")
        assert cursor.fetchall() == [(control_event.id,)]
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document_publication'")
        assert cursor.fetchall() == [(publication_entity.id,)]
        runtime.commit()

        _bind(cursor, tenant.id, "organization", sibling_org.id)
        for table in (
            "core_document",
            "core_block",
            "core_blockrevision",
            "core_documentplacement",
            "core_documentationlistingreference",
            "core_documentattachment",
            "core_documentpublication",
            "core_documentpublicationartifact",
            "core_documentpublicationcontrolevent",
        ):
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed test allowlist
            assert cursor.fetchone() == (0,)
