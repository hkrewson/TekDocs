"""Version native binding evidence without rewriting retained publication formats."""

from importlib import import_module

from django.db import migrations

_evidence = import_module('apps.core.migrations.0188_repository_primary_publication_evidence')
_package = import_module('apps.core.migrations.0189_primary_repository_package')
_static = import_module('apps.core.migrations.0190_primary_repository_static_publication')

NATIVE_VALIDATION = r"""
  IF NEW.manifest->>'format'='tekdocs-repository-publication-evidence/v3' THEN
    IF jsonb_typeof(NEW.manifest->'key_bindings') IS DISTINCT FROM 'object'
      OR jsonb_typeof(NEW.manifest->'key_source') IS DISTINCT FROM 'object'
      OR NEW.manifest->'key_source'->>'path' IS DISTINCT FROM NEW.manifest->'source'->'sources'->0->>'path'
      OR NEW.manifest->'key_source'->>'blob' IS DISTINCT FROM NEW.manifest->'source'->'sources'->0->>'blob'
      OR encode(sha256(convert_to(NEW.manifest->'key_source'->>'source', 'UTF8')), 'hex')
        IS DISTINCT FROM NEW.manifest->'source'->'sources'->0->>'source_sha256'
      OR NOT EXISTS (
        SELECT 1 FROM core_contentnode node WHERE node.repository_id=NEW.repository_id
          AND node.workspace_id=NEW.workspace_id AND node.tenant_id=NEW.tenant_id
          AND node.organization_id IS NOT DISTINCT FROM NEW.organization_id
          AND node.content_id=NEW.content_id AND node.kind='document'
          AND node.indexed_commit_id=NEW.source_commit_id
          AND node.source_path=NEW.manifest->'key_source'->>'path'
          AND COALESCE((SELECT jsonb_object_agg(binding.key, to_jsonb(binding.value::uuid::text))
            FROM jsonb_each_text(COALESCE(node.frontmatter->'key_bindings', '{}'::jsonb)) binding), '{}'::jsonb)
              =NEW.manifest->'key_bindings'
      )
    THEN RAISE EXCEPTION 'native key evidence source mismatch' USING ERRCODE='23514'; END IF;
    IF NEW.manifest ? 'key_snapshot' THEN
      IF jsonb_typeof(NEW.manifest->'key_snapshot') IS DISTINCT FROM 'object'
        OR jsonb_typeof(NEW.manifest->'key_snapshot'->'records') IS DISTINCT FROM 'array'
        OR NEW.manifest->'key_snapshot'->>'sha256' IS DISTINCT FROM
          encode(sha256(convert_to(NEW.manifest->'key_snapshot'->>'markdown', 'UTF8')), 'hex')
      THEN RAISE EXCEPTION 'native key evidence snapshot mismatch' USING ERRCODE='23514'; END IF;
      IF jsonb_array_length(NEW.manifest->'key_snapshot'->'records') NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'native key evidence resolution limit' USING ERRCODE='23514'; END IF;
      IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'key_snapshot'->'records') record
        WHERE NEW.manifest->'key_bindings'->>split_part(record->>'expression', '.', 1)
            IS DISTINCT FROM record->>'source_entity_id'
          OR record->>'resolved_at' IS DISTINCT FROM NEW.manifest->>'signed_at'
          OR (record->>'kind'='content' AND record->>'source_entity_type' IS DISTINCT FROM 'repository_fragment')
          OR (record->>'kind'='content' AND (
            record->'git_source'->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
            OR record->'git_source'->>'repository_id' IS DISTINCT FROM NEW.repository_id::text
            OR record->'git_source'->>'commit' IS DISTINCT FROM NEW.manifest->>'source_commit'))
          OR NOT (
            (record->>'source_entity_type'='repository_fragment' AND EXISTS (
              SELECT 1 FROM core_contentnode fragment WHERE fragment.repository_id=NEW.repository_id
                AND fragment.workspace_id=NEW.workspace_id AND fragment.tenant_id=NEW.tenant_id
                AND fragment.kind='fragment' AND fragment.indexed_commit_id=NEW.source_commit_id
                AND fragment.content_id::text=record->>'source_entity_id'
                AND fragment.content_id::text=record->'git_source'->>'content_id'
                AND record->>'kind'='content'
                AND NOT EXISTS (SELECT 1 FROM core_block legacy JOIN core_entity owner ON owner.id=legacy.entity_id
                  WHERE legacy.id=fragment.content_id AND legacy.tenant_id=NEW.tenant_id
                    AND owner.workspace_id=NEW.workspace_id
                    AND legacy.organization_id IS NOT DISTINCT FROM NEW.organization_id)))
            OR (record->>'source_entity_type'<>'repository_fragment' AND EXISTS (
              SELECT 1 FROM core_entity entity WHERE entity.id::text=record->>'source_entity_id'
                AND entity.tenant_id=NEW.tenant_id AND entity.workspace_id=NEW.workspace_id
                AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
                AND entity.entity_type=record->>'source_entity_type' AND entity.archived_at IS NULL))
          )
      ) THEN RAISE EXCEPTION 'native key evidence binding scope mismatch' USING ERRCODE='23514'; END IF;
    END IF;
  END IF;
"""

FORWARD_SQL = _evidence.FORWARD_SQL.replace(
    "'tekdocs-repository-publication-evidence/v2'\n    )",
    "'tekdocs-repository-publication-evidence/v2', 'tekdocs-repository-publication-evidence/v3'\n    )",
).replace(
    "  RETURN NEW;\nEND $$;", NATIVE_VALIDATION + "  RETURN NEW;\nEND $$;", 1,
).replace(
    "evidence.manifest->>'format'=\n        'tekdocs-repository-publication-evidence/v2'",
    "evidence.manifest->>'format' IN (\n        'tekdocs-repository-publication-evidence/v2', "
    "'tekdocs-repository-publication-evidence/v3')",
)


def _accept_native(sql: str) -> str:
    return sql.replace(
        "evidence.manifest->>'format'='tekdocs-repository-publication-evidence/v1'",
        "evidence.manifest->>'format' IN ('tekdocs-repository-publication-evidence/v1', "
        "'tekdocs-repository-publication-evidence/v3') AND NOT (evidence.manifest ? 'primary_file')",
    ).replace(
        "evidence.manifest->>'format'='tekdocs-repository-publication-evidence/v2'",
        "evidence.manifest->>'format' IN ('tekdocs-repository-publication-evidence/v2', "
        "'tekdocs-repository-publication-evidence/v3') AND jsonb_typeof(evidence.manifest->'primary_file')='object'",
    )


FORWARD_SQL += _accept_native(_package.PACKAGE_VALIDATOR) + _accept_native(_static.STATIC_VALIDATOR)
REVERSE_SQL = "".join((r"""
ALTER TABLE core_repositorypublicationevidence NO FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM core_repositorypublicationevidence
    WHERE manifest->>'format'='tekdocs-repository-publication-evidence/v3') THEN
    RAISE EXCEPTION 'Retained native key evidence prevents schema rollback' USING ERRCODE='23514';
  END IF;
END $$;
ALTER TABLE core_repositorypublicationevidence FORCE ROW LEVEL SECURITY;
""", _evidence.FORWARD_SQL, _package.PACKAGE_VALIDATOR, _static.STATIC_VALIDATOR))


class Migration(migrations.Migration):
    dependencies = [('core', '0219_native_internal_publication')]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
