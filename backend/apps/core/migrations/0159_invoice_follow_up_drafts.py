import django.db.models.deletion
from django.db import migrations, models

FORWARD_SQL = r"""
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
"""

REVERSE_SQL = FORWARD_SQL.replace(
    "  IF NEW.source_invoice_id IS NOT NULL AND NOT EXISTS (\n"
    "    SELECT 1 FROM core_invoice source\n"
    "    WHERE source.id=NEW.source_invoice_id AND source.tenant_id=NEW.tenant_id\n"
    "      AND source.organization_id=NEW.organization_id AND source.state='issued'\n"
    "  ) THEN RAISE EXCEPTION 'invoice source scope mismatch'; END IF;\n",
    "",
)


def backfill_draft_parties(apps, schema_editor):  # type: ignore[no-untyped-def]
    Invoice = apps.get_model("core", "Invoice")
    BillingProfile = apps.get_model("core", "TenantBillingProfile")
    profiles = {profile.tenant_id: profile for profile in BillingProfile.objects.all()}
    for invoice in Invoice.objects.filter(state="draft").select_related("organization__entity").iterator():
        updates = {}
        if not invoice.customer_snapshot:
            organization = invoice.organization
            updates["customer_snapshot"] = {
                "display_name": organization.entity.display_name,
                "legal_name": organization.legal_name,
                "website": organization.website,
                "contact_name": organization.billing_contact_name,
                "billing_email": organization.billing_email,
                "phone": organization.billing_phone,
                "address_line_1": organization.billing_address_line_1,
                "address_line_2": organization.billing_address_line_2,
                "city": organization.billing_city,
                "region": organization.billing_region,
                "postal_code": organization.billing_postal_code,
                "country_code": organization.billing_country_code,
            }
        if not invoice.issuer_snapshot and (profile := profiles.get(invoice.tenant_id)) is not None:
            updates["issuer_snapshot"] = {
                "legal_name": profile.legal_name,
                "address_line_1": profile.address_line_1,
                "address_line_2": profile.address_line_2,
                "city": profile.city,
                "region": profile.region,
                "postal_code": profile.postal_code,
                "country_code": profile.country_code,
                "billing_email": profile.billing_email,
                "phone": profile.phone,
                "tax_registration": profile.tax_registration,
                "payment_instructions": profile.payment_instructions,
            }
        if updates:
            Invoice.objects.filter(pk=invoice.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("core", "0158_netbox_write_credential")]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="source_invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="derived_invoices",
                to="core.invoice",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="source_kind",
            field=models.CharField(
                blank=True,
                choices=[("supplement", "Supplement"), ("replacement", "Replacement")],
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_draft_parties, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(source_invoice__isnull=True, source_kind="")
                    | models.Q(source_invoice__isnull=False, source_kind__in=["supplement", "replacement"])
                ),
                name="invoice_source_fields_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=models.Q(source_invoice__isnull=True) | ~models.Q(source_invoice=models.F("id")),
                name="invoice_source_not_self",
            ),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
