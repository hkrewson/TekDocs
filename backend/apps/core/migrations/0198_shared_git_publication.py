"""Admit exact ordered shared-source snapshots while preserving prior guards."""

from importlib import import_module

from django.db import migrations

V6 = import_module("apps.core.migrations.0197_file_git_publication").V6
V7 = (
    V6.replace(
        "'tekdocs-static-publication/v6')",
        "'tekdocs-static-publication/v6', 'tekdocs-static-publication/v7')",
        1,
    )
    .replace(
        "IF NEW.manifest->>'format' = 'tekdocs-static-publication/v6' THEN",
        "IF NEW.manifest->>'format' = 'tekdocs-static-publication/v6' OR "
        "(NEW.manifest->>'format' = 'tekdocs-static-publication/v7' "
        "AND NEW.manifest->'managed_files' <> '[]'::jsonb) THEN",
    )
    .replace(
        "  RETURN NEW;",
        r"""
  IF NEW.manifest->>'format' = 'tekdocs-static-publication/v7' THEN
    IF NOT COALESCE(
      NEW.audience = 'msp_internal' AND NEW.retention = 'permanent'
      AND NEW.manifest->'placements' = '[]'::jsonb
      AND NEW.manifest->'key_resolutions' = '[]'::jsonb
      AND NEW.manifest->'entities' = '[]'::jsonb
      AND NEW.manifest->'diagrams' = '[]'::jsonb
      AND jsonb_typeof(NEW.manifest->'managed_files') = 'array'
      AND (NEW.manifest->'managed_files' <> '[]'::jsonb OR (
        NEW.manifest->'attachments' = '[]'::jsonb
        AND jsonb_array_length(NEW.manifest->'artifacts') = 1
        AND NEW.manifest->'artifacts'->0->>'kind' = 'pdf'
        AND NOT EXISTS (SELECT 1 FROM core_documentattachment f
                        WHERE f.document_id=NEW.document_id AND f.archived_at IS NULL)
      ))
      AND NEW.manifest->'git_source'->>'format' = 'tekdocs.git-dependencies/v1'
      AND NEW.manifest->'git_source'->>'content_id' = NEW.document_id::text
      AND NEW.manifest->'git_source'->>'audience' = NEW.audience
      AND NEW.manifest->'git_source'->>'markdown_sha256' =
          encode(sha256(convert_to(NEW.canonical_markdown, 'UTF8')), 'hex')
      AND jsonb_typeof(NEW.manifest->'git_source'->'sources') = 'array'
      AND jsonb_array_length(NEW.manifest->'git_source'->'sources') BETWEEN 2 AND 512
      AND NEW.manifest->'git_source'->'sources'->0->>'id' = NEW.document_id::text
      AND NEW.manifest->'git_source'->'sources'->0->>'mode' = 'root'
      AND NEW.manifest->'git_source'->'sources'->0->'ordinal_path' = '[]'::jsonb
      AND NEW.manifest->'git_source'->'sources'->0->>'commit' =
          NEW.manifest->'git_source'->>'accepted_commit'
      AND (SELECT count(DISTINCT s->>'id')
           FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s)
          = jsonb_array_length(NEW.manifest->'git_source'->'sources')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
        WHERE NOT COALESCE(s->>'source_sha256' ~ '^[0-9a-f]{64}$', false)
           OR NOT COALESCE(s->>'blob' ~ '^([0-9a-f]{40}|[0-9a-f]{64})$', false)
      )
      AND EXISTS (
        SELECT 1 FROM core_document d JOIN core_entity e ON e.id=d.entity_id
        JOIN core_workspacerepository r ON r.workspace_id=e.workspace_id
        JOIN core_repositorycommit c ON c.id=r.accepted_commit_id
        JOIN core_contentnode n ON n.repository_id=r.id AND n.content_id=d.id
        JOIN core_documentauthority a ON a.workspace_id=r.workspace_id AND a.content_id=d.id
        WHERE d.id=NEW.document_id AND d.tenant_id=NEW.tenant_id AND NOT d.is_template
          AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
          AND r.id::text=NEW.manifest->'git_source'->>'repository_id'
          AND r.workspace_id::text=NEW.manifest->'git_source'->>'workspace_id'
          AND r.indexed_commit_id=r.accepted_commit_id AND n.indexed_commit_id=r.accepted_commit_id
          AND a.authority='repository' AND c.object_id=NEW.manifest->'git_source'->>'accepted_commit'
          AND n.title=NEW.title
          AND NEW.manifest->'git_source'->>'root_title'=NEW.title
          AND NEW.manifest->'git_source'->'sources'->0->>'path'=n.source_path
          AND NEW.manifest->'git_source'->'sources'->0->>'content_digest'=n.content_digest
          AND n.composition_variants->'msp_internal'->>'digest' =
              NEW.manifest->'git_source'->>'composition_digest'
          AND n.composition_variants->'msp_internal'->>'markdown'=NEW.canonical_markdown
          AND (SELECT jsonb_agg((item - 'depth' - 'title') ORDER BY ordinal)
               FROM jsonb_array_elements(n.composition_variants->'msp_internal'->'manifest')
                    WITH ORDINALITY entry(item, ordinal)) = (
            SELECT jsonb_agg(jsonb_build_object(
              'id', s->'id', 'commit', s->'commit', 'digest', s->'content_digest',
              'mode', s->'mode', 'audience', s->'audience', 'ordinal_path', s->'ordinal_path'
            ) ORDER BY ordinal)
            FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources')
                 WITH ORDINALITY entry(s, ordinal) WHERE ordinal > 1
          )
          AND (SELECT count(*) FROM core_documentplacement p WHERE p.document_id=d.id) + 1
              = jsonb_array_length(NEW.manifest->'git_source'->'sources')
          AND EXISTS (SELECT 1 FROM core_documentplacement p JOIN core_block b ON b.id=p.block_id
                      WHERE p.document_id=d.id AND b.source_document_id=d.id)
          AND NOT EXISTS (
            SELECT 1 FROM core_documentplacement p JOIN core_block b ON b.id=p.block_id
            JOIN core_document owner ON owner.id=b.source_document_id
            JOIN core_entity oe ON oe.id=owner.entity_id
            LEFT JOIN core_documentauthority ba ON ba.workspace_id=r.workspace_id AND ba.content_id=b.id
            WHERE p.document_id=d.id AND (
              p.audience_profile <> 'shared' OR oe.workspace_id <> r.workspace_id
              OR b.tenant_id <> NEW.tenant_id
              OR b.organization_id IS DISTINCT FROM NEW.organization_id
              OR (p.resolution_mode='live' AND ba.authority IS DISTINCT FROM 'repository')
              OR NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
                WHERE s->>'id'=b.id::text AND s->>'mode'=p.resolution_mode
              )
            )
          )
      ), false)
    THEN RAISE EXCEPTION 'shared Git publication source is invalid'; END IF;
  END IF;
  RETURN NEW;
""",
    )
)


class Migration(migrations.Migration):
    dependencies = [("core", "0197_file_git_publication")]
    operations = [migrations.RunSQL(V7, V6)]
