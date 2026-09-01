from django.db import migrations, models

TOPIC_CHOICES = [
    ("unstructured", "Unstructured"),
    ("policy", "Policy"),
    ("procedure", "Procedure"),
    ("guide", "Guide"),
    ("troubleshooting", "Troubleshooting"),
    ("reference", "Reference"),
    ("system_overview", "System overview"),
    ("change_runbook", "Change runbook"),
]
TOPIC_VALUES = [value for value, _label in TOPIC_CHOICES]


class Migration(migrations.Migration):
    dependencies = [("core", "0134_document_topics")]
    operations = [
        migrations.RemoveConstraint(model_name="document", name="document_topic_type_supported"),
        migrations.RemoveConstraint(model_name="blockrevision", name="block_revision_topic_type_supported"),
        migrations.AlterField(
            model_name="document",
            name="topic_type",
            field=models.CharField(choices=TOPIC_CHOICES, default="unstructured", max_length=32),
        ),
        migrations.AlterField(
            model_name="blockrevision",
            name="topic_type",
            field=models.CharField(choices=TOPIC_CHOICES, default="unstructured", max_length=32),
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                condition=models.Q(topic_type__in=TOPIC_VALUES), name="document_topic_type_supported"
            ),
        ),
        migrations.AddConstraint(
            model_name="blockrevision",
            constraint=models.CheckConstraint(
                condition=models.Q(topic_type__in=TOPIC_VALUES), name="block_revision_topic_type_supported"
            ),
        ),
    ]
