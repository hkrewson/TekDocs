from django.db import migrations


POSTGRES_SCOPE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('tekdocs.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION tekdocs_current_organization_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('tekdocs.organization_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION tekdocs_scope_matches(row_tenant_id uuid, row_organization_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN tekdocs_current_tenant_id() IS NULL THEN false
        WHEN row_tenant_id <> tekdocs_current_tenant_id() THEN false
        WHEN current_setting('tekdocs.organization_mode', true) = 'all' THEN true
        WHEN current_setting('tekdocs.organization_mode', true) = 'msp' THEN row_organization_id IS NULL
        WHEN current_setting('tekdocs.organization_mode', true) = 'organization'
            THEN row_organization_id = tekdocs_current_organization_id()
        ELSE false
    END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_entity_organization_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.entity_id = NEW.id
          AND (organization.tenant_id <> NEW.tenant_id OR NEW.organization_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'organization anchor must remain MSP-scoped in its tenant' USING ERRCODE = '23514';
    END IF;
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'entity organization scope must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_organization_anchor()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM core_entity entity
        WHERE entity.id = NEW.entity_id
          AND entity.tenant_id = NEW.tenant_id
          AND entity.organization_id IS NULL
    ) THEN
        RAISE EXCEPTION 'organization anchor must be an MSP-scoped entity in the same tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_entity_link_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.source_id AND entity.tenant_id = NEW.tenant_id
    ) OR NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.target_id AND entity.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'entity link endpoints must belong to the link tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER core_entity_organization_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id ON core_entity
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_organization_scope();

CREATE TRIGGER core_organization_anchor_guard
BEFORE INSERT OR UPDATE OF tenant_id, entity_id ON core_organization
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_organization_anchor();

CREATE TRIGGER core_entity_link_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, source_id, target_id ON core_entitylink
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_link_scope();
"""


POSTGRES_SCOPE_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_entity_link_scope_guard ON core_entitylink;
DROP TRIGGER IF EXISTS core_organization_anchor_guard ON core_organization;
DROP TRIGGER IF EXISTS core_entity_organization_scope_guard ON core_entity;
DROP FUNCTION IF EXISTS tekdocs_validate_entity_link_scope();
DROP FUNCTION IF EXISTS tekdocs_validate_organization_anchor();
DROP FUNCTION IF EXISTS tekdocs_validate_entity_organization_scope();
DROP FUNCTION IF EXISTS tekdocs_scope_matches(uuid, uuid);
DROP FUNCTION IF EXISTS tekdocs_current_organization_id();
DROP FUNCTION IF EXISTS tekdocs_current_tenant_id();
"""


def install_postgres_scope_contract(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_SCOPE_SQL)


def remove_postgres_scope_contract(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_SCOPE_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0003_organization_entity_organization_and_more")]

    operations = [migrations.RunPython(install_postgres_scope_contract, remove_postgres_scope_contract)]
