"""Serialize legacy placement writers with shared authority handoff globally."""

from importlib import import_module

from django.db import migrations

PREVIOUS_AUTHORITY = import_module("apps.core.migrations.0199_pinned_consumer_authority").LIVE_ONLY
SECURE_AUTHORITY = (
    PREVIOUS_AUTHORITY.replace(
        "RETURNS trigger LANGUAGE plpgsql AS",
        "RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER "
        "SET search_path = pg_catalog, public, pg_temp SET row_security = off AS",
    ).replace(
        "  IF NEW.authority='repository' AND NOT EXISTS (",
        """  PERFORM 1 FROM public.core_document d
  WHERE d.id=NEW.content_id AND d.tenant_id=NEW.tenant_id FOR UPDATE;
  IF NEW.authority='repository' THEN
    PERFORM 1 FROM public.core_block b
    WHERE b.id=NEW.content_id AND b.tenant_id=NEW.tenant_id FOR UPDATE;
  END IF;
  IF NEW.authority='repository' AND NOT EXISTS (""",
    )
    + "\nREVOKE ALL ON FUNCTION tekdocs_validate_document_authority() FROM PUBLIC;\n"
)

PLACEMENT_GUARD = r"""
CREATE FUNCTION tekdocs_guard_shared_placement_writer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp SET row_security = off AS $$
DECLARE
  destination uuid;
  source_block uuid;
  tenant_scope uuid;
  organization_scope uuid;
  old_destination uuid;
  old_block uuid;
BEGIN
  IF TG_OP='DELETE' THEN
    destination := OLD.document_id; source_block := OLD.block_id;
    tenant_scope := OLD.tenant_id; organization_scope := OLD.organization_id;
  ELSE
    destination := NEW.document_id; source_block := NEW.block_id;
    tenant_scope := NEW.tenant_id; organization_scope := NEW.organization_id;
  END IF;
  IF TG_OP='UPDATE' OR TG_OP='DELETE' THEN
    old_destination := OLD.document_id; old_block := OLD.block_id;
  END IF;
  PERFORM 1 FROM public.core_document d WHERE d.id IN (destination, old_destination)
    ORDER BY d.id FOR UPDATE;
  IF NOT EXISTS (
    SELECT 1 FROM public.core_document d WHERE d.id=destination AND d.tenant_id=tenant_scope
      AND d.organization_id IS NOT DISTINCT FROM organization_scope
  ) OR (TG_OP='UPDATE' AND NOT EXISTS (
    SELECT 1 FROM public.core_document d WHERE d.id=old_destination AND d.tenant_id=OLD.tenant_id
      AND d.organization_id IS NOT DISTINCT FROM OLD.organization_id
  )) THEN RAISE EXCEPTION 'placement owner scope is invalid' USING ERRCODE='23514'; END IF;
  IF EXISTS (
    SELECT 1 FROM public.core_document d JOIN public.core_entity e ON e.id=d.entity_id
    JOIN public.core_documentauthority a ON a.workspace_id=e.workspace_id AND a.content_id=d.id
    WHERE d.id IN (destination, old_destination) AND a.authority='repository'
  ) THEN RAISE EXCEPTION 'legacy placement writes are retired for this document' USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM public.core_block b WHERE b.id IN (source_block, old_block) ORDER BY b.id FOR UPDATE;
  IF NOT EXISTS (
    SELECT 1 FROM public.core_block b WHERE b.id=source_block AND b.tenant_id=tenant_scope
  ) THEN RAISE EXCEPTION 'placement source scope is invalid' USING ERRCODE='23514'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  IF NEW.resolution_mode='live' AND EXISTS (
    SELECT 1 FROM public.core_block b JOIN public.core_entity e ON e.id=b.entity_id
    JOIN public.core_documentauthority a ON a.workspace_id=e.workspace_id AND a.content_id=b.id
    WHERE b.id=source_block AND a.authority='repository'
  ) THEN RAISE EXCEPTION 'live placements require legacy source authority' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION tekdocs_guard_shared_placement_writer() FROM PUBLIC;
CREATE TRIGGER tekdocs_shared_placement_writer_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_documentplacement
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_shared_placement_writer();
"""

REVERSE_PLACEMENT = """
DROP TRIGGER tekdocs_shared_placement_writer_guard ON core_documentplacement;
DROP FUNCTION tekdocs_guard_shared_placement_writer();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0199_pinned_consumer_authority")]
    operations = [
        migrations.RunSQL(SECURE_AUTHORITY, PREVIOUS_AUTHORITY),
        migrations.RunSQL(PLACEMENT_GUARD, REVERSE_PLACEMENT),
    ]
