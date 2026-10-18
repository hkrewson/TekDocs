from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0194_fragment_authority_scope_validation")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE POLICY core_entity_asset_supplier_select ON core_entity FOR SELECT USING (
                    tenant_id = tekdocs_current_tenant_id()
                    AND entity_type = 'organization'
                    AND EXISTS (
                        SELECT 1 FROM core_clientasset asset
                        JOIN core_organization supplier ON supplier.id = asset.supplier_id
                        WHERE supplier.entity_id = core_entity.id
                          AND supplier.tenant_id = core_entity.tenant_id
                          AND asset.tenant_id = core_entity.tenant_id
                          AND asset.archived_at IS NULL
                          AND tekdocs_scope_matches(asset.tenant_id, asset.organization_id)
                    )
                );
            """,
            reverse_sql="DROP POLICY IF EXISTS core_entity_asset_supplier_select ON core_entity;",
        ),
    ]
