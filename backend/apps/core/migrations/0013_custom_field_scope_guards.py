from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_custom_field_definition_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.key IS DISTINCT FROM OLD.key
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
    ) THEN
        RAISE EXCEPTION 'custom-field definition identity is immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'custom-field organization must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_custom_field_version_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_customfielddefinition definition
        WHERE definition.id = NEW.definition_id
          AND definition.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'custom-field version must belong to its definition tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_reject_custom_field_version_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'custom-field definition versions are immutable' USING ERRCODE = '23514';
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_entity_custom_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    item record;
BEGIN
    IF jsonb_typeof(NEW.custom_fields) != 'object' THEN
        RAISE EXCEPTION 'entity custom fields must be an object' USING ERRCODE = '23514';
    END IF;
    FOR item IN SELECT key, value FROM jsonb_each(NEW.custom_fields)
    LOOP
        IF jsonb_typeof(item.value) != 'object'
           OR NOT item.value ? 'definition_version_id'
           OR NOT item.value ? 'version'
           OR NOT item.value ? 'value'
           OR (SELECT count(*) FROM jsonb_object_keys(item.value)) != 3
        THEN
            RAISE EXCEPTION 'entity custom-field envelope is malformed' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1
            FROM core_customfielddefinition definition
            JOIN core_customfielddefinitionversion definition_version
              ON definition_version.definition_id = definition.id
            WHERE definition.id = item.key::uuid
              AND definition.tenant_id = NEW.tenant_id
              AND definition.entity_type = NEW.entity_type
              AND definition.archived_at IS NULL
              AND (
                  definition.organization_id IS NULL
                  OR definition.organization_id = NEW.organization_id
              )
              AND definition_version.id = (item.value ->> 'definition_version_id')::uuid
              AND definition_version.tenant_id = NEW.tenant_id
              AND definition_version.version = (item.value ->> 'version')::integer
        ) THEN
            RAISE EXCEPTION 'entity custom field must use an applicable definition version' USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NEW;
EXCEPTION
    WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'entity custom-field envelope identifiers are malformed' USING ERRCODE = '23514';
END
$$;

CREATE TRIGGER core_custom_field_definition_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id, key, entity_type ON core_customfielddefinition
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_custom_field_definition_scope();

CREATE TRIGGER core_custom_field_version_scope_guard
BEFORE INSERT ON core_customfielddefinitionversion
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_custom_field_version_scope();

CREATE TRIGGER core_custom_field_version_immutable_update
BEFORE UPDATE ON core_customfielddefinitionversion
FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_custom_field_version_change();

CREATE TRIGGER core_custom_field_version_immutable_delete
BEFORE DELETE ON core_customfielddefinitionversion
FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_custom_field_version_change();

CREATE TRIGGER core_entity_custom_fields_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id, entity_type, custom_fields ON core_entity
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_custom_fields();
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_entity_custom_fields_guard ON core_entity;
DROP TRIGGER IF EXISTS core_custom_field_version_immutable_delete ON core_customfielddefinitionversion;
DROP TRIGGER IF EXISTS core_custom_field_version_immutable_update ON core_customfielddefinitionversion;
DROP TRIGGER IF EXISTS core_custom_field_version_scope_guard ON core_customfielddefinitionversion;
DROP TRIGGER IF EXISTS core_custom_field_definition_scope_guard ON core_customfielddefinition;
DROP FUNCTION IF EXISTS tekdocs_validate_entity_custom_fields();
DROP FUNCTION IF EXISTS tekdocs_reject_custom_field_version_change();
DROP FUNCTION IF EXISTS tekdocs_validate_custom_field_version_scope();
DROP FUNCTION IF EXISTS tekdocs_validate_custom_field_definition_scope();
"""


def install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0012_customfielddefinition_and_versions")]

    operations = [migrations.RunPython(install_postgres_guards, remove_postgres_guards)]
