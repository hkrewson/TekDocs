from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_inbox_notification() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_outboxevent event
    WHERE event.id=NEW.event_id
      AND event.tenant_id=NEW.tenant_id
      AND event.organization_id=NEW.organization_id
  ) THEN RAISE EXCEPTION 'inbox notification event scope mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'inbox notification organization scope mismatch'; END IF;
  IF NEW.surface = 'client_portal' THEN
    IF NOT EXISTS (
      SELECT 1 FROM accounts_tenantmembership membership
      WHERE membership.tenant_id=NEW.tenant_id
        AND membership.user_id=NEW.recipient_id
        AND membership.organization_id=NEW.organization_id
        AND membership.role IN ('client_administrator', 'client_user')
    ) THEN RAISE EXCEPTION 'client inbox recipient scope mismatch'; END IF;
  ELSIF NEW.surface = 'msp' THEN
    IF NOT EXISTS (
      SELECT 1 FROM core_installationstate installation
      WHERE installation.id=1
        AND installation.tenant_id=NEW.tenant_id
        AND installation.owner_id=NEW.recipient_id
      UNION ALL
      SELECT 1 FROM accounts_tenantmembership membership
      WHERE membership.tenant_id=NEW.tenant_id
        AND membership.user_id=NEW.recipient_id
        AND membership.organization_id IS NULL
        AND membership.role IN ('administrator', 'technician', 'contributor', 'read_only')
    ) THEN RAISE EXCEPTION 'MSP inbox recipient scope mismatch'; END IF;
  ELSE
    RAISE EXCEPTION 'inbox notification surface is invalid';
  END IF;
  IF NEW.read_at IS NOT NULL AND NEW.read_at < NEW.created_at
  THEN RAISE EXCEPTION 'inbox read time precedes creation'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_inbox_notification() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'inbox notifications cannot be deleted';
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
     OR NEW.event_id IS DISTINCT FROM OLD.event_id
     OR NEW.recipient_id IS DISTINCT FROM OLD.recipient_id
     OR NEW.surface IS DISTINCT FROM OLD.surface
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'inbox notification identity is immutable'; END IF;
  IF NEW.read_at IS NOT NULL AND NEW.read_at < NEW.created_at
  THEN RAISE EXCEPTION 'inbox read time precedes creation'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_inbox_notification_validate
  BEFORE INSERT ON core_inboxnotification
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_inbox_notification();
CREATE TRIGGER core_inbox_notification_guard
  BEFORE UPDATE OR DELETE ON core_inboxnotification
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_inbox_notification();

ALTER TABLE core_inboxnotification ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_inboxnotification FORCE ROW LEVEL SECURITY;
CREATE POLICY core_inboxnotification_runtime_scope ON core_inboxnotification
  USING (tenant_id=tekdocs_current_tenant_id())
  WITH CHECK (tenant_id=tekdocs_current_tenant_id());
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_inboxnotification_runtime_scope ON core_inboxnotification;
ALTER TABLE core_inboxnotification DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_inbox_notification_guard ON core_inboxnotification;
DROP TRIGGER IF EXISTS core_inbox_notification_validate ON core_inboxnotification;
DROP FUNCTION IF EXISTS tekdocs_guard_inbox_notification();
DROP FUNCTION IF EXISTS tekdocs_validate_inbox_notification();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_client_portal_scope_guards"),
        ("core", "0068_inbox_notifications"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
