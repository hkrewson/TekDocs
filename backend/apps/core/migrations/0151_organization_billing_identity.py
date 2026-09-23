from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0150_invoice_document_details")]

    operations = [
        migrations.AddField(model_name="organization", name="billing_contact_name", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="organization", name="billing_email", field=models.EmailField(blank=True, max_length=254)),
        migrations.AddField(model_name="organization", name="billing_phone", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="organization", name="billing_address_line_1", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="organization", name="billing_address_line_2", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="organization", name="billing_city", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="organization", name="billing_region", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="organization", name="billing_postal_code", field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name="organization", name="billing_country_code", field=models.CharField(blank=True, max_length=2)),
    ]
