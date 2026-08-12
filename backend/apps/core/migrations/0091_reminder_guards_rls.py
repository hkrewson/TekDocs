from django.db import migrations

SQL = r"""
CREATE FUNCTION tekdocs_guard_reminder_schedule() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
      AND w.tenant_id=NEW.tenant_id
      AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) OR NOT EXISTS (
    SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
      AND e.workspace_id=NEW.workspace_id AND e.entity_type='reminder_schedule'
  ) OR NOT EXISTS (
    SELECT 1 FROM core_entity e WHERE e.id=NEW.source_entity_id
      AND e.workspace_id=NEW.workspace_id AND e.archived_at IS NULL
  ) OR NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id
  ) OR (
    NEW.owner_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.owner_id
    )
  ) THEN RAISE EXCEPTION 'reminder schedule scope invalid'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id<>OLD.tenant_id OR NEW.workspace_id<>OLD.workspace_id
    OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    OR NEW.entity_id<>OLD.entity_id OR NEW.source_entity_id<>OLD.source_entity_id
    OR NEW.domain<>OLD.domain OR NEW.kind<>OLD.kind OR NEW.created_by_id<>OLD.created_by_id
  ) THEN RAISE EXCEPTION 'reminder schedule identity is immutable'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_reminder_guard BEFORE INSERT OR UPDATE ON core_reminderschedule
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_reminder_schedule();
ALTER TABLE core_reminderschedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_reminderschedule FORCE ROW LEVEL SECURITY;
CREATE POLICY core_reminderschedule_runtime_scope ON core_reminderschedule
USING (
  workspace_id=tekdocs_current_workspace_id()
  AND tekdocs_scope_matches(tenant_id, organization_id)
)
WITH CHECK (
  workspace_id=tekdocs_current_workspace_id()
  AND tekdocs_scope_matches(tenant_id, organization_id)
);
"""

REVERSE = r"""
DROP POLICY IF EXISTS core_reminderschedule_runtime_scope ON core_reminderschedule;
ALTER TABLE core_reminderschedule DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_reminder_guard ON core_reminderschedule;
DROP FUNCTION IF EXISTS tekdocs_guard_reminder_schedule();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0090_reminder_schedules")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
