from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_organization_classification_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'organization classification must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER core_organization_classification_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id ON core_organizationclassification
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_organization_classification_scope();
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_organization_classification_scope_guard ON core_organizationclassification;
DROP FUNCTION IF EXISTS tekdocs_validate_organization_classification_scope();
"""


def install_postgres_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_postgres_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0005_organization_legal_name_organization_website_and_more")]

    operations = [migrations.RunPython(install_postgres_guard, remove_postgres_guard)]
