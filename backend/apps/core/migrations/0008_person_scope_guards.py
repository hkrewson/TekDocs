from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_person_anchor()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.entity_id
          AND entity.tenant_id = NEW.tenant_id
          AND entity.organization_id IS NULL
    ) THEN
        RAISE EXCEPTION 'person identity must use a tenant-scoped entity in the same tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_person_association_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_person person
        WHERE person.id = NEW.person_id
          AND person.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'person association must belong to the person tenant' USING ERRCODE = '23514';
    END IF;
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'person association organization must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER core_person_anchor_guard
BEFORE INSERT OR UPDATE OF tenant_id, entity_id ON core_person
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_person_anchor();

CREATE TRIGGER core_person_association_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, person_id, organization_id ON core_personassociation
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_person_association_scope();
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_person_association_scope_guard ON core_personassociation;
DROP TRIGGER IF EXISTS core_person_anchor_guard ON core_person;
DROP FUNCTION IF EXISTS tekdocs_validate_person_association_scope();
DROP FUNCTION IF EXISTS tekdocs_validate_person_anchor();
"""


def install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_person_personassociation_and_more")]

    operations = [migrations.RunPython(install_postgres_guards, remove_postgres_guards)]
