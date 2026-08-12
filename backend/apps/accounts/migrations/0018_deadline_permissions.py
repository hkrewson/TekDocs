from importlib import import_module

from django.db import migrations

PREVIOUS_SQL = import_module(
    "apps.accounts.migrations.0014_publication_control_permissions"
).PUBLICATION_CONTROL_PERMISSION_GUARD_SQL

DEADLINE_PERMISSION_SQL = PREVIOUS_SQL.replace(
    "'compliance.view', 'compliance.edit',",
    "'compliance.view', 'compliance.edit', 'deadlines.view', 'deadlines.edit',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DEADLINE_PERMISSION_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PREVIOUS_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_api_tokens")]
    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
