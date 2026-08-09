import hashlib
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_markdown_to_revisions(apps, schema_editor):
    Block = apps.get_model("core", "Block")
    BlockRevision = apps.get_model("core", "BlockRevision")
    for block in Block.objects.all().iterator():
        markdown = block.markdown
        revision = BlockRevision.objects.create(
            id=uuid.uuid4(),
            tenant_id=block.tenant_id,
            organization_id=block.organization_id,
            block_id=block.id,
            parent_id=None,
            revision_number=1,
            markdown=markdown,
            checksum=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            created_by_id=None,
        )
        block.current_revision_id = revision.id
        block.save(update_fields=("current_revision",))


def restore_markdown_from_revisions(apps, schema_editor):
    Block = apps.get_model("core", "Block")
    for block in Block.objects.select_related("current_revision").all().iterator():
        block.markdown = block.current_revision.markdown if block.current_revision_id else ""
        block.save(update_fields=("markdown",))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0021_document_scope_guards_and_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("revision_number", models.PositiveIntegerField()),
                ("markdown", models.TextField(blank=True)),
                ("checksum", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "block",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisions",
                        to="core.block",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="block_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="block_revisions",
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
                        to="core.blockrevision",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="block_revisions",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ("-revision_number", "-created_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["tenant", "organization", "block", "-revision_number"],
                        name="core_blockr_tenant__42e5a8_idx",
                    ),
                    models.Index(fields=["block", "checksum"], name="core_blockr_block_i_a9954b_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("block", "revision_number"), name="unique_block_revision_number"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("revision_number__gte", 1)), name="block_revision_number_positive"
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="block",
            name="current_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="current_for_blocks",
                to="core.blockrevision",
            ),
        ),
        migrations.RunPython(migrate_markdown_to_revisions, restore_markdown_from_revisions),
        migrations.RemoveField(model_name="block", name="markdown"),
    ]
