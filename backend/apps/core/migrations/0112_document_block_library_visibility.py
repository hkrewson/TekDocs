from django.db import migrations, models


PLACEMENT_SCOPE_GUARD_TEMPLATE = r"""
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
             d.organization_id IS NOT NULL AND b.organization_id IS NULL AND (
               EXISTS (
                 SELECT 1 FROM core_documentplacement source_placement
                 JOIN core_documentationlistingreference listing
                   ON listing.document_id = source_placement.document_id
                  AND listing.organization_id = d.organization_id
                  AND listing.archived_at IS NULL
                 WHERE source_placement.block_id = b.id
                   AND source_placement.parent_id IS NULL
                   AND source_placement.position = 0
               ){library_visibility_clause}
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
END $$;
"""


PLACEMENT_SCOPE_GUARD = PLACEMENT_SCOPE_GUARD_TEMPLATE.format(
    library_visibility_clause=r""" OR (
                 b.library_visible = TRUE AND EXISTS (
                   SELECT 1 FROM core_document source_document
                    WHERE source_document.id = b.source_document_id
                      AND source_document.tenant_id = NEW.tenant_id
                      AND source_document.organization_id IS NULL
                      AND source_document.archived_at IS NULL
                      AND source_document.library_visible = TRUE
                 )
               )"""
)
PRE_LIBRARY_PLACEMENT_SCOPE_GUARD = PLACEMENT_SCOPE_GUARD_TEMPLATE.format(library_visibility_clause="")


LIBRARY_VISIBILITY_GUARD = r"""
CREATE FUNCTION tekdocs_guard_document_library_visibility() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.library_visible = TRUE AND NEW.library_visible = FALSE AND EXISTS (
    SELECT 1 FROM core_documentplacement placement
    JOIN core_document destination ON destination.id = placement.document_id
    WHERE destination.organization_id IS NOT NULL
      AND (
        (TG_TABLE_NAME = 'core_block' AND placement.block_id = OLD.id) OR
        (TG_TABLE_NAME = 'core_document' AND placement.block_id IN (
          SELECT source_block.id FROM core_block source_block WHERE source_block.source_document_id = OLD.id
        ))
      )
  ) THEN RAISE EXCEPTION 'detach client block reuse before removing library visibility'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_document_library_visibility_guard
BEFORE UPDATE OF library_visible ON core_document
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_document_library_visibility();

CREATE TRIGGER core_block_library_visibility_guard
BEFORE UPDATE OF library_visible ON core_block
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_document_library_visibility();
"""


DROP_LIBRARY_VISIBILITY_GUARD = r"""
DROP TRIGGER IF EXISTS core_block_library_visibility_guard ON core_block;
DROP TRIGGER IF EXISTS core_document_library_visibility_guard ON core_document;
DROP FUNCTION IF EXISTS tekdocs_guard_document_library_visibility();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0111_document_block_kinds")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="library_visible",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="block",
            name="library_visible",
            field=models.BooleanField(default=False),
        ),
        migrations.RunSQL(PLACEMENT_SCOPE_GUARD, PRE_LIBRARY_PLACEMENT_SCOPE_GUARD),
        migrations.RunSQL(LIBRARY_VISIBILITY_GUARD, DROP_LIBRARY_VISIBILITY_GUARD),
    ]
