from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_compliance_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE catalog_framework uuid; entry_framework uuid; entry_control uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
    AND w.tenant_id=NEW.tenant_id AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'compliance workspace scope mismatch'; END IF;

  IF TG_TABLE_NAME='core_complianceframework' THEN
    IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.entity_type='compliance_framework'
      AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id
      AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance framework entity scope mismatch'; END IF;
    IF NEW.current_revision_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM core_compliancecatalogrevision r WHERE r.id=NEW.current_revision_id
        AND r.framework_id=NEW.id AND r.tenant_id=NEW.tenant_id AND r.workspace_id=NEW.workspace_id
        AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance current revision scope mismatch'; END IF;
    IF TG_OP='UPDATE' AND OLD.current_revision_id IS NOT NULL
      AND NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id
      AND NOT EXISTS (
        SELECT 1 FROM core_compliancecatalogrevision prior
        JOIN core_compliancecatalogrevision next ON next.id=NEW.current_revision_id
        WHERE prior.id=OLD.current_revision_id AND next.framework_id=NEW.id
          AND next.revision_number=prior.revision_number + 1)
    THEN RAISE EXCEPTION 'compliance current revision must advance monotonically'; END IF;
    IF TG_OP='UPDATE' AND (OLD.tenant_id, OLD.workspace_id, OLD.organization_id, OLD.entity_id)
      IS DISTINCT FROM (NEW.tenant_id, NEW.workspace_id, NEW.organization_id, NEW.entity_id)
    THEN RAISE EXCEPTION 'compliance framework identity is immutable'; END IF;
  ELSIF TG_TABLE_NAME='core_compliancecontrol' THEN
    IF NOT EXISTS (SELECT 1 FROM core_complianceframework f WHERE f.id=NEW.framework_id
      AND f.tenant_id=NEW.tenant_id AND f.workspace_id=NEW.workspace_id
      AND f.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance control framework scope mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.entity_type='compliance_control'
      AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id
      AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance control entity scope mismatch'; END IF;
  ELSIF TG_TABLE_NAME='core_compliancecatalogrevision' THEN
    IF NOT EXISTS (SELECT 1 FROM core_complianceframework f WHERE f.id=NEW.framework_id
      AND f.tenant_id=NEW.tenant_id AND f.workspace_id=NEW.workspace_id
      AND f.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance catalog framework scope mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
    THEN RAISE EXCEPTION 'compliance catalog creator scope mismatch'; END IF;
  ELSIF TG_TABLE_NAME='core_compliancecontrolrevision' THEN
    IF NOT EXISTS (SELECT 1 FROM core_compliancecontrol c WHERE c.id=NEW.control_id
      AND c.tenant_id=NEW.tenant_id AND c.workspace_id=NEW.workspace_id
      AND c.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance control revision scope mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
    THEN RAISE EXCEPTION 'compliance control creator scope mismatch'; END IF;
  ELSE
    SELECT r.framework_id INTO catalog_framework FROM core_compliancecatalogrevision r
      WHERE r.id=NEW.catalog_revision_id AND r.tenant_id=NEW.tenant_id AND r.workspace_id=NEW.workspace_id
      AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id;
    SELECT c.framework_id, c.id INTO entry_framework, entry_control
      FROM core_compliancecontrolrevision cr JOIN core_compliancecontrol c ON c.id=cr.control_id
      WHERE cr.id=NEW.control_revision_id AND cr.tenant_id=NEW.tenant_id AND cr.workspace_id=NEW.workspace_id
      AND cr.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND c.framework_id=catalog_framework;
    IF catalog_framework IS NULL OR entry_framework IS NULL OR entry_control IS NULL
    THEN RAISE EXCEPTION 'compliance catalog entry scope mismatch'; END IF;
    IF EXISTS (SELECT 1 FROM core_compliancecatalogentry e
      JOIN core_compliancecontrolrevision er ON er.id=e.control_revision_id
      WHERE e.catalog_revision_id=NEW.catalog_revision_id AND er.control_id=entry_control AND e.id<>NEW.id)
    THEN RAISE EXCEPTION 'compliance catalog contains duplicate stable control'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_compliance_retained() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained compliance record is immutable'; END $$;

CREATE TRIGGER core_compfw_validate BEFORE INSERT OR UPDATE ON core_complianceframework
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_scope();
CREATE TRIGGER core_compfw_retain BEFORE DELETE ON core_complianceframework
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_retained();
CREATE TRIGGER core_compctl_validate BEFORE INSERT ON core_compliancecontrol
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_scope();
CREATE TRIGGER core_compctl_retain BEFORE UPDATE OR DELETE ON core_compliancecontrol
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_retained();
CREATE TRIGGER core_compcat_validate BEFORE INSERT ON core_compliancecatalogrevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_scope();
CREATE TRIGGER core_compcat_retain BEFORE UPDATE OR DELETE ON core_compliancecatalogrevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_retained();
CREATE TRIGGER core_compctlrev_validate BEFORE INSERT ON core_compliancecontrolrevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_scope();
CREATE TRIGGER core_compctlrev_retain BEFORE UPDATE OR DELETE ON core_compliancecontrolrevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_retained();
CREATE TRIGGER core_compentry_validate BEFORE INSERT ON core_compliancecatalogentry
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_scope();
CREATE TRIGGER core_compentry_retain BEFORE UPDATE OR DELETE ON core_compliancecatalogentry
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_retained();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'core_complianceframework','core_compliancecatalogrevision','core_compliancecontrol',
    'core_compliancecontrolrevision','core_compliancecatalogentry'
  ] LOOP
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
  FOREACH table_name IN ARRAY ARRAY[
    'core_complianceframework','core_compliancecatalogrevision','core_compliancecontrol',
    'core_compliancecontrolrevision','core_compliancecatalogentry'
  ] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_compentry_retain ON core_compliancecatalogentry;
DROP TRIGGER IF EXISTS core_compentry_validate ON core_compliancecatalogentry;
DROP TRIGGER IF EXISTS core_compctlrev_retain ON core_compliancecontrolrevision;
DROP TRIGGER IF EXISTS core_compctlrev_validate ON core_compliancecontrolrevision;
DROP TRIGGER IF EXISTS core_compcat_retain ON core_compliancecatalogrevision;
DROP TRIGGER IF EXISTS core_compcat_validate ON core_compliancecatalogrevision;
DROP TRIGGER IF EXISTS core_compctl_retain ON core_compliancecontrol;
DROP TRIGGER IF EXISTS core_compctl_validate ON core_compliancecontrol;
DROP TRIGGER IF EXISTS core_compfw_retain ON core_complianceframework;
DROP TRIGGER IF EXISTS core_compfw_validate ON core_complianceframework;
DROP FUNCTION IF EXISTS tekdocs_guard_compliance_retained();
DROP FUNCTION IF EXISTS tekdocs_validate_compliance_scope();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0080_compliancecatalogrevision_compliancecontrol_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
