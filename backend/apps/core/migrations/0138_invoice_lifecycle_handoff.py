import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


SQL = r"""
CREATE FUNCTION tekdocs_guard_invoice_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_invoice invoice
    WHERE invoice.id=NEW.invoice_id AND invoice.tenant_id=NEW.tenant_id
      AND invoice.organization_id=NEW.organization_id AND invoice.state='issued'
  ) THEN RAISE EXCEPTION 'invoice lifecycle event scope invalid'; END IF;
  IF NEW.related_invoice_id IS NOT NULL AND (
    NEW.related_invoice_id=NEW.invoice_id OR NOT EXISTS (
      SELECT 1 FROM core_invoice related
      WHERE related.id=NEW.related_invoice_id AND related.tenant_id=NEW.tenant_id
        AND related.organization_id=NEW.organization_id AND related.state='issued'
    )
  ) THEN RAISE EXCEPTION 'related invoice scope invalid'; END IF;
  IF NEW.actor_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership member
    WHERE member.tenant_id=NEW.tenant_id AND member.user_id=NEW.actor_id
  ) THEN RAISE EXCEPTION 'invoice lifecycle actor scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_invoice_lifecycle_scope_guard BEFORE INSERT ON core_invoicelifecycleevent
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_invoice_lifecycle_event();

CREATE FUNCTION tekdocs_retain_invoice_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'invoice lifecycle events are immutable and retained';
END $$;
CREATE TRIGGER core_invoice_lifecycle_retain BEFORE UPDATE OR DELETE ON core_invoicelifecycleevent
FOR EACH ROW EXECUTE FUNCTION tekdocs_retain_invoice_lifecycle_event();

ALTER TABLE core_invoicelifecycleevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_invoicelifecycleevent FORCE ROW LEVEL SECURITY;
CREATE POLICY core_invoicelifecycleevent_runtime_scope ON core_invoicelifecycleevent
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
"""


REVERSE = r"""
DROP POLICY IF EXISTS core_invoicelifecycleevent_runtime_scope ON core_invoicelifecycleevent;
ALTER TABLE core_invoicelifecycleevent DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_invoice_lifecycle_retain ON core_invoicelifecycleevent;
DROP FUNCTION IF EXISTS tekdocs_retain_invoice_lifecycle_event();
DROP TRIGGER IF EXISTS core_invoice_lifecycle_scope_guard ON core_invoicelifecycleevent;
DROP FUNCTION IF EXISTS tekdocs_guard_invoice_lifecycle_event();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0137_organization_taxonomy_terms"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.AlterField(
            model_name="reminderschedule",
            name="domain",
            field=models.CharField(
                choices=[
                    ("compliance", "Compliance"),
                    ("inventory", "Inventory"),
                    ("domain", "Domain"),
                    ("documentation", "Documentation"),
                    ("invoice", "Invoice"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="InvoiceLifecycleEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(choices=[("issued", "Issued"), ("delivery_succeeded", "Delivery succeeded"), ("delivery_failed", "Delivery failed"), ("accounting_synchronized", "Accounting synchronized"), ("accounting_rejected", "Accounting rejected"), ("accounting_duplicate", "Accounting duplicate"), ("accounting_changed", "Externally changed"), ("payment_recorded", "Payment recorded"), ("payment_reversed", "Payment reversed"), ("voided", "Voided by reference"), ("credited", "Credited by reference"), ("reminder_sent", "Reminder sent")], max_length=32)),
                ("occurred_at", models.DateTimeField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("provider", models.CharField(blank=True, max_length=80)),
                ("external_id", models.CharField(blank=True, max_length=160)),
                ("idempotency_key", models.CharField(blank=True, max_length=160)),
                ("amount", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("currency", models.CharField(blank=True, max_length=3)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="recorded_invoice_lifecycle_events", to=settings.AUTH_USER_MODEL)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lifecycle_events", to="core.invoice")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoice_lifecycle_events", to="core.organization")),
                ("related_invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="referenced_by_lifecycle_events", to="core.invoice")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoice_lifecycle_events", to="core.tenant")),
            ],
            options={"ordering": ("occurred_at", "recorded_at", "id")},
        ),
        migrations.AddConstraint(model_name="invoicelifecycleevent", constraint=models.UniqueConstraint(condition=~models.Q(idempotency_key=""), fields=("invoice", "idempotency_key"), name="invoice_event_idempotency_unique")),
        migrations.AddConstraint(model_name="invoicelifecycleevent", constraint=models.UniqueConstraint(condition=~models.Q(provider="") & ~models.Q(external_id=""), fields=("tenant", "provider", "external_id"), name="invoice_provider_event_unique")),
        migrations.AddConstraint(model_name="invoicelifecycleevent", constraint=models.CheckConstraint(condition=models.Q(event_type__in=["issued", "delivery_succeeded", "delivery_failed", "accounting_synchronized", "accounting_rejected", "accounting_duplicate", "accounting_changed", "payment_recorded", "payment_reversed", "voided", "credited", "reminder_sent"]), name="invoice_event_type_valid")),
        migrations.AddConstraint(model_name="invoicelifecycleevent", constraint=models.CheckConstraint(condition=models.Q(amount__isnull=True, currency="") | models.Q(amount__gt=0, currency__regex="^[A-Z]{3}$"), name="invoice_event_amount_consistent")),
        migrations.AddIndex(model_name="invoicelifecycleevent", index=models.Index(fields=["tenant", "organization", "invoice", "occurred_at"], name="core_invevent_scope_idx")),
        migrations.RunSQL(SQL, REVERSE),
    ]
