from django.db import migrations


POSTGRES_PERMISSION_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_custom_role_permission()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.permission NOT IN (
        'workspaces.view', 'organizations.view', 'organizations.create', 'organizations.edit',
        'organizations.archive', 'people.view', 'people.create', 'people.edit', 'people.archive',
        'sites.view', 'sites.create', 'sites.edit', 'sites.archive', 'custom_fields.view',
        'custom_fields.manage', 'custom_fields.edit_values', 'relationships.view',
        'relationships.create', 'relationships.archive', 'recycle_bin.view', 'recycle_bin.restore',
        'documents.view', 'documents.edit', 'documents.publish', 'assets.view', 'assets.edit',
        'networks.view', 'networks.edit', 'costs.view', 'compliance.view', 'compliance.edit',
        'integrations.view'
    ) OR NOT EXISTS (
        SELECT 1 FROM accounts_customrole role
        WHERE role.id = NEW.role_id AND role.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'invalid custom role permission' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'custom role permission identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
"""


POSTGRES_PERMISSION_GUARD_REVERSE_SQL = POSTGRES_PERMISSION_GUARD_SQL.replace(
    "'relationships.create', 'relationships.archive', 'recycle_bin.view', 'recycle_bin.restore',",
    "'relationships.create', 'relationships.archive',",
)


def install_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_PERMISSION_GUARD_SQL)


def remove_permission_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_PERMISSION_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_refresh_access_collection_scope_guards")]

    operations = [migrations.RunPython(install_permission_guard, remove_permission_guard)]
