"""Allow exact template operations only with a matching final Git projection."""

from importlib import import_module

from django.db import migrations

PREVIOUS = import_module("apps.core.migrations.0200_shared_live_writer_guard").PLACEMENT_GUARD
CONTROLLED = r"""
current_setting('tekdocs.template_document_write', true)=destination::text
AND (old_destination IS NULL OR old_destination=destination)
AND tenant_scope=tekdocs_current_tenant_id()
AND tekdocs_scope_matches(tenant_scope, organization_scope)
AND EXISTS (
  SELECT 1 FROM public.core_documenttemplateenrollment enrollment
  WHERE enrollment.destination_document_id=destination AND enrollment.tenant_id=tenant_scope
    AND enrollment.organization_id IS NOT DISTINCT FROM organization_scope AND enrollment.archived_at IS NULL
)
"""
# Replace the function, preserving the original scope and writer serialization.
FUNCTION = PREVIOUS[: PREVIOUS.index("REVOKE ALL ON FUNCTION")].replace(
    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
)
FUNCTION = FUNCTION.replace(
    ") THEN RAISE EXCEPTION 'legacy placement writes are retired for this document'",
    ") AND NOT COALESCE((" + CONTROLLED + "), false) "
    "THEN RAISE EXCEPTION 'legacy placement writes are retired for this document'",
).replace(
    ") THEN RAISE EXCEPTION 'live placements require legacy source authority'",
    ") AND NOT COALESCE(("  # noqa: S608 -- assembled from reviewed static migration constants
    + CONTROLLED
    + r"""
      AND EXISTS (
        SELECT 1 FROM public.core_documenttemplateenrollment enrollment
        JOIN public.core_document source ON source.id=enrollment.source_template_id
        JOIN public.core_block block ON block.source_document_id=source.id
        WHERE enrollment.destination_document_id=destination AND block.id=source_block
          AND source.tenant_id=tenant_scope AND source.organization_id IS NULL
          AND source.is_template AND source.library_visible AND source.archived_at IS NULL
          AND block.library_visible
      )
    ), false) THEN RAISE EXCEPTION 'live placements require legacy source authority'""",  # noqa: S608
)

FINAL_PROJECTION = r"""
CREATE FUNCTION tekdocs_validate_git_template_graph() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp SET row_security = off AS $$
DECLARE destination uuid;
BEGIN
  IF TG_TABLE_NAME='core_documenttemplateenrollment' THEN
    destination := NEW.destination_document_id;
  ELSIF TG_OP='DELETE' THEN destination := OLD.document_id;
  ELSE destination := NEW.document_id;
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.core_document d JOIN public.core_entity e ON e.id=d.entity_id
    JOIN public.core_documentauthority authority
      ON authority.workspace_id=e.workspace_id AND authority.content_id=d.id
    WHERE d.id=destination AND authority.authority='repository'
  ) AND NOT EXISTS (
    SELECT 1 FROM public.core_document d JOIN public.core_entity e ON e.id=d.entity_id
    JOIN public.core_workspacerepository repository ON repository.workspace_id=e.workspace_id
    JOIN public.core_contentnode root ON root.repository_id=repository.id AND root.content_id=d.id
    WHERE d.id=destination AND repository.lifecycle_state='active'
      AND repository.accepted_commit_id=repository.indexed_commit_id
      AND root.indexed_commit_id=repository.accepted_commit_id
      AND NOT EXISTS (
        SELECT 1 FROM (
          SELECT p.*, row_number() OVER (PARTITION BY p.parent_id ORDER BY p.position, p.id)-1 AS ordinal
          FROM public.core_documentplacement p WHERE p.document_id=d.id
        ) placement
        LEFT JOIN public.core_documentplacement parent ON parent.id=placement.parent_id
        WHERE (placement.resolution_mode='live' AND NOT EXISTS (
          SELECT 1 FROM public.core_block placed_block
          JOIN public.core_document owner ON owner.id=placed_block.source_document_id
          JOIN public.core_entity owner_entity ON owner_entity.id=owner.entity_id
          JOIN public.core_documentauthority owner_authority
            ON owner_authority.workspace_id=owner_entity.workspace_id AND owner_authority.content_id=owner.id
          WHERE placed_block.id=placement.block_id AND owner_authority.authority='repository'
        )) OR NOT EXISTS (
          SELECT 1 FROM public.core_contentinclude edge
          JOIN public.core_contentnode source ON source.id=edge.source_id
          WHERE source.repository_id=repository.id AND source.tenant_id=d.tenant_id
            AND source.content_id=CASE WHEN placement.parent_id IS NULL THEN d.id ELSE parent.block_id END
            AND source.indexed_commit_id=repository.accepted_commit_id
            AND edge.ordinal=placement.ordinal AND edge.target_content_id=placement.block_id
            AND edge.resolution_mode=placement.resolution_mode AND edge.audience_profile=placement.audience_profile
            AND (edge.library_workspace_id IS NULL OR EXISTS (
              SELECT 1 FROM public.core_documenttemplateenrollment enrollment
              JOIN public.core_documenttemplaterevision version ON version.id=enrollment.applied_revision_id
              JOIN public.core_block block ON block.id=placement.block_id
              CROSS JOIN LATERAL jsonb_array_elements(enrollment.placement_map) mapped
              CROSS JOIN LATERAL jsonb_array_elements(version.manifest->'blocks') definition
              WHERE enrollment.destination_document_id=d.id AND enrollment.applied_revision_id=edge.library_revision_id
                AND enrollment.archived_at IS NULL
                AND mapped->>'destination_placement_id'=placement.id::text
                AND mapped->>'source_block_id'=block.entity_id::text
                AND mapped->>'mode'=placement.resolution_mode
                AND definition->>'source_block_id'=mapped->>'source_block_id'
                AND definition->>'source_revision_id'=mapped->>'applied_revision_id'
                AND (placement.resolution_mode<>'pinned' OR
                     placement.pinned_revision_id::text=definition->>'source_revision_id')
            ))
        )
      )
      AND (SELECT count(*) FROM public.core_documentplacement p WHERE p.document_id=d.id) = (
        SELECT count(*) FROM public.core_contentinclude edge
        JOIN public.core_contentnode source ON source.id=edge.source_id
        WHERE source.repository_id=repository.id AND (
          source.content_id=d.id OR source.content_id IN (
            SELECT p.block_id FROM public.core_documentplacement p
            JOIN public.core_block b ON b.id=p.block_id AND b.source_document_id=d.id
            WHERE p.document_id=d.id
          )
        )
      )
  ) THEN
    RAISE EXCEPTION 'template graph must match its final indexed Git content'
      USING ERRCODE='23514', CONSTRAINT='tekdocs_git_template_graph';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION tekdocs_validate_git_template_graph() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER tekdocs_git_template_placement_projection
AFTER INSERT OR UPDATE OR DELETE ON core_documentplacement DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_git_template_graph();
CREATE CONSTRAINT TRIGGER tekdocs_git_template_enrollment_projection
AFTER INSERT OR UPDATE ON core_documenttemplateenrollment DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_git_template_graph();
"""
REVERSE = """
DROP TRIGGER tekdocs_git_template_enrollment_projection ON core_documenttemplateenrollment;
DROP TRIGGER tekdocs_git_template_placement_projection ON core_documentplacement;
DROP FUNCTION tekdocs_validate_git_template_graph();
""" + PREVIOUS[: PREVIOUS.index("REVOKE ALL ON FUNCTION")].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


class Migration(migrations.Migration):
    dependencies = [("core", "0205_copied_template_definition_visibility")]
    operations = [migrations.RunSQL(FUNCTION + FINAL_PROJECTION, REVERSE)]
