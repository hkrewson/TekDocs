from django.db import migrations


TABLES = (
    "core_catalogproductdocument",
    "core_clientasset",
    "core_clientassetdocumentprovenance",
)


def enable_client_asset_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_catalog_product_document() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogproduct p
                WHERE p.id = NEW.product_id AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'catalog document product scope mismatch'; END IF;
              IF NEW.model_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_catalogmodel m
                WHERE m.id = NEW.model_id AND m.tenant_id = NEW.tenant_id
                  AND m.organization_id = NEW.organization_id AND m.product_id = NEW.product_id
              ) THEN RAISE EXCEPTION 'catalog document model scope mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_documentpublication p
                WHERE p.id = NEW.publication_id AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id = NEW.organization_id AND p.audience = 'client_visible'
              ) THEN RAISE EXCEPTION 'catalog document requires client-visible supplier publication'; END IF;
              IF TG_OP = 'UPDATE' AND (
                NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR NEW.product_id IS DISTINCT FROM OLD.product_id
                OR NEW.model_id IS DISTINCT FROM OLD.model_id
                OR NEW.publication_id IS DISTINCT FROM OLD.publication_id
                OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
              ) THEN RAISE EXCEPTION 'catalog document provenance is immutable'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_catalog_product_document_guard BEFORE INSERT OR UPDATE "
            "ON core_catalogproductdocument FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_validate_catalog_product_document()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_client_asset() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_organizationclassification c
                WHERE c.organization_id = NEW.organization_id AND c.tenant_id = NEW.tenant_id
                  AND c.kind = 'client'
              ) THEN RAISE EXCEPTION 'client asset requires client organization'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id = NEW.organization_id AND e.entity_type = 'client_asset'
                  AND e.visibility = 'msp_private'
              ) THEN RAISE EXCEPTION 'client asset entity scope mismatch'; END IF;
              IF NOT tekdocs_catalog_supplier(NEW.supplier_id, NEW.tenant_id) THEN
                RAISE EXCEPTION 'client asset requires retained supplier';
              END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogproduct p
                WHERE p.id = NEW.product_id AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id = NEW.supplier_id
              ) THEN RAISE EXCEPTION 'client asset product provenance mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogmodel m
                WHERE m.id = NEW.model_id AND m.tenant_id = NEW.tenant_id
                  AND m.organization_id = NEW.supplier_id AND m.product_id = NEW.product_id
              ) THEN RAISE EXCEPTION 'client asset model provenance mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_catalogmodelrevision r
                WHERE r.id = NEW.model_revision_id AND r.tenant_id = NEW.tenant_id
                  AND r.organization_id = NEW.supplier_id AND r.model_id = NEW.model_id
                  AND r.specification_version_id = NEW.specification_version_id
              ) THEN RAISE EXCEPTION 'client asset revision provenance mismatch'; END IF;
              IF NEW.provenance_checksum !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'client asset provenance checksum invalid';
              END IF;
              IF TG_OP = 'UPDATE' AND (
                NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
                OR NEW.supplier_id IS DISTINCT FROM OLD.supplier_id
                OR NEW.product_id IS DISTINCT FROM OLD.product_id
                OR NEW.model_id IS DISTINCT FROM OLD.model_id
                OR NEW.model_revision_id IS DISTINCT FROM OLD.model_revision_id
                OR NEW.specification_version_id IS DISTINCT FROM OLD.specification_version_id
                OR NEW.specifications IS DISTINCT FROM OLD.specifications
                OR NEW.provenance_checksum IS DISTINCT FROM OLD.provenance_checksum
                OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
              ) THEN RAISE EXCEPTION 'client asset provenance is immutable'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_client_asset_guard BEFORE INSERT OR UPDATE ON core_clientasset "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_client_asset()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_client_asset_document() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_clientasset a
                WHERE a.id = NEW.asset_id AND a.tenant_id = NEW.tenant_id
                  AND a.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'asset document client scope mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1
                FROM core_catalogproductdocument d
                JOIN core_clientasset a ON a.id = NEW.asset_id
                WHERE d.id = NEW.catalog_document_id AND d.tenant_id = NEW.tenant_id
                  AND d.organization_id = a.supplier_id AND d.product_id = a.product_id
                  AND (d.model_id IS NULL OR d.model_id = a.model_id)
                  AND d.publication_id = NEW.publication_id
              ) THEN RAISE EXCEPTION 'asset document catalog provenance mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_documentpublication p
                WHERE p.id = NEW.publication_id AND p.content_digest = NEW.content_digest
                  AND p.audience = 'client_visible'
              ) THEN RAISE EXCEPTION 'asset document publication digest mismatch'; END IF;
              IF NEW.content_digest !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'asset document digest invalid';
              END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_client_asset_document_guard BEFORE INSERT "
            "ON core_clientassetdocumentprovenance FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_validate_client_asset_document()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_reject_client_asset_document_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'client asset document provenance is append-only'; END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_client_asset_document_immutable BEFORE UPDATE OR DELETE "
            "ON core_clientassetdocumentprovenance FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_reject_client_asset_document_mutation()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_protect_client_asset_classification() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.kind = 'client' AND EXISTS (
                SELECT 1 FROM core_clientasset a
                WHERE a.organization_id = OLD.organization_id AND a.tenant_id = OLD.tenant_id
              ) THEN RAISE EXCEPTION 'organization with client assets must remain a client'; END IF;
              RETURN OLD;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_client_asset_classification_guard BEFORE DELETE "
            "ON core_organizationclassification FOR EACH ROW "
            "EXECUTE FUNCTION tekdocs_protect_client_asset_classification()"
        )
        client_catalog_read = (
            "tenant_id = tekdocs_current_tenant_id() "
            "AND current_setting('tekdocs.organization_mode', true) = 'organization' "
            "AND EXISTS (SELECT 1 FROM core_organizationclassification c "
            "WHERE c.organization_id = tekdocs_current_organization_id() "
            "AND c.tenant_id = tekdocs_current_tenant_id() AND c.kind = 'client')"
        )
        for table in (
            "core_catalogproduct",
            "core_catalogmodel",
            "core_catalogspecificationdefinition",
            "core_catalogspecificationdefinitionversion",
            "core_catalogmodelrevision",
            "core_catalogproductdocument",
        ):
            cursor.execute(
                f"CREATE POLICY {table}_client_catalog_select ON {table} FOR SELECT USING ({client_catalog_read})"
            )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_client_catalog_publication_visible(publication_uuid uuid, tenant_uuid uuid)
            RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = pg_catalog, public SET row_security = off AS $$
              SELECT EXISTS (
                SELECT 1 FROM core_documentpublication p
                JOIN core_catalogproductdocument d ON d.publication_id = p.id
                WHERE p.id = publication_uuid AND p.tenant_id = tenant_uuid
                  AND p.audience = 'client_visible'
                  AND tenant_uuid = tekdocs_current_tenant_id()
                  AND current_setting('tekdocs.organization_mode', true) = 'organization'
                  AND EXISTS (
                    SELECT 1 FROM core_organizationclassification c
                    WHERE c.organization_id = tekdocs_current_organization_id()
                      AND c.tenant_id = tekdocs_current_tenant_id() AND c.kind = 'client'
                  )
              )
            $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_client_catalog_document_visible(document_uuid uuid, tenant_uuid uuid)
            RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = pg_catalog, public SET row_security = off AS $$
              SELECT EXISTS (
                SELECT 1 FROM core_documentpublication p
                JOIN core_catalogproductdocument d ON d.publication_id = p.id
                WHERE p.document_id = document_uuid AND p.tenant_id = tenant_uuid
                  AND p.audience = 'client_visible'
                  AND tenant_uuid = tekdocs_current_tenant_id()
                  AND current_setting('tekdocs.organization_mode', true) = 'organization'
                  AND EXISTS (
                    SELECT 1 FROM core_organizationclassification c
                    WHERE c.organization_id = tekdocs_current_organization_id()
                      AND c.tenant_id = tekdocs_current_tenant_id() AND c.kind = 'client'
                  )
              )
            $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_client_catalog_entity_visible(entity_uuid uuid, tenant_uuid uuid)
            RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = pg_catalog, public SET row_security = off AS $$
              SELECT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = entity_uuid AND e.tenant_id = tenant_uuid
                  AND tenant_uuid = tekdocs_current_tenant_id()
                  AND current_setting('tekdocs.organization_mode', true) = 'organization'
                  AND EXISTS (
                    SELECT 1 FROM core_organizationclassification current_client
                    WHERE current_client.organization_id = tekdocs_current_organization_id()
                      AND current_client.tenant_id = tekdocs_current_tenant_id()
                      AND current_client.kind = 'client'
                  ) AND (
                  (e.entity_type IN ('catalog_product', 'catalog_model') AND EXISTS (
                    SELECT 1 FROM core_organizationclassification c
                    WHERE c.organization_id = e.organization_id AND c.tenant_id = e.tenant_id
                      AND c.kind IN ('vendor', 'manufacturer')
                  )) OR (e.entity_type = 'document' AND EXISTS (
                    SELECT 1 FROM core_document doc
                    JOIN core_documentpublication p ON p.document_id = doc.id
                    JOIN core_catalogproductdocument d ON d.publication_id = p.id
                    WHERE doc.entity_id = e.id AND p.audience = 'client_visible'
                  )) OR (e.entity_type = 'document_publication' AND EXISTS (
                    SELECT 1 FROM core_documentpublication p
                    JOIN core_catalogproductdocument d ON d.publication_id = p.id
                    WHERE p.entity_id = e.id AND p.audience = 'client_visible'
                  )) OR (e.entity_type = 'document_publication_artifact' AND EXISTS (
                    SELECT 1 FROM core_documentpublicationartifact a
                    JOIN core_documentpublication p ON p.id = a.publication_id
                    JOIN core_catalogproductdocument d ON d.publication_id = p.id
                    WHERE a.entity_id = e.id AND p.audience = 'client_visible'
                  ))
                )
              )
            $$
            """
        )
        for signature in (
            "tekdocs_client_catalog_publication_visible(uuid, uuid)",
            "tekdocs_client_catalog_document_visible(uuid, uuid)",
            "tekdocs_client_catalog_entity_visible(uuid, uuid)",
        ):
            cursor.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
            cursor.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO tekdocs_runtime")
        cursor.execute(
            "CREATE POLICY core_documentpublication_client_catalog_select ON core_documentpublication "
            f"FOR SELECT USING ({client_catalog_read} AND "
            "tekdocs_client_catalog_publication_visible(id, tenant_id))"
        )
        cursor.execute(
            "CREATE POLICY core_document_client_catalog_select ON core_document FOR SELECT "
            f"USING ({client_catalog_read} AND tekdocs_client_catalog_document_visible(id, tenant_id))"
        )
        cursor.execute(
            "CREATE POLICY core_documentpublicationartifact_client_catalog_select "
            "ON core_documentpublicationartifact FOR SELECT "
            f"USING ({client_catalog_read} AND "
            "tekdocs_client_catalog_publication_visible(publication_id, tenant_id))"
        )
        cursor.execute(
            "CREATE POLICY core_entity_client_catalog_select ON core_entity FOR SELECT "
            f"USING ({client_catalog_read} AND tekdocs_client_catalog_entity_visible(id, tenant_id))"
        )
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"CREATE POLICY {table}_runtime_scope ON {table} "
                "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
                "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
            )


def disable_client_asset_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_entity_client_catalog_select ON core_entity")
        cursor.execute(
            "DROP POLICY IF EXISTS core_documentpublicationartifact_client_catalog_select "
            "ON core_documentpublicationartifact"
        )
        cursor.execute("DROP POLICY IF EXISTS core_document_client_catalog_select ON core_document")
        cursor.execute(
            "DROP POLICY IF EXISTS core_documentpublication_client_catalog_select ON core_documentpublication"
        )
        for table in (
            "core_catalogproduct",
            "core_catalogmodel",
            "core_catalogspecificationdefinition",
            "core_catalogspecificationdefinitionversion",
            "core_catalogmodelrevision",
            "core_catalogproductdocument",
        ):
            cursor.execute(f"DROP POLICY IF EXISTS {table}_client_catalog_select ON {table}")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_client_catalog_entity_visible(uuid, uuid)")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_client_catalog_document_visible(uuid, uuid)")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_client_catalog_publication_visible(uuid, uuid)")
        for table in reversed(TABLES):
            cursor.execute(f"DROP POLICY IF EXISTS {table}_runtime_scope ON {table}")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_client_asset_classification_guard ON core_organizationclassification"
        )
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_client_asset_document_immutable "
            "ON core_clientassetdocumentprovenance"
        )
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_client_asset_document_guard "
            "ON core_clientassetdocumentprovenance"
        )
        cursor.execute("DROP TRIGGER IF EXISTS core_client_asset_guard ON core_clientasset")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_catalog_product_document_guard ON core_catalogproductdocument"
        )
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_protect_client_asset_classification()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_reject_client_asset_document_mutation()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_client_asset_document()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_client_asset()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_catalog_product_document()")


class Migration(migrations.Migration):
    dependencies = [("core", "0036_catalogproductdocument_clientasset_and_more")]
    operations = [migrations.RunPython(enable_client_asset_guards, disable_client_asset_guards)]
