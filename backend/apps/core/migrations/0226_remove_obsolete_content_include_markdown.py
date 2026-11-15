"""Normalize databases that retained a never-authoritative content include column."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0225_document_remote_application")]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE core_contentinclude DROP COLUMN IF EXISTS resolved_markdown;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
