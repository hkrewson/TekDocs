from django.db import migrations

TABLES = ("core_networkvrf", "core_networkvlan", "core_networksubnet")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_network_vrf() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_vrf' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network VRF entity scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_vrf_guard BEFORE INSERT OR UPDATE ON core_networkvrf
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_vrf();

        CREATE FUNCTION tekdocs_validate_network_vlan() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_vlan' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network VLAN entity scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_vlan_guard BEFORE INSERT OR UPDATE ON core_networkvlan
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_vlan();

        CREATE FUNCTION tekdocs_validate_network_subnet() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE normalized text;
        BEGIN
          BEGIN
            normalized := (NEW.cidr::cidr)::text;
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'network subnet CIDR is invalid';
          END;
          IF normalized <> NEW.cidr THEN RAISE EXCEPTION 'network subnet CIDR is not canonical'; END IF;
          IF family(NEW.cidr::inet) <> NEW.address_family THEN
            RAISE EXCEPTION 'network subnet address family mismatch';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_subnet' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network subnet entity scope mismatch'; END IF;
          IF NEW.vrf_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvrf v WHERE v.id=NEW.vrf_id
            AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
          THEN RAISE EXCEPTION 'network subnet VRF scope mismatch'; END IF;
          IF NEW.vlan_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvlan v WHERE v.id=NEW.vlan_id
            AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
          THEN RAISE EXCEPTION 'network subnet VLAN scope mismatch'; END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended(
            NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' ||
            COALESCE(NEW.vrf_id::text, 'default'), 0));
          IF EXISTS (SELECT 1 FROM core_networksubnet s WHERE s.id<>NEW.id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND s.vrf_id IS NOT DISTINCT FROM NEW.vrf_id AND s.cidr::inet && NEW.cidr::inet)
          THEN RAISE EXCEPTION 'network subnet overlaps an existing prefix in its routing namespace'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_subnet_guard BEFORE INSERT OR UPDATE ON core_networksubnet
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_subnet();
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
        cursor.execute("DROP TRIGGER IF EXISTS core_network_subnet_guard ON core_networksubnet")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_vlan_guard ON core_networkvlan")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_vrf_guard ON core_networkvrf")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_subnet()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_vlan()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_vrf()")


class Migration(migrations.Migration):
    dependencies = [("core", "0050_network_addressing_models")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
