import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0023_block_revision_guards_and_rls")]

    operations = [
        migrations.RemoveConstraint(
            model_name="documentplacement",
            name="unique_document_block_position",
        ),
        migrations.RemoveIndex(
            model_name="documentplacement",
            name="core_docume_tenant__46e522_idx",
        ),
        migrations.AddField(
            model_name="documentplacement",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="core.documentplacement",
            ),
        ),
        migrations.AddField(
            model_name="documentplacement",
            name="pinned_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pinned_placements",
                to="core.blockrevision",
            ),
        ),
        migrations.AddField(
            model_name="documentplacement",
            name="resolution_mode",
            field=models.CharField(
                choices=[("live", "Live"), ("pinned", "Pinned")],
                default="live",
                max_length=12,
            ),
        ),
        migrations.AddConstraint(
            model_name="documentplacement",
            constraint=models.UniqueConstraint(
                condition=models.Q(("parent__isnull", True)),
                fields=("document", "position"),
                name="unique_document_root_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentplacement",
            constraint=models.UniqueConstraint(
                condition=models.Q(("parent__isnull", False)),
                fields=("parent", "position"),
                name="unique_document_child_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentplacement",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("pinned_revision__isnull", True), ("resolution_mode", "live"))
                    | models.Q(("pinned_revision__isnull", False), ("resolution_mode", "pinned"))
                ),
                name="document_placement_resolution_target",
            ),
        ),
        migrations.AddIndex(
            model_name="documentplacement",
            index=models.Index(
                fields=["tenant", "organization", "document", "parent", "position"],
                name="core_docpl_scope_tree_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="documentplacement",
            index=models.Index(
                fields=["tenant", "block", "resolution_mode"],
                name="core_docpl_block_mode_idx",
            ),
        ),
    ]
