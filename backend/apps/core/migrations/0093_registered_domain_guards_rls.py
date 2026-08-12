from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_registered_domain() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
      AND w.tenant_id=NEW.tenant_id
      AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) OR NOT EXISTS (
    SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
      AND e.workspace_id=NEW.workspace_id AND e.entity_type='registered_domain'
  ) OR NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id
  ) OR (
    NEW.owner_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.owner_id
    )
  ) OR (
    NEW.registrar_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM core_organization o JOIN core_entity e ON e.id=o.entity_id
      WHERE o.id=NEW.registrar_id AND o.tenant_id=NEW.tenant_id AND e.archived_at IS NULL
    )
  ) THEN RAISE EXCEPTION 'registered domain scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id
    OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.entity_id<>OLD.entity_id OR NEW.created_by_id<>OLD.created_by_id
  ) THEN RAISE EXCEPTION 'registered domain identity is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_registered_domain_guard BEFORE INSERT OR UPDATE ON core_registereddomain
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_registered_domain();
ALTER TABLE core_registereddomain ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_registereddomain FORCE ROW LEVEL SECURITY;
CREATE POLICY core_registereddomain_runtime_scope ON core_registereddomain
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
DROP POLICY IF EXISTS core_registereddomain_runtime_scope ON core_registereddomain;
ALTER TABLE core_registereddomain DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_registered_domain_guard ON core_registereddomain;
DROP FUNCTION IF EXISTS tekdocs_guard_registered_domain();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0092_registered_domains")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
