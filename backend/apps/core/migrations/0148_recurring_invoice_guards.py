from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_guard_recurring_schedule() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF (to_jsonb(NEW) - ARRAY['enabled','updated_at']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['enabled','updated_at']) THEN
      RAISE EXCEPTION 'recurring schedule identity and calendar are immutable';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_contractcost cost
    JOIN core_commercialcontract contract ON contract.id=cost.contract_id
    JOIN core_entity entity ON entity.id=contract.entity_id
    JOIN core_organizationclassification classification ON classification.organization_id=cost.organization_id
    WHERE cost.id=NEW.contract_cost_id AND cost.tenant_id=NEW.tenant_id
      AND cost.organization_id=NEW.organization_id AND contract.tenant_id=NEW.tenant_id
      AND contract.organization_id=NEW.organization_id AND classification.kind='client'
      AND classification.tenant_id=NEW.tenant_id
      AND cost.archived_at IS NULL AND contract.archived_at IS NULL AND entity.archived_at IS NULL
      AND contract.status='active' AND cost.billing_interval=NEW.interval
      AND (cost.starts_on IS NULL OR NEW.anchor>=cost.starts_on)
      AND (contract.starts_on IS NULL OR NEW.anchor>=contract.starts_on)
      AND (cost.ends_on IS NULL OR NEW.ends_on<=cost.ends_on)
      AND (contract.ends_on IS NULL OR NEW.ends_on<=contract.ends_on)
      AND (NEW.ends_on IS NOT NULL OR (cost.ends_on IS NULL AND contract.ends_on IS NULL))
  ) THEN RAISE EXCEPTION 'recurring schedule source scope or effective dates invalid'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership WHERE tenant_id=NEW.tenant_id AND user_id=NEW.created_by_id)
  THEN RAISE EXCEPTION 'recurring schedule actor scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_recurring_schedule_guard BEFORE INSERT OR UPDATE ON core_recurringinvoiceschedule
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_recurring_schedule();

CREATE FUNCTION tekdocs_guard_recurring_terms() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_recurringinvoiceschedule schedule
    JOIN core_contractcost cost ON cost.id=schedule.contract_cost_id
    WHERE schedule.id=NEW.schedule_id AND schedule.tenant_id=NEW.tenant_id
      AND schedule.organization_id=NEW.organization_id AND cost.currency=NEW.currency
  ) THEN RAISE EXCEPTION 'recurring terms scope or currency invalid'; END IF;
  IF NEW.tax_rate_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_taxrate WHERE id=NEW.tax_rate_id AND tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'recurring terms tax scope invalid'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership WHERE tenant_id=NEW.tenant_id AND user_id=NEW.approved_by_id)
  THEN RAISE EXCEPTION 'recurring terms actor scope invalid'; END IF;
  IF NEW.source_digest !~ '^[a-f0-9]{64}$' OR jsonb_typeof(NEW.source_snapshot)<>'object'
  THEN RAISE EXCEPTION 'recurring source snapshot invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_recurring_terms_guard BEFORE INSERT ON core_recurringinvoiceterms
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_recurring_terms();

CREATE FUNCTION tekdocs_guard_recurring_period() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE calendar core_recurringinvoiceschedule%ROWTYPE;
DECLARE month_offset integer;
DECLARE stride integer;
DECLARE expected_start date;
DECLARE expected_end date;
BEGIN
  SELECT * INTO calendar FROM core_recurringinvoiceschedule WHERE id=NEW.schedule_id FOR UPDATE;
  IF NOT FOUND OR calendar.tenant_id<>NEW.tenant_id OR calendar.organization_id<>NEW.organization_id
     OR NOT calendar.enabled THEN RAISE EXCEPTION 'recurring period schedule scope invalid'; END IF;
  stride := CASE calendar.interval WHEN 'monthly' THEN 1 WHEN 'quarterly' THEN 3 WHEN 'annual' THEN 12 END;
  month_offset := (extract(year from NEW.starts_on)::integer-extract(year from calendar.anchor)::integer)*12
    + extract(month from NEW.starts_on)::integer-extract(month from calendar.anchor)::integer;
  expected_start := (calendar.anchor + make_interval(months=>month_offset))::date;
  expected_end := (calendar.anchor + make_interval(months=>month_offset+stride))::date;
  IF month_offset<0 OR month_offset % stride<>0 OR NEW.starts_on<>expected_start OR NEW.ends_before<>expected_end
     OR (calendar.ends_on IS NOT NULL AND NEW.ends_before>calendar.ends_on+1)
  THEN RAISE EXCEPTION 'recurring period must be a full anchored service period'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_recurringinvoiceterms terms
    JOIN core_invoice invoice ON invoice.id=NEW.invoice_id
    JOIN core_invoiceline line ON line.id=NEW.line_id AND line.invoice_id=invoice.id
    WHERE terms.id=NEW.terms_id AND terms.schedule_id=NEW.schedule_id
      AND terms.tenant_id=NEW.tenant_id AND terms.organization_id=NEW.organization_id
      AND invoice.tenant_id=NEW.tenant_id AND invoice.organization_id=NEW.organization_id AND invoice.state='draft'
      AND invoice.currency=terms.currency AND invoice.invoice_date=NEW.starts_on
      AND invoice.due_date=NEW.starts_on+terms.due_days
      AND line.tenant_id=NEW.tenant_id AND line.organization_id=NEW.organization_id
      AND line.contract_cost_id=calendar.contract_cost_id AND line.currency=terms.currency
      AND line.description=terms.description AND line.unit_amount=terms.unit_amount AND line.quantity=terms.quantity
      AND (
        (terms.tax_rate_id IS NULL AND line.tax_rate_value=0 AND line.tax_rate_name='' AND NOT line.tax_inclusive)
        OR EXISTS (SELECT 1 FROM core_taxrate tax WHERE tax.id=terms.tax_rate_id
          AND tax.tenant_id=NEW.tenant_id AND tax.rate=line.tax_rate_value
          AND tax.name=line.tax_rate_name AND tax.inclusive=line.tax_inclusive
          AND NEW.starts_on>=tax.effective_from AND (tax.effective_to IS NULL OR NEW.starts_on<=tax.effective_to))
      )
  ) THEN RAISE EXCEPTION 'recurring period draft or approved terms invalid'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership WHERE tenant_id=NEW.tenant_id AND user_id=NEW.generated_by_id)
  THEN RAISE EXCEPTION 'recurring period actor scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_recurring_period_guard BEFORE INSERT ON core_recurringinvoiceperiod
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_recurring_period();

CREATE FUNCTION tekdocs_retain_recurring_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'recurring billing records are immutable and retained';
END $$;
CREATE TRIGGER core_recurring_schedule_retain BEFORE DELETE ON core_recurringinvoiceschedule
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_recurring_record();
CREATE TRIGGER core_recurring_terms_retain BEFORE UPDATE OR DELETE ON core_recurringinvoiceterms
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_recurring_record();
CREATE TRIGGER core_recurring_period_retain BEFORE UPDATE OR DELETE ON core_recurringinvoiceperiod
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_recurring_record();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_recurringinvoiceschedule','core_recurringinvoiceterms','core_recurringinvoiceperiod'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('CREATE POLICY %I_runtime_scope ON %I USING (tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))', table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_recurringinvoiceschedule','core_recurringinvoiceterms','core_recurringinvoiceperiod'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER core_recurring_schedule_guard ON core_recurringinvoiceschedule;
DROP TRIGGER core_recurring_terms_guard ON core_recurringinvoiceterms;
DROP TRIGGER core_recurring_period_guard ON core_recurringinvoiceperiod;
DROP TRIGGER core_recurring_schedule_retain ON core_recurringinvoiceschedule;
DROP TRIGGER core_recurring_terms_retain ON core_recurringinvoiceterms;
DROP TRIGGER core_recurring_period_retain ON core_recurringinvoiceperiod;
DROP FUNCTION tekdocs_guard_recurring_schedule();
DROP FUNCTION tekdocs_guard_recurring_terms();
DROP FUNCTION tekdocs_guard_recurring_period();
DROP FUNCTION tekdocs_retain_recurring_record();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0147_recurring_invoice_enrollment")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
