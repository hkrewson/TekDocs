from django.db import migrations


def complete_legacy_invoice_revisions(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Turn editable change-only drafts into complete replacement invoices."""
    Invoice = apps.get_model("core", "Invoice")
    InvoiceLine = apps.get_model("core", "InvoiceLine")
    database = schema_editor.connection.alias

    drafts = (
        Invoice.objects.using(database)
        .filter(state="draft", source_kind="supplement", source_invoice__isnull=False)
        .select_related("source_invoice")
        .order_by("id")
    )
    for draft in drafts.iterator():
        source_lines = list(
            InvoiceLine.objects.using(database)
            .filter(invoice_id=draft.source_invoice_id)
            .order_by("position", "created_at", "id")
        )
        added_lines = list(
            InvoiceLine.objects.using(database)
            .filter(invoice_id=draft.id)
            .order_by("-position", "-created_at", "-id")
        )

        # Free positions 1..N before inserting the immutable source snapshot.
        # Descending updates avoid transient unique-position collisions.
        shift = len(source_lines)
        for line in added_lines:
            InvoiceLine.objects.using(database).filter(pk=line.pk).update(position=line.position + shift)

        for position, original in enumerate(source_lines, start=1):
            InvoiceLine.objects.using(database).create(
                tenant_id=draft.tenant_id,
                organization_id=draft.organization_id,
                invoice_id=draft.id,
                position=position,
                description=original.description,
                quantity=original.quantity,
                unit=original.unit,
                unit_amount=original.unit_amount,
                currency=original.currency,
                tax_rate_name=original.tax_rate_name,
                tax_rate_value=original.tax_rate_value,
                tax_inclusive=original.tax_inclusive,
                stock_quantity_consumed=0,
            )

        reference = draft.reference
        expected = f"Supplement to {draft.source_invoice.number}"
        if reference == expected:
            reference = f"Replacement to {draft.source_invoice.number}"
        Invoice.objects.using(database).filter(pk=draft.pk).update(
            source_kind="replacement",
            reference=reference,
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0159_invoice_follow_up_drafts")]

    operations = [
        migrations.RunPython(complete_legacy_invoice_revisions, migrations.RunPython.noop),
    ]
