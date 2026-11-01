"""Bind Git snapshot guards to the selected audience, preserving prior custody."""

from importlib import import_module

from django.db import migrations

PRIOR = import_module("apps.core.migrations.0211_diagram_git_publication").V11
CLIENT = PRIOR.replace(
    "NEW.audience = 'msp_internal' AND NEW.retention = 'permanent'",
    "NEW.audience IN ('msp_internal', 'client_visible') "
    "AND (NEW.audience <> 'client_visible' OR NEW.organization_id IS NOT NULL) "
    "AND NEW.retention IN ('permanent', 'review_on')",
).replace("n.composition_variants->'msp_internal'", "n.composition_variants->(NEW.audience)")
# A certificate contains the selected composition only. Excluded placements stay
# in retained authoring state and never enter the signed dependency descriptors.
CLIENT = CLIENT.replace(
    "WHERE p.document_id=d.id) + 1",
    "WHERE p.document_id=d.id AND p.audience_profile IN ('shared', NEW.audience)) + 1",
).replace(
    "WHERE p.document_id=d.id AND (",
    "WHERE p.document_id=d.id AND p.audience_profile IN ('shared', NEW.audience) AND (",
).replace("p.audience_profile <> 'shared' OR", "p.audience_profile NOT IN ('shared', NEW.audience) OR")


# A filtered snapshot retains the audience's referenced ordinary files and every
# primary-file version. Unfiltered snapshots keep the prior complete-file rule.
_FILE_COUNT = """AND (SELECT count(*) FROM core_documentattachment a WHERE a.document_id = NEW.document_id
           AND a.archived_at IS NULL) = jsonb_array_length(checked_manifest->'managed_files')"""
CLIENT = CLIENT.replace(
    _FILE_COUNT,
    "AND (checked_manifest->'git_source'->'audience_filtered'='true'::jsonb OR ("
    + _FILE_COUNT.removeprefix("AND ") + "))",
).replace(
    """AND NOT EXISTS (SELECT 1 FROM core_documentattachment f
                        WHERE f.document_id=NEW.document_id AND f.archived_at IS NULL)""",
    """AND (checked_manifest->'git_source'->'audience_filtered'='true'::jsonb OR
        NOT EXISTS (SELECT 1 FROM core_documentattachment f
                        WHERE f.document_id=NEW.document_id AND f.archived_at IS NULL))""",
)
AUDIENCE_GUARD = """
  IF checked_manifest->>'format' IN (
    'tekdocs-static-publication/v5', 'tekdocs-static-publication/v6',
    'tekdocs-static-publication/v7', 'tekdocs-static-publication/v8',
    'tekdocs-static-publication/v9', 'tekdocs-static-publication/v10'
  ) THEN
    IF NOT COALESCE(
      checked_manifest->'git_source'->'sources'->0->>'audience'=NEW.audience
      AND (NOT (checked_manifest->'git_source' ? 'audience_filtered')
           OR checked_manifest->'git_source'->'audience_filtered'='true'::jsonb)
      AND (NOT (NEW.audience='client_visible' OR EXISTS (
        SELECT 1 FROM core_documentplacement p WHERE p.document_id=NEW.document_id
          AND p.audience_profile<>'shared'
      )) OR (
        checked_manifest->'git_source'->'audience_filtered'='true'::jsonb
        AND checked_manifest->>'format' NOT IN ('tekdocs-static-publication/v5', 'tekdocs-static-publication/v6')
      ))
      AND NOT EXISTS (
        SELECT 1 FROM core_documentattachment a
        WHERE a.document_id=NEW.document_id AND a.archived_at IS NULL AND a.purpose='primary_file'
          AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(checked_manifest->'managed_files') f
                          WHERE f->>'id'=a.entity_id::text)
      ), false)
    THEN RAISE EXCEPTION 'Git publication audience proof is invalid'; END IF;
  END IF;
"""
CLIENT = CLIENT.replace("  RETURN NEW;", AUDIENCE_GUARD + "  RETURN NEW;")


# The signed map contains only keys used in the selected edition. Both the
# accepted frontmatter and live owner bindings must attest those exact targets.
CLIENT = CLIENT.replace(
    "checked_manifest->'key_bindings' = COALESCE(n.frontmatter->'key_bindings', '{}'::jsonb)",
    """checked_manifest->'key_bindings' = CASE
      WHEN checked_manifest->'git_source'->'audience_filtered'='true'::jsonb THEN COALESCE((
        SELECT jsonb_object_agg(k, v) FROM jsonb_each(n.frontmatter->'key_bindings') binding(k, v)
        WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(checked_manifest->'key_resolutions') item
                      WHERE split_part(item->>'expression', '.', 1)=k)
      ), '{}'::jsonb) ELSE COALESCE(n.frontmatter->'key_bindings', '{}'::jsonb) END""",
).replace(
    "FROM core_documentkeybinding b WHERE b.document_id=d.id AND b.archived_at IS NULL",
    """FROM core_documentkeybinding b WHERE b.document_id=d.id AND b.archived_at IS NULL
      AND (checked_manifest->'git_source'->'audience_filtered' IS DISTINCT FROM 'true'::jsonb OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(checked_manifest->'key_resolutions') item
        WHERE split_part(item->>'expression', '.', 1)=b.name
      ))""",
).replace(
    "AND target.entity_type=item->>'source_entity_type'",
    "AND target.entity_type=item->>'source_entity_type' "
    "AND (NEW.audience<>'client_visible' OR target.visibility='client_visible')",
).replace(
    "AND target.entity_type=card->>'entity_type' AND target.display_name=card->>'display_name'",
    "AND target.entity_type=card->>'entity_type' AND target.display_name=card->>'display_name' "
    "AND (NEW.audience<>'client_visible' OR target.visibility='client_visible')",
)


class Migration(migrations.Migration):
    dependencies = [("core", "0211_diagram_git_publication")]
    operations = [migrations.RunSQL(CLIENT, PRIOR)]
