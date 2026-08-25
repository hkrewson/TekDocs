from django.db import migrations

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_data_flow_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'data flow snapshots are immutable';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'data flow snapshot workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) THEN RAISE EXCEPTION 'data flow snapshot creator scope mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_dataflowsnap_validate BEFORE INSERT OR UPDATE OR DELETE ON core_dataflowsnapshot
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_data_flow_snapshot();

ALTER TABLE core_dataflowsnapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_dataflowsnapshot FORCE ROW LEVEL SECURITY;
CREATE POLICY core_dataflowsnapshot_runtime_scope ON core_dataflowsnapshot
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_dataflowsnapshot_runtime_scope ON core_dataflowsnapshot;
ALTER TABLE core_dataflowsnapshot NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_dataflowsnapshot DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_dataflowsnap_validate ON core_dataflowsnapshot;
DROP FUNCTION IF EXISTS tekdocs_validate_data_flow_snapshot();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0122_data_flow_snapshots")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
