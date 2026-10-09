"""Guard both legacy and Git-owned files at the database and runtime-role boundary."""

from django.db import migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_document_attachment() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  expected_workspace uuid;
BEGIN
  IF NEW.document_id IS NOT NULL THEN
    SELECT entity.workspace_id INTO expected_workspace
    FROM core_document document
    JOIN core_entity entity ON entity.id=document.entity_id
    JOIN core_workspace workspace ON workspace.id=entity.workspace_id
    WHERE document.id=NEW.document_id
      AND document.tenant_id=NEW.tenant_id
      AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id;
    IF expected_workspace IS NULL THEN
      RAISE EXCEPTION 'attachment document workspace mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.owner_workspace_id IS NULL THEN NEW.owner_workspace_id := expected_workspace; END IF;
    IF NEW.owner_content_id IS NULL THEN NEW.owner_content_id := NEW.document_id; END IF;
    IF NEW.owner_workspace_id IS DISTINCT FROM expected_workspace
      OR NEW.owner_content_id IS DISTINCT FROM NEW.document_id THEN
      RAISE EXCEPTION 'attachment content owner mismatch' USING ERRCODE='23514';
    END IF;
  ELSE
    expected_workspace := NEW.owner_workspace_id;
    IF expected_workspace IS NULL OR NEW.owner_content_id IS NULL OR NEW.purpose <> 'attachment' THEN
      RAISE EXCEPTION 'repository attachment owner is incomplete' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM core_workspace workspace
      WHERE workspace.id=expected_workspace AND workspace.tenant_id=NEW.tenant_id
        AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN RAISE EXCEPTION 'repository attachment workspace mismatch' USING ERRCODE='23514'; END IF;
    IF TG_OP='INSERT' AND NOT EXISTS (
      SELECT 1 FROM core_contentnode node
      JOIN core_workspacerepository repository ON repository.id=node.repository_id
      WHERE node.content_id=NEW.owner_content_id AND node.kind='document'
        AND node.workspace_id=expected_workspace AND node.tenant_id=NEW.tenant_id
        AND node.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND repository.workspace_id=expected_workspace AND repository.tenant_id=NEW.tenant_id
        AND repository.accepted_commit_id IS NOT NULL
        AND repository.accepted_commit_id=repository.indexed_commit_id
        AND node.indexed_commit_id=repository.accepted_commit_id
    ) THEN RAISE EXCEPTION 'repository attachment source is not indexed' USING ERRCODE='23514'; END IF;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND entity.workspace_id=expected_workspace
      AND entity.entity_type='document_attachment'
  ) THEN RAISE EXCEPTION 'attachment entity workspace mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size < 1 OR NEW.size > 10485760 THEN
    RAISE EXCEPTION 'attachment integrity metadata is invalid' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND (
    OLD.document_id IS DISTINCT FROM NEW.document_id
    OR OLD.owner_workspace_id IS DISTINCT FROM NEW.owner_workspace_id
    OR OLD.owner_content_id IS DISTINCT FROM NEW.owner_content_id
    OR OLD.purpose='primary_file'
    OR NEW.purpose IS DISTINCT FROM OLD.purpose
    OR NEW.version_number IS DISTINCT FROM OLD.version_number
    OR NEW.replaces_id IS DISTINCT FROM OLD.replaces_id
  ) THEN RAISE EXCEPTION 'attachment ownership and version identity are immutable' USING ERRCODE='23514'; END IF;
  IF NEW.purpose='primary_file' AND (
    NEW.version_number IS NULL OR NEW.version_number < 1
    OR (NEW.version_number=1 AND NEW.replaces_id IS NOT NULL)
    OR (NEW.version_number>1 AND NOT EXISTS (
      SELECT 1 FROM core_documentattachment prior
      WHERE prior.id=NEW.replaces_id AND prior.document_id=NEW.document_id
        AND prior.tenant_id=NEW.tenant_id
        AND prior.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND prior.purpose='primary_file'
        AND prior.version_number=NEW.version_number - 1
        AND prior.archived_at IS NULL
    ))
  ) THEN RAISE EXCEPTION 'primary file version chain is invalid' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

DROP POLICY core_documentattachment_runtime_select ON core_documentattachment;
CREATE POLICY core_documentattachment_runtime_select ON core_documentattachment FOR SELECT USING (
  (tenant_id=tekdocs_current_tenant_id() AND EXISTS (
    SELECT 1 FROM core_document document WHERE document.id=document_id
  )) OR (document_id IS NULL AND owner_workspace_id=tekdocs_current_workspace_id()
    AND tekdocs_scope_matches(tenant_id, organization_id))
);
DROP POLICY core_documentattachment_runtime_write ON core_documentattachment;
CREATE POLICY core_documentattachment_runtime_write ON core_documentattachment FOR ALL
  USING (tekdocs_scope_matches(tenant_id, organization_id)
    AND (document_id IS NOT NULL OR owner_workspace_id=tekdocs_current_workspace_id()))
  WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id)
    AND (document_id IS NOT NULL OR owner_workspace_id=tekdocs_current_workspace_id()));
"""

REVERSE_SQL = r"""
DROP POLICY core_documentattachment_runtime_select ON core_documentattachment;
CREATE POLICY core_documentattachment_runtime_select ON core_documentattachment FOR SELECT USING (
  tenant_id=tekdocs_current_tenant_id() AND EXISTS (
    SELECT 1 FROM core_document document WHERE document.id=document_id
  )
);
DROP POLICY core_documentattachment_runtime_write ON core_documentattachment;
CREATE POLICY core_documentattachment_runtime_write ON core_documentattachment FOR ALL
  USING (tekdocs_scope_matches(tenant_id, organization_id))
  WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));

CREATE OR REPLACE FUNCTION tekdocs_validate_document_attachment() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  expected_workspace uuid;
BEGIN
  SELECT entity.workspace_id INTO expected_workspace
  FROM core_document document
  JOIN core_entity entity ON entity.id=document.entity_id
  JOIN core_workspace workspace ON workspace.id=entity.workspace_id
  WHERE document.id=NEW.document_id
    AND document.tenant_id=NEW.tenant_id
    AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND workspace.tenant_id=NEW.tenant_id
    AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id;
  IF expected_workspace IS NULL THEN
    RAISE EXCEPTION 'attachment document workspace mismatch' USING ERRCODE='23514';
  END IF;
  IF NEW.owner_workspace_id IS NULL THEN NEW.owner_workspace_id := expected_workspace; END IF;
  IF NEW.owner_content_id IS NULL THEN NEW.owner_content_id := NEW.document_id; END IF;
  IF NEW.owner_workspace_id IS DISTINCT FROM expected_workspace
    OR NEW.owner_content_id IS DISTINCT FROM NEW.document_id THEN
    RAISE EXCEPTION 'attachment content owner mismatch' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND entity.workspace_id=expected_workspace
      AND entity.entity_type='document_attachment'
  ) THEN RAISE EXCEPTION 'attachment entity workspace mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size < 1 OR NEW.size > 10485760 THEN
    RAISE EXCEPTION 'attachment integrity metadata is invalid' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND (
    OLD.purpose='primary_file'
    OR NEW.purpose IS DISTINCT FROM OLD.purpose
    OR NEW.version_number IS DISTINCT FROM OLD.version_number
    OR NEW.replaces_id IS DISTINCT FROM OLD.replaces_id
  ) THEN RAISE EXCEPTION 'primary file version identity is immutable' USING ERRCODE='23514'; END IF;
  IF NEW.purpose='primary_file' AND (
    NEW.version_number IS NULL OR NEW.version_number < 1
    OR (NEW.version_number=1 AND NEW.replaces_id IS NOT NULL)
    OR (NEW.version_number>1 AND NOT EXISTS (
      SELECT 1 FROM core_documentattachment prior
      WHERE prior.id=NEW.replaces_id AND prior.document_id=NEW.document_id
        AND prior.tenant_id=NEW.tenant_id
        AND prior.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND prior.purpose='primary_file'
        AND prior.version_number=NEW.version_number - 1
        AND prior.archived_at IS NULL
    ))
  ) THEN RAISE EXCEPTION 'primary file version chain is invalid' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0183_native_document_attachment_owner_shape")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
