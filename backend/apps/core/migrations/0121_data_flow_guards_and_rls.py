from django.db import migrations

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_data_flow() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'data flow workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.workspace_id=NEW.workspace_id
      AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND entity.entity_type='data_flow'
  ) THEN RAISE EXCEPTION 'data flow anchor scope mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) THEN RAISE EXCEPTION 'data flow creator scope mismatch'; END IF;
  IF NEW.current_revision_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_dataflowrevision revision
    WHERE revision.id=NEW.current_revision_id AND revision.data_flow_id=NEW.id
  ) THEN RAISE EXCEPTION 'data flow current revision mismatch'; END IF;
  IF TG_OP='UPDATE' AND OLD.current_revision_id IS NOT NULL
    AND NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id
    AND NOT EXISTS (
      SELECT 1 FROM core_dataflowrevision prior
      JOIN core_dataflowrevision next ON next.id=NEW.current_revision_id
      WHERE prior.id=OLD.current_revision_id AND next.data_flow_id=NEW.id
        AND next.revision_number=prior.revision_number + 1
    )
  THEN RAISE EXCEPTION 'data flow current revision must advance monotonically'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_data_flow_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE endpoint uuid;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'data flow revisions are append-only';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'data flow revision workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_dataflow flow
    WHERE flow.id=NEW.data_flow_id AND flow.tenant_id=NEW.tenant_id
      AND flow.workspace_id=NEW.workspace_id
      AND flow.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'data flow revision flow scope mismatch'; END IF;
  -- An endpoint or owner must be a record of this exact Workspace. Without this a
  -- revision could name another client's asset and disclose it through the flow.
  FOREACH endpoint IN ARRAY ARRAY[NEW.source_entity_id, NEW.destination_entity_id, NEW.owner_entity_id] LOOP
    IF endpoint IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM core_entity entity
      WHERE entity.id=endpoint AND entity.tenant_id=NEW.tenant_id
        AND entity.workspace_id=NEW.workspace_id AND entity.archived_at IS NULL
    ) THEN RAISE EXCEPTION 'data flow revision endpoint workspace mismatch'; END IF;
  END LOOP;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) THEN RAISE EXCEPTION 'data flow revision creator scope mismatch'; END IF;
  IF NEW.revision_number = 1 THEN
    IF EXISTS (SELECT 1 FROM core_dataflowrevision prior WHERE prior.data_flow_id=NEW.data_flow_id) THEN
      RAISE EXCEPTION 'data flow revision numbering must start once';
    END IF;
  ELSIF NOT EXISTS (
    SELECT 1 FROM core_dataflowrevision prior
    WHERE prior.data_flow_id=NEW.data_flow_id AND prior.revision_number = NEW.revision_number - 1
  ) THEN RAISE EXCEPTION 'data flow revision numbering must be contiguous'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_dataflow_validate BEFORE INSERT OR UPDATE ON core_dataflow
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_data_flow();

CREATE TRIGGER core_dataflowrev_validate BEFORE INSERT OR UPDATE OR DELETE ON core_dataflowrevision
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_data_flow_revision();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_dataflow', 'core_dataflowrevision'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I_runtime_scope ON %I USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))',
      table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_dataflow', 'core_dataflowrevision'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;

DROP TRIGGER IF EXISTS core_dataflowrev_validate ON core_dataflowrevision;
DROP TRIGGER IF EXISTS core_dataflow_validate ON core_dataflow;
DROP FUNCTION IF EXISTS tekdocs_validate_data_flow_revision();
DROP FUNCTION IF EXISTS tekdocs_validate_data_flow();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0120_data_flows")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
