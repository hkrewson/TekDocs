import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_guard_recurring_withdrawal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_recurringinvoiceperiod period
    JOIN core_invoice invoice ON invoice.id=period.invoice_id
    JOIN core_invoiceline line ON line.id=period.line_id AND line.invoice_id=invoice.id
    WHERE period.id=NEW.period_id AND period.tenant_id=NEW.tenant_id
      AND period.organization_id=NEW.organization_id
      AND invoice.tenant_id=NEW.tenant_id AND invoice.organization_id=NEW.organization_id
      AND invoice.state='draft'
      AND line.tenant_id=NEW.tenant_id AND line.organization_id=NEW.organization_id
  ) THEN RAISE EXCEPTION 'recurring withdrawal must reference an unissued draft in the same scope'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership
    WHERE tenant_id=NEW.tenant_id AND user_id=NEW.withdrawn_by_id
  ) THEN RAISE EXCEPTION 'recurring withdrawal actor scope invalid'; END IF;
  IF char_length(btrim(NEW.reason))<1 OR char_length(NEW.reason)>1000
  THEN RAISE EXCEPTION 'recurring withdrawal reason invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_recurring_withdrawal_guard BEFORE INSERT ON core_recurringinvoicewithdrawal
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_recurring_withdrawal();

CREATE FUNCTION tekdocs_retain_recurring_withdrawal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'recurring draft withdrawals are immutable and retained';
END $$;
CREATE TRIGGER core_recurring_withdrawal_retain BEFORE UPDATE OR DELETE ON core_recurringinvoicewithdrawal
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_recurring_withdrawal();

CREATE FUNCTION tekdocs_guard_withdrawn_invoice_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM core_recurringinvoicewithdrawal withdrawal
    JOIN core_recurringinvoiceperiod period ON period.id=withdrawal.period_id
    WHERE period.invoice_id=OLD.id
  ) THEN RAISE EXCEPTION 'withdrawn recurring drafts are immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_withdrawn_invoice_update_guard BEFORE UPDATE ON core_invoice
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_withdrawn_invoice_update();

CREATE FUNCTION tekdocs_guard_withdrawn_invoice_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_invoice uuid;
BEGIN
  target_invoice := CASE WHEN TG_OP='DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END;
  IF EXISTS (
    SELECT 1 FROM core_recurringinvoicewithdrawal withdrawal
    JOIN core_recurringinvoiceperiod period ON period.id=withdrawal.period_id
    WHERE period.invoice_id=target_invoice
  ) THEN RAISE EXCEPTION 'withdrawn recurring draft lines are immutable'; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_withdrawn_invoice_line_guard BEFORE INSERT OR UPDATE OR DELETE ON core_invoiceline
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_withdrawn_invoice_line();

ALTER TABLE core_recurringinvoicewithdrawal ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_recurringinvoicewithdrawal FORCE ROW LEVEL SECURITY;
CREATE POLICY core_recurringinvoicewithdrawal_runtime_scope ON core_recurringinvoicewithdrawal
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_recurringinvoicewithdrawal_runtime_scope ON core_recurringinvoicewithdrawal;
ALTER TABLE core_recurringinvoicewithdrawal NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_recurringinvoicewithdrawal DISABLE ROW LEVEL SECURITY;
DROP TRIGGER core_withdrawn_invoice_line_guard ON core_invoiceline;
DROP TRIGGER core_withdrawn_invoice_update_guard ON core_invoice;
DROP TRIGGER core_recurring_withdrawal_retain ON core_recurringinvoicewithdrawal;
DROP TRIGGER core_recurring_withdrawal_guard ON core_recurringinvoicewithdrawal;
DROP FUNCTION tekdocs_guard_withdrawn_invoice_line();
DROP FUNCTION tekdocs_guard_withdrawn_invoice_update();
DROP FUNCTION tekdocs_retain_recurring_withdrawal();
DROP FUNCTION tekdocs_guard_recurring_withdrawal();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0152_recurring_terms_versions"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="RecurringInvoiceWithdrawal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.TextField(max_length=1000)),
                ("withdrawn_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recurring_invoice_withdrawals",
                        to="core.organization",
                    ),
                ),
                (
                    "period",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="withdrawal",
                        to="core.recurringinvoiceperiod",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recurring_invoice_withdrawals",
                        to="core.tenant",
                    ),
                ),
                (
                    "withdrawn_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="withdrawn_recurring_drafts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
