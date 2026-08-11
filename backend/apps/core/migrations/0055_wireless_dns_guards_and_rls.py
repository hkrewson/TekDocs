from django.db import migrations


TABLES = ("core_wirelessnetwork", "core_dnszone", "core_dnsrecord")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_wireless_network() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'wireless:' || NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp'), 0));
          IF octet_length(NEW.ssid)<1 OR octet_length(NEW.ssid)>32
          THEN RAISE EXCEPTION 'wireless SSID must contain 1 to 32 bytes'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='wireless_network' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'wireless network entity scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s JOIN core_entity e ON e.id=s.entity_id
            WHERE s.id=NEW.site_id AND s.tenant_id=NEW.tenant_id
            AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'wireless network site scope mismatch'; END IF;
          IF NEW.vlan_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvlan v JOIN core_entity e ON e.id=v.entity_id
            WHERE v.id=NEW.vlan_id AND v.tenant_id=NEW.tenant_id
            AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'wireless network VLAN scope mismatch'; END IF;
          IF NEW.subnet_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networksubnet s JOIN core_entity e ON e.id=s.entity_id
            WHERE s.id=NEW.subnet_id AND s.tenant_id=NEW.tenant_id
            AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'wireless network subnet scope mismatch'; END IF;
          IF NEW.vlan_id IS NOT NULL AND NEW.subnet_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_networksubnet s WHERE s.id=NEW.subnet_id AND s.vlan_id=NEW.vlan_id)
          THEN RAISE EXCEPTION 'wireless network subnet does not belong to selected VLAN'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_wireless_network_guard BEFORE INSERT OR UPDATE ON core_wirelessnetwork
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_wireless_network();

        CREATE FUNCTION tekdocs_validate_dns_zone() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'dns:' || NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp'), 0));
          IF NEW.name<>lower(NEW.name) OR NEW.name LIKE '.%' OR NEW.name LIKE '%.' OR length(NEW.name)>253
            OR NEW.name !~ '^[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?)*$'
          THEN RAISE EXCEPTION 'DNS zone name is not canonical'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='dns_zone' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'DNS zone entity scope mismatch'; END IF;
          IF TG_OP='UPDATE' AND NEW.name<>OLD.name AND EXISTS (
            SELECT 1 FROM core_dnsrecord r WHERE r.zone_id=NEW.id)
          THEN RAISE EXCEPTION 'DNS zone with records cannot be renamed'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_dns_zone_guard BEFORE INSERT OR UPDATE ON core_dnszone
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_dns_zone();

        CREATE FUNCTION tekdocs_validate_dns_record() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE zone_name text; linked_ip text;
        BEGIN
          SELECT z.name INTO zone_name FROM core_dnszone z JOIN core_entity e ON e.id=z.entity_id
            WHERE z.id=NEW.zone_id AND z.tenant_id=NEW.tenant_id
            AND z.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL;
          IF zone_name IS NULL THEN RAISE EXCEPTION 'DNS record zone scope mismatch'; END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'dns:' || NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp'), 0));
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='dns_record' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'DNS record entity scope mismatch'; END IF;
          IF NEW.owner_name<>lower(NEW.owner_name)
            OR NEW.owner_name !~ '^[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?)*$' OR NOT (
            NEW.owner_name=zone_name OR right(NEW.owner_name, length(zone_name)+1)='.' || zone_name)
          THEN RAISE EXCEPTION 'DNS record owner is outside its zone'; END IF;
          IF NEW.ip_address_id IS NOT NULL THEN
            SELECT a.address INTO linked_ip FROM core_networkipaddress a JOIN core_entity e ON e.id=a.entity_id
              WHERE a.id=NEW.ip_address_id AND a.tenant_id=NEW.tenant_id
              AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL;
            IF linked_ip IS NULL THEN RAISE EXCEPTION 'DNS record IP scope mismatch'; END IF;
          END IF;
          IF NEW.record_type IN ('A','AAAA') THEN
            BEGIN
              IF host(NEW.value::inet)<>NEW.value OR
                (NEW.record_type='A' AND family(NEW.value::inet)<>4) OR
                (NEW.record_type='AAAA' AND family(NEW.value::inet)<>6)
              THEN RAISE EXCEPTION 'DNS address value is not canonical'; END IF;
            EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'DNS address value is invalid'; END;
            IF linked_ip IS NOT NULL AND linked_ip<>NEW.value THEN RAISE EXCEPTION 'DNS linked IP does not match value'; END IF;
            IF NEW.priority IS NOT NULL OR NEW.weight IS NOT NULL OR NEW.port IS NOT NULL
            THEN RAISE EXCEPTION 'address records contain unsupported fields'; END IF;
          ELSIF NEW.ip_address_id IS NOT NULL THEN RAISE EXCEPTION 'only A and AAAA records may link an IP';
          END IF;
          IF NEW.record_type IN ('CNAME','NS','PTR','MX','SRV') AND (
            NEW.value<>lower(NEW.value) OR NEW.value !~ '^[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?)*$')
          THEN RAISE EXCEPTION 'DNS target is not canonical'; END IF;
          IF NEW.record_type='MX' AND (NEW.priority IS NULL OR NEW.weight IS NOT NULL OR NEW.port IS NOT NULL)
          THEN RAISE EXCEPTION 'MX record fields are invalid'; END IF;
          IF NEW.record_type='SRV' AND (NEW.priority IS NULL OR NEW.weight IS NULL OR NEW.port IS NULL)
          THEN RAISE EXCEPTION 'SRV record fields are invalid'; END IF;
          IF NEW.record_type IN ('CNAME','NS','PTR','TXT','CAA') AND
            (NEW.priority IS NOT NULL OR NEW.weight IS NOT NULL OR NEW.port IS NOT NULL)
          THEN RAISE EXCEPTION 'DNS record contains unsupported fields'; END IF;
          IF NEW.record_type='TXT' AND (octet_length(NEW.value)<1 OR octet_length(NEW.value)>2048 OR NEW.value ~ '[\r\n]')
          THEN RAISE EXCEPTION 'TXT record value is invalid'; END IF;
          IF NEW.record_type='CAA' AND NEW.value !~ '^(0|[1-9][0-9]{0,2}) (issue|issuewild|iodef) "[^\r\n]{1,512}"$'
          THEN RAISE EXCEPTION 'CAA record value is invalid'; END IF;
          IF EXISTS (SELECT 1 FROM core_dnsrecord r WHERE r.id<>NEW.id AND r.zone_id=NEW.zone_id
            AND r.owner_name=NEW.owner_name AND (r.record_type='CNAME' OR NEW.record_type='CNAME'))
          THEN RAISE EXCEPTION 'CNAME cannot coexist with another record'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_dns_record_guard BEFORE INSERT OR UPDATE ON core_dnsrecord
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_dns_record();
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
        cursor.execute("DROP TRIGGER IF EXISTS core_dns_record_guard ON core_dnsrecord")
        cursor.execute("DROP TRIGGER IF EXISTS core_dns_zone_guard ON core_dnszone")
        cursor.execute("DROP TRIGGER IF EXISTS core_wireless_network_guard ON core_wirelessnetwork")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_dns_record()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_dns_zone()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_wireless_network()")


class Migration(migrations.Migration):
    dependencies = [("core", "0054_wireless_dns_inventory")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
