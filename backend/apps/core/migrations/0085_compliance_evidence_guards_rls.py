from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_compliance_evidence_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id
    AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'compliance evidence workspace mismatch'; END IF;
  IF TG_TABLE_NAME='core_complianceevidence' THEN
    IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
      AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND e.entity_type='compliance_evidence')
    THEN RAISE EXCEPTION 'compliance evidence entity mismatch'; END IF;
    IF NEW.source_entity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_entity e
      WHERE e.id=NEW.source_entity_id AND e.workspace_id=NEW.workspace_id AND e.archived_at IS NULL)
    THEN RAISE EXCEPTION 'compliance evidence source mismatch'; END IF;
    IF (NEW.kind='url') <> (NEW.source_url<>'') OR (NEW.kind='entity') <> (NEW.source_entity_id IS NOT NULL)
    THEN RAISE EXCEPTION 'compliance evidence source shape mismatch'; END IF;
    IF NEW.collection_start IS NOT NULL AND NEW.collection_end IS NOT NULL
      AND NEW.collection_end < NEW.collection_start
    THEN RAISE EXCEPTION 'compliance evidence collection window mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance evidence creator mismatch'; END IF;
    IF TG_OP='UPDATE' AND (OLD.tenant_id,OLD.workspace_id,OLD.organization_id,OLD.entity_id,OLD.created_by_id)
      IS DISTINCT FROM (NEW.tenant_id,NEW.workspace_id,NEW.organization_id,NEW.entity_id,NEW.created_by_id)
    THEN RAISE EXCEPTION 'compliance evidence identity is immutable'; END IF;
  ELSIF TG_TABLE_NAME='core_complianceevidencelink' THEN
    IF NOT EXISTS (SELECT 1 FROM core_compliancecontrolassignment a
      WHERE a.id=NEW.assignment_id AND a.tenant_id=NEW.tenant_id AND a.workspace_id=NEW.workspace_id
        AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id AND a.control_revision_id=NEW.control_revision_id)
    THEN RAISE EXCEPTION 'compliance evidence assignment mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM core_complianceevidence e
      WHERE e.id=NEW.evidence_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id
        AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance evidence link mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.linked_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance evidence linker mismatch'; END IF;
  ELSE
    IF NOT EXISTS (SELECT 1 FROM core_complianceevidence e
      WHERE e.id=NEW.evidence_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id
        AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    THEN RAISE EXCEPTION 'compliance evidence review mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m JOIN accounts_user u ON u.id=m.user_id
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.reviewed_by_id AND u.is_active)
    THEN RAISE EXCEPTION 'compliance evidence reviewer mismatch'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_compliance_evidence_retained() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained compliance evidence edge is immutable'; END $$;
CREATE TRIGGER core_compevidence_validate BEFORE INSERT OR UPDATE ON core_complianceevidence
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_evidence_scope();
CREATE TRIGGER core_compevlink_validate BEFORE INSERT ON core_complianceevidencelink
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_evidence_scope();
CREATE TRIGGER core_compevreview_validate BEFORE INSERT ON core_complianceevidencereview
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_compliance_evidence_scope();
CREATE TRIGGER core_compevlink_retain BEFORE UPDATE OR DELETE ON core_complianceevidencelink
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_evidence_retained();
CREATE TRIGGER core_compevreview_retain BEFORE UPDATE OR DELETE ON core_complianceevidencereview
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_compliance_evidence_retained();
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_complianceevidence','core_complianceevidencelink','core_complianceevidencereview'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('CREATE POLICY %I_runtime_scope ON %I USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))', table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_complianceevidence','core_complianceevidencelink','core_complianceevidencereview'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_compevreview_retain ON core_complianceevidencereview;
DROP TRIGGER IF EXISTS core_compevlink_retain ON core_complianceevidencelink;
DROP TRIGGER IF EXISTS core_compevreview_validate ON core_complianceevidencereview;
DROP TRIGGER IF EXISTS core_compevlink_validate ON core_complianceevidencelink;
DROP TRIGGER IF EXISTS core_compevidence_validate ON core_complianceevidence;
DROP FUNCTION IF EXISTS tekdocs_guard_compliance_evidence_retained();
DROP FUNCTION IF EXISTS tekdocs_validate_compliance_evidence_scope();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0084_compliance_evidence")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
