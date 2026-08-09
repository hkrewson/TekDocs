from django.db import migrations


def enable_attachment_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_document_attachment() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_document d
                WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
                  AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'attachment document workspace mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND e.entity_type = 'document_attachment'
              ) THEN RAISE EXCEPTION 'attachment entity workspace mismatch'; END IF;
              IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size < 1 OR NEW.size > 10485760 THEN
                RAISE EXCEPTION 'attachment integrity metadata is invalid';
              END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_documentattachment_scope_guard "
            "BEFORE INSERT OR UPDATE ON core_documentattachment "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_attachment()"
        )
        cursor.execute("ALTER TABLE core_documentattachment ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_documentattachment FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_documentattachment_runtime_select ON core_documentattachment FOR SELECT USING ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.id = document_id))"
        )
        cursor.execute(
            "CREATE POLICY core_documentattachment_runtime_write ON core_documentattachment FOR ALL USING ("
            "tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id))"
        )
        cursor.execute("DROP POLICY core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')) OR EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id))"
        )


def disable_attachment_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')) OR EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id))"
        )
        cursor.execute("DROP POLICY IF EXISTS core_documentattachment_runtime_select ON core_documentattachment")
        cursor.execute("DROP POLICY IF EXISTS core_documentattachment_runtime_write ON core_documentattachment")
        cursor.execute("ALTER TABLE core_documentattachment DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_documentattachment_scope_guard ON core_documentattachment")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_document_attachment()")


class Migration(migrations.Migration):
    dependencies = [("core", "0026_document_categories_and_attachments")]
    operations = [migrations.RunPython(enable_attachment_guards, disable_attachment_guards)]
