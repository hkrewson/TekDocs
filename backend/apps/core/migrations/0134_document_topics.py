from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0133_documentationmap_documentationmaprevision_and_more")]
    operations = [
        migrations.AddField(
            model_name="document",
            name="topic_type",
            field=models.CharField(
                choices=[
                    ("unstructured", "Unstructured"),
                    ("procedure", "Procedure"),
                    ("troubleshooting", "Troubleshooting"),
                    ("reference", "Reference"),
                    ("system_overview", "System overview"),
                    ("change_runbook", "Change runbook"),
                ],
                default="unstructured",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="document", name="topic_schema_version", field=models.PositiveSmallIntegerField(default=1)
        ),
        migrations.AddField(
            model_name="blockrevision",
            name="topic_type",
            field=models.CharField(
                choices=[
                    ("unstructured", "Unstructured"),
                    ("procedure", "Procedure"),
                    ("troubleshooting", "Troubleshooting"),
                    ("reference", "Reference"),
                    ("system_overview", "System overview"),
                    ("change_runbook", "Change runbook"),
                ],
                default="unstructured",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="blockrevision", name="topic_schema_version", field=models.PositiveSmallIntegerField(default=1)
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    topic_type__in=[
                        "unstructured",
                        "procedure",
                        "troubleshooting",
                        "reference",
                        "system_overview",
                        "change_runbook",
                    ]
                ),
                name="document_topic_type_supported",
            ),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(topic_schema_version__gte=1), name="document_topic_schema_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="blockrevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    topic_type__in=[
                        "unstructured",
                        "procedure",
                        "troubleshooting",
                        "reference",
                        "system_overview",
                        "change_runbook",
                    ]
                ),
                name="block_revision_topic_type_supported",
            ),
        ),
    ]
