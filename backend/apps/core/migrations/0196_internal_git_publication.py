"""Preserve v4 guards and admit only current, exact-owner internal Git snapshots."""

from importlib import import_module

from django.db import migrations

V4 = import_module("apps.core.migrations.0125_document_placement_audiences").PUBLICATION_V4_GUARD
V5 = (
    V4.replace(
        "NEW.manifest->>'format' <> 'tekdocs-static-publication/v4'",
        "NEW.manifest->>'format' NOT IN ('tekdocs-static-publication/v4', 'tekdocs-static-publication/v5')",
    )
    .replace(
        "IF jsonb_typeof(NEW.manifest->'placements') <> 'array'",
        "IF NEW.manifest->>'format' = 'tekdocs-static-publication/v4' AND "
        "(jsonb_typeof(NEW.manifest->'placements') <> 'array'",
    )
    .replace(
        "THEN RAISE EXCEPTION 'publication placement audience metadata is invalid'; END IF;",
        ") THEN RAISE EXCEPTION 'publication placement audience metadata is invalid'; END IF;",
    )
    .replace(
        "  RETURN NEW;",
        """
  IF NEW.manifest->>'format' = 'tekdocs-static-publication/v5' THEN
    IF NOT COALESCE(
      NEW.audience = 'msp_internal'
      AND NEW.manifest->'placements' = '[]'::jsonb
      AND NEW.manifest->'key_resolutions' = '[]'::jsonb
      AND NEW.manifest->'attachments' = '[]'::jsonb
      AND NEW.manifest->'entities' = '[]'::jsonb
      AND NEW.manifest->'diagrams' = '[]'::jsonb
      AND NEW.manifest->'git_source'->>'format' = 'tekdocs.git-dependencies/v1'
      AND NEW.manifest->'git_source'->>'content_id' = NEW.document_id::text
      AND NEW.manifest->'git_source'->>'audience' = NEW.audience
      AND NEW.manifest->'git_source'->>'markdown_sha256' =
          encode(sha256(convert_to(NEW.canonical_markdown, 'UTF8')), 'hex')
      AND jsonb_typeof(NEW.manifest->'git_source'->'sources') = 'array'
      AND jsonb_array_length(NEW.manifest->'git_source'->'sources') = 2
      AND NEW.manifest->'git_source'->'sources'->0->>'id' = NEW.document_id::text
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') item
        WHERE (item->>'commit') IS DISTINCT FROM (NEW.manifest->'git_source'->>'accepted_commit')
          OR NOT COALESCE(item->>'source_sha256' ~ '^[0-9a-f]{64}$', false)
          OR NOT COALESCE(item->>'blob' ~ '^([0-9a-f]{40}|[0-9a-f]{64})$', false)
      )
      AND jsonb_array_length(NEW.manifest->'artifacts') = 1
      AND NEW.manifest->'artifacts'->0->>'kind' = 'pdf'
      AND EXISTS (
        SELECT 1 FROM core_documentplacement p JOIN core_block b ON b.id = p.block_id
        WHERE p.document_id = NEW.document_id AND b.source_document_id = NEW.document_id
          AND p.parent_id IS NULL
          AND b.id::text = NEW.manifest->'git_source'->'sources'->1->>'id'
          AND (SELECT count(*) FROM core_documentplacement p2 WHERE p2.document_id = NEW.document_id) = 1
      )
      AND EXISTS (
        SELECT 1 FROM core_workspacerepository r
        JOIN core_repositorycommit c ON c.id = r.accepted_commit_id
        JOIN core_document d ON d.id = NEW.document_id
        JOIN core_documentauthority a ON a.workspace_id = r.workspace_id AND a.content_id = d.id
        JOIN core_entity e ON e.id = d.entity_id
        WHERE r.id::text = NEW.manifest->'git_source'->>'repository_id'
          AND r.workspace_id::text = NEW.manifest->'git_source'->>'workspace_id'
          AND r.workspace_id = e.workspace_id AND r.tenant_id = NEW.tenant_id
          AND r.indexed_commit_id = r.accepted_commit_id
          AND c.object_id = NEW.manifest->'git_source'->>'accepted_commit'
          AND a.authority = 'repository'
      ), false)
    THEN RAISE EXCEPTION 'internal Git publication source is invalid'; END IF;
  END IF;
  RETURN NEW;
""",
    )
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(V5)


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(V4)


class Migration(migrations.Migration):
    dependencies = [("core", "0195_retained_asset_supplier_anchor")]
    operations = [migrations.RunPython(install, reverse)]
