from django.db import migrations

TABLES = ("core_networkinterface", "core_networkipaddress", "core_networkmacaddress")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_network_interface() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended('interface:' || NEW.device_id::text, 0));
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_interface' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network interface entity scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_networkdevice d JOIN core_entity e ON e.id=d.entity_id
            WHERE d.id=NEW.device_id AND d.tenant_id=NEW.tenant_id
            AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network interface device scope mismatch'; END IF;
          IF EXISTS (SELECT 1 FROM core_networkinterface i
            JOIN core_entity candidate ON candidate.id=i.entity_id
            JOIN core_entity submitted ON submitted.id=NEW.entity_id
            WHERE i.id<>NEW.id AND i.device_id=NEW.device_id
            AND lower(candidate.display_name)=lower(submitted.display_name))
          THEN RAISE EXCEPTION 'network interface name conflicts on this device'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_interface_guard BEFORE INSERT OR UPDATE ON core_networkinterface
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_interface();

        CREATE FUNCTION tekdocs_validate_network_mac() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.address !~ '^[0-9a-f]{2}(:[0-9a-f]{2}){5}$'
          THEN RAISE EXCEPTION 'network MAC address is not canonical'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_mac_address' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network MAC entity scope mismatch'; END IF;
          IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
            WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
            AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network MAC interface scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_mac_guard BEFORE INSERT OR UPDATE ON core_networkmacaddress
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_mac();

        CREATE FUNCTION tekdocs_validate_network_ip() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE normalized text; subnet_cidr cidr; subnet_vrf uuid; namespace_key text;
        BEGIN
          BEGIN
            normalized := host(NEW.address::inet);
          EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'network IP address is invalid';
          END;
          IF normalized <> NEW.address THEN RAISE EXCEPTION 'network IP address is not canonical'; END IF;
          IF family(NEW.address::inet) <> NEW.address_family
          THEN RAISE EXCEPTION 'network IP address family mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_ip_address' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network IP entity scope mismatch'; END IF;
          SELECT s.cidr::cidr, s.vrf_id INTO subnet_cidr, subnet_vrf FROM core_networksubnet s
            JOIN core_entity e ON e.id=s.entity_id WHERE s.id=NEW.subnet_id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.archived_at IS NULL;
          IF subnet_cidr IS NULL THEN RAISE EXCEPTION 'network IP subnet scope mismatch'; END IF;
          IF NOT (NEW.address::inet <<= subnet_cidr::inet)
          THEN RAISE EXCEPTION 'network IP address is outside its subnet'; END IF;
          IF family(subnet_cidr::inet)=4 AND masklen(subnet_cidr::inet)<31
            AND (NEW.address::inet=network(subnet_cidr::inet) OR NEW.address::inet=broadcast(subnet_cidr::inet))
          THEN RAISE EXCEPTION 'network or broadcast address cannot be assigned'; END IF;
          IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
            WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
            AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network IP interface scope mismatch'; END IF;
          namespace_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' ||
            COALESCE(subnet_vrf::text, 'default');
          PERFORM pg_advisory_xact_lock(hashtextextended(namespace_key, 0));
          IF EXISTS (SELECT 1 FROM core_networkipaddress a
            JOIN core_networksubnet existing_subnet ON existing_subnet.id=a.subnet_id
            WHERE a.id<>NEW.id AND a.tenant_id=NEW.tenant_id
            AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND existing_subnet.vrf_id IS NOT DISTINCT FROM subnet_vrf
            AND a.address::inet=NEW.address::inet)
          THEN RAISE EXCEPTION 'network IP address conflicts in its routing namespace'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_ip_guard BEFORE INSERT OR UPDATE ON core_networkipaddress
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_ip();

        CREATE OR REPLACE FUNCTION tekdocs_validate_network_subnet() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE normalized text; old_key text; new_key text;
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
          new_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' ||
            COALESCE(NEW.vrf_id::text, 'default');
          old_key := new_key;
          IF TG_OP='UPDATE' THEN
            old_key := OLD.tenant_id::text || ':' || COALESCE(OLD.organization_id::text, 'msp') || ':' ||
              COALESCE(OLD.vrf_id::text, 'default');
          END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended(LEAST(old_key, new_key), 0));
          IF old_key<>new_key THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(GREATEST(old_key, new_key), 0));
          END IF;
          IF EXISTS (SELECT 1 FROM core_networksubnet s WHERE s.id<>NEW.id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND s.vrf_id IS NOT DISTINCT FROM NEW.vrf_id AND s.cidr::inet && NEW.cidr::inet)
          THEN RAISE EXCEPTION 'network subnet overlaps an existing prefix in its routing namespace'; END IF;
          IF EXISTS (SELECT 1 FROM core_networkipaddress a WHERE a.subnet_id=NEW.id
            AND (NOT (a.address::inet <<= NEW.cidr::inet) OR family(a.address::inet)<>NEW.address_family
              OR (family(NEW.cidr::inet)=4 AND masklen(NEW.cidr::inet)<31
                AND (a.address::inet=network(NEW.cidr::inet) OR a.address::inet=broadcast(NEW.cidr::inet)))))
          THEN RAISE EXCEPTION 'network subnet change invalidates an assigned address'; END IF;
          IF EXISTS (SELECT 1 FROM core_networkipaddress assigned
            JOIN core_networkipaddress candidate ON candidate.address::inet=assigned.address::inet
            JOIN core_networksubnet candidate_subnet ON candidate_subnet.id=candidate.subnet_id
            WHERE assigned.subnet_id=NEW.id AND candidate.subnet_id<>NEW.id
            AND candidate.tenant_id=NEW.tenant_id
            AND candidate.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND candidate_subnet.vrf_id IS NOT DISTINCT FROM NEW.vrf_id)
          THEN RAISE EXCEPTION 'network subnet move creates an IP address conflict'; END IF;
          RETURN NEW;
        END $$;
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
        cursor.execute("DROP TRIGGER IF EXISTS core_network_ip_guard ON core_networkipaddress")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_mac_guard ON core_networkmacaddress")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_interface_guard ON core_networkinterface")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_ip()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_mac()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_interface()")
        cursor.execute(r"""
        CREATE OR REPLACE FUNCTION tekdocs_validate_network_subnet() RETURNS trigger LANGUAGE plpgsql AS $$
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
        """)


class Migration(migrations.Migration):
    dependencies = [("core", "0052_networkinterface_networkipaddress_networkmacaddress_and_more")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
