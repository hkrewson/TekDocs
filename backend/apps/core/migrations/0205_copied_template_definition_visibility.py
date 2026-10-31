"""Expose only the immutable definition already copied into a scoped client."""

from django.db import migrations

FORWARD = r"""
CREATE POLICY core_copied_template_definition_select ON core_documenttemplaterevision FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND EXISTS (
    SELECT 1 FROM core_documenttemplateenrollment enrollment
    WHERE enrollment.applied_revision_id=core_documenttemplaterevision.id
      AND enrollment.source_template_id=core_documenttemplaterevision.template_id
      AND enrollment.tenant_id=core_documenttemplaterevision.tenant_id
      AND tekdocs_scope_matches(enrollment.tenant_id, enrollment.organization_id)
      AND jsonb_typeof(enrollment.placement_map)='array'
      AND jsonb_array_length(enrollment.placement_map)>0
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(
          CASE WHEN jsonb_typeof(enrollment.placement_map)='array' THEN enrollment.placement_map ELSE '[]'::jsonb END
        ) mapped WHERE mapped->>'mode' IS DISTINCT FROM 'copy'
      )
  )
);
"""
REVERSE = "DROP POLICY core_copied_template_definition_select ON core_documenttemplaterevision;"


class Migration(migrations.Migration):
    dependencies = [("core", "0204_template_git_publication")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
