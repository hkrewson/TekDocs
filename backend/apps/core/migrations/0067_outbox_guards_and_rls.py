from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_guard_outbox_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'outbox events cannot be deleted';
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
     OR NEW.topic IS DISTINCT FROM OLD.topic
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.payload IS DISTINCT FROM OLD.payload
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'outbox event identity and payload are immutable'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_outbox_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'outbox organization tenant mismatch'; END IF;
  IF NEW.organization_id IS NULL
  THEN RAISE EXCEPTION 'outbox topic requires organization scope'; END IF;
  IF NEW.topic IN ('client_invitation.issued', 'client_invitation.accepted') THEN
    IF NEW.payload IS DISTINCT FROM jsonb_build_object('role', NEW.payload->>'role')
       OR NEW.payload->>'role' NOT IN ('client_administrator', 'client_user')
    THEN RAISE EXCEPTION 'outbox payload contract mismatch'; END IF;
  ELSIF NEW.topic IN ('document_publication.available', 'document_publication.withdrawn') THEN
    IF NEW.payload IS DISTINCT FROM jsonb_build_object('audience', NEW.payload->>'audience')
       OR NEW.payload->>'audience' <> 'client_visible'
    THEN RAISE EXCEPTION 'outbox payload contract mismatch'; END IF;
  ELSE
    RAISE EXCEPTION 'outbox topic is not allowlisted';
  END IF;
  IF NEW.state <> 'pending' OR NEW.attempts <> 0 OR NEW.locked_at IS NOT NULL
     OR NEW.delivered_at IS NOT NULL OR NEW.last_error_code <> ''
  THEN RAISE EXCEPTION 'outbox event must begin pending'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_outbox_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'outbox delivery receipts are append-only';
END $$;

CREATE FUNCTION tekdocs_validate_outbox_receipt() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_outboxevent event
    WHERE event.id=NEW.event_id AND event.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'outbox receipt tenant mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_outbox_event_validate
  BEFORE INSERT ON core_outboxevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_outbox_event();
CREATE TRIGGER core_outbox_event_guard
  BEFORE UPDATE OR DELETE ON core_outboxevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_outbox_event();
CREATE TRIGGER core_outbox_receipt_validate
  BEFORE INSERT ON core_outboxdeliveryreceipt
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_outbox_receipt();
CREATE TRIGGER core_outbox_receipt_immutable
  BEFORE UPDATE OR DELETE ON core_outboxdeliveryreceipt
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_outbox_receipt();

ALTER TABLE core_outboxevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_outboxevent FORCE ROW LEVEL SECURITY;
CREATE POLICY core_outboxevent_runtime_scope ON core_outboxevent
  USING (tenant_id=tekdocs_current_tenant_id())
  WITH CHECK (tenant_id=tekdocs_current_tenant_id());

ALTER TABLE core_outboxdeliveryreceipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_outboxdeliveryreceipt FORCE ROW LEVEL SECURITY;
CREATE POLICY core_outboxdeliveryreceipt_runtime_scope ON core_outboxdeliveryreceipt
  USING (tenant_id=tekdocs_current_tenant_id())
  WITH CHECK (tenant_id=tekdocs_current_tenant_id());
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_outboxdeliveryreceipt_runtime_scope ON core_outboxdeliveryreceipt;
ALTER TABLE core_outboxdeliveryreceipt DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_outboxevent_runtime_scope ON core_outboxevent;
ALTER TABLE core_outboxevent DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_outbox_receipt_immutable ON core_outboxdeliveryreceipt;
DROP TRIGGER IF EXISTS core_outbox_receipt_validate ON core_outboxdeliveryreceipt;
DROP TRIGGER IF EXISTS core_outbox_event_guard ON core_outboxevent;
DROP TRIGGER IF EXISTS core_outbox_event_validate ON core_outboxevent;
DROP FUNCTION IF EXISTS tekdocs_guard_outbox_receipt();
DROP FUNCTION IF EXISTS tekdocs_validate_outbox_receipt();
DROP FUNCTION IF EXISTS tekdocs_guard_outbox_event();
DROP FUNCTION IF EXISTS tekdocs_validate_outbox_event();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0066_outboxevent_outboxdeliveryreceipt_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
