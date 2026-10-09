"""Allow a stable content owner without manufacturing a legacy Document row."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0182_guard_document_attachment_content_owner")]

    operations = [
        migrations.AlterField(
            model_name="documentattachment",
            name="document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attachments",
                to="core.document",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentattachment",
            constraint=models.CheckConstraint(
                condition=models.Q(document__isnull=False) | models.Q(purpose="attachment"),
                name="native_attachment_not_primary_file",
            ),
        ),
    ]
