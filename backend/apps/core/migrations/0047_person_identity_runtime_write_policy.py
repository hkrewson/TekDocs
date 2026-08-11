from django.db import migrations

FORWARD_SQL = r"""
DROP POLICY IF EXISTS core_entity_runtime_insert ON core_entity;
CREATE POLICY core_entity_runtime_insert ON core_entity FOR INSERT WITH CHECK (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'person')
);

DROP POLICY IF EXISTS core_entity_runtime_update ON core_entity;
CREATE POLICY core_entity_runtime_update ON core_entity FOR UPDATE USING (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
) WITH CHECK (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'person')
);
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_entity_runtime_insert ON core_entity;
CREATE POLICY core_entity_runtime_insert ON core_entity FOR INSERT WITH CHECK (
    workspace_id = tekdocs_current_workspace_id() AND (
        tekdocs_scope_matches(tenant_id, organization_id)
        OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
            AND entity_type IN ('organization', 'person'))
    )
);
DROP POLICY IF EXISTS core_entity_runtime_update ON core_entity;
CREATE POLICY core_entity_runtime_update ON core_entity FOR UPDATE USING (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
) WITH CHECK (
    workspace_id = tekdocs_current_workspace_id() AND (
        tekdocs_scope_matches(tenant_id, organization_id)
        OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
            AND entity_type IN ('organization', 'person'))
    )
);
"""


def install_policy(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def remove_policy(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0046_documentattachment_scan_engine_and_more")]

    operations = [migrations.RunPython(install_policy, remove_policy)]
