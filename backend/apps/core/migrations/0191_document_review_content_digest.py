"""Pin document review decisions to the Markdown content reviewed."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0190_primary_repository_static_publication")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="review_content_sha256",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
