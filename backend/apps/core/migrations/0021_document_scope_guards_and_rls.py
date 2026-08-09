from django.db import migrations


TABLES = (
    "core_document",
    "core_block",
    "core_documentplacement",
    "core_documentationlistingreference",
)


def enable_document_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION tekdocs_validate_document_scope() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_TABLE_NAME IN ('core_document', 'core_block') AND NOT EXISTS (
                SELECT 1 FROM core_entity e WHERE e.id = (to_jsonb(NEW)->>'entity_id')::uuid
                  AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'document entity workspace mismatch'; END IF;
              IF TG_TABLE_NAME = 'core_documentplacement' AND NOT EXISTS (
                SELECT 1 FROM core_document d JOIN core_block b
                  ON b.id = (to_jsonb(NEW)->>'block_id')::uuid
                 WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id
                   AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
                   AND b.tenant_id = NEW.tenant_id
                   AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'document placement workspace mismatch'; END IF;
              IF TG_TABLE_NAME = 'core_documentationlistingreference' AND NOT EXISTS (
                SELECT 1 FROM core_document d JOIN core_organization o ON o.id = NEW.organization_id
                 WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id
                   AND d.organization_id IS NULL AND o.tenant_id = NEW.tenant_id
              ) THEN RAISE EXCEPTION 'documentation reference must project an MSP document into its tenant'; END IF;
              RETURN NEW;
            END $$
            """
        )
        for table in TABLES:
            cursor.execute(
                f"CREATE TRIGGER {table}_scope_guard BEFORE INSERT OR UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_scope()"
            )
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        document_visible = (
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND current_setting('tekdocs.organization_mode', true) = 'organization' AND EXISTS ("
            "SELECT 1 FROM core_documentationlistingreference r WHERE r.document_id = core_document.id "
            "AND r.organization_id = tekdocs_current_organization_id() AND r.archived_at IS NULL))"
        )
        cursor.execute(
            "CREATE POLICY core_document_runtime_select ON core_document FOR SELECT "
            f"USING ({document_visible})"
        )
        cursor.execute(
            "CREATE POLICY core_document_runtime_write ON core_document FOR ALL "
            "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
            "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
        )
        cursor.execute(
            "CREATE POLICY core_documentationlistingreference_runtime_scope "
            "ON core_documentationlistingreference FOR ALL USING ("
            "tenant_id = tekdocs_current_tenant_id() AND ("
            "current_setting('tekdocs.organization_mode', true) = 'msp' OR "
            "organization_id = tekdocs_current_organization_id())) WITH CHECK ("
            "tenant_id = tekdocs_current_tenant_id() AND ("
            "current_setting('tekdocs.organization_mode', true) = 'msp' OR "
            "organization_id = tekdocs_current_organization_id()))"
        )
        cursor.execute(
            "CREATE POLICY core_documentplacement_runtime_scope ON core_documentplacement FOR ALL USING ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.id = document_id)) WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id))"
        )
        cursor.execute(
            "CREATE POLICY core_block_runtime_scope ON core_block FOR ALL USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_documentplacement p WHERE p.block_id = core_block.id))) WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id))"
        )

        # Referenced MSP documents need their stable document/block entity labels.
        cursor.execute("DROP POLICY core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')) OR EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id))"
        )


def disable_document_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')))"
        )
        for table in TABLES:
            cursor.execute(f"DROP TRIGGER IF EXISTS {table}_scope_guard ON {table}")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_document_scope()")


class Migration(migrations.Migration):
    dependencies = [("core", "0020_block_document_documentationlistingreference_and_more")]
    operations = [migrations.RunPython(enable_document_rls, disable_document_rls)]
