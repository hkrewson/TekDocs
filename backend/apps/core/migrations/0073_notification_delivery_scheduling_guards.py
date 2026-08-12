from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_notification_email_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_inboxnotification notification
    WHERE notification.id=NEW.notification_id AND notification.tenant_id=NEW.tenant_id
      AND notification.organization_id=NEW.organization_id
      AND notification.recipient_id=NEW.recipient_id AND notification.surface=NEW.surface
  ) THEN RAISE EXCEPTION 'notification email scope mismatch'; END IF;
  IF NEW.state <> 'pending' OR NEW.attempts <> 0 OR NEW.retry_generation <> 0
     OR NEW.locked_at IS NOT NULL OR NEW.delivered_at IS NOT NULL
     OR NEW.last_attempt_at IS NOT NULL OR NEW.last_error_code <> ''
  THEN RAISE EXCEPTION 'notification email must begin pending'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_guard_notification_email() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'notification email deliveries cannot be deleted'; END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
     OR NEW.notification_id IS DISTINCT FROM OLD.notification_id OR NEW.recipient_id IS DISTINCT FROM OLD.recipient_id
     OR NEW.surface IS DISTINCT FROM OLD.surface OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'notification email identity is immutable'; END IF;
  IF OLD.state IN ('delivered', 'suppressed') THEN RAISE EXCEPTION 'notification email terminal state is immutable'; END IF;
  IF OLD.state = 'dead_letter' THEN
    IF NEW.state <> 'pending' OR NEW.retry_generation <> OLD.retry_generation + 1 OR NEW.attempts <> 0
       OR NEW.locked_at IS NOT NULL OR NEW.delivered_at IS NOT NULL OR NEW.last_attempt_at IS NOT NULL OR NEW.last_error_code <> ''
       OR NOT EXISTS (
         SELECT 1 FROM core_auditevent event WHERE event.tenant_id=OLD.tenant_id
           AND event.entity_id=OLD.id AND event.action='notification.delivery_retried'
           AND jsonb_typeof(event.metadata->'generation')='number'
           AND (event.metadata->>'generation')::integer=NEW.retry_generation
       )
    THEN RAISE EXCEPTION 'notification email retry requires matching audit evidence'; END IF;
    RETURN NEW;
  END IF;
  IF OLD.state = 'pending' AND NEW.state = 'pending' THEN
    IF NEW.attempts IS DISTINCT FROM OLD.attempts OR NEW.locked_at IS DISTINCT FROM OLD.locked_at
       OR NEW.delivered_at IS DISTINCT FROM OLD.delivered_at OR NEW.last_attempt_at IS DISTINCT FROM OLD.last_attempt_at
       OR NEW.last_error_code IS DISTINCT FROM OLD.last_error_code OR NEW.retry_generation IS DISTINCT FROM OLD.retry_generation
    THEN RAISE EXCEPTION 'pending notification email may only be rescheduled'; END IF;
    RETURN NEW;
  END IF;
  IF OLD.state = 'pending' AND NEW.state NOT IN ('processing', 'suppressed')
  THEN RAISE EXCEPTION 'notification email must be claimed before completion'; END IF;
  IF OLD.state = 'processing' AND NEW.state NOT IN ('processing', 'pending', 'delivered', 'suppressed', 'dead_letter')
  THEN RAISE EXCEPTION 'notification email transition is invalid'; END IF;
  IF NEW.last_error_code NOT IN ('', 'smtp_unavailable', 'smtp_rejected', 'recipient_invalid', 'recipient_rejected', 'delivery_failed')
  THEN RAISE EXCEPTION 'notification email error code is invalid'; END IF;
  RETURN NEW;
END $$;
"""

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_notification_email_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_inboxnotification notification
    WHERE notification.id=NEW.notification_id AND notification.tenant_id=NEW.tenant_id
      AND notification.organization_id=NEW.organization_id
      AND notification.recipient_id=NEW.recipient_id AND notification.surface=NEW.surface
  ) THEN RAISE EXCEPTION 'notification email scope mismatch'; END IF;
  IF NEW.state <> 'pending' OR NEW.attempts <> 0 OR NEW.locked_at IS NOT NULL
     OR NEW.delivered_at IS NOT NULL OR NEW.last_error_code <> ''
  THEN RAISE EXCEPTION 'notification email must begin pending'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_guard_notification_email() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'notification email deliveries cannot be deleted'; END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
     OR NEW.notification_id IS DISTINCT FROM OLD.notification_id OR NEW.recipient_id IS DISTINCT FROM OLD.recipient_id
     OR NEW.surface IS DISTINCT FROM OLD.surface OR NEW.created_at IS DISTINCT FROM OLD.created_at
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
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0072_notificationemaildelivery_last_attempt_at_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
