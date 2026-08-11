import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_publication_control_permissions"),
        ("core", "0065_refresh_publication_control_validation"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="tenantmembership",
            name="tenant_membership_role_valid",
        ),
        migrations.AddField(
            model_name="invitation",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_invitations",
                to="core.organization",
            ),
        ),
        migrations.AddField(
            model_name="invitation",
            name="role",
            field=models.CharField(
                choices=[
                    ("administrator", "Administrator"),
                    ("technician", "Technician"),
                    ("contributor", "Contributor"),
                    ("read_only", "Read-only"),
                    ("client_administrator", "Client Administrator"),
                    ("client_user", "Client User"),
                ],
                default="read_only",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="tenantmembership",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_memberships",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="tenantmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("administrator", "Administrator"),
                    ("technician", "Technician"),
                    ("contributor", "Contributor"),
                    ("read_only", "Read-only"),
                    ("client_administrator", "Client Administrator"),
                    ("client_user", "Client User"),
                ],
                default="read_only",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="invitation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("organization__isnull", False), ("role__in", ("client_administrator", "client_user"))),
                    models.Q(
                        ("organization__isnull", True),
                        ("role__in", ("administrator", "technician", "contributor", "read_only")),
                    ),
                    _connector="OR",
                ),
                name="invitation_role_matches_organization_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "role__in",
                        (
                            "administrator",
                            "technician",
                            "contributor",
                            "read_only",
                            "client_administrator",
                            "client_user",
                        ),
                    )
                ),
                name="tenant_membership_role_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("organization__isnull", False), ("role__in", ("client_administrator", "client_user"))),
                    models.Q(
                        ("organization__isnull", True),
                        ("role__in", ("administrator", "technician", "contributor", "read_only")),
                    ),
                    _connector="OR",
                ),
                name="membership_role_matches_organization_scope",
            ),
        ),
    ]
