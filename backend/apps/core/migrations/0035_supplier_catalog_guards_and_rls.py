from django.db import migrations

TABLES = (
    "core_catalogproduct",
    "core_catalogmodel",
    "core_catalogspecificationdefinition",
    "core_catalogspecificationdefinitionversion",
    "core_catalogmodelrevision",
)


def enable_supplier_catalog_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_catalog_supplier(organization_uuid uuid, tenant_uuid uuid) RETURNS boolean
            LANGUAGE sql STABLE AS $$
              SELECT EXISTS (
                SELECT 1 FROM core_organization o
                JOIN core_organizationclassification c ON c.organization_id = o.id AND c.tenant_id = o.tenant_id
                WHERE o.id = organization_uuid AND o.tenant_id = tenant_uuid
                  AND c.kind IN ('vendor', 'manufacturer')
              )
            $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_product() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT tekdocs_catalog_supplier(NEW.organization_id, NEW.tenant_id) THEN
                RAISE EXCEPTION 'catalog product requires supplier organization';
              END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id = NEW.organization_id AND e.entity_type = 'catalog_product'
                  AND e.visibility = 'msp_private'
              ) THEN RAISE EXCEPTION 'catalog product entity scope mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_product_scope_guard BEFORE INSERT OR UPDATE ON core_catalogproduct "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_catalog_product()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_definition() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT tekdocs_catalog_supplier(NEW.organization_id, NEW.tenant_id) THEN
                RAISE EXCEPTION 'catalog definition requires supplier organization';
              END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_definition_scope_guard BEFORE INSERT OR UPDATE "
            "ON core_catalogspecificationdefinition "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_catalog_definition()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_definition_version() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogspecificationdefinition d
                WHERE d.id = NEW.definition_id AND d.tenant_id = NEW.tenant_id
                  AND d.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'catalog definition version scope mismatch'; END IF;
              IF NEW.checksum !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'catalog definition checksum invalid'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_definition_version_scope_guard BEFORE INSERT "
            "ON core_catalogspecificationdefinitionversion "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_catalog_definition_version()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_model() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogproduct p WHERE p.id = NEW.product_id AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'catalog model product scope mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id = NEW.organization_id AND e.entity_type = 'catalog_model'
                  AND e.visibility = 'msp_private'
              ) THEN RAISE EXCEPTION 'catalog model entity scope mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_model_scope_guard BEFORE INSERT OR UPDATE ON core_catalogmodel "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_catalog_model()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_model_revision() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE parent_revision integer;
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogmodel m WHERE m.id = NEW.model_id AND m.tenant_id = NEW.tenant_id
                  AND m.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'catalog model revision model scope mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogspecificationdefinitionversion v
                WHERE v.id = NEW.specification_version_id AND v.tenant_id = NEW.tenant_id
                  AND v.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'catalog model revision specification scope mismatch'; END IF;
              IF NEW.revision = 1 AND NEW.parent_id IS NOT NULL THEN
                RAISE EXCEPTION 'first catalog model revision cannot have a parent';
              ELSIF NEW.revision > 1 THEN
                SELECT r.revision INTO parent_revision FROM core_catalogmodelrevision r
                WHERE r.id = NEW.parent_id AND r.model_id = NEW.model_id
                  AND r.tenant_id = NEW.tenant_id AND r.organization_id = NEW.organization_id;
                IF parent_revision IS NULL OR parent_revision <> NEW.revision - 1 THEN
                  RAISE EXCEPTION 'catalog model revision parent mismatch';
                END IF;
              END IF;
              IF NEW.checksum !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'catalog model revision checksum invalid';
              END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_model_revision_scope_guard BEFORE INSERT ON core_catalogmodelrevision "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_catalog_model_revision()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_protect_catalog_supplier_classification() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.kind IN ('vendor', 'manufacturer')
                AND NOT EXISTS (
                  SELECT 1 FROM core_organizationclassification c
                  WHERE c.organization_id = OLD.organization_id AND c.tenant_id = OLD.tenant_id
                    AND c.id <> OLD.id AND c.kind IN ('vendor', 'manufacturer')
                )
                AND (
                  EXISTS (
                    SELECT 1 FROM core_catalogproduct p
                    WHERE p.organization_id = OLD.organization_id AND p.tenant_id = OLD.tenant_id
                  )
                  OR EXISTS (
                    SELECT 1 FROM core_catalogspecificationdefinition d
                    WHERE d.organization_id = OLD.organization_id AND d.tenant_id = OLD.tenant_id
                  )
                )
              THEN
                RAISE EXCEPTION 'organization with catalog records must remain a supplier';
              END IF;
              RETURN OLD;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_supplier_classification_guard BEFORE DELETE "
            "ON core_organizationclassification FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_protect_catalog_supplier_classification()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_reject_catalog_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'catalog history is append-only'; END $$
            """
        )
        for table in ("core_catalogspecificationdefinitionversion", "core_catalogmodelrevision"):
            cursor.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_catalog_history_mutation()"
            )
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"CREATE POLICY {table}_runtime_scope ON {table} "
                "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
                "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
            )


def disable_supplier_catalog_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            cursor.execute(f"DROP POLICY IF EXISTS {table}_runtime_scope ON {table}")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_catalog_model_revision_scope_guard ON core_catalogmodelrevision")
        cursor.execute("DROP TRIGGER IF EXISTS core_catalog_model_scope_guard ON core_catalogmodel")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_catalog_definition_version_scope_guard "
            "ON core_catalogspecificationdefinitionversion"
        )
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_catalog_definition_scope_guard ON core_catalogspecificationdefinition"
        )
        cursor.execute("DROP TRIGGER IF EXISTS core_catalog_product_scope_guard ON core_catalogproduct")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_catalog_supplier_classification_guard "
            "ON core_organizationclassification"
        )
        for table in ("core_catalogspecificationdefinitionversion", "core_catalogmodelrevision"):
            cursor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_reject_catalog_history_mutation()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_model_revision()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_model()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_definition_version()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_definition()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_product()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_protect_catalog_supplier_classification()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_catalog_supplier(uuid, uuid)")


class Migration(migrations.Migration):
    dependencies = [("core", "0034_supplier_catalogs")]
    operations = [migrations.RunPython(enable_supplier_catalog_guards, disable_supplier_catalog_guards)]
