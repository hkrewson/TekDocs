from django.db import migrations


def enable_publication_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_document_publication() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_document d
                WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
                  AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND NEW.manifest->>'source_document_id' = d.entity_id::text
              ) THEN RAISE EXCEPTION 'publication document workspace mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND e.entity_type = 'document_publication'
              ) THEN RAISE EXCEPTION 'publication entity workspace mismatch'; END IF;
              IF NEW.content_digest !~ '^[0-9a-f]{64}$'
                 OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
                 OR NEW.signature_algorithm <> 'Ed25519'
                 OR jsonb_typeof(NEW.manifest) <> 'object'
                 OR NEW.manifest->>'format' <> 'tekdocs-static-publication/v1'
                 OR NEW.manifest->>'publication_id' <> NEW.id::text
                 OR NEW.manifest->>'publication_entity_id' <> NEW.entity_id::text
              THEN RAISE EXCEPTION 'publication integrity metadata is invalid'; END IF;
              IF NOT (
                (NEW.organization_id IS NULL
                  AND NEW.manifest->'workspace'->>'kind' = 'msp'
                  AND NEW.manifest->'workspace'->>'id' IS NULL)
                OR EXISTS (
                  SELECT 1 FROM core_organization o
                  WHERE o.id = NEW.organization_id
                    AND NEW.manifest->'workspace'->>'kind' = 'organization'
                    AND NEW.manifest->'workspace'->>'id' = o.entity_id::text
                )
              ) THEN RAISE EXCEPTION 'publication manifest workspace mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_documentpublication_scope_guard "
            "BEFORE INSERT ON core_documentpublication "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_publication()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_guard_document_publication_immutability() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'document publications are append-only';
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_documentpublication_immutable "
            "BEFORE UPDATE OR DELETE ON core_documentpublication "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_document_publication_immutability()"
        )
        cursor.execute("ALTER TABLE core_documentpublication ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_documentpublication FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_documentpublication_runtime_select ON core_documentpublication FOR SELECT USING ("
            "tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.id = document_id))"
        )
        cursor.execute(
            "CREATE POLICY core_documentpublication_runtime_write ON core_documentpublication FOR INSERT WITH CHECK ("
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
            "SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id))"
        )


def disable_publication_guards(apps, schema_editor):
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
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id))"
        )
        cursor.execute("DROP POLICY IF EXISTS core_documentpublication_runtime_select ON core_documentpublication")
        cursor.execute("DROP POLICY IF EXISTS core_documentpublication_runtime_write ON core_documentpublication")
        cursor.execute("ALTER TABLE core_documentpublication DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_documentpublication_immutable ON core_documentpublication")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_guard_document_publication_immutability()")
        cursor.execute("DROP TRIGGER IF EXISTS core_documentpublication_scope_guard ON core_documentpublication")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_document_publication()")


class Migration(migrations.Migration):
    dependencies = [("core", "0028_document_publication")]
    operations = [migrations.RunPython(enable_publication_guards, disable_publication_guards)]
