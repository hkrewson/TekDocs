"""Accept signed v2 primary-file evidence without enabling its distribution."""

from django.db import migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_publication_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspacerepository repository
    JOIN core_workspace workspace ON workspace.id=repository.workspace_id
    JOIN core_repositorycommit commit ON commit.id=NEW.source_commit_id
    WHERE repository.id=NEW.repository_id AND repository.tenant_id=NEW.tenant_id
      AND workspace.id=NEW.workspace_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND commit.repository_id=repository.id AND commit.tenant_id=NEW.tenant_id
      AND repository.accepted_commit_id=commit.id
      AND repository.indexed_commit_id=commit.id
      AND NEW.manifest->>'source_commit'=commit.object_id
      AND NEW.manifest->'source'->>'accepted_commit'=commit.object_id
      AND NEW.manifest->'source'->>'object_format'=commit.object_format
  ) THEN RAISE EXCEPTION 'repository publication evidence source mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.content_digest !~ '^[0-9a-f]{64}$'
    OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
    OR NEW.signature_algorithm IS DISTINCT FROM 'Ed25519'
    OR jsonb_typeof(NEW.manifest) IS DISTINCT FROM 'object'
    OR COALESCE(NEW.manifest->>'format', '') NOT IN (
      'tekdocs-repository-publication-evidence/v1',
      'tekdocs-repository-publication-evidence/v2'
    )
    OR (NEW.manifest->>'format'='tekdocs-repository-publication-evidence/v2'
      AND jsonb_typeof(NEW.manifest->'primary_file') IS DISTINCT FROM 'object')
    OR NEW.manifest->>'evidence_id' IS DISTINCT FROM NEW.id::text
    OR NEW.manifest->>'repository_id' IS DISTINCT FROM NEW.repository_id::text
    OR NEW.manifest->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
    OR NEW.manifest->>'content_id' IS DISTINCT FROM NEW.content_id::text
    OR NEW.manifest->>'audience' IS DISTINCT FROM NEW.audience
    OR NEW.manifest->>'signed_by' IS DISTINCT FROM NEW.signed_by_id::text
    OR NEW.manifest->'source'->>'format' IS DISTINCT FROM 'tekdocs.git-dependencies/v1'
    OR NEW.manifest->'source'->>'repository_id' IS DISTINCT FROM NEW.repository_id::text
    OR NEW.manifest->'source'->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
    OR NEW.manifest->'source'->>'content_id' IS DISTINCT FROM NEW.content_id::text
    OR NEW.manifest->'source'->>'audience' IS DISTINCT FROM NEW.audience
  THEN RAISE EXCEPTION 'repository publication evidence manifest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

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
      AND attachment.purpose IN ('attachment', 'primary_file')
      AND (attachment.purpose='attachment' OR evidence.manifest->>'format'=
        'tekdocs-repository-publication-evidence/v2')
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
      JOIN core_documentattachment attachment ON attachment.id=NEW.source_attachment_id
      CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN attachment.purpose='primary_file'
          THEN COALESCE(evidence.manifest->'primary_file'->'versions', '[]'::jsonb)
          ELSE COALESCE(evidence.manifest->'attachments', '[]'::jsonb)
        END
      ) descriptor
      WHERE evidence.id=NEW.evidence_id
        AND descriptor->>'id'=NEW.id::text
        AND descriptor->>'source_id' IN (NEW.source_attachment_id::text, attachment.entity_id::text)
        AND descriptor->>'checksum'=NEW.checksum
        AND descriptor->>'size'=NEW.size::text
        AND descriptor->>'media_type'=NEW.media_type
        AND (attachment.purpose='attachment' OR (
          descriptor->>'source_record_id'=attachment.id::text
          AND descriptor->>'source_id'=attachment.entity_id::text
          AND descriptor->>'version_number'=attachment.version_number::text
        ))
    )
  THEN RAISE EXCEPTION 'repository evidence attachment manifest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_publication_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspacerepository repository
    JOIN core_workspace workspace ON workspace.id=repository.workspace_id
    JOIN core_repositorycommit commit ON commit.id=NEW.source_commit_id
    WHERE repository.id=NEW.repository_id AND repository.tenant_id=NEW.tenant_id
      AND workspace.id=NEW.workspace_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND commit.repository_id=repository.id AND commit.tenant_id=NEW.tenant_id
      AND repository.accepted_commit_id=commit.id
      AND repository.indexed_commit_id=commit.id
      AND NEW.manifest->>'source_commit'=commit.object_id
      AND NEW.manifest->'source'->>'accepted_commit'=commit.object_id
      AND NEW.manifest->'source'->>'object_format'=commit.object_format
  ) THEN RAISE EXCEPTION 'repository publication evidence source mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.content_digest !~ '^[0-9a-f]{64}$'
    OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
    OR NEW.signature_algorithm IS DISTINCT FROM 'Ed25519'
    OR jsonb_typeof(NEW.manifest) IS DISTINCT FROM 'object'
    OR NEW.manifest->>'format' IS DISTINCT FROM 'tekdocs-repository-publication-evidence/v1'
    OR NEW.manifest->>'evidence_id' IS DISTINCT FROM NEW.id::text
    OR NEW.manifest->>'repository_id' IS DISTINCT FROM NEW.repository_id::text
    OR NEW.manifest->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
    OR NEW.manifest->>'content_id' IS DISTINCT FROM NEW.content_id::text
    OR NEW.manifest->>'audience' IS DISTINCT FROM NEW.audience
    OR NEW.manifest->>'signed_by' IS DISTINCT FROM NEW.signed_by_id::text
    OR NEW.manifest->'source'->>'format' IS DISTINCT FROM 'tekdocs.git-dependencies/v1'
    OR NEW.manifest->'source'->>'repository_id' IS DISTINCT FROM NEW.repository_id::text
    OR NEW.manifest->'source'->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
    OR NEW.manifest->'source'->>'content_id' IS DISTINCT FROM NEW.content_id::text
    OR NEW.manifest->'source'->>'audience' IS DISTINCT FROM NEW.audience
  THEN RAISE EXCEPTION 'repository publication evidence manifest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

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


class Migration(migrations.Migration):
    dependencies = [("core", "0187_native_primary_file_versions")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
