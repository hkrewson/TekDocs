from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_current_user_id()
RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT NULLIF(current_setting('tekdocs.user_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION tekdocs_organization_anchor_visible(row_entity_id uuid, row_tenant_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT tekdocs_current_user_id() IS NOT NULL AND EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.entity_id = row_entity_id
          AND organization.tenant_id = row_tenant_id
          AND organization.entity_id IN (
              SELECT candidate.entity_id
              FROM core_organization candidate
              WHERE candidate.tenant_id = row_tenant_id
                AND (
                    candidate.access_mode = 'all_authorized'
                    OR EXISTS (
                        SELECT 1 FROM core_installationstate installation
                        WHERE installation.tenant_id = row_tenant_id
                          AND installation.owner_id = tekdocs_current_user_id()
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM accounts_organizationaccessassignment assignment
                        JOIN accounts_tenantmembership membership
                          ON membership.id = assignment.membership_id
                        WHERE assignment.organization_id = candidate.id
                          AND assignment.tenant_id = row_tenant_id
                          AND membership.tenant_id = row_tenant_id
                          AND membership.user_id = tekdocs_current_user_id()
                    )
                )
          )
    )
$$;

CREATE OR REPLACE FUNCTION tekdocs_person_anchor_visible(row_entity_id uuid, row_tenant_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM core_person person
        JOIN core_personassociation association ON association.person_id = person.id
        WHERE person.entity_id = row_entity_id
          AND person.tenant_id = row_tenant_id
          AND association.tenant_id = row_tenant_id
          AND association.archived_at IS NULL
          AND (
              (current_setting('tekdocs.organization_mode', true) = 'msp'
               AND association.organization_id IS NULL)
              OR
              (current_setting('tekdocs.organization_mode', true) = 'organization'
               AND association.organization_id = tekdocs_current_organization_id())
          )
    )
$$;

REVOKE ALL ON FUNCTION tekdocs_current_user_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION tekdocs_person_anchor_visible(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_current_user_id() TO tekdocs_runtime;
GRANT EXECUTE ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) TO tekdocs_runtime;
GRANT EXECUTE ON FUNCTION tekdocs_person_anchor_visible(uuid, uuid) TO tekdocs_runtime;

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


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity;
CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
    OR EXISTS (SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id)
);
DROP FUNCTION IF EXISTS tekdocs_person_anchor_visible(uuid, uuid);
DROP FUNCTION IF EXISTS tekdocs_organization_anchor_visible(uuid, uuid);
DROP FUNCTION IF EXISTS tekdocs_current_user_id();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0105_organization_access_fail_closed_default"),
        ("accounts", "0019_domain_permissions"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
