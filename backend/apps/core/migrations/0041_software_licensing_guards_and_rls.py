from django.db import migrations


TABLES = (
    "core_clientsoftwareinstallation",
    "core_softwarelicense",
    "core_softwarelicenseinstallation",
    "core_softwarelicenseseat",
    "core_softwarelicenseevent",
)


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
        CREATE FUNCTION tekdocs_validate_software_installation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
            WHERE a.id=NEW.asset_id AND a.tenant_id=NEW.tenant_id AND a.organization_id=NEW.organization_id AND p.kind='software')
          THEN RAISE EXCEPTION 'software installation asset scope mismatch'; END IF;
          IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
            AND s.tenant_id=NEW.tenant_id AND s.organization_id=NEW.organization_id AND s.archived_at IS NULL)
          THEN RAISE EXCEPTION 'software installation site scope mismatch'; END IF;
          IF NEW.status='installed' AND NEW.installed_on IS NULL THEN RAISE EXCEPTION 'installed date required'; END IF;
          IF TG_OP='UPDATE' AND OLD.status='uninstalled' THEN RAISE EXCEPTION 'uninstalled state is terminal'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_software_installation_guard BEFORE INSERT OR UPDATE ON core_clientsoftwareinstallation
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_software_installation();
        CREATE FUNCTION tekdocs_validate_software_license() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
            AND e.organization_id=NEW.organization_id AND e.entity_type='software_license')
          THEN RAISE EXCEPTION 'software license entity scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_catalogproduct p WHERE p.id=NEW.product_id AND p.tenant_id=NEW.tenant_id
            AND p.organization_id=NEW.supplier_id AND p.kind='software')
          THEN RAISE EXCEPTION 'software license product scope mismatch'; END IF;
          IF NEW.model_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_catalogmodel m WHERE m.id=NEW.model_id
            AND m.product_id=NEW.product_id AND m.organization_id=NEW.supplier_id AND m.tenant_id=NEW.tenant_id)
          THEN RAISE EXCEPTION 'software license model scope mismatch'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on < NEW.starts_on
          THEN RAISE EXCEPTION 'software license term invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.renews_on IS NOT NULL AND NEW.renews_on < NEW.starts_on
          THEN RAISE EXCEPTION 'software renewal date invalid'; END IF;
          IF NEW.kind='perpetual' AND (NEW.auto_renew OR NEW.renewal_interval <> 'none')
          THEN RAISE EXCEPTION 'perpetual renewal invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_software_license_guard BEFORE INSERT OR UPDATE ON core_softwarelicense
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_software_license();
        CREATE FUNCTION tekdocs_validate_software_license_edge() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_softwarelicense l WHERE l.id=NEW.license_id
            AND l.tenant_id=NEW.tenant_id AND l.organization_id=NEW.organization_id)
          THEN RAISE EXCEPTION 'software license edge scope mismatch'; END IF;
          IF (to_jsonb(NEW)->>'installation_id') IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM core_clientsoftwareinstallation i JOIN core_clientasset a ON a.id=i.asset_id
            JOIN core_softwarelicense l ON l.id=NEW.license_id WHERE i.id=(to_jsonb(NEW)->>'installation_id')::uuid
              AND i.tenant_id=NEW.tenant_id AND i.organization_id=NEW.organization_id AND a.product_id=l.product_id)
          THEN RAISE EXCEPTION 'software installation edge scope mismatch'; END IF;
          IF (to_jsonb(NEW)->>'person_id') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_personassociation p WHERE p.id=(to_jsonb(NEW)->>'person_id')::uuid
            AND p.tenant_id=NEW.tenant_id AND p.organization_id=NEW.organization_id AND p.archived_at IS NULL)
          THEN RAISE EXCEPTION 'software seat person scope mismatch'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_software_license_installation_guard BEFORE INSERT OR UPDATE ON core_softwarelicenseinstallation
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_software_license_edge();
        CREATE TRIGGER core_software_license_seat_guard BEFORE INSERT OR UPDATE ON core_softwarelicenseseat
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_software_license_edge();
        CREATE TRIGGER core_software_license_event_guard BEFORE INSERT ON core_softwarelicenseevent
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_software_license_edge();
        CREATE FUNCTION tekdocs_reject_software_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'software license history is append-only'; END $$;
        CREATE TRIGGER core_software_license_event_immutable BEFORE UPDATE OR DELETE ON core_softwarelicenseevent
          FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_software_history_mutation();
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
        cursor.execute("DROP TRIGGER IF EXISTS core_software_license_event_immutable ON core_softwarelicenseevent")
        cursor.execute("DROP TRIGGER IF EXISTS core_software_license_event_guard ON core_softwarelicenseevent")
        cursor.execute("DROP TRIGGER IF EXISTS core_software_license_seat_guard ON core_softwarelicenseseat")
        cursor.execute(
            "DROP TRIGGER IF EXISTS core_software_license_installation_guard ON core_softwarelicenseinstallation"
        )
        cursor.execute("DROP TRIGGER IF EXISTS core_software_license_guard ON core_softwarelicense")
        cursor.execute("DROP TRIGGER IF EXISTS core_software_installation_guard ON core_clientsoftwareinstallation")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_reject_software_history_mutation()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_software_license_edge()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_software_license()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_software_installation()")


class Migration(migrations.Migration):
    dependencies = [("core", "0040_software_licensing")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
