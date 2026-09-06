from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0145_stock_inventory")]

    operations = [
        migrations.AddField(
            model_name="invoiceline",
            name="stock_quantity_consumed",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=15),
        ),
        migrations.AddConstraint(
            model_name="invoiceline",
            constraint=models.CheckConstraint(
                condition=models.Q(("stock_quantity_consumed__gte", 0)),
                name="invoice_line_stock_consumed_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="invoiceline",
            constraint=models.CheckConstraint(
                condition=models.Q(("stock_item__isnull", False), ("stock_quantity_consumed", 0), _connector="OR"),
                name="invoice_line_stock_consumed_origin",
            ),
        ),
    ]
