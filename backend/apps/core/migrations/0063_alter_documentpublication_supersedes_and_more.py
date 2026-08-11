import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_publication_control_permissions"),
        ("core", "0062_asset_backed_network_guards"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentpublication",
            name="supersedes",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="successors",
                to="core.documentpublication",
            ),
        ),
        migrations.CreateModel(
            name="DocumentPublicationControlEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "action",
                    models.CharField(
                        choices=[("submitted", "Submitted"), ("approved", "Approved"), ("withdrawn", "Withdrawn")],
                        max_length=20,
                    ),
                ),
                ("reason", models.CharField(max_length=500)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="document_publication_control_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_publication_events",
                        to="core.organization",
                    ),
                ),
                (
                    "publication",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="control_events",
                        to="core.documentpublication",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_publication_events",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ("occurred_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant", "organization", "publication", "occurred_at"],
                        name="core_pubctl_scope_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("action__in", ["submitted", "approved", "withdrawn"])),
                        name="publication_control_action_valid",
                    ),
                    models.UniqueConstraint(
                        fields=("publication", "action"),
                        name="unique_publication_control_action",
                    ),
                ],
            },
        ),
    ]
