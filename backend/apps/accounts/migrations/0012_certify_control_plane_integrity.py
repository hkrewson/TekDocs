from django.db import migrations


POSTGRES_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_tenant_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.user_id IS DISTINCT FROM OLD.user_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'tenant membership identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_invitation_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.invited_by_id
    ) OR (NEW.accepted_by_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.accepted_by_id
    )) THEN
        RAISE EXCEPTION 'invitation actors must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.email IS DISTINCT FROM OLD.email
        OR NEW.invited_by_id IS DISTINCT FROM OLD.invited_by_id
    ) THEN
        RAISE EXCEPTION 'invitation ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_organization_access_assignment_actor()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id
          AND membership.user_id = NEW.created_by_id
    ) THEN
        RAISE EXCEPTION 'organization staff assignment creator must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_custom_role_creator()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.tenant_id = NEW.tenant_id AND membership.user_id = NEW.created_by_id
    ) THEN
        RAISE EXCEPTION 'custom role creator must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS accounts_tenant_membership_guard ON accounts_tenantmembership;
CREATE TRIGGER accounts_tenant_membership_guard
BEFORE UPDATE ON accounts_tenantmembership
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_tenant_membership();

DROP TRIGGER IF EXISTS accounts_invitation_scope_guard ON accounts_invitation;
CREATE TRIGGER accounts_invitation_scope_guard
BEFORE INSERT OR UPDATE ON accounts_invitation
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_invitation_scope();

DROP TRIGGER IF EXISTS accounts_organization_access_assignment_actor_guard
ON accounts_organizationaccessassignment;
CREATE TRIGGER accounts_organization_access_assignment_actor_guard
BEFORE INSERT OR UPDATE ON accounts_organizationaccessassignment
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_organization_access_assignment_actor();

DROP TRIGGER IF EXISTS accounts_custom_role_creator_guard ON accounts_customrole;
CREATE TRIGGER accounts_custom_role_creator_guard
BEFORE INSERT OR UPDATE ON accounts_customrole
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_custom_role_creator();

DROP TRIGGER IF EXISTS accounts_access_collection_creator_guard ON accounts_accesscollection;
CREATE TRIGGER accounts_access_collection_creator_guard
BEFORE INSERT ON accounts_accesscollection
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_access_collection();
"""


POSTGRES_GUARD_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS accounts_access_collection_creator_guard ON accounts_accesscollection;
DROP TRIGGER IF EXISTS accounts_custom_role_creator_guard ON accounts_customrole;
DROP TRIGGER IF EXISTS accounts_organization_access_assignment_actor_guard
ON accounts_organizationaccessassignment;
DROP TRIGGER IF EXISTS accounts_invitation_scope_guard ON accounts_invitation;
DROP TRIGGER IF EXISTS accounts_tenant_membership_guard ON accounts_tenantmembership;
DROP FUNCTION IF EXISTS tekdocs_validate_custom_role_creator();
DROP FUNCTION IF EXISTS tekdocs_validate_organization_access_assignment_actor();
DROP FUNCTION IF EXISTS tekdocs_validate_invitation_scope();
DROP FUNCTION IF EXISTS tekdocs_validate_tenant_membership();
"""


def install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_SQL)


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_recovery_permission_guard")]

    operations = [migrations.RunPython(install_postgres_guards, remove_postgres_guards)]
