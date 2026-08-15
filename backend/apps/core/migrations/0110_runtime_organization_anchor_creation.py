from django.db import migrations


ENTITY_POLICY_SQL = r"""
DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity;
CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING (
    (workspace_id = tekdocs_current_workspace_id()
        AND tekdocs_scope_matches(tenant_id, organization_id)
        AND entity_type NOT IN ('organization', 'person'))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'organization'
        AND (
            tekdocs_organization_anchor_visible(id, tenant_id)
            OR (
                COALESCE(current_setting('tekdocs.principal_mode', true), '') = 'system'
                AND NOT EXISTS (
                    SELECT 1 FROM core_organization organization
                    WHERE organization.entity_id = core_entity.id
                      AND organization.tenant_id = core_entity.tenant_id
                )
            )
        ))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'person'
        AND (
            tekdocs_person_anchor_visible(id, tenant_id)
            OR (
                COALESCE(current_setting('tekdocs.principal_mode', true), '') = 'system'
                AND NOT EXISTS (
                    SELECT 1 FROM core_person person
                    WHERE person.entity_id = core_entity.id
                      AND person.tenant_id = core_entity.tenant_id
                )
            )
        ))
    OR EXISTS (SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id)
);
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity;
CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING (
    (workspace_id = tekdocs_current_workspace_id()
        AND tekdocs_scope_matches(tenant_id, organization_id)
        AND entity_type NOT IN ('organization', 'person'))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'organization'
        AND tekdocs_organization_anchor_visible(id, tenant_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type = 'person'
        AND tekdocs_person_anchor_visible(id, tenant_id))
    OR EXISTS (SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id)
);
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0109_restrict_legacy_scope_helpers")]

    operations = [migrations.RunSQL(ENTITY_POLICY_SQL, REVERSE_SQL)]
