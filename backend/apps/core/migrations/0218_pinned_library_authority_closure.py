"""Keep foreign pinned consumers publishable across every authority entry point."""

from django.db import migrations

FORWARD = r"""
CREATE FUNCTION tekdocs_library_pinned_cohort_closed(row_tenant uuid, members uuid[], target text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
  SELECT COALESCE(row_tenant=public.tekdocs_current_tenant_id()
    AND target IN ('repository', 'legacy') AND cardinality(members) BETWEEN 1 AND 64
    AND NOT EXISTS (
      SELECT 1 FROM public.core_documentplacement p JOIN public.core_block b ON b.id=p.block_id
      JOIN public.core_document source ON source.id=b.source_document_id AND source.tenant_id=row_tenant
      JOIN public.core_entity source_entity ON source_entity.id=source.entity_id
      JOIN public.core_document consumer ON consumer.id=p.document_id AND consumer.tenant_id=row_tenant
      JOIN public.core_entity consumer_entity ON consumer_entity.id=consumer.entity_id
      WHERE p.tenant_id=row_tenant AND b.tenant_id=row_tenant AND p.resolution_mode='pinned'
        AND b.organization_id IS DISTINCT FROM p.organization_id
        AND ((target='repository' AND p.document_id=ANY(members)
          AND NOT b.source_document_id=ANY(members) AND NOT EXISTS (
            SELECT 1 FROM public.core_documentauthority a WHERE a.tenant_id=row_tenant
              AND a.content_id=b.source_document_id AND a.workspace_id=source_entity.workspace_id
              AND a.authority='repository'
          )) OR (target='legacy' AND b.source_document_id=ANY(members)
          AND NOT p.document_id=ANY(members) AND EXISTS (
            SELECT 1 FROM public.core_documentauthority a WHERE a.tenant_id=row_tenant
              AND a.content_id=p.document_id AND a.workspace_id=consumer_entity.workspace_id
              AND a.authority='repository'
          )))
    ), false)
$$;
REVOKE ALL ON FUNCTION tekdocs_library_pinned_cohort_closed(uuid, uuid[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_library_pinned_cohort_closed(uuid, uuid[], text) TO tekdocs_runtime;
CREATE FUNCTION tekdocs_document_is_library_participant(row_tenant uuid, row_workspace uuid, document_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
  SELECT COALESCE(row_tenant=public.tekdocs_current_tenant_id()
    AND row_workspace=public.tekdocs_current_workspace_id() AND EXISTS (
      SELECT 1 FROM public.core_document d JOIN public.core_entity e ON e.id=d.entity_id
      WHERE d.id=document_uuid AND d.tenant_id=row_tenant AND e.workspace_id=row_workspace AND EXISTS (
        SELECT 1 FROM public.core_documentplacement p JOIN public.core_block b ON b.id=p.block_id
        WHERE p.tenant_id=row_tenant AND b.tenant_id=row_tenant
          AND b.organization_id IS DISTINCT FROM p.organization_id
          AND (p.document_id=d.id OR b.source_document_id=d.id)
      )
    ), false)
$$;
REVOKE ALL ON FUNCTION tekdocs_document_is_library_participant(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_document_is_library_participant(uuid, uuid, uuid) TO tekdocs_runtime;
CREATE FUNCTION tekdocs_guard_pinned_library_authority() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
DECLARE owner_document uuid;
BEGIN
  SELECT d.id INTO owner_document FROM public.core_document d
    JOIN public.core_entity e ON e.id=d.entity_id
    WHERE d.id=NEW.content_id AND d.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id;
  IF owner_document IS NULL THEN
    SELECT b.source_document_id INTO owner_document FROM public.core_block b
      JOIN public.core_document d ON d.id=b.source_document_id AND d.tenant_id=NEW.tenant_id
      JOIN public.core_entity e ON e.id=d.entity_id
      WHERE b.id=NEW.content_id AND b.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id;
  END IF;
  IF owner_document IS NULL THEN RETURN NULL; END IF;
  -- Serialize a source rollback and consumer promotion on the same stable Block.
  -- The invariant query runs after this lock, so it sees the preceding commit.
  PERFORM b.id FROM public.core_block b WHERE b.tenant_id=NEW.tenant_id AND EXISTS (
    SELECT 1 FROM public.core_documentplacement p WHERE p.block_id=b.id AND p.tenant_id=NEW.tenant_id
      AND p.resolution_mode='pinned' AND b.organization_id IS DISTINCT FROM p.organization_id
      AND (p.document_id=owner_document OR b.source_document_id=owner_document)
  ) ORDER BY b.id FOR UPDATE OF b;
  IF EXISTS (
    SELECT 1 FROM public.core_documentplacement p
    JOIN public.core_block b ON b.id=p.block_id AND b.tenant_id=NEW.tenant_id
    JOIN public.core_document source ON source.id=b.source_document_id AND source.tenant_id=NEW.tenant_id
    JOIN public.core_entity source_entity ON source_entity.id=source.entity_id
    JOIN public.core_document consumer ON consumer.id=p.document_id AND consumer.tenant_id=NEW.tenant_id
    JOIN public.core_entity consumer_entity ON consumer_entity.id=consumer.entity_id
    JOIN public.core_documentauthority consumer_authority
      ON consumer_authority.tenant_id=NEW.tenant_id AND consumer_authority.content_id=consumer.id
      AND consumer_authority.workspace_id=consumer_entity.workspace_id
    LEFT JOIN public.core_documentauthority source_authority
      ON source_authority.tenant_id=NEW.tenant_id AND source_authority.content_id=source.id
      AND source_authority.workspace_id=source_entity.workspace_id
    WHERE p.tenant_id=NEW.tenant_id AND p.resolution_mode='pinned'
      AND b.organization_id IS DISTINCT FROM p.organization_id
      AND (source.id=owner_document OR consumer.id=owner_document)
      AND consumer_authority.authority='repository'
      AND source_authority.authority IS DISTINCT FROM 'repository'
  ) THEN
    RAISE EXCEPTION 'authority transition must preserve pinned repository consumers' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION tekdocs_guard_pinned_library_authority() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER tekdocs_pinned_library_authority_closure
AFTER INSERT OR UPDATE ON core_documentauthority DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_pinned_library_authority();
"""
REVERSE = """
DROP TRIGGER tekdocs_pinned_library_authority_closure ON core_documentauthority;
DROP FUNCTION tekdocs_guard_pinned_library_authority();
DROP FUNCTION tekdocs_library_pinned_cohort_closed(uuid, uuid[], text);
DROP FUNCTION tekdocs_document_is_library_participant(uuid, uuid, uuid);
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0217_library_projection_isolation")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
