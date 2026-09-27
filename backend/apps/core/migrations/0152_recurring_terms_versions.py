from django.db import migrations, models

DROP_RETAIN_TRIGGER = "DROP TRIGGER core_recurring_terms_retain ON core_recurringinvoiceterms;"
CREATE_RETAIN_TRIGGER = """
CREATE TRIGGER core_recurring_terms_retain BEFORE UPDATE OR DELETE ON core_recurringinvoiceterms
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_recurring_record();
"""

POPULATE_EFFECTIVE_FROM = """
UPDATE core_recurringinvoiceterms terms
SET effective_from = schedule.anchor
FROM core_recurringinvoiceschedule schedule
WHERE schedule.id = terms.schedule_id;
"""

FORWARD_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_guard_recurring_terms() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE calendar core_recurringinvoiceschedule%ROWTYPE;
DECLARE expected_version integer;
DECLARE prior_effective date;
DECLARE month_offset integer;
DECLARE stride integer;
DECLARE expected_start date;
DECLARE expected_end date;
BEGIN
  SELECT * INTO calendar FROM core_recurringinvoiceschedule WHERE id=NEW.schedule_id FOR UPDATE;
  IF NOT FOUND OR calendar.tenant_id<>NEW.tenant_id OR calendar.organization_id<>NEW.organization_id
     OR NOT calendar.enabled THEN RAISE EXCEPTION 'recurring terms schedule scope invalid'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_contractcost cost
    WHERE cost.id=calendar.contract_cost_id AND cost.tenant_id=NEW.tenant_id
      AND cost.organization_id=NEW.organization_id AND cost.currency=NEW.currency
  ) THEN RAISE EXCEPTION 'recurring terms source scope or currency invalid'; END IF;
  SELECT COALESCE(max(version), 0)+1, max(effective_from)
    INTO expected_version, prior_effective
    FROM core_recurringinvoiceterms WHERE schedule_id=NEW.schedule_id;
  IF NEW.version<>expected_version
  THEN RAISE EXCEPTION 'recurring terms version must extend the retained chain'; END IF;
  IF NEW.version=1 AND NEW.effective_from<>calendar.anchor
  THEN RAISE EXCEPTION 'initial recurring terms must begin at the schedule anchor'; END IF;
  IF NEW.version>1 AND (prior_effective IS NULL OR NEW.effective_from<=prior_effective)
  THEN RAISE EXCEPTION 'recurring terms effective date must advance'; END IF;
  IF NEW.version>1 AND EXISTS (
    SELECT 1 FROM core_recurringinvoiceperiod period
    WHERE period.schedule_id=NEW.schedule_id AND period.starts_on>=NEW.effective_from
  ) THEN RAISE EXCEPTION 'recurring terms cannot replace a claimed period'; END IF;
  stride := CASE calendar.interval WHEN 'monthly' THEN 1 WHEN 'quarterly' THEN 3 WHEN 'annual' THEN 12 END;
  month_offset := (extract(year from NEW.effective_from)::integer-extract(year from calendar.anchor)::integer)*12
    + extract(month from NEW.effective_from)::integer-extract(month from calendar.anchor)::integer;
  expected_start := (calendar.anchor + make_interval(months=>month_offset))::date;
  expected_end := (calendar.anchor + make_interval(months=>month_offset+stride))::date;
  IF month_offset<0 OR month_offset % stride<>0 OR NEW.effective_from<>expected_start
     OR (calendar.ends_on IS NOT NULL AND expected_end>calendar.ends_on+1)
  THEN RAISE EXCEPTION 'recurring terms must begin at a full billing-period boundary'; END IF;
  IF NEW.tax_rate_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_taxrate tax WHERE tax.id=NEW.tax_rate_id AND tax.tenant_id=NEW.tenant_id
      AND NEW.effective_from>=tax.effective_from
      AND (tax.effective_to IS NULL OR NEW.effective_from<=tax.effective_to)
  ) THEN RAISE EXCEPTION 'recurring terms tax scope or effective date invalid'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership
    WHERE tenant_id=NEW.tenant_id AND user_id=NEW.approved_by_id
  ) THEN RAISE EXCEPTION 'recurring terms actor scope invalid'; END IF;
  IF NEW.source_digest !~ '^[a-f0-9]{64}$' OR jsonb_typeof(NEW.source_snapshot)<>'object'
  THEN RAISE EXCEPTION 'recurring source snapshot invalid'; END IF;
  RETURN NEW;
END $$;
"""

REVERSE_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_guard_recurring_terms() RETURNS trigger LANGUAGE plpgsql AS $$
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
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership WHERE tenant_id=NEW.tenant_id AND user_id=NEW.approved_by_id
  ) THEN RAISE EXCEPTION 'recurring terms actor scope invalid'; END IF;
  IF NEW.source_digest !~ '^[a-f0-9]{64}$' OR jsonb_typeof(NEW.source_snapshot)<>'object'
  THEN RAISE EXCEPTION 'recurring source snapshot invalid'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0151_organization_billing_identity")]

    operations = [
        migrations.RunSQL(DROP_RETAIN_TRIGGER, CREATE_RETAIN_TRIGGER),
        migrations.AddField(
            model_name="recurringinvoiceterms",
            name="effective_from",
            field=models.DateField(null=True),
        ),
        migrations.RunSQL(POPULATE_EFFECTIVE_FROM, migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="recurringinvoiceterms",
            name="effective_from",
            field=models.DateField(),
        ),
        migrations.RemoveConstraint(
            model_name="recurringinvoiceterms",
            name="recurring_terms_initial_version_only",
        ),
        migrations.AddConstraint(
            model_name="recurringinvoiceterms",
            constraint=models.UniqueConstraint(
                fields=("schedule", "effective_from"), name="recurring_terms_effective_from_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="recurringinvoiceterms",
            constraint=models.CheckConstraint(
                condition=models.Q(version__gte=1), name="recurring_terms_version_positive"
            ),
        ),
        migrations.RunSQL(
            FORWARD_GUARD_SQL + CREATE_RETAIN_TRIGGER,
            DROP_RETAIN_TRIGGER + REVERSE_GUARD_SQL,
        ),
    ]
