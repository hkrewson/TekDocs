from django.db import migrations
from django.utils import timezone

TABLES = ("core_clienthardwareasset", "core_clientassetlifecycleevent")


def seed_hardware_profiles(apps, schema_editor):
    ClientAsset = apps.get_model("core", "ClientAsset")
    ClientHardwareAsset = apps.get_model("core", "ClientHardwareAsset")
    ClientAssetLifecycleEvent = apps.get_model("core", "ClientAssetLifecycleEvent")
    now = timezone.now()
    for asset in ClientAsset.objects.filter(product__kind="hardware").iterator():
        profile, created = ClientHardwareAsset.objects.get_or_create(
            asset=asset,
            defaults={"tenant_id": asset.tenant_id, "organization_id": asset.organization_id},
        )
        if created:
            ClientAssetLifecycleEvent.objects.create(
                tenant_id=asset.tenant_id,
                organization_id=asset.organization_id,
                asset=asset,
                event_type="created",
                to_state="in_stock",
                occurred_at=asset.created_at or now,
                actor_id=asset.created_by_id,
            )


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_hardware_profile() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id = a.product_id
                WHERE a.id = NEW.asset_id AND a.tenant_id = NEW.tenant_id
                  AND a.organization_id = NEW.organization_id AND p.kind = 'hardware'
              ) THEN RAISE EXCEPTION 'hardware profile asset scope mismatch'; END IF;
              IF NEW.serial_number <> upper(btrim(NEW.serial_number))
                OR NEW.asset_tag <> upper(btrim(NEW.asset_tag))
              THEN RAISE EXCEPTION 'hardware identifiers must be normalized'; END IF;
              IF NEW.warranty_starts_on IS NOT NULL AND NEW.warranty_ends_on IS NOT NULL
                AND NEW.warranty_ends_on < NEW.warranty_starts_on
              THEN RAISE EXCEPTION 'hardware warranty dates invalid'; END IF;
              IF NEW.assigned_person_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_personassociation p WHERE p.id = NEW.assigned_person_id
                  AND p.tenant_id = NEW.tenant_id AND p.organization_id = NEW.organization_id
                  AND p.archived_at IS NULL
              ) THEN RAISE EXCEPTION 'hardware person assignment scope mismatch'; END IF;
              IF NEW.assigned_site_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_site s WHERE s.id = NEW.assigned_site_id
                  AND s.tenant_id = NEW.tenant_id AND s.organization_id = NEW.organization_id
                  AND s.archived_at IS NULL
              ) THEN RAISE EXCEPTION 'hardware site assignment scope mismatch'; END IF;
              IF NEW.assigned_location_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_location l WHERE l.id = NEW.assigned_location_id
                  AND l.tenant_id = NEW.tenant_id AND l.organization_id = NEW.organization_id
                  AND l.site_id = NEW.assigned_site_id AND l.archived_at IS NULL
              ) THEN RAISE EXCEPTION 'hardware location assignment scope mismatch'; END IF;
              IF NEW.lifecycle_state = 'disposed' THEN
                IF NEW.disposed_on IS NULL OR NEW.disposal_method = '' OR NEW.assigned_person_id IS NOT NULL
                  OR NEW.assigned_site_id IS NOT NULL OR NEW.assigned_location_id IS NOT NULL
                  OR NEW.assigned_at IS NOT NULL
                THEN RAISE EXCEPTION 'disposed hardware state invalid'; END IF;
              ELSIF NEW.disposed_on IS NOT NULL OR NEW.disposal_method <> '' OR NEW.disposal_reason <> '' THEN
                RAISE EXCEPTION 'disposal details require disposed hardware';
              END IF;
              IF TG_OP = 'UPDATE' AND OLD.lifecycle_state = 'disposed' THEN
                RAISE EXCEPTION 'disposed hardware lifecycle is terminal';
              END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_hardware_profile_guard BEFORE INSERT OR UPDATE ON core_clienthardwareasset "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_hardware_profile()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_hardware_event() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_clientasset a WHERE a.id = NEW.asset_id
                  AND a.tenant_id = NEW.tenant_id AND a.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'hardware event asset scope mismatch'; END IF;
              IF NEW.person_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_personassociation p WHERE p.id = NEW.person_id
                  AND p.tenant_id = NEW.tenant_id AND p.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'hardware event person scope mismatch'; END IF;
              IF NEW.site_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_site s WHERE s.id = NEW.site_id
                  AND s.tenant_id = NEW.tenant_id AND s.organization_id = NEW.organization_id
              ) THEN RAISE EXCEPTION 'hardware event site scope mismatch'; END IF;
              IF NEW.location_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_location l WHERE l.id = NEW.location_id
                  AND l.tenant_id = NEW.tenant_id AND l.organization_id = NEW.organization_id
                  AND l.site_id = NEW.site_id
              ) THEN RAISE EXCEPTION 'hardware event location scope mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_hardware_event_guard BEFORE INSERT ON core_clientassetlifecycleevent "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_hardware_event()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_reject_hardware_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'hardware lifecycle history is append-only'; END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_hardware_event_immutable BEFORE UPDATE OR DELETE ON core_clientassetlifecycleevent "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_hardware_history_mutation()"
        )
        cursor.execute(
            "CREATE TRIGGER core_hardware_profile_delete_guard BEFORE DELETE ON core_clienthardwareasset "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_hardware_history_mutation()"
        )
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
        cursor.execute("DROP TRIGGER IF EXISTS core_hardware_profile_delete_guard ON core_clienthardwareasset")
        cursor.execute("DROP TRIGGER IF EXISTS core_hardware_event_immutable ON core_clientassetlifecycleevent")
        cursor.execute("DROP TRIGGER IF EXISTS core_hardware_event_guard ON core_clientassetlifecycleevent")
        cursor.execute("DROP TRIGGER IF EXISTS core_hardware_profile_guard ON core_clienthardwareasset")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_reject_hardware_history_mutation()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_hardware_event()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_hardware_profile()")


class Migration(migrations.Migration):
    dependencies = [("core", "0038_hardware_asset_lifecycle")]
    operations = [
        migrations.RunPython(seed_hardware_profiles, migrations.RunPython.noop),
        migrations.RunPython(enable_guards, disable_guards),
    ]
