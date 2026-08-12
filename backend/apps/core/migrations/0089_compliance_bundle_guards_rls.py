from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_compliance_bundle() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'compliance evidence bundle is immutable'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
      AND w.tenant_id=NEW.tenant_id
      AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) OR NOT EXISTS (
    SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
      AND e.workspace_id=NEW.workspace_id
      AND e.entity_type='compliance_evidence_bundle'
  ) OR NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id
  ) OR NEW.signature_algorithm <> 'Ed25519'
    OR NEW.content_digest !~ '^[0-9a-f]{64}$'
    OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
  THEN RAISE EXCEPTION 'compliance evidence bundle invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_compbundle_guard BEFORE INSERT OR UPDATE OR DELETE
ON core_complianceevidencebundle FOR EACH ROW
EXECUTE FUNCTION tekdocs_guard_compliance_bundle();
ALTER TABLE core_complianceevidencebundle ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_complianceevidencebundle FORCE ROW LEVEL SECURITY;
CREATE POLICY core_complianceevidencebundle_runtime_scope ON core_complianceevidencebundle
USING (
  workspace_id=tekdocs_current_workspace_id()
  AND tekdocs_scope_matches(tenant_id, organization_id)
)
WITH CHECK (
  workspace_id=tekdocs_current_workspace_id()
  AND tekdocs_scope_matches(tenant_id, organization_id)
);
"""
REVERSE = r"""
DROP POLICY IF EXISTS core_complianceevidencebundle_runtime_scope ON core_complianceevidencebundle;
ALTER TABLE core_complianceevidencebundle DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_compbundle_guard ON core_complianceevidencebundle;
DROP FUNCTION IF EXISTS tekdocs_guard_compliance_bundle();
"""

class Migration(migrations.Migration):
    dependencies = [("core", "0088_compliance_evidence_bundles")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
