import django.db.models.deletion
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_document_remote_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND (
    OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
    OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
    OR OLD.document_id IS DISTINCT FROM NEW.document_id
    OR OLD.repository_id IS DISTINCT FROM NEW.repository_id
    OR OLD.content_id IS DISTINCT FROM NEW.content_id
  ) THEN RAISE EXCEPTION 'remote source owner is immutable'; END IF;
  IF (NEW.document_id IS NULL) = (NEW.repository_id IS NULL) THEN
    RAISE EXCEPTION 'remote source owner shape mismatch';
  END IF;
  IF NEW.document_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_document document
    WHERE document.id=NEW.document_id AND document.tenant_id=NEW.tenant_id
      AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND document.archived_at IS NULL
  ) THEN RAISE EXCEPTION 'remote source document workspace mismatch'; END IF;
  IF NEW.repository_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_workspacerepository repository
    JOIN core_workspace workspace ON workspace.id=repository.workspace_id
    JOIN core_contentnode node ON node.repository_id=repository.id
      AND node.content_id=NEW.content_id AND node.kind='document'
      AND node.indexed_commit_id=repository.indexed_commit_id
    WHERE repository.id=NEW.repository_id AND repository.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND repository.accepted_commit_id=repository.indexed_commit_id
      AND NOT EXISTS (
        SELECT 1 FROM core_document legacy WHERE legacy.id=NEW.content_id
          AND legacy.tenant_id=NEW.tenant_id
          AND legacy.organization_id IS NOT DISTINCT FROM NEW.organization_id
      )
  ) THEN RAISE EXCEPTION 'remote source repository owner mismatch'; END IF;
  IF NEW.last_applied_observation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_documentremoteobservation observation
    WHERE observation.id=NEW.last_applied_observation_id AND observation.source_id=NEW.id
  ) THEN RAISE EXCEPTION 'applied observation source mismatch'; END IF;
  RETURN NEW;
END $$;
"""


REVERSE_SQL = r"""
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM core_documentremotesource WHERE repository_id IS NOT NULL) THEN
    RAISE EXCEPTION 'native monitored sources prevent schema rollback';
  END IF;
END $$;
CREATE OR REPLACE FUNCTION tekdocs_validate_document_remote_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_document document
    WHERE document.id=NEW.document_id AND document.tenant_id=NEW.tenant_id
      AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND document.archived_at IS NULL
  ) THEN RAISE EXCEPTION 'remote source document workspace mismatch'; END IF;
  IF NEW.last_applied_observation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_documentremoteobservation observation
    WHERE observation.id=NEW.last_applied_observation_id AND observation.source_id=NEW.id
  ) THEN RAISE EXCEPTION 'applied observation source mismatch'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0222_native_template_evidence")]

    operations = [
        migrations.AlterField(
            model_name="documentremotesource",
            name="document",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="remote_source", to="core.document",
            ),
        ),
        migrations.AddField(
            model_name="documentremotesource", name="content_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentremotesource", name="repository",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="native_remote_sources", to="core.workspacerepository",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentremotesource",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(document__isnull=False, repository__isnull=True, content_id__isnull=True)
                    | models.Q(document__isnull=True, repository__isnull=False, content_id__isnull=False)
                ),
                name="document_source_owner_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentremotesource",
            constraint=models.UniqueConstraint(
                fields=("repository", "content_id"), condition=models.Q(repository__isnull=False),
                name="document_source_native_owner_unique",
            ),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
