from importlib import import_module

from django.db import migrations


DROP_ACCESS_COLLECTION_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS accounts_access_collection_organization_guard
ON accounts_accesscollectionorganization;
DROP TRIGGER IF EXISTS accounts_access_collection_guard
ON accounts_accesscollection;
"""


def refresh_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    guard_migration = import_module(
        "apps.accounts.migrations.0009_access_collection_scope_guards"
    )
    schema_editor.execute(DROP_ACCESS_COLLECTION_TRIGGERS_SQL)
    schema_editor.execute(guard_migration.POSTGRES_GUARD_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_access_collection_scope_guards")]

    operations = [migrations.RunPython(refresh_postgres_guards, migrations.RunPython.noop)]
