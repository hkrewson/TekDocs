import uuid

import django.db.models.deletion
from django.db import migrations, models


FORWARD_SQL = """
CREATE FUNCTION tekdocs_protect_tax_rate_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'tax rate versions are immutable';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_taxrate_immutable
BEFORE UPDATE OR DELETE ON core_taxrate
FOR EACH ROW EXECUTE FUNCTION tekdocs_protect_tax_rate_version();

CREATE FUNCTION tekdocs_validate_billing_profile() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.default_currency !~ '^[A-Z]{3}$' THEN
    RAISE EXCEPTION 'billing profile currency invalid';
  END IF;
  IF NEW.country_code <> '' AND NEW.country_code !~ '^[A-Z]{2}$' THEN
    RAISE EXCEPTION 'billing profile country invalid';
  END IF;
  IF NEW.invoice_prefix !~ '^[A-Z0-9-]{1,16}$' THEN
    RAISE EXCEPTION 'billing profile invoice prefix invalid';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_billingprofile_validate
BEFORE INSERT OR UPDATE ON core_tenantbillingprofile
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_billing_profile();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_tenantbillingprofile', 'core_taxrate'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I_runtime_scope ON %I USING (tenant_id=tekdocs_current_tenant_id()) WITH CHECK (tenant_id=tekdocs_current_tenant_id())',
      table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = """
DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_tenantbillingprofile', 'core_taxrate'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_billingprofile_validate ON core_tenantbillingprofile;
DROP FUNCTION IF EXISTS tekdocs_validate_billing_profile();
DROP TRIGGER IF EXISTS core_taxrate_immutable ON core_taxrate;
DROP FUNCTION IF EXISTS tekdocs_protect_tax_rate_version();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0126_document_operations")]

    operations = [
        migrations.CreateModel(
            name="TenantBillingProfile",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("legal_name", models.CharField(blank=True, max_length=240)),
                ("address_line_1", models.CharField(blank=True, max_length=240)),
                ("address_line_2", models.CharField(blank=True, max_length=240)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("region", models.CharField(blank=True, max_length=120)),
                ("postal_code", models.CharField(blank=True, max_length=32)),
                ("country_code", models.CharField(blank=True, max_length=2)),
                ("billing_email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("tax_registration", models.CharField(blank=True, max_length=120)),
                ("default_currency", models.CharField(default="USD", max_length=3)),
                ("payment_terms_days", models.PositiveSmallIntegerField(default=30)),
                ("invoice_prefix", models.CharField(default="INV", max_length=16)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="billing_profile",
                        to="core.tenant",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaxRate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("series_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("version", models.PositiveIntegerField(default=1)),
                ("name", models.CharField(max_length=120)),
                ("rate", models.DecimalField(decimal_places=6, max_digits=9)),
                ("inclusive", models.BooleanField(default=False)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tax_rates",
                        to="core.tenant",
                    ),
                ),
            ],
            options={"ordering": ("name", "-version", "id")},
        ),
        migrations.AddConstraint(
            model_name="tenantbillingprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(("payment_terms_days__lte", 365)),
                name="billing_profile_payment_terms_bounded",
            ),
        ),
        migrations.AddConstraint(
            model_name="taxrate",
            constraint=models.UniqueConstraint(
                fields=("tenant", "series_id", "version"), name="tax_rate_version_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="taxrate",
            constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="tax_rate_version_positive"),
        ),
        migrations.AddConstraint(
            model_name="taxrate",
            constraint=models.CheckConstraint(condition=models.Q(("rate__gte", 0)), name="tax_rate_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="taxrate",
            constraint=models.CheckConstraint(
                condition=models.Q(("effective_to__isnull", True))
                | models.Q(("effective_to__gte", models.F("effective_from"))),
                name="tax_rate_effective_range_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="taxrate",
            index=models.Index(fields=("tenant", "series_id", "version"), name="core_taxrate_series_idx"),
        ),
        migrations.AddIndex(
            model_name="taxrate",
            index=models.Index(fields=("tenant", "effective_from", "effective_to"), name="core_taxrate_effective_idx"),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
