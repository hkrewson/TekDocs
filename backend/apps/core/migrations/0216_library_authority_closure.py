"""Check complete library cohorts without exposing another client's records."""

from importlib import import_module

from django.db import migrations

prior = import_module("apps.core.migrations.0206_controlled_template_graph").FINAL_PROJECTION
PRIOR_FUNCTION = prior[:prior.index("REVOKE ALL ON FUNCTION")].replace(
    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1,
)
FUNCTION = PRIOR_FUNCTION.replace(
    "AND (edge.library_workspace_id IS NULL OR EXISTS (",
    """AND (edge.library_workspace_id IS NULL OR (
              edge.library_source_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM public.core_block shared
                JOIN public.core_document owner ON owner.id=shared.source_document_id
                JOIN public.core_entity owner_entity ON owner_entity.id=owner.entity_id
                WHERE shared.id=placement.block_id AND shared.tenant_id=d.tenant_id
                  AND owner.tenant_id=d.tenant_id AND owner.organization_id IS NULL
                  AND shared.organization_id IS NULL
                  AND public.tekdocs_shared_library_placement_allowed(d.tenant_id, placement.id)
                  AND owner.archived_at IS NULL AND shared.archived_at IS NULL
                  AND owner.id=edge.library_source_id AND owner_entity.workspace_id=edge.library_workspace_id
                  AND (placement.resolution_mode<>'pinned' OR placement.pinned_revision_id=edge.library_revision_id)
              )
            ) OR EXISTS (""", 1,
)
CLOSURE = r"""
CREATE FUNCTION tekdocs_library_has_live_clients(row_tenant uuid, source_uuid uuid, source_kind text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
  SELECT COALESCE(row_tenant=public.tekdocs_current_tenant_id()
    AND current_setting('tekdocs.organization_mode', true)='msp' AND EXISTS (
      SELECT 1 FROM public.core_documentplacement p JOIN public.core_block b ON b.id=p.block_id
      WHERE p.tenant_id=row_tenant AND b.tenant_id=row_tenant AND b.organization_id IS NULL
        AND p.organization_id IS NOT NULL AND p.resolution_mode='live'
        AND ((source_kind='block' AND b.id=source_uuid)
          OR (source_kind='document' AND b.source_document_id=source_uuid))
    ), false)
$$;
REVOKE ALL ON FUNCTION tekdocs_library_has_live_clients(uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_library_has_live_clients(uuid, uuid, text) TO tekdocs_runtime;
CREATE FUNCTION tekdocs_library_cohort_closed(row_tenant uuid, members uuid[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog, public, pg_temp SET row_security=off AS $$
  SELECT COALESCE(row_tenant=public.tekdocs_current_tenant_id()
    AND cardinality(members) BETWEEN 1 AND 64 AND NOT EXISTS (
      SELECT 1 FROM public.core_documentplacement p JOIN public.core_block b ON b.id=p.block_id
      WHERE p.tenant_id=row_tenant AND b.tenant_id=row_tenant AND p.resolution_mode='live'
        AND ((p.document_id=ANY(members)) IS DISTINCT FROM (b.source_document_id=ANY(members)))
    ) AND NOT EXISTS (
      SELECT 1 FROM public.core_documentkeybinding k JOIN public.core_block b ON b.entity_id=k.target_entity_id
      WHERE k.tenant_id=row_tenant AND b.tenant_id=row_tenant AND k.archived_at IS NULL
        AND ((k.document_id=ANY(members)) IS DISTINCT FROM (b.source_document_id=ANY(members)))
    ), false)
$$;
REVOKE ALL ON FUNCTION tekdocs_library_cohort_closed(uuid, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_library_cohort_closed(uuid, uuid[]) TO tekdocs_runtime;

"""


class Migration(migrations.Migration):
    dependencies = [("core", "0215_ordinary_library_publication")]
    operations = [
        migrations.RunSQL(FUNCTION, PRIOR_FUNCTION),
        migrations.RunSQL(CLOSURE, """
            DROP FUNCTION tekdocs_library_cohort_closed(uuid, uuid[]);
            DROP FUNCTION tekdocs_library_has_live_clients(uuid, uuid, text);
        """),
    ]
