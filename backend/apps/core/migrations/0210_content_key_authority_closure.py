"""Serialize binding writers and keep content-key source/consumer authority together."""

from importlib import import_module

from django.db import migrations

prior = import_module("apps.core.migrations.0208_promoted_key_binding_guard")
WRITER = (
    prior.FORWARD.split("CREATE TRIGGER", 1)[0]  # noqa: S608 -- static migration SQL, no runtime input
    .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    .replace(
        "LANGUAGE plpgsql AS",
        "LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, public, pg_temp SET row_security=off AS",
    )
    .replace(
        "WHERE id IN (old_document, new_document) ORDER BY id FOR UPDATE;",
        """WHERE id IN (old_document, new_document) OR id IN (
      SELECT b.source_document_id FROM public.core_block b
      WHERE b.entity_id IN (
        CASE WHEN TG_OP<>'INSERT' THEN OLD.target_entity_id ELSE NULL END,
        CASE WHEN TG_OP<>'DELETE' THEN NEW.target_entity_id ELSE NULL END
      )
    ) ORDER BY id FOR UPDATE;""",
    )
    .replace(
        "  IF TG_OP='DELETE' THEN RETURN OLD; END IF;",
        """  IF TG_OP<>'DELETE' AND NEW.archived_at IS NULL AND EXISTS (
    SELECT 1 FROM public.core_block b JOIN public.core_entity e ON e.id=b.entity_id
    JOIN public.core_documentauthority a
      ON a.content_id=b.source_document_id AND a.workspace_id=e.workspace_id
    WHERE b.entity_id=NEW.target_entity_id AND a.authority='repository'
  ) THEN RAISE EXCEPTION 'content-key binding requires legacy source authority' USING ERRCODE='23514'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;""",
    )
    + "\nREVOKE ALL ON FUNCTION tekdocs_guard_promoted_key_binding() FROM PUBLIC;\n"
)

CLOSURE = r"""
CREATE FUNCTION tekdocs_guard_content_key_authority() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
BEGIN
  IF NEW.authority=OLD.authority THEN RETURN NULL; END IF;
  IF EXISTS (
    SELECT 1 FROM public.core_documentkeybinding k
    JOIN public.core_block b ON b.entity_id=k.target_entity_id
    JOIN public.core_document source ON source.id=b.source_document_id
    JOIN public.core_entity source_entity ON source_entity.id=source.entity_id
    JOIN public.core_documentauthority source_authority
      ON source_authority.workspace_id=source_entity.workspace_id AND source_authority.content_id=source.id
    JOIN public.core_document consumer ON consumer.id=k.document_id
    JOIN public.core_entity consumer_entity ON consumer_entity.id=consumer.entity_id
    JOIN public.core_documentauthority consumer_authority
      ON consumer_authority.workspace_id=consumer_entity.workspace_id AND consumer_authority.content_id=consumer.id
    WHERE k.archived_at IS NULL AND k.tenant_id=NEW.tenant_id
      AND NEW.content_id IN (source.id, consumer.id, b.id)
      AND source_authority.authority<>consumer_authority.authority
  ) THEN RAISE EXCEPTION 'content-key authority must include source and consumer' USING ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION tekdocs_guard_content_key_authority() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER tekdocs_content_key_authority_closure
AFTER UPDATE ON core_documentauthority DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_content_key_authority();
"""

REVERSE = """
DROP TRIGGER tekdocs_content_key_authority_closure ON core_documentauthority;
DROP FUNCTION tekdocs_guard_content_key_authority();
""" + prior.FORWARD.split("CREATE TRIGGER", 1)[0].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


class Migration(migrations.Migration):
    dependencies = [("core", "0209_content_key_git_publication")]
    operations = [migrations.RunSQL(WRITER + CLOSURE, REVERSE)]
