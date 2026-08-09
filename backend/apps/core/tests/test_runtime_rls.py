import uuid

import psycopg
import pytest
from django.conf import settings
from django.db import connection

from apps.core.models import Entity, Organization, Tenant
from apps.core.rls_contract import RLS_TABLES, RUNTIME_ROLE


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create(tenant=tenant, entity_type="organization", display_name=name)
    return Organization.objects.create(tenant=tenant, entity=anchor)


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def _bind(cursor, tenant_id, mode, organization_id=None):
    cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(tenant_id)])
    cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(organization_id or "")])
    cursor.execute("SELECT set_config('tekdocs.organization_mode', %s, true)", [mode])


@pytest.mark.django_db(transaction=True)
def test_runtime_role_is_constrained_and_forced_rls_inventory_is_complete():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

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
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("CREATE TABLE runtime_role_escape (id integer)")
        runtime.rollback()


@pytest.mark.django_db(transaction=True)
def test_runtime_raw_sql_denies_missing_cross_tenant_sibling_write_and_all_mode():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

    first = Tenant.objects.create(name="First runtime tenant", slug=f"first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second runtime tenant", slug=f"second-{uuid.uuid4()}")
    first_org = _organization(first, "First client")
    sibling_org = _organization(first, "Sibling client")
    foreign_org = _organization(second, "Foreign client")
    msp = Entity.objects.create(tenant=first, entity_type="document", display_name="MSP runbook")
    selected = Entity.objects.create(
        tenant=first,
        organization=first_org,
        entity_type="document",
        display_name="Selected client runbook",
    )
    Entity.objects.create(
        tenant=first,
        organization=sibling_org,
        entity_type="document",
        display_name="Sibling client runbook",
    )
    Entity.objects.create(
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
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "UPDATE core_entity SET organization_id = %s WHERE id = %s",
                [sibling_org.id, selected.id],
            )
        runtime.rollback()

        _bind(cursor, first.id, "all")
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert cursor.fetchall() == []
