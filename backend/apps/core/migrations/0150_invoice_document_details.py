from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0149_collectionpreference")]

    operations = [
        migrations.AddField(
            model_name="tenantbillingprofile",
            name="payment_instructions",
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.AddField(
            model_name="invoiceline",
            name="unit",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
