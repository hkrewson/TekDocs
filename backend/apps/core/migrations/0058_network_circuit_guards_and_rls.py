from django.db import migrations

TABLES = ("core_networkcircuit", "core_networkcircuithandoff")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(r"""
        CREATE FUNCTION tekdocs_validate_network_circuit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtextextended(
            'circuits:' || NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp'), 0));
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_circuit' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network circuit entity scope mismatch'; END IF;
          IF btrim(NEW.service_identifier)='' OR NEW.service_identifier<>btrim(NEW.service_identifier)
          THEN RAISE EXCEPTION 'network circuit service identifier is invalid'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM core_organization o
            JOIN core_entity e ON e.id=o.entity_id
            WHERE o.id=NEW.provider_id AND o.tenant_id=NEW.tenant_id
              AND (e.archived_at IS NULL OR (TG_OP='UPDATE' AND OLD.provider_id=NEW.provider_id))
              AND o.id IS DISTINCT FROM NEW.organization_id
              AND EXISTS (SELECT 1 FROM core_organizationclassification c
                WHERE c.organization_id=o.id AND c.kind IN ('vendor','manufacturer','partner')))
          THEN RAISE EXCEPTION 'network circuit provider is unavailable'; END IF;
          IF NEW.contract_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_commercialcontract c JOIN core_entity e ON e.id=c.entity_id
            WHERE c.id=NEW.contract_id AND c.tenant_id=NEW.tenant_id
              AND c.organization_id IS NOT DISTINCT FROM NEW.organization_id
              AND c.provider_id=NEW.provider_id AND c.archived_at IS NULL AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'network circuit contract scope or provider mismatch'; END IF;
          IF NEW.service_starts_on IS NOT NULL AND NEW.planned_disconnect_on IS NOT NULL
            AND NEW.planned_disconnect_on<NEW.service_starts_on
          THEN RAISE EXCEPTION 'network circuit disconnect precedes service start'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_circuit_guard BEFORE INSERT OR UPDATE ON core_networkcircuit
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_circuit();

        CREATE FUNCTION tekdocs_validate_network_circuit_handoff() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE handoff_site uuid; device_site uuid; interface_device uuid;
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
            AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
            AND e.entity_type='network_circuit_handoff' AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'circuit handoff entity scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_networkcircuit c JOIN core_entity e ON e.id=c.entity_id
            WHERE c.id=NEW.circuit_id AND c.tenant_id=NEW.tenant_id
              AND c.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'circuit handoff circuit scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL THEN
            SELECT s.id INTO handoff_site FROM core_site s JOIN core_entity e ON e.id=s.entity_id
              WHERE s.id=NEW.site_id AND s.tenant_id=NEW.tenant_id
                AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL;
            IF handoff_site IS NULL THEN RAISE EXCEPTION 'circuit handoff site scope mismatch'; END IF;
          END IF;
          IF NEW.location_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_location l JOIN core_entity e ON e.id=l.entity_id
            WHERE l.id=NEW.location_id AND l.site_id=NEW.site_id AND l.tenant_id=NEW.tenant_id
              AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
          THEN RAISE EXCEPTION 'circuit handoff location scope mismatch'; END IF;
          IF NEW.device_id IS NOT NULL THEN
            SELECT d.site_id INTO device_site FROM core_networkdevice d JOIN core_entity e ON e.id=d.entity_id
              WHERE d.id=NEW.device_id AND d.tenant_id=NEW.tenant_id
                AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL;
            IF NOT FOUND THEN RAISE EXCEPTION 'circuit handoff device scope mismatch'; END IF;
            IF NEW.site_id IS NOT NULL AND device_site IS NOT NULL AND device_site<>NEW.site_id
            THEN RAISE EXCEPTION 'circuit handoff device placement mismatch'; END IF;
          END IF;
          IF NEW.interface_id IS NOT NULL THEN
            SELECT i.device_id INTO interface_device FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
              WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
                AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL;
            IF interface_device IS NULL OR interface_device IS DISTINCT FROM NEW.device_id
            THEN RAISE EXCEPTION 'circuit handoff interface/device mismatch'; END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_network_circuit_handoff_guard BEFORE INSERT OR UPDATE ON core_networkcircuithandoff
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_network_circuit_handoff();
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
        cursor.execute("DROP TRIGGER IF EXISTS core_network_circuit_handoff_guard ON core_networkcircuithandoff")
        cursor.execute("DROP TRIGGER IF EXISTS core_network_circuit_guard ON core_networkcircuit")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_circuit_handoff()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_network_circuit()")


class Migration(migrations.Migration):
    dependencies = [("core", "0057_circuit_handoff_interface_uniqueness")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
