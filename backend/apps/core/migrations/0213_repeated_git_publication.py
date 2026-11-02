"""Admit ordered occurrence proof without changing historical format constraints."""

from importlib import import_module

from django.db import migrations

PRIOR = import_module("apps.core.migrations.0212_client_git_publication").CLIENT
DIAGRAM_VIEW = import_module("apps.core.migrations.0211_diagram_git_publication").DIAGRAM_VIEW

OCCURRENCE_VIEW = DIAGRAM_VIEW.replace("NEW.manifest", "envelope_manifest").replace(
    "  checked_manifest jsonb;", "  checked_manifest jsonb;\n  envelope_manifest jsonb;",
).replace("BEGIN\n", r"""BEGIN
  envelope_manifest := NEW.manifest;
  IF NEW.manifest->>'format'='tekdocs-static-publication/v12' THEN
    IF NOT COALESCE(
      NEW.manifest->>'occurrence_format' IN (
        'tekdocs-static-publication/v7', 'tekdocs-static-publication/v8',
        'tekdocs-static-publication/v9', 'tekdocs-static-publication/v10',
        'tekdocs-static-publication/v11'
      )
      AND jsonb_typeof(NEW.manifest->'git_source'->'sources')='array'
      AND jsonb_array_length(NEW.manifest->'git_source'->'sources') BETWEEN 3 AND 512
      AND (SELECT count(DISTINCT (COALESCE(s->>'library_workspace',
             NEW.manifest->'git_source'->>'workspace_id'), s->>'id'))
           FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s)
          < jsonb_array_length(NEW.manifest->'git_source'->'sources')
      AND (SELECT count(DISTINCT s->'ordinal_path')
           FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s)
          = jsonb_array_length(NEW.manifest->'git_source'->'sources')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
        WHERE jsonb_typeof(s->'ordinal_path') IS DISTINCT FROM 'array'
      ), false)
    THEN RAISE EXCEPTION 'Git occurrence publication proof is invalid'; END IF;
    envelope_manifest := (NEW.manifest - 'occurrence_format') || jsonb_build_object(
      'format', NEW.manifest->'occurrence_format'
    );
  END IF;
""", 1)

# Only a v12 envelope admits repeated source identities. Every normalized content
# branch still binds the exact ordered indexed manifest, audience and file/key
# custody. Historical v5-v11 insertions retain their original uniqueness rule.
V12 = PRIOR.replace(DIAGRAM_VIEW, OCCURRENCE_VIEW, 1)
V12 = V12.replace(
    "count(DISTINCT s->>'id')",
    "count(DISTINCT CASE WHEN NEW.manifest->>'format'='tekdocs-static-publication/v12' "
    "THEN (s->'ordinal_path')::text ELSE s->>'id' END)",
).replace(
    "count(DISTINCT (COALESCE(s->>'library_workspace', checked_manifest->'git_source'->>'workspace_id'), s->>'id'))",
    "count(DISTINCT CASE WHEN NEW.manifest->>'format'='tekdocs-static-publication/v12' "
    "THEN s->'ordinal_path' ELSE jsonb_build_array(COALESCE(s->>'library_workspace', "
    "checked_manifest->'git_source'->>'workspace_id'), s->>'id') END)",
)


class Migration(migrations.Migration):
    dependencies = [("core", "0212_client_git_publication")]
    operations = [migrations.RunSQL(V12, PRIOR)]
