# ruff: noqa: E501
from django.db import migrations

SQL = r"""
DROP TRIGGER IF EXISTS core_domain_monitor_run_guard ON core_domainmonitorrun;
CREATE OR REPLACE FUNCTION tekdocs_guard_domain_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'domain monitor runs are retained'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.tenant_id=NEW.tenant_id AND d.workspace_id=NEW.workspace_id AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'domain monitor run scope invalid'; END IF;
  IF NEW.state='succeeded' AND (NEW.evidence_digest !~ '^[0-9a-f]{64}$' OR NEW.caa_digest !~ '^[0-9a-f]{64}$')
  THEN RAISE EXCEPTION 'domain monitor run evidence digest invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.domain_id<>OLD.domain_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at
    OR OLD.state IN ('succeeded','failed')
  ) THEN RAISE EXCEPTION 'domain monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_monitor_run_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domainmonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_monitor_run();

DROP TRIGGER IF EXISTS core_certificate_monitor_run_guard ON core_certificatemonitorrun;
CREATE OR REPLACE FUNCTION tekdocs_guard_certificate_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'certificate monitor runs are retained'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_certificateendpoint e WHERE e.id=NEW.endpoint_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'certificate monitor run scope invalid'; END IF;
  IF NEW.state='succeeded' AND NEW.evidence_digest !~ '^[0-9a-f]{64}$'
  THEN RAISE EXCEPTION 'certificate monitor run evidence digest invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.endpoint_id<>OLD.endpoint_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at
    OR OLD.state IN ('succeeded','failed')
  ) THEN RAISE EXCEPTION 'certificate monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_certificate_monitor_run_guard BEFORE INSERT OR UPDATE OR DELETE ON core_certificatemonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_certificate_monitor_run();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS core_domain_monitor_run_guard ON core_domainmonitorrun;
CREATE OR REPLACE FUNCTION tekdocs_guard_domain_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.tenant_id=NEW.tenant_id AND d.workspace_id=NEW.workspace_id AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'domain monitor run scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.domain_id<>OLD.domain_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at OR OLD.state IN ('succeeded','failed'))
  THEN RAISE EXCEPTION 'domain monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_monitor_run_guard BEFORE INSERT OR UPDATE ON core_domainmonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_monitor_run();
DROP TRIGGER IF EXISTS core_certificate_monitor_run_guard ON core_certificatemonitorrun;
CREATE OR REPLACE FUNCTION tekdocs_guard_certificate_monitor_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'certificate monitor runs are retained'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_certificateendpoint e WHERE e.id=NEW.endpoint_id AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
    OR (NEW.requested_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.requested_by_id))
  THEN RAISE EXCEPTION 'certificate monitor run scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.endpoint_id<>OLD.endpoint_id OR NEW.trigger<>OLD.trigger OR NEW.requested_by_id IS DISTINCT FROM OLD.requested_by_id OR NEW.created_at<>OLD.created_at OR OLD.state IN ('succeeded','failed'))
  THEN RAISE EXCEPTION 'certificate monitor run identity or terminal evidence is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_certificate_monitor_run_guard BEFORE INSERT OR UPDATE OR DELETE ON core_certificatemonitorrun FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_certificate_monitor_run();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0103_monitoring_evidence_constraints")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
