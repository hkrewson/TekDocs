"""Keep approved foreign library edges distinct from same-Workspace includes."""

from importlib import import_module

from django.db import migrations, models

_PREVIOUS = import_module("apps.core.migrations.0166_file_backed_fragment_composition").FORWARD_SQL
PREVIOUS = _PREVIOUS[
    _PREVIOUS.index("CREATE FUNCTION tekdocs_validate_content_include()") : _PREVIOUS.index(
        "CREATE FUNCTION tekdocs_validate_content_template_source()"
    )
].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)

LIBRARY_BRANCH = r"""
  IF NEW.library_workspace_id IS NOT NULL THEN
    IF NEW.target_id IS NOT NULL THEN
      RAISE EXCEPTION 'library include cannot use a local target' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM core_documenttemplateenrollment enrollment
      JOIN core_document source_template ON source_template.id=enrollment.source_template_id
      JOIN core_entity source_entity ON source_entity.id=source_template.entity_id
      JOIN core_workspace library_workspace ON library_workspace.id=source_entity.workspace_id
      JOIN core_block block ON block.id=NEW.target_content_id AND block.source_document_id=source_template.id
      JOIN core_workspacerepository library_repository ON library_repository.workspace_id=library_workspace.id
      JOIN core_repositorycommit selected_commit ON selected_commit.repository_id=library_repository.id
        AND selected_commit.object_id=NEW.resolved_object_id
      JOIN core_documentplacement placement ON placement.document_id=enrollment.destination_document_id
        AND placement.block_id=block.id AND placement.resolution_mode=NEW.resolution_mode
        AND placement.audience_profile=NEW.audience_profile
      CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(enrollment.placement_map)='array'
          THEN enrollment.placement_map ELSE '[]'::jsonb END
      ) AS mapped(item)
      WHERE EXISTS (
        SELECT 1 FROM core_contentnode caller WHERE caller.id=NEW.source_id
          AND caller.workspace_id=NEW.workspace_id
          AND ((caller.content_id=enrollment.destination_document_id AND placement.parent_id IS NULL) OR EXISTS (
            SELECT 1 FROM core_documentplacement parent
            JOIN core_block owned_parent ON owned_parent.id=parent.block_id
            WHERE parent.id=placement.parent_id AND parent.document_id=enrollment.destination_document_id
              AND owned_parent.source_document_id=enrollment.destination_document_id
              AND owned_parent.id=caller.content_id
          ))
      )
        AND enrollment.tenant_id=NEW.tenant_id AND enrollment.organization_id=NEW.organization_id
        AND NEW.library_revision_id=enrollment.applied_revision_id
        AND source_template.tenant_id=NEW.tenant_id AND block.tenant_id=NEW.tenant_id
        AND library_workspace.tenant_id=NEW.tenant_id AND library_repository.tenant_id=NEW.tenant_id
        AND selected_commit.tenant_id=NEW.tenant_id
        AND library_workspace.id=NEW.library_workspace_id AND library_workspace.organization_id IS NULL
        AND source_template.organization_id IS NULL AND source_template.is_template
        AND source_template.library_visible AND block.library_visible
        AND source_template.archived_at IS NULL AND enrollment.archived_at IS NULL
        AND item->>'mode'=NEW.resolution_mode AND item->>'source_block_id'=block.entity_id::text
        AND item->>'destination_placement_id'=placement.id::text
        AND (NEW.resolution_mode<>'pinned' OR placement.pinned_revision_id::text=item->>'applied_revision_id')
        AND library_repository.lifecycle_state='active'
        AND (NEW.resolution_mode<>'live' OR selected_commit.id=library_repository.accepted_commit_id)
    ) THEN RAISE EXCEPTION 'enrolled library include scope mismatch' USING ERRCODE='23514'; END IF;
    IF NEW.resolution_mode='pinned' AND NEW.pinned_object_id<>NEW.resolved_object_id THEN
      RAISE EXCEPTION 'pinned library include commit mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
"""
FORWARD = PREVIOUS.replace(
    "  IF NEW.target_id IS NOT NULL AND NOT EXISTS (",
    LIBRARY_BRANCH + "\n  IF NEW.target_id IS NOT NULL AND NOT EXISTS (",
    1,
)


class Migration(migrations.Migration):
    dependencies = [("core", "0200_shared_live_writer_guard")]
    operations = [
        migrations.AddField(
            model_name="contentinclude",
            name="library_workspace_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contentinclude",
            name="library_revision_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="contentinclude",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(library_workspace_id__isnull=True, library_revision_id__isnull=True)
                    | models.Q(library_workspace_id__isnull=False, library_revision_id__isnull=False)
                ),
                name="content_include_library_identity_pair",
            ),
        ),
        migrations.RunSQL(FORWARD, PREVIOUS),
    ]
