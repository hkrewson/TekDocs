from django.db import migrations


RUNTIME_ROLE = "tekdocs_runtime"

SIMPLE_ORGANIZATION_TABLES = (
    "core_site",
    "core_location",
    "core_personassociation",
)

TENANT_TABLES = (
    "core_organization",
    "core_organizationclassification",
    "core_auditevent",
)

ALL_RLS_TABLES = (
    "core_entity",
    *SIMPLE_ORGANIZATION_TABLES,
    "core_customfielddefinition",
    "core_customfielddefinitionversion",
    "core_person",
    "core_entitylink",
    *TENANT_TABLES,
)


def _policy_name(table):
    return f"{table}_runtime_scope"


def activate_runtime_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [RUNTIME_ROLE])
        if cursor.fetchone() is None:
            raise RuntimeError("Provision the tekdocs_runtime PostgreSQL role before applying migrations.")

        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION tekdocs_scope_matches(row_tenant_id uuid, row_organization_id uuid)
            RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
                SELECT CASE
                    WHEN tekdocs_current_tenant_id() IS NULL THEN false
                    WHEN row_tenant_id <> tekdocs_current_tenant_id() THEN false
                    WHEN current_setting('tekdocs.organization_mode', true) = 'all'
                        AND current_user = 'tekdocs_runtime' THEN false
                    WHEN current_setting('tekdocs.organization_mode', true) = 'all' THEN true
                    WHEN current_setting('tekdocs.organization_mode', true) = 'msp'
                        THEN row_organization_id IS NULL
                    WHEN current_setting('tekdocs.organization_mode', true) = 'organization'
                        THEN row_organization_id = tekdocs_current_organization_id()
                    ELSE false
                END
            $$
            """
        )

        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute(f"REVOKE CREATE ON SCHEMA public FROM {RUNTIME_ROLE}")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME_ROLE}")
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {RUNTIME_ROLE}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {RUNTIME_ROLE}"
        )
        cursor.execute(f"REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM {RUNTIME_ROLE}")

        for table in SIMPLE_ORGANIZATION_TABLES:
            policy = _policy_name(table)
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"CREATE POLICY {policy} ON {table} "
                "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
                "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
            )

        cursor.execute("ALTER TABLE core_customfielddefinition ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_customfielddefinition FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_customfielddefinition_runtime_scope ON core_customfielddefinition "
            "USING (tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND current_setting('tekdocs.organization_mode', true) = 'organization')) "
            "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
        )

        cursor.execute("ALTER TABLE core_customfielddefinitionversion ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_customfielddefinitionversion FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_customfielddefinitionversion_runtime_scope "
            "ON core_customfielddefinitionversion USING ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_customfielddefinition definition "
            "WHERE definition.id = definition_id)) "
            "WITH CHECK (tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_customfielddefinition definition "
            "WHERE definition.id = definition_id))"
        )

        cursor.execute("ALTER TABLE core_person ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_person FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_person_runtime_scope ON core_person "
            "USING (tenant_id = tekdocs_current_tenant_id()) "
            "WITH CHECK (tenant_id = tekdocs_current_tenant_id())"
        )

        cursor.execute("ALTER TABLE core_entity ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_entity FORCE ROW LEVEL SECURITY")
        entity_visibility = (
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL AND entity_type = 'organization') OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL AND entity_type = 'person')"
        )
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT "
            f"USING ({entity_visibility})"
        )
        cursor.execute(
            "CREATE POLICY core_entity_runtime_insert ON core_entity FOR INSERT WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')))"
        )
        cursor.execute(
            "CREATE POLICY core_entity_runtime_update ON core_entity FOR UPDATE "
            f"USING ({entity_visibility}) WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')))"
        )
        cursor.execute(
            "CREATE POLICY core_entity_runtime_delete ON core_entity FOR DELETE "
            f"USING ({entity_visibility})"
        )

        cursor.execute("ALTER TABLE core_entitylink ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_entitylink FORCE ROW LEVEL SECURITY")
        link_visibility = (
            "tenant_id = tekdocs_current_tenant_id() AND "
            "EXISTS (SELECT 1 FROM core_entity source WHERE source.id = source_id) AND "
            "EXISTS (SELECT 1 FROM core_entity target WHERE target.id = target_id)"
        )
        cursor.execute(
            "CREATE POLICY core_entitylink_runtime_scope ON core_entitylink "
            f"USING ({link_visibility}) WITH CHECK ({link_visibility})"
        )

        for table in TENANT_TABLES:
            policy = _policy_name(table)
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            if table == "core_auditevent":
                expression = (
                    "tenant_id = tekdocs_current_tenant_id() OR "
                    "(tenant_id IS NULL AND tekdocs_current_tenant_id() IS NULL)"
                )
            else:
                expression = "tenant_id = tekdocs_current_tenant_id()"
            cursor.execute(
                f"CREATE POLICY {policy} ON {table} USING ({expression}) WITH CHECK ({expression})"
            )


def deactivate_runtime_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ALL_RLS_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {_policy_name(table)} ON {table}")
        for table in ("core_entity",):
            for operation in ("select", "insert", "update", "delete"):
                cursor.execute(f"DROP POLICY IF EXISTS {table}_runtime_{operation} ON {table}")
        cursor.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {RUNTIME_ROLE}")
        cursor.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {RUNTIME_ROLE}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {RUNTIME_ROLE}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {RUNTIME_ROLE}"
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION tekdocs_scope_matches(row_tenant_id uuid, row_organization_id uuid)
            RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
                SELECT CASE
                    WHEN tekdocs_current_tenant_id() IS NULL THEN false
                    WHEN row_tenant_id <> tekdocs_current_tenant_id() THEN false
                    WHEN current_setting('tekdocs.organization_mode', true) = 'all' THEN true
                    WHEN current_setting('tekdocs.organization_mode', true) = 'msp'
                        THEN row_organization_id IS NULL
                    WHEN current_setting('tekdocs.organization_mode', true) = 'organization'
                        THEN row_organization_id = tekdocs_current_organization_id()
                    ELSE false
                END
            $$
            """
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0018_audit_event_database_immutability")]

    operations = [migrations.RunPython(activate_runtime_rls, deactivate_runtime_rls)]
