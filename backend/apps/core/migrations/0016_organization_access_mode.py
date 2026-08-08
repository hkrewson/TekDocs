from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0015_entity_link_guards")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="access_mode",
            field=models.CharField(
                choices=[
                    ("all_authorized", "All authorized MSP staff"),
                    ("assigned_only", "Assigned MSP staff only"),
                ],
                default="all_authorized",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.CheckConstraint(
                condition=models.Q(access_mode__in=("all_authorized", "assigned_only")),
                name="organization_access_mode_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["tenant", "access_mode", "entity"],
                name="core_org_tenant_access_idx",
            ),
        ),
    ]
