from django.db import migrations

TABLES = ("core_commercialcontract", "core_contractcost")


def enable_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
        CREATE FUNCTION tekdocs_validate_commercial_contract() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
            AND e.organization_id=NEW.organization_id AND e.entity_type='commercial_contract'
            AND e.visibility='msp_private')
          THEN RAISE EXCEPTION 'commercial contract entity scope mismatch'; END IF;
          IF NEW.provider_id=NEW.organization_id OR NOT EXISTS (SELECT 1 FROM core_organization p
            WHERE p.id=NEW.provider_id AND p.tenant_id=NEW.tenant_id)
          THEN RAISE EXCEPTION 'commercial contract provider scope mismatch'; END IF;
          IF NOT EXISTS (SELECT 1 FROM core_organizationclassification c WHERE c.organization_id=NEW.provider_id
            AND c.tenant_id=NEW.tenant_id AND c.kind IN ('vendor','manufacturer','partner'))
          THEN RAISE EXCEPTION 'commercial contract provider classification invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on < NEW.starts_on
          THEN RAISE EXCEPTION 'commercial contract term invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.renews_on IS NOT NULL AND NEW.renews_on < NEW.starts_on
          THEN RAISE EXCEPTION 'commercial contract renewal invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_commercial_contract_guard BEFORE INSERT OR UPDATE ON core_commercialcontract
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_commercial_contract();
        CREATE FUNCTION tekdocs_validate_contract_cost() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM core_commercialcontract c WHERE c.id=NEW.contract_id
            AND c.tenant_id=NEW.tenant_id AND c.organization_id=NEW.organization_id AND c.archived_at IS NULL)
          THEN RAISE EXCEPTION 'contract cost scope mismatch'; END IF;
          IF NEW.currency !~ '^[A-Z]{3}$' THEN RAISE EXCEPTION 'contract cost currency invalid'; END IF;
          IF NEW.starts_on IS NOT NULL AND NEW.ends_on IS NOT NULL AND NEW.ends_on < NEW.starts_on
          THEN RAISE EXCEPTION 'contract cost term invalid'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER core_contract_cost_guard BEFORE INSERT OR UPDATE ON core_contractcost
          FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_contract_cost();
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
        cursor.execute("DROP TRIGGER IF EXISTS core_contract_cost_guard ON core_contractcost")
        cursor.execute("DROP TRIGGER IF EXISTS core_commercial_contract_guard ON core_commercialcontract")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_contract_cost()")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_commercial_contract()")


class Migration(migrations.Migration):
    dependencies = [("core", "0042_commercial_contracts")]
    operations = [migrations.RunPython(enable_guards, disable_guards)]
