"""Admit truthful ordinary-library custody only under the new v13 envelope."""

from importlib import import_module

from django.db import migrations

previous = import_module("apps.core.migrations.0213_repeated_git_publication")
template = import_module("apps.core.migrations.0204_template_git_publication")

ORDINARY_EDGE = template.LIBRARY_EDGE.replace(
    "SELECT 1 FROM core_documenttemplateenrollment enrollment\n"
    "  JOIN core_document source_template ON source_template.id=enrollment.source_template_id",
    "SELECT 1 FROM core_document source_template",
).replace(
    "JOIN core_documenttemplaterevision version ON version.id=enrollment.applied_revision_id",
    "JOIN core_blockrevision version ON version.block_id=b.id "
    "AND version.id=COALESCE(p.pinned_revision_id, b.current_revision_id)",
).replace(
    "  CROSS JOIN LATERAL jsonb_array_elements(enrollment.placement_map) mapped\n", "",
).replace(
    "WHERE enrollment.destination_document_id=d.id AND enrollment.tenant_id=NEW.tenant_id\n"
    "    AND enrollment.organization_id IS NOT DISTINCT FROM NEW.organization_id AND enrollment.archived_at IS NULL",
    "WHERE NEW.manifest->>'format'='tekdocs-static-publication/v13'",
).replace(
    "AND source_template.organization_id IS NULL AND source_template.is_template\n"
    "    AND source_template.library_visible AND source_template.archived_at IS NULL AND b.library_visible",
    "AND source_template.organization_id IS NULL AND source_template.archived_at IS NULL\n"
    "    AND tekdocs_shared_library_placement_allowed(NEW.tenant_id, p.id)",
).replace(
    "AND edge.library_workspace_id=library.workspace_id AND edge.library_revision_id=version.id",
    "AND edge.library_workspace_id=library.workspace_id AND edge.library_source_id=source_template.id\n"
    "    AND (p.resolution_mode<>'pinned' OR edge.library_revision_id=version.id)",
).replace(
    "proof->>'template_revision'=version.id::text", "proof->>'block_revision'=version.id::text",
).replace(
    "proof->>'template_checksum'=version.checksum", "proof->>'block_checksum'=version.checksum\n"
    "    AND proof->>'library_source'=source_template.id::text",
).replace(
    "    AND mapped->>'source_block_id'=b.entity_id::text\n"
    "    AND mapped->>'destination_placement_id'=p.id::text AND mapped->>'mode'=p.resolution_mode\n"
    "    AND (p.resolution_mode<>'pinned' OR p.pinned_revision_id::text=mapped->>'applied_revision_id')\n", "",
).replace("'template-snapshots/'", "'shared-snapshots/'")

LIBRARY_VIEW = r"""
  IF NEW.manifest ? 'ordinary_library' THEN RAISE EXCEPTION 'reserved publication validation marker'; END IF;
  IF NEW.manifest->>'format'='tekdocs-static-publication/v13' THEN
    IF NOT COALESCE(
      NEW.manifest->>'library_format' IN (
        'tekdocs-static-publication/v7', 'tekdocs-static-publication/v8',
        'tekdocs-static-publication/v9', 'tekdocs-static-publication/v10',
        'tekdocs-static-publication/v11', 'tekdocs-static-publication/v12'
      ) AND NEW.manifest->'git_source'->>'format'='tekdocs.git-dependencies/v3'
      AND jsonb_typeof(NEW.manifest->'git_source'->'sources')='array'
      AND jsonb_array_length(NEW.manifest->'git_source'->'sources') BETWEEN 2 AND 512
      AND EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
                  WHERE s ? 'library_source')
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
        WHERE s ? 'library_source' AND NOT COALESCE(
          s->>'library_source' ~ '^[0-9a-f-]{36}$' AND s->>'block_revision' ~ '^[0-9a-f-]{36}$'
          AND s->>'block_checksum' ~ '^[0-9a-f]{64}$' AND s ? 'library_workspace'
          AND NOT (s ? 'template_revision' OR s ? 'template_checksum'), false
        )
      ), false)
    THEN RAISE EXCEPTION 'ordinary library publication proof is invalid'; END IF;
    envelope_manifest := jsonb_set(NEW.manifest, '{git_source,format}', '"tekdocs.git-dependencies/v2"')
      || jsonb_build_object('format', NEW.manifest->'library_format');
  ELSIF EXISTS (
    SELECT 1 FROM jsonb_array_elements(COALESCE(NEW.manifest->'git_source'->'sources', '[]'::jsonb)) s
    WHERE s ? 'library_source'
  ) THEN RAISE EXCEPTION 'historical publication format cannot admit ordinary library proof'; END IF;
"""

# Unwrap v13 before the existing occurrence and diagram layers. Signed bytes
# remain NEW.manifest; every SQL comparison uses the checked local view.
VIEW = previous.OCCURRENCE_VIEW.replace("NEW.manifest", "envelope_manifest").replace(
    "  envelope_manifest := envelope_manifest;",
    "  envelope_manifest := NEW.manifest;\n" + LIBRARY_VIEW, 1,
)
V13 = previous.V12.replace(previous.OCCURRENCE_VIEW, VIEW, 1)
V13 = V13.replace(
    "NEW.manifest->>'format'='tekdocs-static-publication/v12'",
    "(NEW.manifest->>'format'='tekdocs-static-publication/v12' OR "
    "(NEW.manifest->>'format'='tekdocs-static-publication/v13' "
    "AND NEW.manifest->>'library_format'='tekdocs-static-publication/v12'))",
)
V13 = V13.replace(
    template.LIBRARY_EDGE.replace("NEW.manifest", "checked_manifest"),
    "(" + template.LIBRARY_EDGE.replace("NEW.manifest", "checked_manifest")
    + " OR " + ORDINARY_EDGE.replace("NEW.manifest->'git_source'", "checked_manifest->'git_source'") + ")",
)
V13 = V13.replace(
    "'workspace', s->'library_workspace', 'template_revision', s->'template_revision'",
    "'workspace', s->'library_workspace'\n"
    "            ) || CASE WHEN s ? 'library_source' THEN jsonb_build_object(\n"
    "                'library_source', s->'library_source'\n"
    "            ) || CASE WHEN s->>'mode'='pinned' THEN jsonb_build_object(\n"
    "                'block_revision', s->'block_revision'\n"
    "            ) ELSE '{}'::jsonb END ELSE jsonb_build_object(\n"
    "                'template_revision', s->'template_revision'",
).replace(
    "'template_revision', s->'template_revision'\n            ) ELSE '{}'::jsonb END",
    "'template_revision', s->'template_revision'\n            ) END ELSE '{}'::jsonb END",
)


class Migration(migrations.Migration):
    dependencies = [("core", "0214_ordinary_library_includes")]
    operations = [migrations.RunSQL(V13, previous.V12)]
