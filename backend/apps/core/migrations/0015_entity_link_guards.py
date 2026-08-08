from django.db import migrations


POSTGRES_LINK_GUARD_SQL = r"""
DROP TRIGGER IF EXISTS core_entity_link_scope_guard ON core_entitylink;

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
    IF NEW.metadata <> '{}'::jsonb THEN
        RAISE EXCEPTION 'entity link metadata is not accepted by this release' USING ERRCODE = '23514';
    END IF;
    IF NEW.link_type IN ('related_to', 'partnered_with') AND NEW.source_id > NEW.target_id THEN
        RAISE EXCEPTION 'symmetric entity links must use canonical endpoint order' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
            OR NEW.source_id IS DISTINCT FROM OLD.source_id
            OR NEW.target_id IS DISTINCT FROM OLD.target_id
            OR NEW.link_type IS DISTINCT FROM OLD.link_type
            OR NEW.metadata IS DISTINCT FROM OLD.metadata
        THEN
            RAISE EXCEPTION 'entity link identity is immutable' USING ERRCODE = '23514';
        END IF;
        IF OLD.archived_at IS NOT NULL AND NEW.archived_at IS DISTINCT FROM OLD.archived_at THEN
            RAISE EXCEPTION 'archived entity links are immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER core_entity_link_scope_guard
BEFORE INSERT OR UPDATE ON core_entitylink
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_link_scope();
"""


POSTGRES_LINK_GUARD_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_entity_link_scope_guard ON core_entitylink;

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

CREATE TRIGGER core_entity_link_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, source_id, target_id ON core_entitylink
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_link_scope();
"""


def install_link_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_LINK_GUARD_SQL)


def remove_link_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_LINK_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0014_typed_entity_links")]

    operations = [migrations.RunPython(install_link_guards, remove_link_guards)]
