from django.db import migrations

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_workspace_repository() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'repository identities cannot be deleted' USING ERRCODE = '23514';
  END IF;
  IF TG_OP = 'UPDATE' AND (
    NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id
    OR NEW.workspace_id <> OLD.workspace_id
    OR NEW.storage_relative_path <> OLD.storage_relative_path
  ) THEN RAISE EXCEPTION 'repository ownership identity is immutable' USING ERRCODE = '23514'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'repository workspace must belong to its tenant' USING ERRCODE = '23514'; END IF;
  IF NEW.storage_relative_path <> 'repositories/' || NEW.id::text || '.git' THEN
    RAISE EXCEPTION 'repository storage path must use its stable identity' USING ERRCODE = '23514';
  END IF;
  IF NEW.accepted_commit_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_repositorycommit commit
    WHERE commit.id=NEW.accepted_commit_id AND commit.tenant_id=NEW.tenant_id
      AND commit.repository_id=NEW.id
  ) THEN RAISE EXCEPTION 'accepted head must name a verified object in this repository' USING ERRCODE = '23514'; END IF;
  IF NEW.indexed_commit_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_repositorycommit commit
    WHERE commit.id=NEW.indexed_commit_id AND commit.tenant_id=NEW.tenant_id
      AND commit.repository_id=NEW.id
  ) THEN RAISE EXCEPTION 'indexed head must name a verified object in this repository' USING ERRCODE = '23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_repository_commit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'verified repository objects are immutable' USING ERRCODE = '23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_workspacerepository repository
    WHERE repository.id=NEW.repository_id AND repository.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'verified repository object must belong to its tenant' USING ERRCODE = '23514'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_workspace_repository_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_workspacerepository
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_workspace_repository();

CREATE TRIGGER core_repository_commit_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_repositorycommit
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_commit();
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_repository_commit_guard ON core_repositorycommit;
DROP TRIGGER IF EXISTS core_workspace_repository_guard ON core_workspacerepository;
DROP FUNCTION IF EXISTS tekdocs_validate_repository_commit();
DROP FUNCTION IF EXISTS tekdocs_validate_workspace_repository();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0162_repositorycommit_workspacerepository_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
