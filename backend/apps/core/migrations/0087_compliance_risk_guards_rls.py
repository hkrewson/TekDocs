from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_compliance_risk_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id
    AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'compliance risk workspace mismatch'; END IF;
  IF TG_TABLE_NAME='core_compliancerisk' THEN
    IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
      AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND e.entity_type='compliance_risk')
    THEN RAISE EXCEPTION 'compliance risk entity mismatch'; END IF;
    IF NEW.assignment_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_compliancecontrolassignment a
      WHERE a.id=NEW.assignment_id AND a.tenant_id=NEW.tenant_id AND a.workspace_id=NEW.workspace_id
        AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance risk assignment mismatch'; END IF;
    IF NEW.owner_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.owner_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance risk owner mismatch'; END IF;
    IF (NEW.status='accepted') <> (NEW.treatment='accept')
      OR (NEW.status='accepted') <> (NEW.accepted_by_id IS NOT NULL AND NEW.accepted_at IS NOT NULL)
    THEN RAISE EXCEPTION 'compliance risk acceptance mismatch'; END IF;
    IF NEW.accepted_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.accepted_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance risk accepter mismatch'; END IF;
    IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.workspace_id,OLD.organization_id,OLD.entity_id)
      IS DISTINCT FROM (NEW.tenant_id,NEW.workspace_id,NEW.organization_id,NEW.entity_id)
    THEN RAISE EXCEPTION 'compliance risk identity is immutable'; END IF;
  ELSE
    IF NOT EXISTS (SELECT 1 FROM core_compliancerisk r
      WHERE r.id=NEW.risk_id AND r.tenant_id=NEW.tenant_id AND r.workspace_id=NEW.workspace_id
        AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance risk event mismatch'; END IF;
    IF (SELECT a.control_revision_id FROM core_compliancerisk r
      LEFT JOIN core_compliancecontrolassignment a ON a.id=r.assignment_id WHERE r.id=NEW.risk_id)
      IS DISTINCT FROM NEW.control_revision_id
    THEN RAISE EXCEPTION 'compliance risk control revision mismatch'; END IF;
    IF (NEW.status='accepted') <> (NEW.treatment='accept')
    THEN RAISE EXCEPTION 'compliance risk event acceptance mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.recorded_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance risk recorder mismatch'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_compliance_risk_event_retained() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained compliance risk event is immutable'; END $$;
CREATE TRIGGER core_comprisk_validate BEFORE INSERT OR UPDATE ON core_compliancerisk
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_risk_scope();
CREATE TRIGGER core_compriskev_validate BEFORE INSERT ON core_complianceriskevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_risk_scope();
CREATE TRIGGER core_compriskev_retain BEFORE UPDATE OR DELETE ON core_complianceriskevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_risk_event_retained();
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_compliancerisk','core_complianceriskevent'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('CREATE POLICY %I_runtime_scope ON %I USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))', table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_compliancerisk','core_complianceriskevent'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_compriskev_retain ON core_complianceriskevent;
DROP TRIGGER IF EXISTS core_compriskev_validate ON core_complianceriskevent;
DROP TRIGGER IF EXISTS core_comprisk_validate ON core_compliancerisk;
DROP FUNCTION IF EXISTS tekdocs_guard_compliance_risk_event_retained();
DROP FUNCTION IF EXISTS tekdocs_validate_compliance_risk_scope();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0086_compliance_risks")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
