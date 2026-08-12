from importlib import import_module

from django.db import migrations

PREVIOUS_SQL = import_module("apps.accounts.migrations.0018_deadline_permissions").DEADLINE_PERMISSION_SQL
DOMAIN_PERMISSION_SQL = PREVIOUS_SQL.replace(
    "'deadlines.view', 'deadlines.edit',",
    "'deadlines.view', 'deadlines.edit', 'domains.view', 'domains.edit',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DOMAIN_PERMISSION_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PREVIOUS_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0018_deadline_permissions")]
    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
