"""Layer retained diagram proof over the unchanged v5-v10 content certificates."""

from importlib import import_module

from django.db import migrations

prior = import_module("apps.core.migrations.0209_content_key_git_publication")

# Validate a separate local view. NEW.manifest remains the original signed v11
# object throughout insertion, including every retained SVG/PNG descriptor.
DIAGRAM_VIEW = r"""
DECLARE
  checked_manifest jsonb;
BEGIN
  checked_manifest := NEW.manifest;
  IF NEW.manifest->>'format'='tekdocs-static-publication/v11' THEN
    IF NOT COALESCE(
      NEW.manifest->>'content_format' IN (
        'tekdocs-static-publication/v5', 'tekdocs-static-publication/v6',
        'tekdocs-static-publication/v7', 'tekdocs-static-publication/v8',
        'tekdocs-static-publication/v9', 'tekdocs-static-publication/v10'
      )
      AND jsonb_typeof(NEW.manifest->'diagrams')='array'
      AND jsonb_array_length(NEW.manifest->'diagrams') BETWEEN 1 AND 20
      AND jsonb_typeof(NEW.manifest->'artifacts')='array'
      AND jsonb_array_length(NEW.manifest->'artifacts') BETWEEN 3 AND 91
      AND (SELECT count(DISTINCT a->>'entity_id') FROM jsonb_array_elements(NEW.manifest->'artifacts') a)
        =jsonb_array_length(NEW.manifest->'artifacts')
      AND (SELECT count(DISTINCT a->>'id') FROM jsonb_array_elements(NEW.manifest->'artifacts') a)
        =jsonb_array_length(NEW.manifest->'artifacts')
      AND (SELECT count(*) FROM jsonb_array_elements(NEW.manifest->'artifacts') a
           WHERE a->>'kind' IN ('diagram_svg', 'diagram_png'))=2*jsonb_array_length(NEW.manifest->'diagrams')
      AND (SELECT count(DISTINCT identity) FROM (
        SELECT d->>'svg_artifact_id' identity FROM jsonb_array_elements(NEW.manifest->'diagrams') d
        UNION ALL SELECT d->>'png_artifact_id' FROM jsonb_array_elements(NEW.manifest->'diagrams') d
      ) ids)=2*jsonb_array_length(NEW.manifest->'diagrams')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'diagrams') WITH ORDINALITY entry(d, ordinal)
        WHERE NOT COALESCE(
          jsonb_typeof(d)='object' AND (SELECT count(*) FROM jsonb_object_keys(d))=13
          AND d->>'index'=ordinal::text AND d->>'state'='rendered'
          AND jsonb_typeof(d->'title')='string' AND jsonb_typeof(d->'description')='string'
          AND jsonb_typeof(d->'family')='string' AND d->>'source_checksum' ~ '^[0-9a-f]{64}$'
          AND d->>'renderer_version' ~ '^@mermaid-js/mermaid-cli@[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$'
          AND NOT EXISTS (
            SELECT 1 FROM (VALUES ('svg', 'image/svg+xml', 2097152), ('png', 'image/png', 5242880)) spec(ext, media, maximum)
            WHERE NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(NEW.manifest->'artifacts') a
              WHERE a->>'entity_id'=d->>(ext||'_artifact_id') AND a->>'kind'='diagram_'||ext
                AND a->>'media_type'=media AND a->'source_attachment_id'='null'::jsonb
                AND jsonb_typeof(a->'size')='number' AND (a->>'size')::bigint BETWEEN 1 AND maximum
                AND a->>'checksum'=d->>(ext||'_checksum') AND a->>'checksum' ~ '^[0-9a-f]{64}$'
                AND a->>'filename'=d->>(ext||'_filename')
                AND a->>'filename'='diagram-'||lpad(ordinal::text, 3, '0')||'.'||ext
            )
          ), false)
      ), false)
    THEN RAISE EXCEPTION 'Git diagram publication proof is invalid'; END IF;
    checked_manifest := (NEW.manifest - 'content_format') || jsonb_build_object(
      'format', NEW.manifest->'content_format', 'diagrams', '[]'::jsonb,
      'artifacts', (SELECT jsonb_agg(a ORDER BY ordinal)
                   FROM jsonb_array_elements(NEW.manifest->'artifacts') WITH ORDINALITY entry(a, ordinal)
                   WHERE a->>'kind' NOT IN ('diagram_svg', 'diagram_png'))
    );
  END IF;
"""

V11 = prior.V10.replace("NEW.manifest", "checked_manifest").replace("BEGIN\n", DIAGRAM_VIEW, 1)


class Migration(migrations.Migration):
    dependencies = [("core", "0210_content_key_authority_closure")]
    operations = [migrations.RunSQL(V11, prior.V10)]
