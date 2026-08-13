# ruff: noqa: E501
from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_certificate_endpoint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'certificate endpoints must be archived'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.entity_type='certificate_endpoint')
    OR NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.tenant_id=NEW.tenant_id AND d.workspace_id=NEW.workspace_id AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.hostname_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_managedhostname h WHERE h.id=NEW.hostname_id AND h.domain_id=NEW.domain_id AND h.workspace_id=NEW.workspace_id AND h.organization_id IS NOT DISTINCT FROM NEW.organization_id))
    OR NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
    OR NEW.port <> (CASE NEW.protocol WHEN 'https' THEN 443 WHEN 'smtps' THEN 465 WHEN 'imaps' THEN 993 WHEN 'pop3s' THEN 995 ELSE 0 END)
  THEN RAISE EXCEPTION 'certificate endpoint scope or protocol invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.entity_id<>OLD.entity_id OR NEW.domain_id<>OLD.domain_id OR NEW.hostname_id IS DISTINCT FROM OLD.hostname_id
    OR NEW.protocol<>OLD.protocol OR NEW.port<>OLD.port OR NEW.created_by_id<>OLD.created_by_id OR NEW.created_at<>OLD.created_at
  ) THEN RAISE EXCEPTION 'certificate endpoint identity is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_certificate_endpoint_guard BEFORE INSERT OR UPDATE OR DELETE ON core_certificateendpoint FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_certificate_endpoint();

CREATE FUNCTION tekdocs_guard_certificate_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'certificate monitor runs are retained'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_certificateendpoint e WHERE e.id=NEW.endpoint_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'certificate monitor run scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.endpoint_id<>OLD.endpoint_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at
    OR OLD.state IN ('succeeded','failed')
  ) THEN RAISE EXCEPTION 'certificate monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_certificate_monitor_run_guard BEFORE INSERT OR UPDATE OR DELETE ON core_certificatemonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_certificate_monitor_run();

CREATE FUNCTION tekdocs_guard_certificate_monitor_alert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'certificate monitoring alerts are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_certificatemonitorrun r WHERE r.id=NEW.run_id AND r.endpoint_id=NEW.endpoint_id AND r.tenant_id=NEW.tenant_id AND r.workspace_id=NEW.workspace_id AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'certificate monitoring alert scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_certificate_monitor_alert_guard BEFORE INSERT OR UPDATE OR DELETE ON core_certificatemonitoralert FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_certificate_monitor_alert();

ALTER TABLE core_certificateendpoint ENABLE ROW LEVEL SECURITY; ALTER TABLE core_certificateendpoint FORCE ROW LEVEL SECURITY;
ALTER TABLE core_certificatemonitorrun ENABLE ROW LEVEL SECURITY; ALTER TABLE core_certificatemonitorrun FORCE ROW LEVEL SECURITY;
ALTER TABLE core_certificatemonitoralert ENABLE ROW LEVEL SECURITY; ALTER TABLE core_certificatemonitoralert FORCE ROW LEVEL SECURITY;
CREATE POLICY core_certificateendpoint_runtime_scope ON core_certificateendpoint USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
CREATE POLICY core_certificatemonitorrun_runtime_scope ON core_certificatemonitorrun USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
CREATE POLICY core_certificatemonitoralert_runtime_scope ON core_certificatemonitoralert USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
"""

REVERSE = r"""
DROP POLICY IF EXISTS core_certificatemonitoralert_runtime_scope ON core_certificatemonitoralert;
DROP POLICY IF EXISTS core_certificatemonitorrun_runtime_scope ON core_certificatemonitorrun;
DROP POLICY IF EXISTS core_certificateendpoint_runtime_scope ON core_certificateendpoint;
ALTER TABLE core_certificatemonitoralert DISABLE ROW LEVEL SECURITY;
ALTER TABLE core_certificatemonitorrun DISABLE ROW LEVEL SECURITY;
ALTER TABLE core_certificateendpoint DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_certificate_monitor_alert_guard ON core_certificatemonitoralert; DROP FUNCTION IF EXISTS tekdocs_guard_certificate_monitor_alert();
DROP TRIGGER IF EXISTS core_certificate_monitor_run_guard ON core_certificatemonitorrun; DROP FUNCTION IF EXISTS tekdocs_guard_certificate_monitor_run();
DROP TRIGGER IF EXISTS core_certificate_endpoint_guard ON core_certificateendpoint; DROP FUNCTION IF EXISTS tekdocs_guard_certificate_endpoint();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0100_certificate_monitoring")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
