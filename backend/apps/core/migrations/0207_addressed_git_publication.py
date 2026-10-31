"""Add addressed Git snapshots without changing any signed v1-v8 contract."""

from importlib import import_module

from django.db import migrations

prior = import_module("apps.core.migrations.0204_template_git_publication")
V8 = prior.V8


def addressed_branch(branch, version, source_format):
    return (
        branch.replace(
            f"IF NEW.manifest->>'format' = 'tekdocs-static-publication/{version}' THEN",
            "IF NEW.manifest->>'format' = 'tekdocs-static-publication/v9' "
            f"AND NEW.manifest->'git_source'->>'format' = '{source_format}' THEN",
            1,
        )
        .replace("      AND NEW.manifest->'key_resolutions' = '[]'::jsonb\n", "")
        .replace("      AND NEW.manifest->'entities' = '[]'::jsonb\n", "")
        .replace("NEW.canonical_markdown", "(NEW.manifest->>'authored_markdown')")
    )


ADDRESS_GUARD = r"""
  IF NEW.manifest->>'format' = 'tekdocs-static-publication/v9' THEN
    IF NOT COALESCE(
      NEW.manifest->'git_source'->>'format' IN ('tekdocs.git-dependencies/v1', 'tekdocs.git-dependencies/v2')
      AND jsonb_typeof(NEW.manifest->'authored_markdown') = 'string'
      AND octet_length(NEW.manifest->>'authored_markdown') <= 2097152
      AND octet_length(NEW.canonical_markdown) <= 2097152
      AND jsonb_typeof(NEW.manifest->'key_bindings') = 'object'
      AND jsonb_typeof(NEW.manifest->'entities') = 'array'
      AND jsonb_array_length(NEW.manifest->'entities') <= 200
      AND (NEW.manifest->'key_snapshot' <> 'null'::jsonb OR NEW.manifest->'entities' <> '[]'::jsonb)
      AND EXISTS (
        SELECT 1 FROM core_document d JOIN core_entity owner ON owner.id=d.entity_id
        JOIN core_contentnode n ON n.workspace_id=owner.workspace_id AND n.content_id=d.id
        WHERE d.id=NEW.document_id
          AND NEW.manifest->'key_bindings' = COALESCE(n.frontmatter->'key_bindings', '{}'::jsonb)
          AND NEW.manifest->'key_bindings' = COALESCE((
            SELECT jsonb_object_agg(b.name, b.target_entity_id::text ORDER BY b.name)
            FROM core_documentkeybinding b WHERE b.document_id=d.id AND b.archived_at IS NULL
          ), '{}'::jsonb)
      )
      AND (
        (NEW.manifest->'key_snapshot' = 'null'::jsonb
          AND NEW.manifest->'key_resolutions' = '[]'::jsonb
          AND NEW.canonical_markdown=NEW.manifest->>'authored_markdown')
        OR (jsonb_typeof(NEW.manifest->'key_snapshot')='object'
          AND (SELECT count(*) FROM jsonb_object_keys(NEW.manifest->'key_snapshot'))=3
          AND NEW.manifest->'key_snapshot' ?& ARRAY['markdown', 'sha256', 'records']
          AND NEW.manifest->'key_snapshot'->>'markdown'=NEW.canonical_markdown
          AND NEW.manifest->'key_snapshot'->>'sha256'=
              encode(sha256(convert_to(NEW.canonical_markdown, 'UTF8')), 'hex')
          AND NEW.manifest->'key_snapshot'->'records'=NEW.manifest->'key_resolutions'
          AND jsonb_array_length(NEW.manifest->'key_resolutions') BETWEEN 1 AND 200
        )
      )
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'key_resolutions') item
        WHERE item->>'kind' <> 'field' OR NOT EXISTS (
          SELECT 1 FROM core_documentkeybinding b JOIN core_entity target ON target.id=b.target_entity_id
          JOIN core_document d ON d.id=b.document_id JOIN core_entity owner ON owner.id=d.entity_id
          WHERE b.document_id=NEW.document_id AND b.archived_at IS NULL
            AND b.tenant_id=NEW.tenant_id AND b.workspace_id=owner.workspace_id
            AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND b.name=split_part(item->>'expression', '.', 1)
            AND item->>'expression' ~ '^[a-z][a-z0-9_]{0,39}(\.[a-z][a-z0-9_]*){1,3}$'
            AND target.id::text=item->>'source_entity_id' AND target.archived_at IS NULL
            AND target.tenant_id=NEW.tenant_id AND target.workspace_id=owner.workspace_id
            AND target.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND target.entity_type=item->>'source_entity_type'
        )
      )
      AND (SELECT count(DISTINCT card->>'id') FROM jsonb_array_elements(NEW.manifest->'entities') card)
          = jsonb_array_length(NEW.manifest->'entities')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'entities') card
        WHERE jsonb_typeof(card)<>'object'
          OR (SELECT count(*) FROM jsonb_object_keys(card))<>4
          OR NOT card ?& ARRAY['id', 'display_name', 'entity_type', 'workspace_label']
          OR jsonb_typeof(card->'workspace_label')<>'string' OR card->>'workspace_label'=''
          OR NOT EXISTS (
            SELECT 1 FROM core_entity target JOIN core_document d ON d.id=NEW.document_id
            JOIN core_entity owner ON owner.id=d.entity_id
            WHERE target.id::text=card->>'id' AND target.tenant_id=NEW.tenant_id
              AND target.workspace_id=owner.workspace_id AND target.archived_at IS NULL
              AND target.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND target.entity_type=card->>'entity_type' AND target.display_name=card->>'display_name'
          )
      ), false)
    THEN RAISE EXCEPTION 'addressed Git publication dependency proof is invalid'; END IF;
  END IF;
"""

V9 = (
    V8.replace(
        "'tekdocs-static-publication/v8')", "'tekdocs-static-publication/v8', 'tekdocs-static-publication/v9')", 1
    )
    .replace(
        "IN ('tekdocs-static-publication/v7', 'tekdocs-static-publication/v8')",
        "IN ('tekdocs-static-publication/v7', 'tekdocs-static-publication/v8', 'tekdocs-static-publication/v9')",
    )
    .replace(
        "  RETURN NEW;",
        ADDRESS_GUARD
        + addressed_branch(prior._BRANCH, "v7", "tekdocs.git-dependencies/v1")
        + addressed_branch(prior.V8_BRANCH, "v8", "tekdocs.git-dependencies/v2")
        + "  RETURN NEW;",
    )
)


class Migration(migrations.Migration):
    dependencies = [("core", "0206_controlled_template_graph")]
    operations = [migrations.RunSQL(V9, V8)]
