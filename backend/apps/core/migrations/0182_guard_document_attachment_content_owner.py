"""Keep legacy attachment owner fields exact while repository-native writes remain disabled."""

from django.db import migrations

FORWARD_SQL = r"""
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
      WHERE prior.id=NEW.replaces_id
        AND prior.document_id=NEW.document_id
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

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_document_attachment() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_document d
    WHERE d.id=NEW.document_id AND d.tenant_id=NEW.tenant_id
      AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'attachment document workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity e
    WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
      AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND e.entity_type='document_attachment'
  ) THEN RAISE EXCEPTION 'attachment entity workspace mismatch'; END IF;
  IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size < 1 OR NEW.size > 10485760 THEN
    RAISE EXCEPTION 'attachment integrity metadata is invalid';
  END IF;
  IF TG_OP='UPDATE' AND (
    OLD.purpose='primary_file'
    OR NEW.purpose IS DISTINCT FROM OLD.purpose
    OR NEW.version_number IS DISTINCT FROM OLD.version_number
    OR NEW.replaces_id IS DISTINCT FROM OLD.replaces_id
  ) THEN RAISE EXCEPTION 'primary file version identity is immutable'; END IF;
  IF NEW.purpose='primary_file' AND (
    NEW.version_number IS NULL OR NEW.version_number < 1
    OR (NEW.version_number=1 AND NEW.replaces_id IS NOT NULL)
    OR (NEW.version_number>1 AND NOT EXISTS (
      SELECT 1 FROM core_documentattachment prior
      WHERE prior.id=NEW.replaces_id
        AND prior.document_id=NEW.document_id
        AND prior.tenant_id=NEW.tenant_id
        AND prior.organization_id IS NOT DISTINCT FROM NEW.organization_id
        AND prior.purpose='primary_file'
        AND prior.version_number=NEW.version_number - 1
        AND prior.archived_at IS NULL
    ))
  ) THEN RAISE EXCEPTION 'primary file version chain is invalid'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0181_backfill_document_attachment_owner")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
