from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0104_monitoring_evidence_guards")]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="access_mode",
            field=models.CharField(
                choices=[
                    ("all_authorized", "All authorized MSP staff"),
                    ("assigned_only", "Assigned MSP staff only"),
                ],
                default="assigned_only",
                max_length=32,
            ),
        ),
    ]
