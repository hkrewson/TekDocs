from django.db import migrations


def enable_placement_guards(apps, schema_editor):
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
              IF TG_TABLE_NAME = 'core_document' AND TG_OP = 'UPDATE'
                 AND to_jsonb(OLD)->>'archived_at' IS NULL
                 AND to_jsonb(NEW)->>'archived_at' IS NOT NULL AND EXISTS (
                   SELECT 1 FROM core_documentplacement source_placement
                   JOIN core_documentplacement dependent
                     ON dependent.block_id = source_placement.block_id
                    AND dependent.document_id <> source_placement.document_id
                   WHERE source_placement.document_id = (to_jsonb(NEW)->>'id')::uuid
                     AND source_placement.parent_id IS NULL
                     AND source_placement.position = 0
                 ) THEN RAISE EXCEPTION 'remove transclusions before archiving source document'; END IF;
              IF TG_TABLE_NAME = 'core_documentplacement' THEN
                IF NOT EXISTS (
                  SELECT 1 FROM core_document d JOIN core_block b ON b.id = NEW.block_id
                   WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
                     AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
                     AND b.tenant_id = NEW.tenant_id AND b.current_revision_id IS NOT NULL
                     AND (
                       b.organization_id IS NOT DISTINCT FROM d.organization_id OR (
                         d.organization_id IS NOT NULL AND b.organization_id IS NULL AND EXISTS (
                           SELECT 1 FROM core_documentplacement source_placement
                           JOIN core_documentationlistingreference listing
                             ON listing.document_id = source_placement.document_id
                            AND listing.organization_id = d.organization_id
                            AND listing.archived_at IS NULL
                           WHERE source_placement.block_id = b.id
                             AND source_placement.parent_id IS NULL
                             AND source_placement.position = 0
                         )
                       )
                     )
                ) THEN RAISE EXCEPTION 'document placement workspace mismatch'; END IF;
                IF NEW.resolution_mode = 'live' AND NEW.pinned_revision_id IS NOT NULL
                   OR NEW.resolution_mode = 'pinned' AND NEW.pinned_revision_id IS NULL
                   OR NEW.resolution_mode NOT IN ('live', 'pinned')
                THEN RAISE EXCEPTION 'document placement resolution target mismatch'; END IF;
                IF NEW.parent_id IS NULL AND NEW.position = 0
                   AND (NEW.resolution_mode <> 'live' OR NEW.pinned_revision_id IS NOT NULL)
                THEN RAISE EXCEPTION 'primary document placement must remain live'; END IF;
                IF NEW.pinned_revision_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM core_blockrevision r WHERE r.id = NEW.pinned_revision_id
                    AND r.block_id = NEW.block_id AND r.tenant_id = NEW.tenant_id
                ) THEN RAISE EXCEPTION 'pinned revision must belong to the placed block'; END IF;
                IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM core_documentplacement p WHERE p.id = NEW.parent_id
                    AND p.document_id = NEW.document_id AND p.tenant_id = NEW.tenant_id
                    AND p.organization_id IS NOT DISTINCT FROM NEW.organization_id
                ) THEN RAISE EXCEPTION 'placement parent must belong to the same document'; END IF;
                IF NEW.parent_id = NEW.id THEN RAISE EXCEPTION 'placement cannot parent itself'; END IF;
                IF NEW.parent_id IS NOT NULL AND EXISTS (
                  WITH RECURSIVE ancestors AS (
                    SELECT p.id, p.parent_id, p.block_id FROM core_documentplacement p WHERE p.id = NEW.parent_id
                    UNION ALL
                    SELECT p.id, p.parent_id, p.block_id FROM core_documentplacement p
                      JOIN ancestors a ON p.id = a.parent_id
                  )
                  SELECT 1 FROM ancestors WHERE block_id = NEW.block_id
                ) THEN RAISE EXCEPTION 'circular block transclusion'; END IF;
              END IF;
              IF TG_TABLE_NAME = 'core_documentationlistingreference' AND NOT EXISTS (
                SELECT 1 FROM core_document d JOIN core_organization o ON o.id = NEW.organization_id
                 WHERE d.id = (to_jsonb(NEW)->>'document_id')::uuid AND d.tenant_id = NEW.tenant_id
                   AND d.organization_id IS NULL AND o.tenant_id = NEW.tenant_id
              ) THEN RAISE EXCEPTION 'documentation reference must project an MSP document into its tenant'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_guard_document_reference_removal() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.archived_at IS NULL
                 AND (TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND NEW.archived_at IS NOT NULL))
                 AND EXISTS (
                SELECT 1 FROM core_documentplacement destination_placement
                JOIN core_document destination_document
                  ON destination_document.id = destination_placement.document_id
                WHERE destination_document.organization_id = OLD.organization_id
                  AND destination_placement.block_id IN (
                    SELECT source_placement.block_id FROM core_documentplacement source_placement
                    WHERE source_placement.document_id = OLD.document_id
                      AND source_placement.parent_id IS NULL
                      AND source_placement.position = 0
                  )
              ) THEN RAISE EXCEPTION 'remove client transclusions before removing documentation reference'; END IF;
              IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_documentation_reference_removal_guard "
            "BEFORE UPDATE OR DELETE ON core_documentationlistingreference "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_document_reference_removal()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_guard_primary_placement_delete() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.parent_id IS NULL AND OLD.position = 0
              THEN RAISE EXCEPTION 'primary document placement cannot be deleted'; END IF;
              RETURN OLD;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_document_primary_placement_delete_guard "
            "BEFORE DELETE ON core_documentplacement "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_primary_placement_delete()"
        )


def disable_placement_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_document_primary_placement_delete_guard ON core_documentplacement"
        )
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_guard_primary_placement_delete()")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_documentation_reference_removal_guard "
            "ON core_documentationlistingreference"
        )
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_guard_document_reference_removal()")
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
                SELECT 1 FROM core_document d JOIN core_block b ON b.id = NEW.block_id
                 WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
                   AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
                   AND b.tenant_id = NEW.tenant_id AND b.current_revision_id IS NOT NULL
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


class Migration(migrations.Migration):
    dependencies = [("core", "0024_document_placement_resolution")]
    operations = [migrations.RunPython(enable_placement_guards, disable_placement_guards)]
