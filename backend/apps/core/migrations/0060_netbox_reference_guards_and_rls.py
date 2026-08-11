from django.db import migrations


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_netbox_reference() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected_entity_type text;
        BEGIN
          expected_entity_type := CASE NEW.object_type
            WHEN 'dcim.rack' THEN 'network_rack'
            WHEN 'dcim.device' THEN 'client_asset'
            WHEN 'dcim.macaddress' THEN 'network_mac_address'
            WHEN 'ipam.vlan' THEN 'network_vlan'
            WHEN 'ipam.prefix' THEN 'network_subnet'
            WHEN 'ipam.ipaddress' THEN 'network_ip_address'
            ELSE NULL
          END;
          IF expected_entity_type IS NULL THEN RAISE EXCEPTION 'unsupported NetBox object type'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM core_workspace w
            WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id
              AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
          THEN RAISE EXCEPTION 'NetBox reference Workspace ownership mismatch'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM core_entity e
            WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
              AND e.workspace_id=NEW.workspace_id
              AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND e.entity_type=expected_entity_type AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'NetBox reference entity scope or type mismatch'; END IF;
          IF NEW.object_type='dcim.device' AND NOT EXISTS (
            SELECT 1 FROM core_clientasset a
            JOIN core_catalogproduct p ON p.id=a.product_id
            WHERE a.entity_id=NEW.entity_id AND a.tenant_id=NEW.tenant_id
              AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND a.archived_at IS NULL AND p.kind='hardware')
          THEN RAISE EXCEPTION 'NetBox device reference requires hardware asset'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_netbox_reference_guard
          BEFORE INSERT OR UPDATE ON core_netboxreference
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_netbox_reference();
        ALTER TABLE core_netboxreference ENABLE ROW LEVEL SECURITY;
        ALTER TABLE core_netboxreference FORCE ROW LEVEL SECURITY;
        CREATE POLICY core_netboxreference_runtime_scope ON core_netboxreference
          USING (tekdocs_scope_matches(tenant_id, organization_id))
          WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
        """)


def disable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_netboxreference_runtime_scope ON core_netboxreference")
        cursor.execute("ALTER TABLE core_netboxreference DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_netbox_reference_guard ON core_netboxreference")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_netbox_reference()")


class Migration(migrations.Migration):
    dependencies = [("core", "0059_netboxreference")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
