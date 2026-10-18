from django.db import migrations, models


INVITATION_SCOPE_GUARD = r"""
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
        RAISE EXCEPTION 'client invitation organization must be an active tenant client' USING ERRCODE = '23514';
    END IF;
    IF (NEW.role IN ('client_administrator', 'client_user')) IS DISTINCT FROM (NEW.organization_id IS NOT NULL) THEN
        RAISE EXCEPTION 'invitation role does not match organization scope' USING ERRCODE = '23514';
    END IF;
    IF NEW.role IN ('client_administrator', 'client_user') AND NEW.workspace_scope <> 'tenant' THEN
        RAISE EXCEPTION 'client portal invitations cannot use staff workspace scope' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.email IS DISTINCT FROM OLD.email
        OR NEW.invited_by_id IS DISTINCT FROM OLD.invited_by_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.role IS DISTINCT FROM OLD.role
        OR NEW.workspace_scope IS DISTINCT FROM OLD.workspace_scope
    ) THEN
        RAISE EXCEPTION 'invitation ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
"""

INVITATION_SCOPE_GUARD_REVERSE = INVITATION_SCOPE_GUARD.replace(
    "    IF NEW.role IN ('client_administrator', 'client_user') AND NEW.workspace_scope <> 'tenant' THEN\n"
    "        RAISE EXCEPTION 'client portal invitations cannot use staff workspace scope' USING ERRCODE = '23514';\n"
    "    END IF;\n",
    "",
).replace(
    "        OR NEW.workspace_scope IS DISTINCT FROM OLD.workspace_scope\n",
    "",
)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_data_flow_permissions")]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="workspace_scope",
            field=models.CharField(
                choices=[("tenant", "All authorized workspaces"), ("assigned_organizations", "Assigned organizations only")],
                default="tenant",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="tenantmembership",
            name="workspace_scope",
            field=models.CharField(
                choices=[("tenant", "All authorized workspaces"), ("assigned_organizations", "Assigned organizations only")],
                default="tenant",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="invitation",
            constraint=models.CheckConstraint(
                condition=models.Q(("workspace_scope__in", ("tenant", "assigned_organizations"))),
                name="invitation_workspace_scope_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="invitation",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("role__in", ("client_administrator", "client_user")), ("workspace_scope", "tenant"))
                    | models.Q(("role__in", ("administrator", "technician", "contributor", "read_only")))
                ),
                name="portal_invitation_workspace_scope_default",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(("workspace_scope__in", ("tenant", "assigned_organizations"))),
                name="membership_workspace_scope_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("role__in", ("client_administrator", "client_user")), ("workspace_scope", "tenant"))
                    | models.Q(("role__in", ("administrator", "technician", "contributor", "read_only")))
                ),
                name="portal_membership_workspace_scope_default",
            ),
        ),
        migrations.RunSQL(INVITATION_SCOPE_GUARD, INVITATION_SCOPE_GUARD_REVERSE),
    ]
