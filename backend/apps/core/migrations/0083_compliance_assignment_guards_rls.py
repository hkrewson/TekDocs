from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_compliance_assignment_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id
    AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'compliance assignment workspace mismatch'; END IF;
  IF TG_TABLE_NAME='core_compliancecontrolassignment' THEN
    IF NOT EXISTS (SELECT 1 FROM core_compliancecontrol c JOIN core_complianceframework f ON f.id=c.framework_id
      JOIN core_compliancecontrolrevision r ON r.control_id=c.id
      WHERE c.id=NEW.control_id AND f.id=NEW.framework_id AND r.id=NEW.control_revision_id
        AND c.tenant_id=NEW.tenant_id AND c.workspace_id=NEW.workspace_id
        AND c.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance assignment control mismatch'; END IF;
    IF NEW.owner_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.owner_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance assignment owner mismatch'; END IF;
    IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.workspace_id,OLD.organization_id,OLD.framework_id,OLD.control_id)
      IS DISTINCT FROM (NEW.tenant_id,NEW.workspace_id,NEW.organization_id,NEW.framework_id,NEW.control_id)
    THEN RAISE EXCEPTION 'compliance assignment identity is immutable'; END IF;
  ELSE
    IF NOT EXISTS (SELECT 1 FROM core_compliancecontrolassignment a
      WHERE a.id=NEW.assignment_id AND a.control_revision_id=NEW.control_revision_id
        AND a.tenant_id=NEW.tenant_id AND a.workspace_id=NEW.workspace_id
        AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance review assignment mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.reviewed_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance reviewer mismatch'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_compliance_review_retained() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained compliance review is immutable'; END $$;
CREATE TRIGGER core_compassign_validate BEFORE INSERT OR UPDATE ON core_compliancecontrolassignment
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_assignment_scope();
CREATE TRIGGER core_compreview_validate BEFORE INSERT ON core_complianceassignmentreview
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_assignment_scope();
CREATE TRIGGER core_compreview_retain BEFORE UPDATE OR DELETE ON core_complianceassignmentreview
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_review_retained();
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_compliancecontrolassignment','core_complianceassignmentreview'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('CREATE POLICY %I_runtime_scope ON %I USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))', table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_compliancecontrolassignment','core_complianceassignmentreview'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_compreview_retain ON core_complianceassignmentreview;
DROP TRIGGER IF EXISTS core_compreview_validate ON core_complianceassignmentreview;
DROP TRIGGER IF EXISTS core_compassign_validate ON core_compliancecontrolassignment;
DROP FUNCTION IF EXISTS tekdocs_guard_compliance_review_retained();
DROP FUNCTION IF EXISTS tekdocs_validate_compliance_assignment_scope();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0082_compliance_assignments_reviews")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
