import django.db.migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_document_authority() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'document authority records cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF TG_OP = 'UPDATE' AND (
    NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id
    OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.workspace_id <> OLD.workspace_id OR NEW.content_id <> OLD.content_id
  ) THEN
    RAISE EXCEPTION 'document authority identity is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.authority <> OLD.authority
    AND current_setting('tekdocs.document_authority_transition', true) IS DISTINCT FROM 'on'
  THEN
    RAISE EXCEPTION 'document authority changes require the transition service' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN
    RAISE EXCEPTION 'document authority Workspace scope mismatch' USING ERRCODE='23514';
  END IF;
  IF NEW.authority='legacy' AND NOT (
    EXISTS (
      SELECT 1 FROM core_document document
      JOIN core_entity entity ON entity.id=document.entity_id
      WHERE document.id=NEW.content_id AND document.tenant_id=NEW.tenant_id
        AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND entity.workspace_id=NEW.workspace_id
    ) OR EXISTS (
      SELECT 1 FROM core_contentnode node
      WHERE node.content_id=NEW.content_id AND node.workspace_id=NEW.workspace_id
        AND node.tenant_id=NEW.tenant_id
        AND node.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND node.kind='fragment'
    )
  ) THEN
    RAISE EXCEPTION 'legacy authority requires the exact legacy content owner' USING ERRCODE='23514';
  END IF;
  IF NEW.authority='repository' AND NOT EXISTS (
    SELECT 1 FROM core_contentnode node
    WHERE node.content_id=NEW.content_id AND node.workspace_id=NEW.workspace_id
      AND node.tenant_id=NEW.tenant_id AND node.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND (
        node.kind='document' OR (
          node.kind='fragment' AND NOT EXISTS (
            SELECT 1 FROM core_block block
            JOIN core_documentplacement placement ON placement.block_id=block.id
            JOIN core_document document ON document.id=placement.document_id
            JOIN core_entity entity ON entity.id=document.entity_id
            LEFT JOIN core_documentauthority owner_authority
              ON owner_authority.workspace_id=entity.workspace_id AND owner_authority.content_id=document.id
            WHERE block.id=NEW.content_id
              AND (owner_authority.authority IS NULL OR owner_authority.authority <> 'repository')
          )
        )
      )
  ) THEN
    RAISE EXCEPTION 'repository authority requires indexed content with no legacy-owned consumers'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""


class Migration(django.db.migrations.Migration):
    dependencies = [("core", "0192_document_authority_state")]

    operations = [django.db.migrations.RunSQL(FORWARD_SQL, django.db.migrations.RunSQL.noop)]
