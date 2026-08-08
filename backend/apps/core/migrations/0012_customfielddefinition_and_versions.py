import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_location_cycle_guard"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomFieldDefinition",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=80)),
                ("entity_type", models.CharField(max_length=80)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="custom_field_definitions",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="custom_field_definitions",
                        to="core.tenant",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CustomFieldDefinitionVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("label", models.CharField(max_length=160)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("required", models.BooleanField(default=False)),
                (
                    "field_type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("integer", "Integer"),
                            ("number", "Number"),
                            ("boolean", "Boolean"),
                            ("date", "Date"),
                            ("url", "URL"),
                            ("email", "Email"),
                            ("choice", "Choice"),
                            ("multi_choice", "Multiple choice"),
                        ],
                        max_length=32,
                    ),
                ),
                ("schema", models.JSONField()),
                ("display_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="custom_field_definition_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="core.customfielddefinition",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="custom_field_definition_versions",
                        to="core.tenant",
                    ),
                ),
            ],
            options={"ordering": ("definition_id", "version")},
        ),
        migrations.AddConstraint(
            model_name="customfielddefinition",
            constraint=models.UniqueConstraint(
                fields=("tenant", "organization", "entity_type", "key"),
                name="unique_custom_field_key_in_scope",
                nulls_distinct=False,
            ),
        ),
        migrations.AddIndex(
            model_name="customfielddefinition",
            index=models.Index(
                fields=["tenant", "organization", "entity_type", "archived_at"],
                name="core_cfdef_scope_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="customfielddefinitionversion",
            constraint=models.UniqueConstraint(
                fields=("definition", "version"),
                name="unique_custom_field_definition_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="customfielddefinitionversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)),
                name="custom_field_version_positive",
            ),
        ),
    ]
