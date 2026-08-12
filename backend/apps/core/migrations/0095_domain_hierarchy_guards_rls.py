# ruff: noqa: E501
from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_managed_hostname() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.workspace_id=NEW.workspace_id)
    OR NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.workspace_id=NEW.workspace_id AND e.entity_type='managed_hostname')
    OR (NEW.parent_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_managedhostname p WHERE p.id=NEW.parent_id AND p.domain_id=NEW.domain_id))
  THEN RAISE EXCEPTION 'managed hostname scope invalid'; END IF;
  IF NEW.parent_id=NEW.id THEN RAISE EXCEPTION 'managed hostname cycle'; END IF;
  IF NEW.parent_id IS NOT NULL AND EXISTS (
    WITH RECURSIVE ancestors AS (
      SELECT id,parent_id FROM core_managedhostname WHERE id=NEW.parent_id
      UNION ALL
      SELECT p.id,p.parent_id FROM core_managedhostname p JOIN ancestors a ON p.id=a.parent_id
    ) SELECT 1 FROM ancestors WHERE id=NEW.id
  ) THEN RAISE EXCEPTION 'managed hostname cycle'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_managed_hostname_guard BEFORE INSERT OR UPDATE ON core_managedhostname FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_managed_hostname();
CREATE FUNCTION tekdocs_guard_domain_dns_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'DNS observations are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_managedhostname h WHERE h.id=NEW.hostname_id AND h.workspace_id=NEW.workspace_id)
  THEN RAISE EXCEPTION 'DNS observation scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_dns_observation_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domaindnsobservation FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_dns_observation();
ALTER TABLE core_managedhostname ENABLE ROW LEVEL SECURITY; ALTER TABLE core_managedhostname FORCE ROW LEVEL SECURITY;
ALTER TABLE core_domaindnsobservation ENABLE ROW LEVEL SECURITY; ALTER TABLE core_domaindnsobservation FORCE ROW LEVEL SECURITY;
CREATE POLICY core_managedhostname_runtime_scope ON core_managedhostname USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
CREATE POLICY core_domaindnsobservation_runtime_scope ON core_domaindnsobservation USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
"""
REVERSE = r"""
DROP POLICY IF EXISTS core_managedhostname_runtime_scope ON core_managedhostname;
DROP POLICY IF EXISTS core_domaindnsobservation_runtime_scope ON core_domaindnsobservation;
ALTER TABLE core_managedhostname DISABLE ROW LEVEL SECURITY; ALTER TABLE core_domaindnsobservation DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_managed_hostname_guard ON core_managedhostname; DROP FUNCTION IF EXISTS tekdocs_guard_managed_hostname();
DROP TRIGGER IF EXISTS core_domain_dns_observation_guard ON core_domaindnsobservation; DROP FUNCTION IF EXISTS tekdocs_guard_domain_dns_observation();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0094_domain_hierarchy")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
