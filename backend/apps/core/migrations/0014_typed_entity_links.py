from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_custom_field_scope_guards")]

    operations = [
        migrations.RemoveConstraint(
            model_name="entitylink",
            name="unique_typed_entity_link",
        ),
        migrations.RemoveIndex(
            model_name="entitylink",
            name="core_entity_tenant__b81b7f_idx",
        ),
        migrations.AddField(
            model_name="entitylink",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="entitylink",
            name="link_type",
            field=models.CharField(
                choices=[
                    ("related_to", "Related to"),
                    ("depends_on", "Depends on"),
                    ("managed_by", "Managed by"),
                    ("supplied_by", "Supplied by"),
                    ("manufactured_by", "Manufactured by"),
                    ("partnered_with", "Partnered with"),
                    ("located_at", "Located at"),
                    ("assigned_to", "Assigned to"),
                    ("references", "References"),
                ],
                max_length=80,
            ),
        ),
        migrations.AddConstraint(
            model_name="entitylink",
            constraint=models.UniqueConstraint(
                condition=models.Q(archived_at__isnull=True),
                fields=("source", "target", "link_type"),
                name="unique_active_typed_entity_link",
            ),
        ),
        migrations.AddConstraint(
            model_name="entitylink",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    link_type__in=(
                        "related_to",
                        "depends_on",
                        "managed_by",
                        "supplied_by",
                        "manufactured_by",
                        "partnered_with",
                        "located_at",
                        "assigned_to",
                        "references",
                    )
                ),
                name="entity_link_type_supported",
            ),
        ),
        migrations.AddIndex(
            model_name="entitylink",
            index=models.Index(
                fields=["tenant", "link_type", "archived_at"],
                name="entity_link_type_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="entitylink",
            index=models.Index(
                fields=["tenant", "source", "archived_at"],
                name="entity_link_source_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="entitylink",
            index=models.Index(
                fields=["tenant", "target", "archived_at"],
                name="entity_link_target_active_idx",
            ),
        ),
    ]
