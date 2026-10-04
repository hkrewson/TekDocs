import uuid

import django.db.models.deletion
from django.db import migrations, models


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_repository_commit_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'repository commit attribution is immutable' USING ERRCODE = '55000';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM core_repositorycommit commit
    JOIN core_workspacerepository repository ON repository.id=commit.repository_id
    JOIN core_auditevent audit ON audit.id=NEW.audit_event_id
    WHERE commit.id=NEW.commit_id
      AND commit.repository_id=NEW.repository_id
      AND commit.tenant_id=NEW.tenant_id
      AND repository.tenant_id=NEW.tenant_id
      AND audit.tenant_id=NEW.tenant_id
      AND audit.actor_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'repository attribution boundary is invalid' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_repository_commit_audit_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_repositorycommitaudit
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_commit_audit();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_repository_commit_audit_guard ON core_repositorycommitaudit;
DROP FUNCTION IF EXISTS tekdocs_validate_repository_commit_audit();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0163_repository_authority_guards")]

    operations = [
        migrations.AlterField(
            model_name="workspacerepository",
            name="last_reconciliation_state",
            field=models.CharField(
                choices=[
                    ("never", "Never reconciled"),
                    ("matched", "Matched"),
                    ("missing", "Accepted head missing"),
                    ("advanced", "Repository advanced"),
                    ("mismatched", "Head mismatched"),
                    ("corrupt", "Repository corrupt"),
                    ("unavailable", "Repository unavailable"),
                ],
                default="never",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="RepositoryCommitAudit",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "audit_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="repository_commit_attribution",
                        to="core.auditevent",
                    ),
                ),
                (
                    "commit",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_attribution",
                        to="core.repositorycommit",
                    ),
                ),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commit_audits",
                        to="core.workspacerepository",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="repository_commit_audits",
                        to="core.tenant",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="repositorycommitaudit",
            index=models.Index(fields=["tenant", "repository"], name="core_repocommitaudit_scope_idx"),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
