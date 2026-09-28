from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0155_network_dhcp_server")]

    operations = [
        migrations.RemoveConstraint(
            model_name="integrationconnection",
            name="integration_provider_valid",
        ),
        migrations.AlterField(
            model_name="integrationconnection",
            name="provider",
            field=models.CharField(
                choices=[
                    ("netbox", "NetBox"),
                    ("unifi", "UniFi Network"),
                    ("microsoft_graph", "Microsoft 365"),
                    ("halopsa", "HaloPSA"),
                    ("ninjaone", "NinjaOne"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="integrationconnection",
            constraint=models.CheckConstraint(
                condition=models.Q(provider__in=("netbox", "unifi", "microsoft_graph", "halopsa", "ninjaone")),
                name="integration_provider_valid",
            ),
        ),
    ]
