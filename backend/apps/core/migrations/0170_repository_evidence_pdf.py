"""Retain a private PDF projection on the append-only repository evidence row."""

from django.db import migrations, models

import apps.core.models


class Migration(migrations.Migration):
    dependencies = [("core", "0169_repositoryevidenceattachment")]

    operations = [
        migrations.AddField(
            model_name="repositorypublicationevidence",
            name="pdf_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                upload_to=apps.core.models.repository_evidence_pdf_upload_to,
            ),
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_repositorypublicationevidence
                ADD CONSTRAINT repository_evidence_pdf_manifest_match CHECK (
                    (pdf_file <> '') = (manifest ? 'pdf_snapshot')
                    AND (pdf_file = '' OR pdf_file =
                        'repository-evidence-pdfs/' || tenant_id::text || '/' || id::text || '/snapshot.pdf')
                );
            """,
            reverse_sql="""
                ALTER TABLE core_repositorypublicationevidence
                DROP CONSTRAINT repository_evidence_pdf_manifest_match;
            """,
        ),
    ]
