"""Retain native library proof without widening historical evidence formats."""

from importlib import import_module

from django.db import migrations

_keys = import_module('apps.core.migrations.0220_native_key_evidence')

TEMPLATE_VALIDATION = r"""
  IF NEW.manifest->>'format'='tekdocs-repository-publication-evidence/v4' THEN
    IF jsonb_typeof(NEW.manifest->'source'->'sources') IS DISTINCT FROM 'array'
      OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.manifest->'source'->'sources') item
        WHERE item ? 'library_workspace')
      OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'source'->'sources') item
        WHERE item ? 'library_workspace' AND (
          item->'native_template' IS DISTINCT FROM 'true'::jsonb
          OR item->'body_only' IS DISTINCT FROM 'true'::jsonb
          OR item->>'mode' NOT IN ('live', 'pinned')
          OR jsonb_array_length(item->'ordinal_path')<>1
          OR item->>'source_sha256' IS DISTINCT FROM
            encode(sha256(convert_to(item->>'selected_source', 'UTF8')), 'hex')
          OR NOT EXISTS (
            SELECT 1 FROM core_repositorytemplateenrollment enrollment
            JOIN core_repositorytemplate template ON template.id=enrollment.source_template_id
            JOIN core_repositorytemplaterevision revision ON revision.template_id=template.id
            JOIN core_repositorycommit commit ON commit.id=revision.commit_id
            CROSS JOIN LATERAL jsonb_array_elements(enrollment.placement_map) placement
            CROSS JOIN LATERAL jsonb_array_elements(revision.manifest->'sections') section
            WHERE enrollment.tenant_id=NEW.tenant_id AND enrollment.workspace_id=NEW.workspace_id
              AND enrollment.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND enrollment.repository_id=NEW.repository_id AND enrollment.content_id=NEW.content_id
              AND template.tenant_id=NEW.tenant_id AND template.enabled AND template.library_visible
              AND template.workspace_id::text=item->>'library_workspace'
              AND template.repository_id::text=item->>'repository_id'
              AND template.workspace_id<>NEW.workspace_id AND template.repository_id<>NEW.repository_id
              AND revision.tenant_id=NEW.tenant_id AND revision.id::text=item->>'template_revision'
              AND revision.manifest=item->'template_manifest' AND revision.checksum=item->>'template_checksum'
              AND commit.repository_id=template.repository_id AND commit.tenant_id=NEW.tenant_id
              AND placement->>'id'=item->>'id' AND placement->>'mode'=item->>'mode'
              AND placement->>'revision_id'=item->>'enrollment_revision'
              AND ((item->>'mode'='pinned' AND placement->>'revision_id'=revision.id::text
                AND commit.object_id=item->>'commit' AND placement->>'commit'=item->>'commit')
                OR (item->>'mode'='live' AND revision.id=template.latest_revision_id
                  AND item->>'commit'=item->>'accepted_commit' AND EXISTS (
                    SELECT 1 FROM core_workspacerepository source_repository
                    JOIN core_repositorycommit accepted ON accepted.id=source_repository.accepted_commit_id
                    WHERE source_repository.id=template.repository_id AND accepted.object_id=item->>'commit'
                      AND source_repository.accepted_commit_id=source_repository.indexed_commit_id)))
              AND section->>'id'=item->>'id' AND section->>'source'=item->>'selected_source'
              AND section->>'path'=item->>'path'
          )
        )
      )
    THEN RAISE EXCEPTION 'native template evidence source mismatch' USING ERRCODE='23514'; END IF;
  END IF;
"""

FORWARD_SQL = _keys.FORWARD_SQL.replace(
    "'tekdocs-repository-publication-evidence/v3'\n    )",
    "'tekdocs-repository-publication-evidence/v3', 'tekdocs-repository-publication-evidence/v4'\n    )",
).replace(
    "IF NEW.manifest->>'format'='tekdocs-repository-publication-evidence/v3' THEN",
    "IF NEW.manifest->>'format' IN ('tekdocs-repository-publication-evidence/v3', "
    "'tekdocs-repository-publication-evidence/v4') THEN",
).replace(
    "'tekdocs-repository-publication-evidence/v3')",
    "'tekdocs-repository-publication-evidence/v3', 'tekdocs-repository-publication-evidence/v4')",
).replace(
    "NEW.manifest->'source'->>'format' IS DISTINCT FROM 'tekdocs.git-dependencies/v1'",
    "NEW.manifest->'source'->>'format' IS DISTINCT FROM (CASE WHEN "
    "NEW.manifest->>'format'='tekdocs-repository-publication-evidence/v4' "
    "THEN 'tekdocs.git-dependencies/v4' ELSE 'tekdocs.git-dependencies/v1' END)",
).replace("  RETURN NEW;\nEND $$;", TEMPLATE_VALIDATION + "  RETURN NEW;\nEND $$;", 1)

REVERSE_SQL = r"""
ALTER TABLE core_repositorypublicationevidence NO FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM core_repositorypublicationevidence
    WHERE manifest->>'format'='tekdocs-repository-publication-evidence/v4') THEN
    RAISE EXCEPTION 'Retained native template evidence prevents schema rollback' USING ERRCODE='23514';
  END IF;
END $$;
ALTER TABLE core_repositorypublicationevidence FORCE ROW LEVEL SECURITY;
""" + _keys.FORWARD_SQL


class Migration(migrations.Migration):
    dependencies = [('core', '0221_native_templates')]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
