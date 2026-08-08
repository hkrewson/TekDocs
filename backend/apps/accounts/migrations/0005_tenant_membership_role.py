from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_encrypt_existing_mfa_secrets")]

    operations = [
        migrations.AddField(
            model_name="tenantmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("administrator", "Administrator"),
                    ("technician", "Technician"),
                    ("contributor", "Contributor"),
                    ("read_only", "Read-only"),
                ],
                default="read_only",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(role__in=("administrator", "technician", "contributor", "read_only")),
                name="tenant_membership_role_valid",
            ),
        ),
    ]
