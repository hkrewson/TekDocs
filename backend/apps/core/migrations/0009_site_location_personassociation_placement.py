import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_person_scope_guards")]

    operations = [
        migrations.CreateModel(
            name="Site",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(blank=True, max_length=64)),
                ("address_line_1", models.CharField(blank=True, max_length=240)),
                ("address_line_2", models.CharField(blank=True, max_length=240)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("region", models.CharField(blank=True, max_length=120)),
                ("postal_code", models.CharField(blank=True, max_length=32)),
                ("country_code", models.CharField(blank=True, max_length=2)),
                ("timezone", models.CharField(blank=True, max_length=64)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "entity",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="site_record",
                        to="core.entity",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sites",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sites",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["tenant", "organization", "archived_at"],
                        name="core_site_tenant__11d30d_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=~models.Q(code=""),
                        fields=("tenant", "organization", "code"),
                        name="unique_site_code_in_workspace",
                        nulls_distinct=False,
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Location",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("building", "Building"),
                            ("floor", "Floor"),
                            ("suite", "Suite"),
                            ("room", "Room"),
                            ("office", "Office"),
                            ("desk", "Desk"),
                            ("area", "Area"),
                        ],
                        max_length=32,
                    ),
                ),
                ("code", models.CharField(blank=True, max_length=64)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "entity",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="location_record",
                        to="core.entity",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locations",
                        to="core.organization",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="core.location",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locations",
                        to="core.site",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locations",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["tenant", "organization", "site", "archived_at"],
                        name="core_locati_tenant__33fd50_idx",
                    ),
                    models.Index(fields=["site", "parent", "kind"], name="core_locati_site_id_eefe6d_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=~models.Q(parent=models.F("id")),
                        name="location_not_own_parent",
                    ),
                    models.UniqueConstraint(
                        condition=~models.Q(code=""),
                        fields=("site", "parent", "code"),
                        name="unique_location_code_under_parent",
                        nulls_distinct=False,
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="personassociation",
            name="site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="person_associations",
                to="core.site",
            ),
        ),
        migrations.AddField(
            model_name="personassociation",
            name="structured_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="person_associations",
                to="core.location",
            ),
        ),
    ]
