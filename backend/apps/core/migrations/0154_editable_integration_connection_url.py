from django.db import migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_integration_connection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
    AND w.tenant_id=NEW.tenant_id AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration connection workspace scope mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
    WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection creator scope mismatch'; END IF;
  IF TG_OP='UPDATE' AND (OLD.tenant_id, OLD.workspace_id, OLD.organization_id, OLD.provider, OLD.created_by_id)
    IS DISTINCT FROM (NEW.tenant_id, NEW.workspace_id, NEW.organization_id, NEW.provider, NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection identity is immutable'; END IF;
  IF TG_OP='UPDATE' AND OLD.secret_envelope IS DISTINCT FROM NEW.secret_envelope
    AND NEW.secret_generation <> OLD.secret_generation + 1
  THEN RAISE EXCEPTION 'integration credential rotation must advance its generation'; END IF;
  RETURN NEW;
END $$;
"""

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_integration_connection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_workspace w WHERE w.id=NEW.workspace_id
    AND w.tenant_id=NEW.tenant_id AND w.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'integration connection workspace scope mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM accounts_tenantmembership m
    WHERE m.tenant_id=NEW.tenant_id AND m.user_id=NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection creator scope mismatch'; END IF;
  IF TG_OP='UPDATE' AND
    (OLD.tenant_id, OLD.workspace_id, OLD.organization_id, OLD.provider, OLD.base_url, OLD.created_by_id)
    IS DISTINCT FROM
    (NEW.tenant_id, NEW.workspace_id, NEW.organization_id, NEW.provider, NEW.base_url, NEW.created_by_id)
  THEN RAISE EXCEPTION 'integration connection identity is immutable'; END IF;
  IF TG_OP='UPDATE' AND OLD.secret_envelope IS DISTINCT FROM NEW.secret_envelope
    AND NEW.secret_generation <> OLD.secret_generation + 1
  THEN RAISE EXCEPTION 'integration credential rotation must advance its generation'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0153_recurring_draft_withdrawal")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
