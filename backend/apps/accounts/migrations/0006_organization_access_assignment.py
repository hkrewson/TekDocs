import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


POSTGRES_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_organization_access_assignment()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) OR NOT EXISTS (
        SELECT 1 FROM accounts_tenantmembership membership
        WHERE membership.id = NEW.membership_id
          AND membership.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'organization staff assignment must share one tenant' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.membership_id IS DISTINCT FROM OLD.membership_id
        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'organization staff assignment identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER accounts_organization_access_assignment_guard
BEFORE INSERT OR UPDATE ON accounts_organizationaccessassignment
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_organization_access_assignment();
"""


POSTGRES_GUARD_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS accounts_organization_access_assignment_guard ON accounts_organizationaccessassignment;
DROP FUNCTION IF EXISTS tekdocs_validate_organization_access_assignment();
"""


def install_postgres_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_SQL)


def remove_postgres_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_tenant_membership_role"),
        ("core", "0016_organization_access_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationAccessAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_organization_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_access_assignments",
                        to="accounts.tenantmembership",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="access_assignments",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_access_assignments",
                        to="core.tenant",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="organizationaccessassignment",
            constraint=models.UniqueConstraint(
                fields=("organization", "membership"),
                name="unique_organization_staff_assignment",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationaccessassignment",
            index=models.Index(
                fields=["tenant", "organization", "membership"],
                name="accounts_org_staff_scope_idx",
            ),
        ),
        migrations.RunPython(install_postgres_guard, remove_postgres_guard),
    ]
