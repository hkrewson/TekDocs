from importlib import import_module

from django.db import migrations

POSTGRES_PERMISSION_GUARD_SQL = import_module(
    "apps.accounts.migrations.0011_recovery_permission_guard"
).POSTGRES_PERMISSION_GUARD_SQL


POSTGRES_CREDENTIAL_REFERENCE_PERMISSION_GUARD_SQL = POSTGRES_PERMISSION_GUARD_SQL.replace(
    "'networks.view', 'networks.edit', 'costs.view', 'compliance.view', 'compliance.edit',",
    "'networks.view', 'networks.edit', 'costs.view', 'credential_references.view', "
    "'credential_references.manage', 'credential_references.open', 'compliance.view', 'compliance.edit',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_CREDENTIAL_REFERENCE_PERMISSION_GUARD_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_PERMISSION_GUARD_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_certify_control_plane_integrity")]
    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
