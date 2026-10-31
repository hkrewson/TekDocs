"""Keep promoted binding configuration aligned with reversible root metadata."""

from django.db import migrations

FORWARD = r"""
CREATE FUNCTION tekdocs_guard_promoted_key_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_document uuid; new_document uuid;
BEGIN
  IF TG_OP <> 'INSERT' THEN old_document := OLD.document_id; END IF;
  IF TG_OP <> 'DELETE' THEN new_document := NEW.document_id; END IF;
  PERFORM 1 FROM core_document
    WHERE id IN (old_document, new_document) ORDER BY id FOR UPDATE;
  IF EXISTS (
    SELECT 1 FROM core_documentauthority a
    WHERE a.content_id IN (old_document, new_document) AND a.authority='repository'
  ) THEN
    RAISE EXCEPTION 'promoted document binding configuration is read-only' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_documentkeybinding_promoted_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_documentkeybinding
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_promoted_key_binding();
"""

REVERSE = r"""
DROP TRIGGER core_documentkeybinding_promoted_guard ON core_documentkeybinding;
DROP FUNCTION tekdocs_guard_promoted_key_binding();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0207_addressed_git_publication")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
