"""Admit bounded file-bearing Git snapshots without weakening v4/v5 guards."""

from importlib import import_module

from django.db import migrations

V5 = import_module("apps.core.migrations.0196_internal_git_publication").V5
V6 = V5.replace(
    "('tekdocs-static-publication/v4', 'tekdocs-static-publication/v5')",
    "('tekdocs-static-publication/v4', 'tekdocs-static-publication/v5', 'tekdocs-static-publication/v6')",
).replace(
    "IF NEW.manifest->>'format' = 'tekdocs-static-publication/v5' THEN",
    "IF NEW.manifest->>'format' IN ('tekdocs-static-publication/v5', 'tekdocs-static-publication/v6') THEN",
).replace(
    "AND NEW.manifest->'attachments' = '[]'::jsonb",
    "AND (NEW.manifest->>'format' = 'tekdocs-static-publication/v6' "
    "OR NEW.manifest->'attachments' = '[]'::jsonb)",
).replace(
    "AND jsonb_array_length(NEW.manifest->'artifacts') = 1",
    "AND (NEW.manifest->>'format' = 'tekdocs-static-publication/v6' "
    "OR jsonb_array_length(NEW.manifest->'artifacts') = 1)",
).replace(
    "  RETURN NEW;",
    """
  IF NEW.manifest->>'format' = 'tekdocs-static-publication/v6' THEN
    IF NOT COALESCE(
      jsonb_typeof(NEW.manifest->'managed_files') = 'array'
      AND jsonb_array_length(NEW.manifest->'managed_files') BETWEEN 1 AND 50
      AND NEW.manifest->'attachments' = (
        SELECT jsonb_agg(jsonb_build_object(
          'id', f->'id', 'filename', f->'filename', 'media_type', f->'media_type',
          'size', f->'size', 'checksum', f->'checksum') ORDER BY ordinal)
        FROM jsonb_array_elements(NEW.manifest->'managed_files') WITH ORDINALITY entry(f, ordinal)
      )
      AND jsonb_array_length(NEW.manifest->'artifacts') = jsonb_array_length(NEW.manifest->'managed_files') + 1
      AND (SELECT count(*) FROM jsonb_array_elements(NEW.manifest->'artifacts') a WHERE a->>'kind' = 'pdf') = 1
      AND (SELECT count(DISTINCT f->>'id') FROM jsonb_array_elements(NEW.manifest->'managed_files') f)
          = jsonb_array_length(NEW.manifest->'managed_files')
      AND (SELECT count(DISTINCT f->>'artifact_id') FROM jsonb_array_elements(NEW.manifest->'managed_files') f)
          = jsonb_array_length(NEW.manifest->'managed_files')
      AND (SELECT count(*) FROM core_documentattachment a WHERE a.document_id = NEW.document_id
           AND a.archived_at IS NULL) = jsonb_array_length(NEW.manifest->'managed_files')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'managed_files') f
        WHERE NOT EXISTS (
          SELECT 1 FROM core_documentattachment a
          JOIN core_document d ON d.id = NEW.document_id
          JOIN core_entity e ON e.id = d.entity_id
          WHERE a.document_id = d.id AND a.tenant_id = NEW.tenant_id
            AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND a.owner_workspace_id = e.workspace_id AND a.owner_content_id = d.id
            AND a.archived_at IS NULL AND a.scan_status = 'clean'
            AND a.entity_id::text = f->>'id'
            AND f->'owner'->>'type' = 'repository_document' AND f->'owner'->>'id' = d.id::text
            AND f->>'purpose' = a.purpose AND f->>'checksum' = a.checksum
            AND f->>'filename' = a.original_filename AND f->>'media_type' = a.media_type
            AND f->>'size' = a.size::text
            AND (f->>'version_number') IS NOT DISTINCT FROM a.version_number::text
            AND (f->>'replaces_id') IS NOT DISTINCT FROM
                (SELECT previous.entity_id::text FROM core_documentattachment previous
                 WHERE previous.id = a.replaces_id)
            AND EXISTS (
              SELECT 1 FROM jsonb_array_elements(NEW.manifest->'artifacts') artifact
              WHERE artifact->>'kind' = 'attachment' AND artifact->>'entity_id' = f->>'artifact_id'
                AND artifact->>'source_attachment_id' = f->>'id'
                AND artifact->>'checksum' = f->>'checksum' AND artifact->>'size' = f->>'size'
                AND artifact->>'filename' = f->>'filename' AND artifact->>'media_type' = f->>'media_type'
            )
        )
      ), false)
    THEN RAISE EXCEPTION 'internal Git publication files are invalid'; END IF;
  END IF;
  RETURN NEW;
""",
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(V6)


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(V5)


class Migration(migrations.Migration):
    dependencies = [("core", "0196_internal_git_publication")]
    operations = [migrations.RunPython(install, reverse)]
