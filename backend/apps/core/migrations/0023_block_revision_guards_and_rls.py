from django.db import migrations


def enable_revision_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_block_revision() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP IN ('UPDATE', 'DELETE') THEN
                RAISE EXCEPTION 'block revisions are append-only';
              END IF;
              IF NEW.checksum !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'block revision checksum must be lowercase SHA-256';
              END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_block b WHERE b.id = NEW.block_id
                  AND b.tenant_id = NEW.tenant_id
                  AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'block revision workspace mismatch'; END IF;
              IF NEW.parent_id IS NULL AND NEW.revision_number <> 1 THEN
                RAISE EXCEPTION 'only the first block revision may omit its parent';
              END IF;
              IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_blockrevision p WHERE p.id = NEW.parent_id
                  AND p.block_id = NEW.block_id
                  AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND p.revision_number + 1 = NEW.revision_number
              ) THEN RAISE EXCEPTION 'block revision parent mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_blockrevision_append_only_guard "
            "BEFORE INSERT OR UPDATE OR DELETE ON core_blockrevision "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_block_revision()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_block_current_revision() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.current_revision_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_blockrevision r WHERE r.id = NEW.current_revision_id
                  AND r.block_id = NEW.id
                  AND r.tenant_id = NEW.tenant_id
                  AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'current revision must belong to its block workspace'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_block_current_revision_guard "
            "BEFORE INSERT OR UPDATE ON core_block FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_validate_block_current_revision()"
        )
        cursor.execute(
            "CREATE OR REPLACE FUNCTION tekdocs_validate_document_scope() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "IF TG_TABLE_NAME IN ('core_document', 'core_block') AND NOT EXISTS ("
            "SELECT 1 FROM core_entity e WHERE e.id = (to_jsonb(NEW)->>'entity_id')::uuid "
            "AND e.tenant_id = NEW.tenant_id "
            "AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id) "
            "THEN RAISE EXCEPTION 'document entity workspace mismatch'; END IF; "
            "IF TG_TABLE_NAME = 'core_documentplacement' AND NOT EXISTS ("
            "SELECT 1 FROM core_document d JOIN core_block b "
            "ON b.id = (to_jsonb(NEW)->>'block_id')::uuid "
            "WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id "
            "AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id "
            "AND b.tenant_id = NEW.tenant_id "
            "AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id "
            "AND b.current_revision_id IS NOT NULL) "
            "THEN RAISE EXCEPTION 'document placement workspace mismatch'; END IF; "
            "IF TG_TABLE_NAME = 'core_documentationlistingreference' AND NOT EXISTS ("
            "SELECT 1 FROM core_document d JOIN core_organization o ON o.id = NEW.organization_id "
            "WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id "
            "AND d.organization_id IS NULL AND o.tenant_id = NEW.tenant_id) "
            "THEN RAISE EXCEPTION 'documentation reference must project an MSP document into its tenant'; END IF; "
            "RETURN NEW; END $$"
        )
        cursor.execute("ALTER TABLE core_blockrevision ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_blockrevision FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_blockrevision_runtime_select ON core_blockrevision FOR SELECT USING ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.id = block_id))"
        )
        cursor.execute(
            "CREATE POLICY core_blockrevision_runtime_insert ON core_blockrevision FOR INSERT WITH CHECK ("
            "tekdocs_scope_matches(tenant_id, organization_id))"
        )


def disable_revision_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS core_blockrevision_append_only_guard ON core_blockrevision")
        cursor.execute("DROP TRIGGER IF EXISTS core_block_current_revision_guard ON core_block")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_block_revision()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_block_current_revision()")
        cursor.execute("DROP POLICY IF EXISTS core_blockrevision_runtime_select ON core_blockrevision")
        cursor.execute("DROP POLICY IF EXISTS core_blockrevision_runtime_insert ON core_blockrevision")
        cursor.execute("ALTER TABLE core_blockrevision DISABLE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE OR REPLACE FUNCTION tekdocs_validate_document_scope() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "IF TG_TABLE_NAME IN ('core_document', 'core_block') AND NOT EXISTS ("
            "SELECT 1 FROM core_entity e WHERE e.id = (to_jsonb(NEW)->>'entity_id')::uuid "
            "AND e.tenant_id = NEW.tenant_id "
            "AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id) "
            "THEN RAISE EXCEPTION 'document entity workspace mismatch'; END IF; "
            "IF TG_TABLE_NAME = 'core_documentplacement' AND NOT EXISTS ("
            "SELECT 1 FROM core_document d JOIN core_block b "
            "ON b.id = (to_jsonb(NEW)->>'block_id')::uuid "
            "WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id "
            "AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id "
            "AND b.tenant_id = NEW.tenant_id "
            "AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id) "
            "THEN RAISE EXCEPTION 'document placement workspace mismatch'; END IF; "
            "IF TG_TABLE_NAME = 'core_documentationlistingreference' AND NOT EXISTS ("
            "SELECT 1 FROM core_document d JOIN core_organization o ON o.id = NEW.organization_id "
            "WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id "
            "AND d.organization_id IS NULL AND o.tenant_id = NEW.tenant_id) "
            "THEN RAISE EXCEPTION 'documentation reference must project an MSP document into its tenant'; END IF; "
            "RETURN NEW; END $$"
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0022_immutable_block_revisions")]
    operations = [migrations.RunPython(enable_revision_guards, disable_revision_guards)]
