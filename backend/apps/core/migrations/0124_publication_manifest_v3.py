from django.db import migrations

PUBLICATION_V2_GUARD = """
CREATE OR REPLACE FUNCTION tekdocs_validate_document_publication() RETURNS trigger
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
     OR NEW.manifest->>'format' <> 'tekdocs-static-publication/v2'
     OR NEW.manifest->>'publication_id' <> NEW.id::text
     OR NEW.manifest->>'publication_entity_id' <> NEW.entity_id::text
     OR NEW.manifest->>'reason' <> NEW.reason
     OR NEW.manifest->>'audience' <> NEW.audience
     OR NEW.manifest->>'retention' <> NEW.retention
     OR (NEW.manifest->>'retention_review_on') IS DISTINCT FROM
        (CASE WHEN NEW.retention_review_on IS NULL THEN NULL ELSE NEW.retention_review_on::text END)
     OR (NEW.manifest->>'supersedes_id') IS DISTINCT FROM
        (CASE WHEN NEW.supersedes_id IS NULL THEN NULL ELSE
          (SELECT prior.entity_id::text FROM core_documentpublication prior
           WHERE prior.id = NEW.supersedes_id) END)
     OR jsonb_typeof(NEW.manifest->'artifacts') <> 'array'
  THEN RAISE EXCEPTION 'publication integrity metadata is invalid'; END IF;
  IF NOT (
    (NEW.organization_id IS NULL AND NEW.manifest->'workspace'->>'kind' = 'msp'
      AND NEW.manifest->'workspace'->>'id' IS NULL)
    OR EXISTS (
      SELECT 1 FROM core_organization o WHERE o.id = NEW.organization_id
        AND NEW.manifest->'workspace'->>'kind' = 'organization'
        AND NEW.manifest->'workspace'->>'id' = o.entity_id::text)
  ) THEN RAISE EXCEPTION 'publication manifest workspace mismatch'; END IF;
  IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_documentpublication prior
    WHERE prior.id = NEW.supersedes_id AND prior.tenant_id = NEW.tenant_id
      AND prior.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND prior.document_id = NEW.document_id
  ) THEN RAISE EXCEPTION 'publication supersession mismatch'; END IF;
  RETURN NEW;
END $$
"""

PUBLICATION_V3_GUARD = PUBLICATION_V2_GUARD.replace(
    "NEW.manifest->>'format' <> 'tekdocs-static-publication/v2'",
    "NEW.manifest->>'format' <> 'tekdocs-static-publication/v3'\n"
    "     OR jsonb_typeof(NEW.manifest->'key_resolutions') <> 'array'\n"
    "     OR (NEW.manifest->>'published_at')::timestamptz IS DISTINCT FROM NEW.published_at",
).replace(
    "  RETURN NEW;",
    """  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(NEW.manifest->'key_resolutions') WITH ORDINALITY AS entry(item, ordinal)
    WHERE jsonb_typeof(item) <> 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(item)) <> 11
       OR NOT item ?& ARRAY[
         'kind', 'expression', 'value', 'source_entity_id', 'source_entity_type',
         'source_fingerprint', 'provenance', 'resolved_at', 'source_revision_id',
         'source_revision_number', 'dependency_chain'
       ]
       OR jsonb_typeof(item->'kind') <> 'string'
       OR item->>'kind' NOT IN ('field', 'content')
       OR jsonb_typeof(item->'expression') <> 'string' OR item->>'expression' = ''
       OR jsonb_typeof(item->'value') <> 'string' OR item->>'value' = ''
       OR jsonb_typeof(item->'source_entity_id') <> 'string'
       OR item->>'source_entity_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
       OR jsonb_typeof(item->'source_entity_type') <> 'string' OR item->>'source_entity_type' = ''
       OR jsonb_typeof(item->'source_fingerprint') <> 'string'
       OR item->>'source_fingerprint' !~ '^[0-9a-f]{64}$'
       OR jsonb_typeof(item->'provenance') <> 'string'
       OR item->>'provenance' NOT IN ('local', 'observed')
       OR jsonb_typeof(item->'resolved_at') <> 'string'
       OR (item->>'resolved_at')::timestamptz IS DISTINCT FROM NEW.published_at
       OR jsonb_typeof(item->'dependency_chain') <> 'array'
       OR EXISTS (
         SELECT 1 FROM jsonb_array_elements(item->'dependency_chain') dependency
         WHERE jsonb_typeof(dependency) <> 'string'
            OR dependency #>> '{}' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
       )
       OR (
         item->>'kind' = 'field' AND (
           jsonb_typeof(item->'source_revision_id') <> 'null'
           OR jsonb_typeof(item->'source_revision_number') <> 'null'
           OR jsonb_array_length(item->'dependency_chain') <> 0
         )
       )
       OR (
         item->>'kind' = 'content' AND (
           jsonb_typeof(item->'source_revision_id') <> 'string'
           OR item->>'source_revision_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
           OR jsonb_typeof(item->'source_revision_number') <> 'number'
           OR item->>'source_revision_number' !~ '^[1-9][0-9]*$'
           OR jsonb_array_length(item->'dependency_chain') = 0
         )
       )
  ) OR EXISTS (
    SELECT 1
    FROM (
      SELECT item->>'expression' AS expression,
             lag(item->>'expression') OVER (ORDER BY ordinal) AS previous_expression
      FROM jsonb_array_elements(NEW.manifest->'key_resolutions') WITH ORDINALITY AS entry(item, ordinal)
    ) ordered
    WHERE previous_expression IS NOT NULL AND expression <= previous_expression
  ) THEN RAISE EXCEPTION 'publication key resolution metadata is invalid'; END IF;
  RETURN NEW;""",
)


def install_v3_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(PUBLICATION_V3_GUARD)


def restore_v2_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(PUBLICATION_V2_GUARD)


class Migration(migrations.Migration):
    dependencies = [("core", "0123_data_flow_snapshot_guards")]

    operations = [migrations.RunPython(install_v3_guard, restore_v2_guard)]
