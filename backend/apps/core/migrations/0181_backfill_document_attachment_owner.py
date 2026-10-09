"""Backfill stable content ownership in bounded batches after schema expansion."""

from django.db import migrations, transaction
from django.db.models import Q

BATCH_SIZE = 500


def backfill_owner(apps, schema_editor):  # type: ignore[no-untyped-def]
    Attachment = apps.get_model("core", "DocumentAttachment")
    database = schema_editor.connection.alias
    while True:
        rows = list(
            Attachment.objects.using(database)
            .filter(Q(owner_workspace__isnull=True) | Q(owner_content_id__isnull=True))
            .select_related("document__entity")
            .order_by("pk")[:BATCH_SIZE]
        )
        if not rows:
            return
        for row in rows:
            row.owner_workspace_id = row.document.entity.workspace_id
            row.owner_content_id = row.document_id
        with transaction.atomic(using=database):
            Attachment.objects.using(database).bulk_update(
                rows, ["owner_workspace", "owner_content_id"], batch_size=BATCH_SIZE
            )


def clear_owner(apps, schema_editor):  # type: ignore[no-untyped-def]
    Attachment = apps.get_model("core", "DocumentAttachment")
    database = schema_editor.connection.alias
    while True:
        ids = list(
            Attachment.objects.using(database)
            .filter(Q(owner_workspace__isnull=False) | Q(owner_content_id__isnull=False))
            .order_by("pk")
            .values_list("pk", flat=True)[:BATCH_SIZE]
        )
        if not ids:
            return
        with transaction.atomic(using=database):
            Attachment.objects.using(database).filter(pk__in=ids).update(
                owner_workspace_id=None, owner_content_id=None
            )


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0180_document_attachment_content_owner")]

    operations = [migrations.RunPython(backfill_owner, clear_owner)]
