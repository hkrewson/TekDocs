from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0223_native_monitored_sources")]

    operations = [
        migrations.AlterField(
            model_name="integrationobservation",
            name="schema_version",
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
