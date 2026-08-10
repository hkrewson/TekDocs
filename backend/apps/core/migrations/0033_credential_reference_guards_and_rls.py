from django.db import migrations


def enable_credential_reference_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_credential_reference() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND e.entity_type = 'credential_reference'
                  AND e.visibility = 'msp_private'
              ) THEN RAISE EXCEPTION 'credential reference entity workspace mismatch'; END IF;
              IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_organization o
                WHERE o.id = NEW.organization_id AND o.tenant_id = NEW.tenant_id
              ) THEN RAISE EXCEPTION 'credential reference organization tenant mismatch'; END IF;
              IF NEW.provider <> 'onepassword'
                 OR NEW.reference_url !~ '^https://start[.]1password[.]com/open/i[?]a=[a-z0-9]{26}&v=[a-z0-9]{26}&i=[a-z0-9]{26}&h=[a-z0-9][a-z0-9.-]*[.]1password[.](com|ca|eu)$'
              THEN RAISE EXCEPTION 'credential reference provider data is invalid'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_credential_reference_scope_guard "
            "BEFORE INSERT OR UPDATE ON core_credentialreference "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_credential_reference()"
        )
        cursor.execute("ALTER TABLE core_credentialreference ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_credentialreference FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_credentialreference_runtime_scope ON core_credentialreference "
            "USING (tekdocs_scope_matches(tenant_id, organization_id)) "
            "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
        )


def disable_credential_reference_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_credentialreference_runtime_scope ON core_credentialreference")
        cursor.execute("ALTER TABLE core_credentialreference DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_credential_reference_scope_guard ON core_credentialreference")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_credential_reference()")


class Migration(migrations.Migration):
    dependencies = [("core", "0032_credentialreference")]
    operations = [migrations.RunPython(enable_credential_reference_guards, disable_credential_reference_guards)]
