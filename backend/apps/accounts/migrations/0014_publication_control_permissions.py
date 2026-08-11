from importlib import import_module

from django.db import migrations


CURRENT_PERMISSION_GUARD_SQL = import_module(
    "apps.accounts.migrations.0013_credential_reference_permission_guard"
).POSTGRES_CREDENTIAL_REFERENCE_PERMISSION_GUARD_SQL

PUBLICATION_CONTROL_PERMISSION_GUARD_SQL = CURRENT_PERMISSION_GUARD_SQL.replace(
    "'documents.view', 'documents.edit', 'documents.publish',",
    "'documents.view', 'documents.edit', 'documents.publish', 'documents.approve', 'documents.withdraw',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PUBLICATION_CONTROL_PERMISSION_GUARD_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CURRENT_PERMISSION_GUARD_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_credential_reference_permission_guard")]
    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
