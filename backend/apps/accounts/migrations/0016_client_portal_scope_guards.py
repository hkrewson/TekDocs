from importlib import import_module

from django.db import migrations

PREVIOUS_GUARD_SQL = import_module("apps.accounts.migrations.0012_certify_control_plane_integrity").POSTGRES_GUARD_SQL

CLIENT_PORTAL_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_tenant_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        JOIN core_entity entity ON entity.id = organization.entity_id AND entity.archived_at IS NULL
        JOIN core_organizationclassification classification
          ON classification.organization_id = organization.id AND classification.kind = 'client'
        WHERE organization.id = NEW.organization_id AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'client membership organization must be an active tenant client' USING ERRCODE = '23514';
    END IF;
    IF (NEW.role IN ('client_administrator', 'client_user')) IS DISTINCT FROM (NEW.organization_id IS NOT NULL) THEN
        RAISE EXCEPTION 'membership role does not match organization scope' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.user_id IS DISTINCT FROM OLD.user_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
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
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        JOIN core_entity entity ON entity.id = organization.entity_id AND entity.archived_at IS NULL
        JOIN core_organizationclassification classification
          ON classification.organization_id = organization.id AND classification.kind = 'client'
        WHERE organization.id = NEW.organization_id AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'client invitation organization must be a tenant client' USING ERRCODE = '23514';
    END IF;
    IF (NEW.role IN ('client_administrator', 'client_user')) IS DISTINCT FROM (NEW.organization_id IS NOT NULL) THEN
        RAISE EXCEPTION 'invitation role does not match organization scope' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.email IS DISTINCT FROM OLD.email
        OR NEW.invited_by_id IS DISTINCT FROM OLD.invited_by_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.role IS DISTINCT FROM OLD.role
    ) THEN
        RAISE EXCEPTION 'invitation ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
"""


def install_client_portal_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CLIENT_PORTAL_GUARD_SQL)


def restore_previous_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(PREVIOUS_GUARD_SQL)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_client_portal_membership_scope")]
    operations = [migrations.RunPython(install_client_portal_guards, restore_previous_guards)]
