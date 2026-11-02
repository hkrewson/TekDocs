"""Foreign source visibility must never grant unshared block reads or writes."""

from django.db import migrations

FORWARD = r"""
CREATE FUNCTION tekdocs_foreign_source_placement_visible(row_tenant uuid, placement_uuid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
  SELECT COALESCE(row_tenant=public.tekdocs_current_tenant_id()
    AND current_setting('tekdocs.organization_mode', true)='organization' AND EXISTS (
      SELECT 1 FROM public.core_documentplacement p
      JOIN public.core_document d ON d.id=p.document_id
      JOIN public.core_block b ON b.id=p.block_id
      WHERE p.id=placement_uuid AND p.tenant_id=row_tenant AND p.organization_id IS NULL
        AND d.tenant_id=row_tenant AND d.organization_id IS NULL AND d.archived_at IS NULL
        AND b.tenant_id=row_tenant AND b.archived_at IS NULL
        AND ((d.is_template AND d.library_visible) OR EXISTS (
          SELECT 1 FROM public.core_documentationlistingreference listing
          WHERE listing.document_id=d.id AND listing.tenant_id=row_tenant
            AND listing.organization_id=public.tekdocs_current_organization_id() AND listing.archived_at IS NULL
        ) OR (d.library_visible AND b.library_visible AND b.source_document_id=d.id))
    ), false)
$$;
REVOKE ALL ON FUNCTION tekdocs_foreign_source_placement_visible(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_foreign_source_placement_visible(uuid, uuid) TO tekdocs_runtime;

ALTER POLICY core_documentplacement_runtime_scope ON core_documentplacement
  USING (tekdocs_scope_matches(tenant_id, organization_id));
CREATE POLICY core_documentplacement_shared_select ON core_documentplacement FOR SELECT
  USING (tekdocs_foreign_source_placement_visible(tenant_id, id));
ALTER POLICY core_block_runtime_scope ON core_block
  USING (tekdocs_scope_matches(tenant_id, organization_id));
CREATE POLICY core_block_shared_select ON core_block FOR SELECT
  USING (tenant_id=tekdocs_current_tenant_id() AND EXISTS (
    SELECT 1 FROM core_documentplacement p WHERE p.block_id=core_block.id
  ));
"""
REVERSE = r"""
DROP POLICY core_block_shared_select ON core_block;
ALTER POLICY core_block_runtime_scope ON core_block USING (
  tekdocs_scope_matches(tenant_id, organization_id) OR (
    tenant_id=tekdocs_current_tenant_id() AND EXISTS (
      SELECT 1 FROM core_documentplacement p WHERE p.block_id=core_block.id
    )
  )
);
DROP POLICY core_documentplacement_shared_select ON core_documentplacement;
ALTER POLICY core_documentplacement_runtime_scope ON core_documentplacement USING (
  tekdocs_scope_matches(tenant_id, organization_id) OR (
    tenant_id=tekdocs_current_tenant_id() AND EXISTS (
      SELECT 1 FROM core_document d WHERE d.id=document_id
    )
  )
);
DROP FUNCTION tekdocs_foreign_source_placement_visible(uuid, uuid);
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0216_library_authority_closure")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
