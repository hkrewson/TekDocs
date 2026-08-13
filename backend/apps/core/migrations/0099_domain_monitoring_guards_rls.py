# ruff: noqa: E501
from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_domain_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.tenant_id=NEW.tenant_id AND d.workspace_id=NEW.workspace_id AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'domain monitor run scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.domain_id<>OLD.domain_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at
    OR OLD.state IN ('succeeded','failed')
  ) THEN RAISE EXCEPTION 'domain monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_monitor_run_guard BEFORE INSERT OR UPDATE ON core_domainmonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_monitor_run();

CREATE FUNCTION tekdocs_guard_domain_monitor_alert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'domain monitoring alerts are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_domainmonitorrun r WHERE r.id=NEW.run_id AND r.domain_id=NEW.domain_id AND r.workspace_id=NEW.workspace_id)
  THEN RAISE EXCEPTION 'domain monitoring alert scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_monitor_alert_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domainmonitoralert FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_monitor_alert();

DROP TRIGGER IF EXISTS core_domain_dns_observation_guard ON core_domaindnsobservation;
DROP FUNCTION IF EXISTS tekdocs_guard_domain_dns_observation();
CREATE FUNCTION tekdocs_guard_domain_dns_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'DNS observations are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.workspace_id=NEW.workspace_id)
    OR (NEW.hostname_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_managedhostname h WHERE h.id=NEW.hostname_id AND h.domain_id=NEW.domain_id AND h.workspace_id=NEW.workspace_id))
  THEN RAISE EXCEPTION 'DNS observation scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_dns_observation_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domaindnsobservation FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_dns_observation();

DROP TRIGGER IF EXISTS core_domain_review_guard ON core_domainreviewevent;
DROP FUNCTION IF EXISTS tekdocs_guard_domain_review_event();
CREATE FUNCTION tekdocs_guard_domain_review_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'domain review events are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.workspace_id=NEW.workspace_id)
    OR (NEW.reviewed_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.reviewed_by_id))
  THEN RAISE EXCEPTION 'domain review event scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_review_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domainreviewevent FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_review_event();

ALTER TABLE core_domainmonitorrun ENABLE ROW LEVEL SECURITY; ALTER TABLE core_domainmonitorrun FORCE ROW LEVEL SECURITY;
ALTER TABLE core_domainmonitoralert ENABLE ROW LEVEL SECURITY; ALTER TABLE core_domainmonitoralert FORCE ROW LEVEL SECURITY;
CREATE POLICY core_domainmonitorrun_runtime_scope ON core_domainmonitorrun USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
CREATE POLICY core_domainmonitoralert_runtime_scope ON core_domainmonitoralert USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
"""

REVERSE = r"""
DROP POLICY IF EXISTS core_domainmonitoralert_runtime_scope ON core_domainmonitoralert; DROP POLICY IF EXISTS core_domainmonitorrun_runtime_scope ON core_domainmonitorrun;
ALTER TABLE core_domainmonitoralert DISABLE ROW LEVEL SECURITY; ALTER TABLE core_domainmonitorrun DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_domain_monitor_alert_guard ON core_domainmonitoralert; DROP FUNCTION IF EXISTS tekdocs_guard_domain_monitor_alert();
DROP TRIGGER IF EXISTS core_domain_monitor_run_guard ON core_domainmonitorrun; DROP FUNCTION IF EXISTS tekdocs_guard_domain_monitor_run();
DROP TRIGGER IF EXISTS core_domain_dns_observation_guard ON core_domaindnsobservation; DROP FUNCTION IF EXISTS tekdocs_guard_domain_dns_observation();
CREATE FUNCTION tekdocs_guard_domain_dns_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'DNS observations are immutable'; END IF;
  IF NEW.hostname_id IS NULL OR NOT EXISTS (SELECT 1 FROM core_managedhostname h WHERE h.id=NEW.hostname_id AND h.workspace_id=NEW.workspace_id)
  THEN RAISE EXCEPTION 'DNS observation scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_dns_observation_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domaindnsobservation FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_dns_observation();
DROP TRIGGER IF EXISTS core_domain_review_guard ON core_domainreviewevent; DROP FUNCTION IF EXISTS tekdocs_guard_domain_review_event();
CREATE FUNCTION tekdocs_guard_domain_review_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'domain review events are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.workspace_id=NEW.workspace_id)
    OR NEW.reviewed_by_id IS NULL
    OR NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.reviewed_by_id)
  THEN RAISE EXCEPTION 'domain review event scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_review_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domainreviewevent FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_review_event();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0098_domain_monitoring")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
