from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0154_editable_integration_connection_url")]

    operations = [
        migrations.AddField(
            model_name="networksubnet",
            name="dhcp_server",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
    ]
