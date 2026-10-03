from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_credit_note_prefix() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.credit_note_prefix !~ '^[A-Z0-9-]{1,16}$' THEN
    RAISE EXCEPTION 'billing profile credit-note prefix invalid';
  END IF;
  IF NEW.credit_note_prefix = NEW.invoice_prefix THEN
    RAISE EXCEPTION 'credit notes require a separate numbering prefix';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_billingprofile_credit_prefix BEFORE INSERT OR UPDATE ON core_tenantbillingprofile
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_credit_note_prefix();

CREATE OR REPLACE FUNCTION tekdocs_validate_invoice_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'invoice organization scope mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_organizationclassification classification
    WHERE classification.organization_id=NEW.organization_id AND classification.tenant_id=NEW.tenant_id
      AND classification.kind='client'
  ) THEN RAISE EXCEPTION 'invoice requires client organization'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.organization_id=NEW.organization_id AND entity.entity_type='invoice'
      AND entity.visibility='msp_private'
  ) THEN RAISE EXCEPTION 'invoice entity scope mismatch'; END IF;
  IF NEW.source_invoice_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_invoice source
    WHERE source.id=NEW.source_invoice_id AND source.tenant_id=NEW.tenant_id
      AND source.organization_id=NEW.organization_id AND source.state='issued'
      AND source.document_kind='invoice'
  ) THEN RAISE EXCEPTION 'invoice source scope mismatch'; END IF;
  IF (NEW.document_kind='invoice' AND NEW.source_invoice_id IS NULL AND NEW.source_kind='')
    OR (NEW.document_kind='invoice' AND NEW.source_invoice_id IS NOT NULL
        AND NEW.source_kind IN ('supplement','replacement'))
    OR (NEW.document_kind='credit_note' AND NEW.source_invoice_id IS NOT NULL AND NEW.source_kind='credit_note')
  THEN NULL;
  ELSE RAISE EXCEPTION 'invoice document/source shape invalid'; END IF;
  IF TG_OP = 'UPDATE'
    AND (NEW.tenant_id, NEW.organization_id, NEW.currency, NEW.document_kind, NEW.source_invoice_id, NEW.source_kind)
      IS DISTINCT FROM (OLD.tenant_id, OLD.organization_id, OLD.currency, OLD.document_kind,
                        OLD.source_invoice_id, OLD.source_kind)
    AND EXISTS (SELECT 1 FROM core_invoiceline line WHERE line.invoice_id=NEW.id)
  THEN RAISE EXCEPTION 'invoice scope, kind, source, and currency are fixed while lines exist'; END IF;
  IF NEW.currency !~ '^[A-Z]{3}$' THEN RAISE EXCEPTION 'invoice currency invalid'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_reject_issued_invoice_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state = 'issued' AND (
    (to_jsonb(NEW) - ARRAY[
      'updated_at', 'delivered_at', 'delivered_by_id', 'delivery_recipient', 'delivery_count'
    ]) IS DISTINCT FROM
    (to_jsonb(OLD) - ARRAY['updated_at', 'delivered_at', 'delivered_by_id', 'delivery_recipient', 'delivery_count'])
  ) THEN RAISE EXCEPTION 'issued invoice is immutable'; END IF;
  IF OLD.state = 'issued' AND NEW.delivery_count > OLD.delivery_count AND EXISTS (
    SELECT 1 FROM core_invoicelifecycleevent event
    WHERE event.invoice_id=OLD.id AND event.event_type='voided'
  ) THEN RAISE EXCEPTION 'voided invoice cannot be delivered'; END IF;
  IF OLD.state = 'issued' AND (
    NEW.delivered_at IS NULL OR NEW.delivered_by_id IS NULL OR NEW.delivery_recipient = ''
    OR NEW.delivery_count < 1 OR NEW.delivery_count < OLD.delivery_count
  ) THEN RAISE EXCEPTION 'issued invoice delivery metadata is invalid'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_guard_invoice_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
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
  IF NEW.event_type='voided' AND (
    NEW.related_invoice_id IS NOT NULL OR EXISTS (
      SELECT 1 FROM core_invoice invoice WHERE invoice.id=NEW.invoice_id AND invoice.delivery_count > 0
    )
  ) THEN RAISE EXCEPTION 'only an undelivered invoice can be voided'; END IF;
  IF NEW.event_type='credited' AND (
    NEW.related_invoice_id IS NULL OR NOT EXISTS (
      SELECT 1 FROM core_invoice related
      WHERE related.id=NEW.related_invoice_id AND related.document_kind='credit_note'
        AND related.source_kind='credit_note' AND related.source_invoice_id=NEW.invoice_id
    )
  ) THEN RAISE EXCEPTION 'credit event requires a credit note issued for this invoice'; END IF;
  IF NEW.actor_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership member
    WHERE member.tenant_id=NEW.tenant_id AND member.user_id=NEW.actor_id
  ) THEN RAISE EXCEPTION 'invoice lifecycle actor scope invalid'; END IF;
  RETURN NEW;
END $$;
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_billingprofile_credit_prefix ON core_tenantbillingprofile;
DROP FUNCTION IF EXISTS tekdocs_validate_credit_note_prefix();

CREATE OR REPLACE FUNCTION tekdocs_validate_invoice_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'invoice organization scope mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_organizationclassification classification
    WHERE classification.organization_id=NEW.organization_id AND classification.tenant_id=NEW.tenant_id
      AND classification.kind='client'
  ) THEN RAISE EXCEPTION 'invoice requires client organization'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.organization_id=NEW.organization_id AND entity.entity_type='invoice'
      AND entity.visibility='msp_private'
  ) THEN RAISE EXCEPTION 'invoice entity scope mismatch'; END IF;
  IF NEW.source_invoice_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_invoice source
    WHERE source.id=NEW.source_invoice_id AND source.tenant_id=NEW.tenant_id
      AND source.organization_id=NEW.organization_id AND source.state='issued'
  ) THEN RAISE EXCEPTION 'invoice source scope mismatch'; END IF;
  IF TG_OP = 'UPDATE'
    AND (NEW.tenant_id, NEW.organization_id, NEW.currency)
      IS DISTINCT FROM (OLD.tenant_id, OLD.organization_id, OLD.currency)
    AND EXISTS (SELECT 1 FROM core_invoiceline line WHERE line.invoice_id=NEW.id)
  THEN RAISE EXCEPTION 'invoice scope and currency are fixed while lines exist'; END IF;
  IF NEW.currency !~ '^[A-Z]{3}$' THEN RAISE EXCEPTION 'invoice currency invalid'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_reject_issued_invoice_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state = 'issued' AND
    (to_jsonb(NEW) - ARRAY['updated_at', 'delivered_at', 'delivered_by_id', 'delivery_recipient', 'delivery_count'])
      IS DISTINCT FROM
    (to_jsonb(OLD) - ARRAY['updated_at', 'delivered_at', 'delivered_by_id', 'delivery_recipient', 'delivery_count'])
  THEN RAISE EXCEPTION 'issued invoice is immutable'; END IF;
  IF OLD.state = 'issued' AND (
    NEW.delivered_at IS NULL OR NEW.delivered_by_id IS NULL OR NEW.delivery_recipient = ''
    OR NEW.delivery_count < 1 OR NEW.delivery_count < OLD.delivery_count
  ) THEN RAISE EXCEPTION 'issued invoice delivery metadata is invalid'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_guard_invoice_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
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
"""


def configure_credit_note_series(apps, schema_editor):  # type: ignore[no-untyped-def]
    BillingProfile = apps.get_model("core", "TenantBillingProfile")
    InvoiceNumberSeries = apps.get_model("core", "InvoiceNumberSeries")
    for profile in BillingProfile.objects.all().iterator():
        if profile.credit_note_prefix == profile.invoice_prefix:
            profile.credit_note_prefix = "CRN"
            profile.save(update_fields=("credit_note_prefix", "updated_at"))
        InvoiceNumberSeries.objects.get_or_create(
            tenant_id=profile.tenant_id,
            prefix=profile.credit_note_prefix,
            date_component=profile.invoice_date_component,
            separator=profile.invoice_separator,
            sequence_digits=profile.invoice_sequence_digits,
            reset_period=profile.invoice_reset_period,
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0160_complete_legacy_invoice_revisions")]

    operations = [
        migrations.AddField(
            model_name="tenantbillingprofile",
            name="credit_note_prefix",
            field=models.CharField(default="CR", max_length=16),
        ),
        migrations.AddField(
            model_name="invoice",
            name="document_kind",
            field=models.CharField(
                choices=[("invoice", "Invoice"), ("credit_note", "Credit note")],
                default="invoice",
                max_length=16,
            ),
        ),
        migrations.RunPython(configure_credit_note_series, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="invoice", name="invoice_source_fields_consistent"),
        migrations.AlterField(
            model_name="invoice",
            name="source_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("supplement", "Supplement"),
                    ("replacement", "Replacement"),
                    ("credit_note", "Credit note"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(document_kind="invoice", source_invoice__isnull=True, source_kind="")
                    | models.Q(
                        document_kind="invoice",
                        source_invoice__isnull=False,
                        source_kind__in=("supplement", "replacement"),
                    )
                    | models.Q(
                        document_kind="credit_note",
                        source_invoice__isnull=False,
                        source_kind="credit_note",
                    )
                ),
                name="invoice_source_fields_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=models.Q(document_kind__in=("invoice", "credit_note")),
                name="invoice_document_kind_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoicelifecycleevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(event_type="credited", related_invoice__isnull=False),
                fields=("related_invoice",),
                name="invoice_credit_event_note_unique",
            ),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
