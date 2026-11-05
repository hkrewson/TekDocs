"""Separate ordinary shared MSP sources from enrolled template identities."""

from importlib import import_module

from django.db import migrations, models

PREVIOUS = import_module("apps.core.migrations.0201_template_library_includes").FORWARD
ELIGIBILITY = r"""
CREATE FUNCTION tekdocs_shared_library_placement_allowed(row_tenant uuid, placement_uuid uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM core_documentplacement p
    JOIN core_document destination ON destination.id=p.document_id
    JOIN core_block b ON b.id=p.block_id
    JOIN core_document source ON source.id=b.source_document_id
    WHERE p.id=placement_uuid AND p.tenant_id=row_tenant
      AND destination.tenant_id=row_tenant AND destination.organization_id=p.organization_id
      AND destination.organization_id IS NOT NULL AND destination.archived_at IS NULL
      AND b.tenant_id=row_tenant AND b.organization_id IS NULL AND b.archived_at IS NULL
      AND source.tenant_id=row_tenant AND source.organization_id IS NULL AND source.archived_at IS NULL
      AND ((source.library_visible AND b.library_visible) OR EXISTS (
        SELECT 1 FROM core_documentplacement primary_source
        JOIN core_documentationlistingreference listing ON listing.document_id=primary_source.document_id
        WHERE primary_source.block_id=b.id AND primary_source.parent_id IS NULL AND primary_source.position=0
          AND listing.tenant_id=row_tenant AND listing.organization_id=destination.organization_id
          AND listing.archived_at IS NULL
      ))
      AND NOT EXISTS (
        SELECT 1 FROM core_documenttemplateenrollment enrollment
        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(enrollment.placement_map)='array'
          THEN enrollment.placement_map ELSE '[]'::jsonb END) mapped
        WHERE enrollment.tenant_id=row_tenant AND enrollment.destination_document_id=destination.id
          AND mapped->>'destination_placement_id'=p.id::text AND mapped->>'mode' IN ('live', 'pinned')
      )
  )
$$;
REVOKE ALL ON FUNCTION tekdocs_shared_library_placement_allowed(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_shared_library_placement_allowed(uuid, uuid) TO tekdocs_runtime;
"""
ORDINARY = r"""
  IF NEW.library_source_id IS NOT NULL THEN
    IF NEW.target_id IS NOT NULL OR NOT EXISTS (
      SELECT 1 FROM core_document source_document
      JOIN core_entity owner ON owner.id=source_document.entity_id
      JOIN core_block b ON b.source_document_id=source_document.id AND b.id=NEW.target_content_id
      JOIN core_documentplacement p ON p.block_id=b.id
      JOIN core_document destination ON destination.id=p.document_id
      JOIN core_entity destination_owner ON destination_owner.id=destination.entity_id
      JOIN core_workspacerepository library ON library.workspace_id=owner.workspace_id
      JOIN core_repositorycommit selected ON selected.repository_id=library.id
        AND selected.object_id=NEW.resolved_object_id
      JOIN core_contentnode caller ON caller.id=NEW.source_id
      LEFT JOIN core_documentplacement parent ON parent.id=p.parent_id AND parent.document_id=destination.id
      LEFT JOIN core_block parent_block ON parent_block.id=parent.block_id
      WHERE source_document.id=NEW.library_source_id AND source_document.tenant_id=NEW.tenant_id
        AND source_document.organization_id IS NULL AND source_document.archived_at IS NULL
        AND tekdocs_shared_library_placement_allowed(NEW.tenant_id, p.id)
        AND b.tenant_id=NEW.tenant_id AND b.organization_id IS NULL
        AND b.archived_at IS NULL
        AND p.tenant_id=NEW.tenant_id AND p.organization_id=NEW.organization_id
        AND destination.tenant_id=NEW.tenant_id AND destination.organization_id=NEW.organization_id
        AND destination.archived_at IS NULL AND destination_owner.workspace_id=NEW.workspace_id
        AND caller.workspace_id=NEW.workspace_id
        AND ((p.parent_id IS NULL AND caller.content_id=destination.id) OR
          (parent_block.source_document_id=destination.id AND caller.content_id=parent.block_id))
        AND p.resolution_mode=NEW.resolution_mode AND p.audience_profile=NEW.audience_profile
        AND p.position=NEW.ordinal
        AND (NEW.resolution_mode<>'pinned' OR p.pinned_revision_id=NEW.library_revision_id)
        AND library.tenant_id=NEW.tenant_id AND library.lifecycle_state='active'
        AND library.workspace_id=NEW.library_workspace_id AND library.workspace_id<>NEW.workspace_id
        AND library.indexed_commit_id=library.accepted_commit_id AND selected.tenant_id=NEW.tenant_id
        AND (NEW.resolution_mode<>'live' OR selected.id=library.accepted_commit_id)
        AND (NEW.resolution_mode<>'pinned' OR NEW.pinned_object_id=NEW.resolved_object_id)
    ) THEN RAISE EXCEPTION 'ordinary library include scope mismatch' USING ERRCODE='23514'; END IF;
    RETURN NEW;
  END IF;
"""
FORWARD = PREVIOUS.replace(
    "  IF NEW.library_workspace_id IS NOT NULL THEN",
    ORDINARY + "\n  IF NEW.library_workspace_id IS NOT NULL THEN", 1,
).replace(
    "AND placement.audience_profile=NEW.audience_profile",
    "AND placement.audience_profile=NEW.audience_profile AND placement.position=NEW.ordinal",
)
POLICY = r"""
CREATE POLICY core_shared_library_document_select ON core_document FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND NOT is_template AND library_visible AND archived_at IS NULL
);
CREATE POLICY core_shared_library_block_select ON core_block FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND library_visible AND archived_at IS NULL AND EXISTS (
    SELECT 1 FROM core_document source WHERE source.id=core_block.source_document_id
      AND source.tenant_id=core_block.tenant_id AND source.organization_id IS NULL
      AND NOT source.is_template AND source.library_visible AND source.archived_at IS NULL
  )
);
CREATE POLICY core_shared_library_authority_select ON core_documentauthority FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND EXISTS (
    SELECT 1 FROM core_document source JOIN core_entity owner ON owner.id=source.entity_id
    WHERE source.id=core_documentauthority.content_id AND source.tenant_id=core_documentauthority.tenant_id
      AND source.organization_id IS NULL AND source.archived_at IS NULL
      AND (source.library_visible OR EXISTS (
        SELECT 1 FROM core_documentationlistingreference listing
        WHERE listing.document_id=source.id AND listing.tenant_id=source.tenant_id
          AND listing.organization_id=tekdocs_current_organization_id() AND listing.archived_at IS NULL
      ))
      AND owner.workspace_id=core_documentauthority.workspace_id
  )
);
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0213_repeated_git_publication")]
    operations = [
        migrations.AddField(model_name="contentinclude", name="library_source_id",
                            field=models.UUIDField(blank=True, null=True)),
        migrations.RemoveConstraint(model_name="contentinclude", name="content_include_library_identity_pair"),
        migrations.AddConstraint(model_name="contentinclude", constraint=models.CheckConstraint(
            condition=(
                models.Q(library_workspace_id__isnull=True, library_revision_id__isnull=True,
                         library_source_id__isnull=True)
                | models.Q(library_workspace_id__isnull=False, library_revision_id__isnull=False,
                           library_source_id__isnull=True)
                | models.Q(library_workspace_id__isnull=False, library_source_id__isnull=False,
                           library_revision_id__isnull=True, resolution_mode="live")
                | models.Q(library_workspace_id__isnull=False, library_source_id__isnull=False,
                           library_revision_id__isnull=False, resolution_mode="pinned")
            ), name="content_include_library_identity_pair")),
        migrations.RunSQL(ELIGIBILITY, "DROP FUNCTION tekdocs_shared_library_placement_allowed(uuid, uuid);"),
        migrations.RunSQL(FORWARD, PREVIOUS),
        migrations.RunSQL(POLICY, """
            DROP POLICY core_shared_library_authority_select ON core_documentauthority;
            DROP POLICY core_shared_library_block_select ON core_block;
            DROP POLICY core_shared_library_document_select ON core_document;
        """),
    ]
