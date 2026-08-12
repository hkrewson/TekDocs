# ruff: noqa: E501
from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_domain_review_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'domain review events are immutable'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_registereddomain d WHERE d.id=NEW.domain_id AND d.workspace_id=NEW.workspace_id)
    OR NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.reviewed_by_id)
  THEN RAISE EXCEPTION 'domain review event scope invalid'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_domain_review_guard BEFORE INSERT OR UPDATE OR DELETE ON core_domainreviewevent FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_domain_review_event();
ALTER TABLE core_domainreviewevent ENABLE ROW LEVEL SECURITY; ALTER TABLE core_domainreviewevent FORCE ROW LEVEL SECURITY;
CREATE POLICY core_domainreviewevent_runtime_scope ON core_domainreviewevent USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id,organization_id));
"""
REVERSE = r"""
DROP POLICY IF EXISTS core_domainreviewevent_runtime_scope ON core_domainreviewevent;
ALTER TABLE core_domainreviewevent DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_domain_review_guard ON core_domainreviewevent;
DROP FUNCTION IF EXISTS tekdocs_guard_domain_review_event();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0096_domain_renewal_reviews")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
