from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_notification_preference() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.surface = 'client_portal' THEN
    IF NOT EXISTS (
      SELECT 1 FROM accounts_tenantmembership membership
      WHERE membership.tenant_id=NEW.tenant_id
        AND membership.user_id=NEW.user_id
        AND membership.organization_id IS NOT NULL
        AND membership.role IN ('client_administrator', 'client_user')
    ) THEN RAISE EXCEPTION 'client notification preference scope mismatch'; END IF;
  ELSIF NEW.surface = 'msp' THEN
    IF NOT EXISTS (
      SELECT 1 FROM core_installationstate installation
      WHERE installation.id=1
        AND installation.tenant_id=NEW.tenant_id
        AND installation.owner_id=NEW.user_id
      UNION ALL
      SELECT 1 FROM accounts_tenantmembership membership
      WHERE membership.tenant_id=NEW.tenant_id
        AND membership.user_id=NEW.user_id
        AND membership.organization_id IS NULL
        AND membership.role IN ('administrator', 'technician', 'contributor', 'read_only')
    ) THEN RAISE EXCEPTION 'MSP notification preference scope mismatch'; END IF;
  ELSE
    RAISE EXCEPTION 'notification preference surface is invalid';
  END IF;
  IF TG_OP = 'UPDATE' AND (
    NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR NEW.user_id IS DISTINCT FROM OLD.user_id
    OR NEW.surface IS DISTINCT FROM OLD.surface
    OR NEW.created_at IS DISTINCT FROM OLD.created_at
  ) THEN RAISE EXCEPTION 'notification preference identity is immutable'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_notification_preference_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'notification preferences cannot be deleted';
END $$;

CREATE FUNCTION tekdocs_validate_notification_email_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_inboxnotification notification
    WHERE notification.id=NEW.notification_id
      AND notification.tenant_id=NEW.tenant_id
      AND notification.organization_id=NEW.organization_id
      AND notification.recipient_id=NEW.recipient_id
      AND notification.surface=NEW.surface
  ) THEN RAISE EXCEPTION 'notification email scope mismatch'; END IF;
  IF NEW.state <> 'pending' OR NEW.attempts <> 0 OR NEW.locked_at IS NOT NULL
     OR NEW.delivered_at IS NOT NULL OR NEW.last_error_code <> ''
  THEN RAISE EXCEPTION 'notification email must begin pending'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_notification_email() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'notification email deliveries cannot be deleted';
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
     OR NEW.notification_id IS DISTINCT FROM OLD.notification_id
     OR NEW.recipient_id IS DISTINCT FROM OLD.recipient_id
     OR NEW.surface IS DISTINCT FROM OLD.surface
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'notification email identity is immutable'; END IF;
  IF OLD.state IN ('delivered', 'suppressed', 'dead_letter')
  THEN RAISE EXCEPTION 'notification email terminal state is immutable'; END IF;
  IF OLD.state = 'pending' AND NEW.state <> 'processing'
  THEN RAISE EXCEPTION 'notification email must be claimed before completion'; END IF;
  IF OLD.state = 'processing' AND NEW.state NOT IN ('processing', 'pending', 'delivered', 'suppressed', 'dead_letter')
  THEN RAISE EXCEPTION 'notification email transition is invalid'; END IF;
  IF NEW.last_error_code NOT IN ('', 'smtp_unavailable', 'smtp_rejected', 'recipient_invalid', 'recipient_rejected', 'delivery_failed')
  THEN RAISE EXCEPTION 'notification email error code is invalid'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_notification_preference_validate
  BEFORE INSERT OR UPDATE ON core_notificationpreference
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_notification_preference();
CREATE TRIGGER core_notification_preference_no_delete
  BEFORE DELETE ON core_notificationpreference
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_notification_preference_delete();
CREATE TRIGGER core_notification_email_validate_insert
  BEFORE INSERT ON core_notificationemaildelivery
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_notification_email_insert();
CREATE TRIGGER core_notification_email_guard
  BEFORE UPDATE OR DELETE ON core_notificationemaildelivery
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_notification_email();

ALTER TABLE core_notificationpreference ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_notificationpreference FORCE ROW LEVEL SECURITY;
CREATE POLICY core_notificationpreference_runtime_scope ON core_notificationpreference
  USING (tenant_id=tekdocs_current_tenant_id())
  WITH CHECK (tenant_id=tekdocs_current_tenant_id());
ALTER TABLE core_notificationemaildelivery ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_notificationemaildelivery FORCE ROW LEVEL SECURITY;
CREATE POLICY core_notificationemaildelivery_runtime_scope ON core_notificationemaildelivery
  USING (tenant_id=tekdocs_current_tenant_id())
  WITH CHECK (tenant_id=tekdocs_current_tenant_id());
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_notificationemaildelivery_runtime_scope ON core_notificationemaildelivery;
ALTER TABLE core_notificationemaildelivery DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_notificationpreference_runtime_scope ON core_notificationpreference;
ALTER TABLE core_notificationpreference DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_notification_email_guard ON core_notificationemaildelivery;
DROP TRIGGER IF EXISTS core_notification_email_validate_insert ON core_notificationemaildelivery;
DROP TRIGGER IF EXISTS core_notification_preference_no_delete ON core_notificationpreference;
DROP TRIGGER IF EXISTS core_notification_preference_validate ON core_notificationpreference;
DROP FUNCTION IF EXISTS tekdocs_guard_notification_email();
DROP FUNCTION IF EXISTS tekdocs_validate_notification_email_insert();
DROP FUNCTION IF EXISTS tekdocs_guard_notification_preference_delete();
DROP FUNCTION IF EXISTS tekdocs_validate_notification_preference();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0070_notificationemaildelivery_notificationpreference")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
