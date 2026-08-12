from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_guard_webhook_endpoint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NOT EXISTS (SELECT 1 FROM core_organization o WHERE o.id=NEW.organization_id AND o.tenant_id=NEW.tenant_id)
    THEN RAISE EXCEPTION 'webhook endpoint organization scope mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.user_id=NEW.created_by_id
      AND m.tenant_id=NEW.tenant_id)
    THEN RAISE EXCEPTION 'webhook endpoint creator scope mismatch'; END IF;
  ELSE
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
      OR NEW.direction IS DISTINCT FROM OLD.direction OR NEW.name IS DISTINCT FROM OLD.name
      OR NEW.url IS DISTINCT FROM OLD.url OR NEW.topics IS DISTINCT FROM OLD.topics
      OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN RAISE EXCEPTION 'webhook endpoint identity and destination are immutable'; END IF;
    IF NEW.secret_generation < OLD.secret_generation OR NEW.secret_generation > OLD.secret_generation + 1
    THEN RAISE EXCEPTION 'webhook secret generation must advance exactly once'; END IF;
    IF (NEW.secret_generation=OLD.secret_generation) <> (NEW.secret_envelope IS NOT DISTINCT FROM OLD.secret_envelope
      AND NEW.secret_prefix IS NOT DISTINCT FROM OLD.secret_prefix)
    THEN RAISE EXCEPTION 'webhook signing material and generation must rotate together'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_webhook_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_webhookendpoint e WHERE e.id=NEW.endpoint_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id=NEW.organization_id AND e.direction='outbound')
  THEN RAISE EXCEPTION 'webhook delivery endpoint scope mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_outboxevent e WHERE e.id=NEW.event_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id=NEW.organization_id)
  THEN RAISE EXCEPTION 'webhook delivery event scope mismatch'; END IF;
  IF NEW.state<>'pending' OR NEW.attempts<>0 OR NEW.locked_at IS NOT NULL OR NEW.delivered_at IS NOT NULL
    OR NEW.last_attempt_at IS NOT NULL OR NEW.response_status IS NOT NULL OR NEW.last_error_code<>''
  THEN RAISE EXCEPTION 'webhook delivery must begin pending'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_webhook_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'webhook deliveries cannot be deleted'; END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.endpoint_id IS DISTINCT FROM OLD.endpoint_id OR NEW.event_id IS DISTINCT FROM OLD.event_id
    OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.attempts < OLD.attempts
  THEN RAISE EXCEPTION 'webhook delivery identity and attempt history are immutable'; END IF;
  IF OLD.state='delivered' AND NEW IS DISTINCT FROM OLD
  THEN RAISE EXCEPTION 'delivered webhook records are immutable'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_webhook_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_webhookendpoint e WHERE e.id=NEW.endpoint_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id=NEW.organization_id AND e.direction='inbound')
  THEN RAISE EXCEPTION 'webhook receipt endpoint scope mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_webhook_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'webhook inbound receipts are append-only'; END $$;

CREATE TRIGGER core_webhook_endpoint_guard BEFORE INSERT OR UPDATE ON core_webhookendpoint
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_webhook_endpoint();
CREATE TRIGGER core_webhook_delivery_validate BEFORE INSERT ON core_webhookoutbounddelivery
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_webhook_delivery();
CREATE TRIGGER core_webhook_delivery_guard BEFORE UPDATE OR DELETE ON core_webhookoutbounddelivery
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_webhook_delivery();
CREATE TRIGGER core_webhook_receipt_validate BEFORE INSERT ON core_webhookinboundreceipt
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_webhook_receipt();
CREATE TRIGGER core_webhook_receipt_guard BEFORE UPDATE OR DELETE ON core_webhookinboundreceipt
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_webhook_receipt();

ALTER TABLE core_webhookoutbounddelivery ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_webhookoutbounddelivery FORCE ROW LEVEL SECURITY;
CREATE POLICY core_webhookoutbounddelivery_runtime_scope ON core_webhookoutbounddelivery
  USING (tenant_id=tekdocs_current_tenant_id()) WITH CHECK (tenant_id=tekdocs_current_tenant_id());
ALTER TABLE core_webhookinboundreceipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_webhookinboundreceipt FORCE ROW LEVEL SECURITY;
CREATE POLICY core_webhookinboundreceipt_runtime_scope ON core_webhookinboundreceipt
  USING (tenant_id=tekdocs_current_tenant_id()) WITH CHECK (tenant_id=tekdocs_current_tenant_id());
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_webhookinboundreceipt_runtime_scope ON core_webhookinboundreceipt;
ALTER TABLE core_webhookinboundreceipt DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_webhookoutbounddelivery_runtime_scope ON core_webhookoutbounddelivery;
ALTER TABLE core_webhookoutbounddelivery DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_webhook_receipt_guard ON core_webhookinboundreceipt;
DROP TRIGGER IF EXISTS core_webhook_receipt_validate ON core_webhookinboundreceipt;
DROP TRIGGER IF EXISTS core_webhook_delivery_guard ON core_webhookoutbounddelivery;
DROP TRIGGER IF EXISTS core_webhook_delivery_validate ON core_webhookoutbounddelivery;
DROP TRIGGER IF EXISTS core_webhook_endpoint_guard ON core_webhookendpoint;
DROP FUNCTION IF EXISTS tekdocs_guard_webhook_receipt();
DROP FUNCTION IF EXISTS tekdocs_validate_webhook_receipt();
DROP FUNCTION IF EXISTS tekdocs_guard_webhook_delivery();
DROP FUNCTION IF EXISTS tekdocs_validate_webhook_delivery();
DROP FUNCTION IF EXISTS tekdocs_guard_webhook_endpoint();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0076_webhookendpoint_webhookinboundreceipt_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
