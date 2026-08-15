import django.db.models.deletion
from django.db import migrations, models


def populate_block_sources(apps, _schema_editor):  # type: ignore[no-untyped-def]
    Block = apps.get_model("core", "Block")
    DocumentPlacement = apps.get_model("core", "DocumentPlacement")
    for block in Block.objects.filter(source_document__isnull=True).iterator():
        placement = (
            DocumentPlacement.objects.filter(block_id=block.id)
            .order_by("parent_id", "position", "created_at", "id")
            .first()
        )
        if placement is not None:
            block.source_document_id = placement.document_id
            block.save(update_fields=("source_document",))


class Migration(migrations.Migration):
    dependencies = [("core", "0110_runtime_organization_anchor_creation")]

    operations = [
        migrations.AddField(
            model_name="block",
            name="source_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_blocks",
                to="core.document",
            ),
        ),
        migrations.RunPython(populate_block_sources, migrations.RunPython.noop),
        migrations.AddField(
            model_name="block",
            name="kind",
            field=models.CharField(
                choices=[
                    ("rich_text", "Rich text"),
                    ("heading", "Heading"),
                    ("code", "Code"),
                    ("url", "URL"),
                    ("document_link", "Document link"),
                    ("entity_reference", "Entity reference"),
                    ("file_reference", "File reference"),
                ],
                default="rich_text",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="block",
            constraint=models.CheckConstraint(
                condition=models.Q(kind__in=(
                    "rich_text",
                    "heading",
                    "code",
                    "url",
                    "document_link",
                    "entity_reference",
                    "file_reference",
                )),
                name="document_block_kind_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="block",
            index=models.Index(
                fields=["tenant", "organization", "kind", "archived_at"],
                name="core_block_kind_scope_idx",
            ),
        ),
    ]
