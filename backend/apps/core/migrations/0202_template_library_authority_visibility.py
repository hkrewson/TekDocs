"""Expose the approved template root's authority flag without foreign write access."""

from django.db import migrations

FORWARD = r"""
CREATE POLICY core_template_library_authority_select ON core_documentauthority FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND EXISTS (
    SELECT 1 FROM core_document source
    JOIN core_entity owner ON owner.id=source.entity_id
    WHERE source.id=core_documentauthority.content_id
      AND source.tenant_id=core_documentauthority.tenant_id
      AND source.organization_id IS NULL AND source.is_template
      AND source.library_visible AND source.archived_at IS NULL
      AND owner.workspace_id=core_documentauthority.workspace_id
  )
);
"""
REVERSE = "DROP POLICY core_template_library_authority_select ON core_documentauthority;"


class Migration(migrations.Migration):
    dependencies = [("core", "0201_template_library_includes")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
