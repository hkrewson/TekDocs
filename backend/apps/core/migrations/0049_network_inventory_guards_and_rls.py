from django.db import migrations


TABLES = ("core_networkrack", "core_networkdevice")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_network_rack() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_rack' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network rack entity scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND s.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network rack site scope mismatch'; END IF;
          IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l
            WHERE l.id=NEW.location_id AND l.site_id=NEW.site_id AND l.tenant_id=NEW.tenant_id
            AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id AND l.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network rack location scope mismatch'; END IF;
          IF EXISTS (SELECT 1 FROM core_networkdevice d WHERE d.rack_id=NEW.id
            AND (d.site_id<>NEW.site_id OR d.location_id IS DISTINCT FROM NEW.location_id
              OR d.rack_unit + d.rack_units - 1 > NEW.unit_count))
          THEN RAISE EXCEPTION 'network rack conflicts with placed devices'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_rack_guard BEFORE INSERT OR UPDATE ON core_networkrack
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_rack();

        CREATE FUNCTION tekdocs_validate_network_device() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_device' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network device entity scope mismatch'; END IF;
          IF NEW.hardware_asset_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
            WHERE a.id=NEW.hardware_asset_id AND a.tenant_id=NEW.tenant_id
              AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND a.archived_at IS NULL AND p.kind='hardware')
          THEN RAISE EXCEPTION 'network device hardware asset scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND s.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network device site scope mismatch'; END IF;
          IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l
            WHERE l.id=NEW.location_id AND l.site_id=NEW.site_id AND l.tenant_id=NEW.tenant_id
              AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id AND l.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network device location scope mismatch'; END IF;
          IF NEW.rack_id IS NOT NULL THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(NEW.rack_id::text, 0));
            IF NOT EXISTS (SELECT 1 FROM core_networkrack r WHERE r.id=NEW.rack_id
              AND r.tenant_id=NEW.tenant_id AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND r.site_id=NEW.site_id AND r.location_id IS NOT DISTINCT FROM NEW.location_id
              AND NEW.rack_unit + NEW.rack_units - 1 <= r.unit_count)
            THEN RAISE EXCEPTION 'network device rack placement mismatch'; END IF;
            IF EXISTS (SELECT 1 FROM core_networkdevice d WHERE d.rack_id=NEW.rack_id AND d.id<>NEW.id
              AND int4range(d.rack_unit, d.rack_unit + d.rack_units, '[)')
                && int4range(NEW.rack_unit, NEW.rack_unit + NEW.rack_units, '[)'))
            THEN RAISE EXCEPTION 'network device rack placement overlaps'; END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_device_guard BEFORE INSERT OR UPDATE ON core_networkdevice
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_device();
        """)
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(
                f"CREATE POLICY {table}_runtime_scope ON {table} "
                "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
                "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
            )


def disable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            cursor.execute(f"DROP POLICY IF EXISTS {table}_runtime_scope ON {table}")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_device_guard ON core_networkdevice")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_rack_guard ON core_networkrack")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_device()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_rack()")


class Migration(migrations.Migration):
    dependencies = [("core", "0048_networkdevice_networkrack_and_more")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
