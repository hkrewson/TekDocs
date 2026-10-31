"""Add Git content-substitution proof without changing signed v1-v9 formats."""

from importlib import import_module

from django.db import migrations

prior = import_module("apps.core.migrations.0207_addressed_git_publication")

CONTENT_GUARD = r"""
  IF NEW.manifest->>'format'='tekdocs-static-publication/v10' THEN
    IF NOT COALESCE(
      EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.manifest->'key_resolutions') item
              WHERE item->>'kind'='content')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'key_resolutions') item
        WHERE item->>'kind'='content' AND NOT COALESCE(
          item->>'source_entity_type'='document_block'
          AND item->'source_revision_id'='null'::jsonb
          AND item->'source_revision_number'='null'::jsonb
          AND jsonb_array_length(item->'dependency_chain') BETWEEN 1 AND 31
          AND item->'dependency_chain'->>-1=item->>'source_entity_id'
          AND jsonb_typeof(item->'git_source')='object'
          AND (SELECT count(*) FROM jsonb_object_keys(item->'git_source'))=8
          AND item->'git_source' ?& ARRAY[
            'content_id', 'workspace_id', 'repository_id', 'commit', 'object_format', 'blob', 'path', 'source'
          ]
          AND item->'git_source'->>'workspace_id'=NEW.manifest->'git_source'->>'workspace_id'
          AND item->'git_source'->>'repository_id'=NEW.manifest->'git_source'->>'repository_id'
          AND item->'git_source'->>'commit'=NEW.manifest->'git_source'->>'accepted_commit'
          AND item->'git_source'->>'object_format'=NEW.manifest->'git_source'->>'object_format'
          AND item->'git_source'->>'blob' ~ CASE
            WHEN item->'git_source'->>'object_format'='sha1' THEN '^[0-9a-f]{40}$' ELSE '^[0-9a-f]{64}$' END
          AND jsonb_typeof(item->'git_source'->'source')='string'
          AND octet_length(item->'git_source'->>'source')<=2097152
          AND item->>'source_fingerprint'=encode(sha256(convert_to(item->>'value', 'UTF8')), 'hex')
          AND EXISTS (
            SELECT 1 FROM core_block b JOIN core_entity e ON e.id=b.entity_id
            JOIN core_contentnode n ON n.content_id=b.id AND n.workspace_id=e.workspace_id
            JOIN core_documentauthority a ON a.content_id=b.id AND a.workspace_id=e.workspace_id
            WHERE b.entity_id::text=item->>'source_entity_id' AND b.tenant_id=NEW.tenant_id
              AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id AND b.archived_at IS NULL
              AND b.id::text=item->'git_source'->>'content_id' AND a.authority='repository'
              AND n.kind='fragment' AND n.markdown=item->>'value'
              AND n.source_path=item->'git_source'->>'path'
              AND n.source_path='fragments/'||b.id::text||'.md'
              AND n.repository_id::text=item->'git_source'->>'repository_id'
              AND n.indexed_commit_id IN (
                SELECT id FROM core_repositorycommit WHERE object_id=item->'git_source'->>'commit'
                  AND repository_id=n.repository_id
              )
          ), false)
      ), false)
    THEN RAISE EXCEPTION 'Git content-key source proof is invalid'; END IF;
  END IF;
"""

ADDRESS_GUARD = prior.ADDRESS_GUARD.replace("tekdocs-static-publication/v9", "tekdocs-static-publication/v10").replace(
    "WHERE item->>'kind' <> 'field' OR NOT EXISTS (",
    "WHERE item->>'kind' NOT IN ('field', 'content') OR NOT EXISTS (",
)
V10 = (
    prior.V9.replace(
        "'tekdocs-static-publication/v9')", "'tekdocs-static-publication/v9', 'tekdocs-static-publication/v10')",
    )
    .replace(
        "(SELECT count(*) FROM jsonb_object_keys(item)) <> 11",
        "(SELECT count(*) FROM jsonb_object_keys(item)) <> CASE WHEN "
        "NEW.manifest->>'format'='tekdocs-static-publication/v10' AND item->>'kind'='content' THEN 12 ELSE 11 END",
    )
    .replace(
        "item->>'kind' = 'content' AND (",
        "item->>'kind' = 'content' AND NEW.manifest->>'format'<>'tekdocs-static-publication/v10' AND (",
    )
    .replace(
        "  RETURN NEW;",
        ADDRESS_GUARD + CONTENT_GUARD
        + prior.addressed_branch(prior.prior._BRANCH, "v7", "tekdocs.git-dependencies/v1").replace(
            "tekdocs-static-publication/v9", "tekdocs-static-publication/v10",
        )
        + prior.addressed_branch(prior.prior.V8_BRANCH, "v8", "tekdocs.git-dependencies/v2").replace(
            "tekdocs-static-publication/v9", "tekdocs-static-publication/v10",
        )
        + "  RETURN NEW;",
    )
)


class Migration(migrations.Migration):
    dependencies = [("core", "0208_promoted_key_binding_guard")]
    operations = [migrations.RunSQL(V10, prior.V9)]
