"""Expand managed-file ownership without changing legacy attachment reads."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0179_repository_evidence_public_attachment_ids")]

    operations = [
        migrations.AddField(
            model_name="documentattachment",
            name="owner_content_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentattachment",
            name="owner_workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="managed_document_attachments",
                to="core.workspace",
            ),
        ),
    ]
