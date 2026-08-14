from django.db import migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_system_principal_active()
RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT COALESCE(current_setting('tekdocs.principal_mode', true), '') = 'system'
$$;

CREATE OR REPLACE FUNCTION tekdocs_organization_anchor_visible(row_entity_id uuid, row_tenant_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.entity_id = row_entity_id
          AND organization.tenant_id = row_tenant_id
          AND (
              (
                  tekdocs_system_principal_active()
                  AND (
                      current_setting('tekdocs.organization_mode', true) = 'msp'
                      OR (
                          current_setting('tekdocs.organization_mode', true) = 'organization'
                          AND organization.id = tekdocs_current_organization_id()
                      )
                  )
              )
              OR (
                  COALESCE(current_setting('tekdocs.principal_mode', true), '') = 'user'
                  AND tekdocs_current_user_id() IS NOT NULL
                  AND (
                      organization.access_mode = 'all_authorized'
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
                          WHERE assignment.organization_id = organization.id
                            AND assignment.tenant_id = row_tenant_id
                            AND membership.tenant_id = row_tenant_id
                            AND membership.user_id = tekdocs_current_user_id()
                      )
                      OR (
                          current_setting('tekdocs.organization_mode', true) = 'organization'
                          AND organization.id = tekdocs_current_organization_id()
                          AND EXISTS (
                              SELECT 1
                              FROM accounts_tenantmembership client_membership
                              WHERE client_membership.tenant_id = row_tenant_id
                                AND client_membership.user_id = tekdocs_current_user_id()
                                AND client_membership.organization_id = organization.id
                          )
                      )
                  )
              )
          )
    )
$$;

REVOKE ALL ON FUNCTION tekdocs_system_principal_active() FROM PUBLIC;
REVOKE ALL ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_system_principal_active() TO tekdocs_runtime;
GRANT EXECUTE ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) TO tekdocs_runtime;
"""


REVERSE_SQL = r"""
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
REVOKE ALL ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tekdocs_organization_anchor_visible(uuid, uuid) TO tekdocs_runtime;
DROP FUNCTION IF EXISTS tekdocs_system_principal_active();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0106_entity_anchor_access_rls")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
