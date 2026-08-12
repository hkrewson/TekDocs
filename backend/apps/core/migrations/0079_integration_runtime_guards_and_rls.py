from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_integration_connection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
    AND w.tenant_id=NEW.tenant_id AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration connection workspace scope mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
    WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection creator scope mismatch'; END IF;
  IF TG_OP='UPDATE' AND (OLD.tenant_id, OLD.workspace_id, OLD.organization_id, OLD.provider, OLD.base_url, OLD.created_by_id)
    IS DISTINCT FROM (NEW.tenant_id, NEW.workspace_id, NEW.organization_id, NEW.provider, NEW.base_url, NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection identity is immutable'; END IF;
  IF TG_OP='UPDATE' AND OLD.secret_envelope IS DISTINCT FROM NEW.secret_envelope
    AND NEW.secret_generation <> OLD.secret_generation + 1
  THEN RAISE EXCEPTION 'integration credential rotation must advance its generation'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_integration_child() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='core_integrationsyncjob' AND TG_OP='UPDATE'
    AND (to_jsonb(OLD) - ARRAY['state','cursor_after','attempts','available_at','locked_at',
      'started_at','finished_at','last_error_code','result_counts'])
    IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['state','cursor_after','attempts','available_at','locked_at',
      'started_at','finished_at','last_error_code','result_counts'])
  THEN RAISE EXCEPTION 'integration job identity is immutable'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict' AND TG_OP='UPDATE'
    AND jsonb_build_array(to_jsonb(OLD)->'tenant_id', to_jsonb(OLD)->'workspace_id',
      to_jsonb(OLD)->'organization_id', to_jsonb(OLD)->'connection_id',
      to_jsonb(OLD)->'remote_type', to_jsonb(OLD)->'remote_id')
    IS DISTINCT FROM jsonb_build_array(to_jsonb(NEW)->'tenant_id', to_jsonb(NEW)->'workspace_id',
      to_jsonb(NEW)->'organization_id', to_jsonb(NEW)->'connection_id',
      to_jsonb(NEW)->'remote_type', to_jsonb(NEW)->'remote_id')
  THEN RAISE EXCEPTION 'integration conflict identity is immutable'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict' AND TG_OP='UPDATE'
    AND to_jsonb(OLD)->>'status' <> 'open'
  THEN RAISE EXCEPTION 'resolved integration conflict is immutable'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict' AND TG_OP='UPDATE'
    AND to_jsonb(OLD)->>'status'='open' AND to_jsonb(NEW)->>'status' <> 'open'
    AND (to_jsonb(OLD) - ARRAY['status','resolved_by_id','resolved_at','updated_at'])
    IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['status','resolved_by_id','resolved_at','updated_at'])
  THEN RAISE EXCEPTION 'integration conflict evidence cannot change during resolution'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict'
    AND (((to_jsonb(NEW)->>'status')='open'
        AND ((to_jsonb(NEW)->>'resolved_by_id') IS NOT NULL OR (to_jsonb(NEW)->>'resolved_at') IS NOT NULL))
      OR ((to_jsonb(NEW)->>'status')<>'open'
        AND ((to_jsonb(NEW)->>'resolved_by_id') IS NULL OR (to_jsonb(NEW)->>'resolved_at') IS NULL)))
  THEN RAISE EXCEPTION 'integration conflict resolution state mismatch'; END IF;
  IF TG_TABLE_NAME IN ('core_integrationsyncjob','core_integrationlogevent','core_integrationconflict')
    AND NOT EXISTS (
    SELECT 1 FROM core_integrationconnection c WHERE c.id=(to_jsonb(NEW)->>'connection_id')::uuid
      AND c.tenant_id=NEW.tenant_id AND c.workspace_id=NEW.workspace_id
      AND c.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration child connection scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationsyncjob'
    AND (to_jsonb(NEW)->>'requested_by_id') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=(to_jsonb(NEW)->>'requested_by_id')::uuid)
  THEN RAISE EXCEPTION 'integration job requester scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationobservation' AND NOT EXISTS (
    SELECT 1 FROM core_integrationsyncjob j WHERE j.id=(to_jsonb(NEW)->>'job_id')::uuid
      AND j.tenant_id=NEW.tenant_id AND j.workspace_id=NEW.workspace_id
      AND j.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration observation job scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationlogevent'
    AND (to_jsonb(NEW)->>'job_id') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM core_integrationsyncjob j
      WHERE j.id=(to_jsonb(NEW)->>'job_id')::uuid
        AND j.connection_id=(to_jsonb(NEW)->>'connection_id')::uuid
        AND j.tenant_id=NEW.tenant_id AND j.workspace_id=NEW.workspace_id
        AND j.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration log job scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationlogevent'
    AND ((to_jsonb(NEW)->>'code') NOT IN ('sync_started','sync_page_succeeded','sync_retry_scheduled','sync_dead_lettered','sync_completed')
      OR jsonb_typeof(to_jsonb(NEW)->'metrics') <> 'object'
      OR EXISTS (SELECT 1 FROM jsonb_each(to_jsonb(NEW)->'metrics') metric
        WHERE jsonb_typeof(metric.value) <> 'number' OR (metric.value::text)::numeric < 0))
  THEN RAISE EXCEPTION 'integration log metadata is not allowlisted'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict'
    AND (to_jsonb(NEW)->>'observation_id') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM core_integrationobservation o JOIN core_integrationsyncjob j ON j.id=o.job_id
      WHERE o.id=(to_jsonb(NEW)->>'observation_id')::uuid
        AND j.connection_id=(to_jsonb(NEW)->>'connection_id')::uuid
        AND o.tenant_id=NEW.tenant_id AND o.workspace_id=NEW.workspace_id
        AND o.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration conflict observation scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict'
    AND (to_jsonb(NEW)->>'local_entity_id') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM core_entity e
      WHERE e.id=(to_jsonb(NEW)->>'local_entity_id')::uuid
        AND e.tenant_id=NEW.tenant_id AND e.workspace_id=NEW.workspace_id
        AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration conflict local entity scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_integrationconflict'
    AND (to_jsonb(NEW)->>'resolved_by_id') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=(to_jsonb(NEW)->>'resolved_by_id')::uuid)
  THEN RAISE EXCEPTION 'integration conflict resolver scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_gitexportbundle' AND NOT EXISTS (
    SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id AND w.tenant_id=NEW.tenant_id
      AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'Git export workspace scope mismatch'; END IF;
  IF TG_TABLE_NAME='core_gitexportbundle' AND NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership m
      WHERE m.tenant_id=NEW.tenant_id AND m.user_id=(to_jsonb(NEW)->>'created_by_id')::uuid)
  THEN RAISE EXCEPTION 'Git export creator scope mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_integration_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained integration record is immutable'; END $$;

CREATE TRIGGER core_intconn_validate BEFORE INSERT OR UPDATE ON core_integrationconnection
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_connection();
CREATE TRIGGER core_intjob_validate BEFORE INSERT OR UPDATE ON core_integrationsyncjob
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_child();
CREATE TRIGGER core_intobs_validate BEFORE INSERT ON core_integrationobservation
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_child();
CREATE TRIGGER core_intobs_immutable BEFORE UPDATE OR DELETE ON core_integrationobservation
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_integration_immutable();
CREATE TRIGGER core_intlog_validate BEFORE INSERT OR UPDATE ON core_integrationlogevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_child();
CREATE TRIGGER core_intlog_immutable BEFORE UPDATE ON core_integrationlogevent
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_integration_immutable();
CREATE TRIGGER core_intconf_validate BEFORE INSERT OR UPDATE ON core_integrationconflict
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_child();
CREATE TRIGGER core_gitexport_validate BEFORE INSERT ON core_gitexportbundle
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_integration_child();
CREATE TRIGGER core_gitexport_immutable BEFORE UPDATE OR DELETE ON core_gitexportbundle
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_integration_immutable();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'core_integrationconnection','core_integrationsyncjob','core_integrationobservation',
    'core_integrationlogevent','core_integrationconflict','core_gitexportbundle'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I_runtime_scope ON %I USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))',
      table_name, table_name
    );
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'core_integrationconnection','core_integrationsyncjob','core_integrationobservation',
    'core_integrationlogevent','core_integrationconflict','core_gitexportbundle'
  ] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_gitexport_immutable ON core_gitexportbundle;
DROP TRIGGER IF EXISTS core_gitexport_validate ON core_gitexportbundle;
DROP TRIGGER IF EXISTS core_intconf_validate ON core_integrationconflict;
DROP TRIGGER IF EXISTS core_intlog_immutable ON core_integrationlogevent;
DROP TRIGGER IF EXISTS core_intlog_validate ON core_integrationlogevent;
DROP TRIGGER IF EXISTS core_intobs_immutable ON core_integrationobservation;
DROP TRIGGER IF EXISTS core_intobs_validate ON core_integrationobservation;
DROP TRIGGER IF EXISTS core_intjob_validate ON core_integrationsyncjob;
DROP TRIGGER IF EXISTS core_intconn_validate ON core_integrationconnection;
DROP FUNCTION IF EXISTS tekdocs_guard_integration_immutable();
DROP FUNCTION IF EXISTS tekdocs_validate_integration_child();
DROP FUNCTION IF EXISTS tekdocs_validate_integration_connection();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0078_integration_runtime")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
