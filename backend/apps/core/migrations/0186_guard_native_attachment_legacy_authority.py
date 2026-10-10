"""Keep a copied legacy document from acquiring a second managed-file owner."""

from django.db import migrations

FORWARD_SQL = """
CREATE FUNCTION tekdocs_reject_legacy_owned_native_attachment() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.document_id IS NULL AND EXISTS (
    SELECT 1 FROM core_document document
    JOIN core_entity entity ON entity.id=document.entity_id
    WHERE document.id=NEW.owner_content_id
      AND document.tenant_id=NEW.tenant_id
      AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND entity.workspace_id=NEW.owner_workspace_id
  ) THEN
    RAISE EXCEPTION 'legacy document remains authoritative for native attachment owner'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER tekdocs_native_attachment_legacy_authority_guard
  BEFORE INSERT ON core_documentattachment
  FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_legacy_owned_native_attachment();
"""

REVERSE_SQL = """
DROP TRIGGER tekdocs_native_attachment_legacy_authority_guard ON core_documentattachment;
DROP FUNCTION tekdocs_reject_legacy_owned_native_attachment();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0185_repository_evidence_native_file_owner")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
