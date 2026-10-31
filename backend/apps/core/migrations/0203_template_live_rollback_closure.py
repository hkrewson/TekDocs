"""Keep live source/client authority coherent at the end of a grouped transition."""

from django.db import migrations

FORWARD = r"""
CREATE FUNCTION tekdocs_guard_live_authority_rollback() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp SET row_security = off AS $$
DECLARE owner_document uuid;
BEGIN
  IF NEW.authority=OLD.authority THEN RETURN NULL; END IF;
  SELECT d.id INTO owner_document FROM public.core_document d
    WHERE d.id=NEW.content_id AND d.tenant_id=NEW.tenant_id;
  IF owner_document IS NULL THEN
    SELECT b.source_document_id INTO owner_document FROM public.core_block b
      WHERE b.id=NEW.content_id AND b.tenant_id=NEW.tenant_id;
  END IF;
  IF owner_document IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.core_document source
    JOIN public.core_entity source_entity ON source_entity.id=source.entity_id
    JOIN public.core_documentauthority source_authority
      ON source_authority.workspace_id=source_entity.workspace_id AND source_authority.content_id=source.id
    JOIN public.core_block b ON b.source_document_id=source.id
    JOIN public.core_documentplacement p ON p.block_id=b.id AND p.resolution_mode='live'
    JOIN public.core_document destination ON destination.id=p.document_id
    JOIN public.core_entity destination_entity ON destination_entity.id=destination.entity_id
    JOIN public.core_documentauthority destination_authority
      ON destination_authority.workspace_id=destination_entity.workspace_id
      AND destination_authority.content_id=destination.id
    WHERE (source.id=owner_document OR destination.id=owner_document) AND source.tenant_id=NEW.tenant_id
      AND source_authority.authority<>destination_authority.authority
  ) THEN
    RAISE EXCEPTION 'authority rollback must include live repository consumers' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION tekdocs_guard_live_authority_rollback() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER tekdocs_live_authority_rollback_closure
AFTER UPDATE ON core_documentauthority DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_live_authority_rollback();
"""
REVERSE = """
DROP TRIGGER tekdocs_live_authority_rollback_closure ON core_documentauthority;
DROP FUNCTION tekdocs_guard_live_authority_rollback();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0202_template_library_authority_visibility")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
