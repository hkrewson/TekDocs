from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0156_unifi_integration_provider")]

    operations = [
        migrations.AddField(
            model_name="networkdevice",
            name="source_rack_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="networkdevice",
            name="source_rack_position",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="networkdevice",
            name="source_rack_units",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
