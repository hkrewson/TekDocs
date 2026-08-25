from importlib import import_module

from django.db import migrations

PREVIOUS_SQL = import_module("apps.accounts.migrations.0019_domain_permissions").DOMAIN_PERMISSION_SQL
DATA_FLOW_PERMISSION_SQL = PREVIOUS_SQL.replace(
    "'domains.view', 'domains.edit',",
    "'domains.view', 'domains.edit', 'data_flows.view', 'data_flows.edit',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DATA_FLOW_PERMISSION_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PREVIOUS_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_domain_permissions")]
    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
