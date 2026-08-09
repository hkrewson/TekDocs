from django.db import migrations


POSTGRES_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_access_collection()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.created_by_id
    ) OR TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'access collection ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_access_collection_organization()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.created_by_id
    ) OR NOT EXISTS (
        SELECT 1 FROM accounts_accesscollection collection
        WHERE collection.id = NEW.collection_id
          AND collection.tenant_id = NEW.tenant_id
          AND collection.archived_at IS NULL
    ) OR NOT EXISTS (
        SELECT 1 FROM core_organization organization
        JOIN core_entity entity ON entity.id = organization.entity_id
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
          AND entity.archived_at IS NULL
    ) THEN
        RAISE EXCEPTION 'invalid access collection organization' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'access collection organization identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_custom_role_permission()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.permission NOT IN (
        'workspaces.view', 'organizations.view', 'organizations.create', 'organizations.edit',
        'organizations.archive', 'people.view', 'people.create', 'people.edit', 'people.archive',
        'sites.view', 'sites.create', 'sites.edit', 'sites.archive', 'custom_fields.view',
        'custom_fields.manage', 'custom_fields.edit_values', 'relationships.view',
        'relationships.create', 'relationships.archive', 'documents.view', 'documents.edit',
        'documents.publish', 'assets.view', 'assets.edit', 'networks.view', 'networks.edit',
        'costs.view', 'compliance.view', 'compliance.edit', 'integrations.view'
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

CREATE OR REPLACE FUNCTION tekdocs_validate_scoped_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE role_scope varchar(16);
BEGIN
    SELECT scope INTO role_scope FROM accounts_customrole
      WHERE id = NEW.role_id AND tenant_id = NEW.tenant_id AND archived_at IS NULL;
    IF role_scope IS NULL OR role_scope NOT IN ('tenant', 'organization', 'collection') OR NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.id = NEW.membership_id AND membership.tenant_id = NEW.tenant_id
    ) OR NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.created_by_id
    ) OR EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        JOIN core_installationstate installation
          ON installation.tenant_id = membership.tenant_id
         AND installation.owner_id = membership.user_id
        WHERE membership.id = NEW.membership_id
    ) OR (NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        JOIN core_entity entity ON entity.id = organization.entity_id
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
          AND entity.archived_at IS NULL
    )) OR (NEW.collection_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM accounts_accesscollection collection
        WHERE collection.id = NEW.collection_id
          AND collection.tenant_id = NEW.tenant_id
          AND collection.archived_at IS NULL
    )) OR (role_scope = 'tenant' AND (NEW.organization_id IS NOT NULL OR NEW.collection_id IS NOT NULL))
       OR (role_scope = 'organization' AND (NEW.organization_id IS NULL OR NEW.collection_id IS NOT NULL))
       OR (role_scope = 'collection' AND (NEW.collection_id IS NULL OR NEW.organization_id IS NOT NULL)) THEN
        RAISE EXCEPTION 'invalid scoped role assignment' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'scoped role assignment identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER accounts_access_collection_guard BEFORE UPDATE ON accounts_accesscollection
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_access_collection();
CREATE TRIGGER accounts_access_collection_organization_guard BEFORE INSERT OR UPDATE ON accounts_accesscollectionorganization
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_access_collection_organization();
"""

POSTGRES_GUARD_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS accounts_access_collection_organization_guard ON accounts_accesscollectionorganization;
DROP TRIGGER IF EXISTS accounts_access_collection_guard ON accounts_accesscollection;
DROP FUNCTION IF EXISTS tekdocs_validate_access_collection_organization();
DROP FUNCTION IF EXISTS tekdocs_validate_access_collection();

CREATE OR REPLACE FUNCTION tekdocs_validate_custom_role_permission()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.permission NOT IN (
        'workspaces.view', 'organizations.view', 'organizations.create', 'organizations.edit',
        'organizations.archive', 'people.view', 'people.create', 'people.edit', 'people.archive',
        'sites.view', 'sites.create', 'sites.edit', 'sites.archive', 'custom_fields.view',
        'custom_fields.manage', 'custom_fields.edit_values', 'relationships.view',
        'relationships.create', 'relationships.archive', 'documents.view', 'documents.edit',
        'documents.publish', 'assets.view', 'assets.edit', 'networks.view', 'networks.edit',
        'compliance.view', 'compliance.edit', 'integrations.view'
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

CREATE OR REPLACE FUNCTION tekdocs_validate_scoped_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE role_scope varchar(16);
BEGIN
    SELECT scope INTO role_scope FROM accounts_customrole
      WHERE id = NEW.role_id AND tenant_id = NEW.tenant_id AND archived_at IS NULL;
    IF role_scope IS NULL OR role_scope NOT IN ('tenant', 'organization') OR NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.id = NEW.membership_id AND membership.tenant_id = NEW.tenant_id
    ) OR EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        JOIN core_installationstate installation
          ON installation.tenant_id = membership.tenant_id
         AND installation.owner_id = membership.user_id
        WHERE membership.id = NEW.membership_id
    ) OR (NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id AND organization.tenant_id = NEW.tenant_id
    )) OR (role_scope = 'tenant' AND NEW.organization_id IS NOT NULL)
       OR (role_scope = 'organization' AND NEW.organization_id IS NULL) THEN
        RAISE EXCEPTION 'invalid scoped role assignment' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'scoped role assignment identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
"""


def install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_SQL)


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_accesscollection_accesscollectionorganization_and_more")]

    operations = [migrations.RunPython(install_postgres_guards, remove_postgres_guards)]
