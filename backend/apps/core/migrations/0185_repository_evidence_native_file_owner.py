"""Accept exact Git-document owners for retained repository evidence files."""

from django.db import migrations

VALIDATOR_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_evidence_attachment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypublicationevidence evidence
    JOIN core_documentattachment attachment ON attachment.id=NEW.source_attachment_id
    WHERE evidence.id=NEW.evidence_id
      AND evidence.tenant_id=NEW.tenant_id
      AND evidence.workspace_id=NEW.workspace_id
      AND evidence.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND attachment.tenant_id=NEW.tenant_id
      AND attachment.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND attachment.owner_workspace_id=NEW.workspace_id
      AND attachment.owner_content_id=evidence.content_id
      AND attachment.purpose='attachment'
      AND (
        attachment.document_id IS NULL OR EXISTS (
          SELECT 1 FROM core_document document
          JOIN core_entity entity ON entity.id=document.entity_id
          WHERE document.id=attachment.document_id
            AND document.id=evidence.content_id
            AND entity.workspace_id=NEW.workspace_id
        )
      )
  ) THEN RAISE EXCEPTION 'repository evidence attachment scope mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size=0
    OR NEW.file IS DISTINCT FROM
      ('repository-evidence-attachments/' || NEW.tenant_id::text || '/' || NEW.evidence_id::text || '/' || NEW.id::text)
    OR NOT EXISTS (
      SELECT 1 FROM core_repositorypublicationevidence evidence
      JOIN core_documentattachment attachment ON attachment.id=NEW.source_attachment_id,
        jsonb_array_elements(COALESCE(evidence.manifest->'attachments', '[]'::jsonb)) descriptor
      WHERE evidence.id=NEW.evidence_id
        AND descriptor->>'id'=NEW.id::text
        AND descriptor->>'source_id' IN (NEW.source_attachment_id::text, attachment.entity_id::text)
        AND descriptor->>'checksum'=NEW.checksum
        AND descriptor->>'size'=NEW.size::text
        AND descriptor->>'media_type'=NEW.media_type
    )
  THEN RAISE EXCEPTION 'repository evidence attachment manifest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""

LEGACY_VALIDATOR_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_evidence_attachment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypublicationevidence evidence
    JOIN core_documentattachment attachment ON attachment.id=NEW.source_attachment_id
    JOIN core_document document ON document.id=attachment.document_id
    JOIN core_entity entity ON entity.id=document.entity_id
    WHERE evidence.id=NEW.evidence_id
      AND evidence.tenant_id=NEW.tenant_id
      AND evidence.workspace_id=NEW.workspace_id
      AND evidence.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND attachment.tenant_id=NEW.tenant_id
      AND attachment.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND document.id=evidence.content_id
      AND entity.workspace_id=NEW.workspace_id
      AND attachment.purpose='attachment'
  ) THEN RAISE EXCEPTION 'repository evidence attachment scope mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size=0
    OR NEW.file IS DISTINCT FROM
      ('repository-evidence-attachments/' || NEW.tenant_id::text || '/' || NEW.evidence_id::text || '/' || NEW.id::text)
    OR NOT EXISTS (
      SELECT 1 FROM core_repositorypublicationevidence evidence
      JOIN core_documentattachment attachment ON attachment.id=NEW.source_attachment_id,
        jsonb_array_elements(COALESCE(evidence.manifest->'attachments', '[]'::jsonb)) descriptor
      WHERE evidence.id=NEW.evidence_id
        AND descriptor->>'id'=NEW.id::text
        AND descriptor->>'source_id' IN (NEW.source_attachment_id::text, attachment.entity_id::text)
        AND descriptor->>'checksum'=NEW.checksum
        AND descriptor->>'size'=NEW.size::text
        AND descriptor->>'media_type'=NEW.media_type
    )
  THEN RAISE EXCEPTION 'repository evidence attachment manifest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0184_guard_native_document_attachment_owner")]

    operations = [migrations.RunSQL(VALIDATOR_SQL, LEGACY_VALIDATOR_SQL)]
