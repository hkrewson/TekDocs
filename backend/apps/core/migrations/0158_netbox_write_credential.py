from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0157_network_device_source_placement")]

    operations = [
        migrations.AddField(
            model_name="integrationconnection",
            name="write_secret_envelope",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="integrationconnection",
            name="write_secret_generation",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="integrationconnection",
            constraint=models.CheckConstraint(
                condition=models.Q(write_secret_generation__gte=1),
                name="integration_write_secret_generation_valid",
            ),
        ),
    ]
