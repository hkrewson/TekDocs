from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_location_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.entity_id
          AND entity.tenant_id = NEW.tenant_id
          AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location entity must use the location workspace scope' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM core_site site
        WHERE site.id = NEW.site_id
          AND site.tenant_id = NEW.tenant_id
          AND site.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location site must use the location workspace scope' USING ERRCODE = '23514';
    END IF;
    IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_location parent
        WHERE parent.id = NEW.parent_id
          AND parent.site_id = NEW.site_id
          AND parent.tenant_id = NEW.tenant_id
          AND parent.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location parent must belong to the same site and workspace' USING ERRCODE = '23514';
    END IF;
    IF NEW.parent_id IS NOT NULL AND EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_id FROM core_location WHERE id = NEW.parent_id
            UNION
            SELECT location.id, location.parent_id
            FROM core_location location
            JOIN ancestors ON location.id = ancestors.parent_id
        )
        SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'location hierarchy cannot contain a cycle' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_location_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.entity_id
          AND entity.tenant_id = NEW.tenant_id
          AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location entity must use the location workspace scope' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM core_site site
        WHERE site.id = NEW.site_id
          AND site.tenant_id = NEW.tenant_id
          AND site.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location site must use the location workspace scope' USING ERRCODE = '23514';
    END IF;
    IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_location parent
        WHERE parent.id = NEW.parent_id
          AND parent.site_id = NEW.site_id
          AND parent.tenant_id = NEW.tenant_id
          AND parent.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'location parent must belong to the same site and workspace' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
"""


def install_cycle_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_cycle_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0010_site_location_scope_guards")]

    operations = [migrations.RunPython(install_cycle_guard, remove_cycle_guard)]
