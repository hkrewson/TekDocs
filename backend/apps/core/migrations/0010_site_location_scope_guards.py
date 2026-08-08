from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_site_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'site organization must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM core_entity entity
        WHERE entity.id = NEW.entity_id
          AND entity.tenant_id = NEW.tenant_id
          AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'site entity must use the site workspace scope' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

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

CREATE TRIGGER core_site_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id, entity_id ON core_site
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_site_scope();

CREATE TRIGGER core_location_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id, entity_id, site_id, parent_id ON core_location
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_location_scope();

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
    IF NEW.site_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_site site
        WHERE site.id = NEW.site_id
          AND site.tenant_id = NEW.tenant_id
          AND site.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'person association site must use its workspace scope' USING ERRCODE = '23514';
    END IF;
    IF NEW.structured_location_id IS NOT NULL AND (
        NEW.site_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM core_location location
            WHERE location.id = NEW.structured_location_id
              AND location.site_id = NEW.site_id
              AND location.tenant_id = NEW.tenant_id
              AND location.organization_id IS NOT DISTINCT FROM NEW.organization_id
        )
    ) THEN
        RAISE EXCEPTION 'person association location must belong to its selected site and workspace' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_location_scope_guard ON core_location;
DROP TRIGGER IF EXISTS core_site_scope_guard ON core_site;
DROP FUNCTION IF EXISTS tekdocs_validate_location_scope();
DROP FUNCTION IF EXISTS tekdocs_validate_site_scope();

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
"""


def install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0009_site_location_personassociation_placement")]

    operations = [migrations.RunPython(install_postgres_guards, remove_postgres_guards)]
