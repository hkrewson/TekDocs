# ruff: noqa: E501,S608

import django.db.models.deletion
from django.db import migrations, models

CATALOG_TABLES = (
    "core_catalogproduct",
    "core_catalogmodel",
    "core_catalogspecificationdefinition",
    "core_catalogspecificationdefinitionversion",
    "core_catalogmodelrevision",
    "core_catalogproductdocument",
)


def _scope(column: str, *, nullable: bool) -> str:
    operator = "IS NOT DISTINCT FROM" if nullable else "="
    return f"{column} {operator} NEW.organization_id"


def install_scope_guards(apps, schema_editor, *, nullable=True):
    if schema_editor.connection.vendor != "postgresql":
        return
    scope = lambda column: _scope(column, nullable=nullable)  # noqa: E731
    owner_requirement = "NEW.organization_id IS NOT NULL AND " if nullable else ""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""
        CREATE OR REPLACE FUNCTION tekdocs_validate_client_asset() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF {owner_requirement}NOT EXISTS (SELECT 1 FROM core_organizationclassification c
            WHERE c.organization_id=NEW.organization_id AND c.tenant_id=NEW.tenant_id AND c.kind='client')
          THEN RAISE EXCEPTION 'operational asset requires MSP or client ownership'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
            AND {scope("e.organization_id")} AND e.entity_type='client_asset' AND e.visibility='msp_private')
          THEN RAISE EXCEPTION 'operational asset entity scope mismatch'; END IF;
          IF NOT tekdocs_catalog_supplier(NEW.supplier_id, NEW.tenant_id)
          THEN RAISE EXCEPTION 'operational asset requires retained supplier'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogproduct p WHERE p.id=NEW.product_id
            AND p.tenant_id=NEW.tenant_id AND p.organization_id=NEW.supplier_id)
          THEN RAISE EXCEPTION 'operational asset product provenance mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogmodel m WHERE m.id=NEW.model_id
            AND m.tenant_id=NEW.tenant_id AND m.organization_id=NEW.supplier_id AND m.product_id=NEW.product_id)
          THEN RAISE EXCEPTION 'operational asset model provenance mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogmodelrevision r WHERE r.id=NEW.model_revision_id
            AND r.tenant_id=NEW.tenant_id AND r.organization_id=NEW.supplier_id AND r.model_id=NEW.model_id
            AND r.specification_version_id=NEW.specification_version_id)
          THEN RAISE EXCEPTION 'operational asset revision provenance mismatch'; END IF;
          IF NEW.provenance_checksum !~ '^[0-9a-f]{{64}}$'
          THEN RAISE EXCEPTION 'operational asset provenance checksum invalid'; END IF;
          IF TG_OP='UPDATE' AND (NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
            OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
            OR NEW.supplier_id IS DISTINCT FROM OLD.supplier_id OR NEW.product_id IS DISTINCT FROM OLD.product_id
            OR NEW.model_id IS DISTINCT FROM OLD.model_id OR NEW.model_revision_id IS DISTINCT FROM OLD.model_revision_id
            OR NEW.specification_version_id IS DISTINCT FROM OLD.specification_version_id
            OR NEW.specifications IS DISTINCT FROM OLD.specifications OR NEW.provenance_checksum IS DISTINCT FROM OLD.provenance_checksum
            OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id)
          THEN RAISE EXCEPTION 'operational asset provenance is immutable'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_client_asset_document() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_clientasset a WHERE a.id=NEW.asset_id AND a.tenant_id=NEW.tenant_id
            AND {scope("a.organization_id")})
          THEN RAISE EXCEPTION 'asset document workspace scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogproductdocument d JOIN core_clientasset a ON a.id=NEW.asset_id
            WHERE d.id=NEW.catalog_document_id AND d.tenant_id=NEW.tenant_id AND d.organization_id=a.supplier_id
              AND d.product_id=a.product_id AND (d.model_id IS NULL OR d.model_id=a.model_id)
              AND d.publication_id=NEW.publication_id)
          THEN RAISE EXCEPTION 'asset document catalog provenance mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.id=NEW.publication_id
            AND p.content_digest=NEW.content_digest AND p.audience='client_visible')
          THEN RAISE EXCEPTION 'asset document publication digest mismatch'; END IF;
          IF NEW.content_digest !~ '^[0-9a-f]{{64}}$' THEN RAISE EXCEPTION 'asset document digest invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_hardware_profile() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
            WHERE a.id=NEW.asset_id AND a.tenant_id=NEW.tenant_id AND {scope("a.organization_id")} AND p.kind='hardware')
          THEN RAISE EXCEPTION 'hardware profile asset scope mismatch'; END IF;
          IF NEW.serial_number<>upper(btrim(NEW.serial_number)) OR NEW.asset_tag<>upper(btrim(NEW.asset_tag))
          THEN RAISE EXCEPTION 'hardware identifiers must be normalized'; END IF;
          IF NEW.warranty_starts_on IS NOT NULL AND NEW.warranty_ends_on IS NOT NULL AND NEW.warranty_ends_on<NEW.warranty_starts_on
          THEN RAISE EXCEPTION 'hardware warranty dates invalid'; END IF;
          IF NEW.assigned_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_personassociation p
            WHERE p.id=NEW.assigned_person_id AND p.tenant_id=NEW.tenant_id AND {scope("p.organization_id")} AND p.archived_at IS NULL)
          THEN RAISE EXCEPTION 'hardware person assignment scope mismatch'; END IF;
          IF NEW.assigned_site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s
            WHERE s.id=NEW.assigned_site_id AND s.tenant_id=NEW.tenant_id AND {scope("s.organization_id")} AND s.archived_at IS NULL)
          THEN RAISE EXCEPTION 'hardware site assignment scope mismatch'; END IF;
          IF NEW.assigned_location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l
            WHERE l.id=NEW.assigned_location_id AND l.tenant_id=NEW.tenant_id AND {scope("l.organization_id")}
              AND l.site_id=NEW.assigned_site_id AND l.archived_at IS NULL)
          THEN RAISE EXCEPTION 'hardware location assignment scope mismatch'; END IF;
          IF NEW.lifecycle_state='disposed' THEN
            IF NEW.disposed_on IS NULL OR NEW.disposal_method='' OR NEW.assigned_person_id IS NOT NULL
              OR NEW.assigned_site_id IS NOT NULL OR NEW.assigned_location_id IS NOT NULL OR NEW.assigned_at IS NOT NULL
            THEN RAISE EXCEPTION 'disposed hardware state invalid'; END IF;
          ELSIF NEW.disposed_on IS NOT NULL OR NEW.disposal_method<>'' OR NEW.disposal_reason<>''
          THEN RAISE EXCEPTION 'disposal details require disposed hardware'; END IF;
          IF TG_OP='UPDATE' AND OLD.lifecycle_state='disposed' THEN RAISE EXCEPTION 'disposed hardware lifecycle is terminal'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_hardware_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_clientasset a WHERE a.id=NEW.asset_id AND a.tenant_id=NEW.tenant_id
            AND {scope("a.organization_id")}) THEN RAISE EXCEPTION 'hardware event asset scope mismatch'; END IF;
          IF NEW.person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_personassociation p WHERE p.id=NEW.person_id
            AND p.tenant_id=NEW.tenant_id AND {scope("p.organization_id")}) THEN RAISE EXCEPTION 'hardware event person scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
            AND s.tenant_id=NEW.tenant_id AND {scope("s.organization_id")}) THEN RAISE EXCEPTION 'hardware event site scope mismatch'; END IF;
          IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l WHERE l.id=NEW.location_id
            AND l.tenant_id=NEW.tenant_id AND {scope("l.organization_id")} AND l.site_id=NEW.site_id)
          THEN RAISE EXCEPTION 'hardware event location scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_software_installation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
            WHERE a.id=NEW.asset_id AND a.tenant_id=NEW.tenant_id AND {scope("a.organization_id")} AND p.kind='software')
          THEN RAISE EXCEPTION 'software installation asset scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
            AND s.tenant_id=NEW.tenant_id AND {scope("s.organization_id")} AND s.archived_at IS NULL)
          THEN RAISE EXCEPTION 'software installation site scope mismatch'; END IF;
          IF NEW.status='installed' AND NEW.installed_on IS NULL THEN RAISE EXCEPTION 'installed date required'; END IF;
          IF TG_OP='UPDATE' AND OLD.status='uninstalled' THEN RAISE EXCEPTION 'uninstalled state is terminal'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_software_license() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
            AND {scope("e.organization_id")} AND e.entity_type='software_license')
          THEN RAISE EXCEPTION 'software license entity scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogproduct p WHERE p.id=NEW.product_id AND p.tenant_id=NEW.tenant_id
            AND p.organization_id=NEW.supplier_id AND p.kind='software')
          THEN RAISE EXCEPTION 'software license product scope mismatch'; END IF;
          IF NEW.model_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_catalogmodel m WHERE m.id=NEW.model_id
            AND m.product_id=NEW.product_id AND m.organization_id=NEW.supplier_id AND m.tenant_id=NEW.tenant_id)
          THEN RAISE EXCEPTION 'software license model scope mismatch'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on<NEW.starts_on
          THEN RAISE EXCEPTION 'software license term invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.renews_on IS NOT NULL AND NEW.renews_on<NEW.starts_on
          THEN RAISE EXCEPTION 'software renewal date invalid'; END IF;
          IF NEW.kind='perpetual' AND (NEW.auto_renew OR NEW.renewal_interval<>'none')
          THEN RAISE EXCEPTION 'perpetual renewal invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_software_license_edge() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_softwarelicense l WHERE l.id=NEW.license_id AND l.tenant_id=NEW.tenant_id
            AND {scope("l.organization_id")}) THEN RAISE EXCEPTION 'software license edge scope mismatch'; END IF;
          IF (to_jsonb(NEW)->>'installation_id') IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_clientsoftwareinstallation i JOIN core_clientasset a ON a.id=i.asset_id
            JOIN core_softwarelicense l ON l.id=NEW.license_id WHERE i.id=(to_jsonb(NEW)->>'installation_id')::uuid
              AND i.tenant_id=NEW.tenant_id AND {scope("i.organization_id")} AND a.product_id=l.product_id)
          THEN RAISE EXCEPTION 'software installation edge scope mismatch'; END IF;
          IF (to_jsonb(NEW)->>'person_id') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_personassociation p
            WHERE p.id=(to_jsonb(NEW)->>'person_id')::uuid AND p.tenant_id=NEW.tenant_id
              AND {scope("p.organization_id")} AND p.archived_at IS NULL)
          THEN RAISE EXCEPTION 'software seat person scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_commercial_contract() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
            AND {scope("e.organization_id")} AND e.entity_type='commercial_contract' AND e.visibility='msp_private')
          THEN RAISE EXCEPTION 'commercial contract entity scope mismatch'; END IF;
          IF NEW.provider_id=NEW.organization_id OR NOT EXISTS (SELECT 1 FROM core_organization p
            WHERE p.id=NEW.provider_id AND p.tenant_id=NEW.tenant_id)
          THEN RAISE EXCEPTION 'commercial contract provider scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_organizationclassification c WHERE c.organization_id=NEW.provider_id
            AND c.tenant_id=NEW.tenant_id AND c.kind IN ('vendor','manufacturer','partner'))
          THEN RAISE EXCEPTION 'commercial contract provider classification invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on<NEW.starts_on
          THEN RAISE EXCEPTION 'commercial contract term invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.renews_on IS NOT NULL AND NEW.renews_on<NEW.starts_on
          THEN RAISE EXCEPTION 'commercial contract renewal invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE OR REPLACE FUNCTION tekdocs_validate_contract_cost() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_commercialcontract c WHERE c.id=NEW.contract_id
            AND c.tenant_id=NEW.tenant_id AND {scope("c.organization_id")} AND c.archived_at IS NULL)
          THEN RAISE EXCEPTION 'contract cost scope mismatch'; END IF;
          IF NEW.currency !~ '^[A-Z]{{3}}$' THEN RAISE EXCEPTION 'contract cost currency invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on<NEW.starts_on
          THEN RAISE EXCEPTION 'contract cost term invalid'; END IF;
          RETURN NEW;
        END $$;
        """)
        if nullable:
            msp_read = (
                "tenant_id=tekdocs_current_tenant_id() AND current_setting('tekdocs.organization_mode', true)='msp'"
            )
            for table in CATALOG_TABLES:
                cursor.execute(f"CREATE POLICY {table}_msp_operational_select ON {table} FOR SELECT USING ({msp_read})")
            cursor.execute(
                """
                CREATE FUNCTION tekdocs_msp_catalog_publication_visible(publication_uuid uuid, tenant_uuid uuid)
                RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = pg_catalog, public SET row_security = off AS $$
                  SELECT EXISTS (
                    SELECT 1 FROM core_documentpublication p
                    JOIN core_catalogproductdocument d ON d.publication_id = p.id
                    WHERE p.id = publication_uuid AND p.tenant_id = tenant_uuid
                      AND p.audience = 'client_visible'
                      AND tenant_uuid = tekdocs_current_tenant_id()
                      AND current_setting('tekdocs.organization_mode', true) = 'msp'
                  )
                $$
                """
            )
            cursor.execute(
                """
                CREATE FUNCTION tekdocs_msp_catalog_document_visible(document_uuid uuid, tenant_uuid uuid)
                RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = pg_catalog, public SET row_security = off AS $$
                  SELECT EXISTS (
                    SELECT 1 FROM core_documentpublication p
                    JOIN core_catalogproductdocument d ON d.publication_id = p.id
                    WHERE p.document_id = document_uuid AND p.tenant_id = tenant_uuid
                      AND p.audience = 'client_visible'
                      AND tenant_uuid = tekdocs_current_tenant_id()
                      AND current_setting('tekdocs.organization_mode', true) = 'msp'
                  )
                $$
                """
            )
            cursor.execute(
                """
                CREATE FUNCTION tekdocs_msp_catalog_entity_visible(entity_uuid uuid, tenant_uuid uuid)
                RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = pg_catalog, public SET row_security = off AS $$
                  SELECT EXISTS (
                    SELECT 1 FROM core_entity e
                    WHERE e.id = entity_uuid AND e.tenant_id = tenant_uuid
                      AND tenant_uuid = tekdocs_current_tenant_id()
                      AND current_setting('tekdocs.organization_mode', true) = 'msp'
                      AND (
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
                "tekdocs_msp_catalog_publication_visible(uuid, uuid)",
                "tekdocs_msp_catalog_document_visible(uuid, uuid)",
                "tekdocs_msp_catalog_entity_visible(uuid, uuid)",
            ):
                cursor.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
                cursor.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO tekdocs_runtime")
            cursor.execute(
                "CREATE POLICY core_documentpublication_msp_operational_select ON core_documentpublication "
                f"FOR SELECT USING ({msp_read} AND "
                "tekdocs_msp_catalog_publication_visible(id, tenant_id))"
            )
            cursor.execute(
                "CREATE POLICY core_document_msp_operational_select ON core_document FOR SELECT "
                f"USING ({msp_read} AND tekdocs_msp_catalog_document_visible(id, tenant_id))"
            )
            cursor.execute(
                "CREATE POLICY core_documentpublicationartifact_msp_operational_select "
                "ON core_documentpublicationartifact FOR SELECT "
                f"USING ({msp_read} AND "
                "tekdocs_msp_catalog_publication_visible(publication_id, tenant_id))"
            )
            cursor.execute(
                "CREATE POLICY core_entity_msp_operational_select ON core_entity FOR SELECT "
                f"USING ({msp_read} AND tekdocs_msp_catalog_entity_visible(id, tenant_id))"
            )
        else:
            for table in (
                *CATALOG_TABLES,
                "core_documentpublication",
                "core_document",
                "core_documentpublicationartifact",
                "core_entity",
            ):
                cursor.execute(f"DROP POLICY IF EXISTS {table}_msp_operational_select ON {table}")
            cursor.execute("DROP FUNCTION IF EXISTS tekdocs_msp_catalog_entity_visible(uuid, uuid)")
            cursor.execute("DROP FUNCTION IF EXISTS tekdocs_msp_catalog_document_visible(uuid, uuid)")
            cursor.execute("DROP FUNCTION IF EXISTS tekdocs_msp_catalog_publication_visible(uuid, uuid)")


def remove_msp_scope_guards(apps, schema_editor):
    install_scope_guards(apps, schema_editor, nullable=False)


class Migration(migrations.Migration):
    dependencies = [("core", "0043_commercial_contract_guards_and_rls")]
    operations = [
        migrations.AlterField(
            model_name="clientasset",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_assets",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="clientassetdocumentprovenance",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_asset_documents",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="clientassetlifecycleevent",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_asset_lifecycle_events",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="clienthardwareasset",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_hardware_assets",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="clientsoftwareinstallation",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_software_installations",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="commercialcontract",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commercial_contracts",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="contractcost",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contract_costs",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="softwarelicense",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="software_licenses",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="softwarelicenseevent",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="software_license_events",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="softwarelicenseinstallation",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="software_license_installations",
                to="core.organization",
            ),
        ),
        migrations.AlterField(
            model_name="softwarelicenseseat",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="software_license_seats",
                to="core.organization",
            ),
        ),
        migrations.RemoveConstraint(model_name="clienthardwareasset", name="unique_hardware_serial_in_org"),
        migrations.RemoveConstraint(model_name="clienthardwareasset", name="unique_hardware_tag_in_org"),
        migrations.AddConstraint(
            model_name="clienthardwareasset",
            constraint=models.UniqueConstraint(
                condition=~models.Q(serial_number=""),
                fields=("tenant", "organization", "serial_number"),
                name="unique_hardware_serial_in_org",
                nulls_distinct=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="clienthardwareasset",
            constraint=models.UniqueConstraint(
                condition=~models.Q(asset_tag=""),
                fields=("tenant", "organization", "asset_tag"),
                name="unique_hardware_tag_in_org",
                nulls_distinct=False,
            ),
        ),
        migrations.RunPython(install_scope_guards, remove_msp_scope_guards),
    ]
