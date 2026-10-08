import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_package() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositoryevidencereviewdecision decision
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE decision.id=NEW.decision_id
      AND decision.outcome='accepted_for_packaging'
      AND decision.tenant_id=NEW.tenant_id
      AND decision.organization_id=NEW.organization_id
      AND decision.workspace_id=NEW.workspace_id
      AND evidence.tenant_id=NEW.tenant_id
      AND evidence.organization_id=NEW.organization_id
      AND evidence.workspace_id=NEW.workspace_id
      AND NEW.manifest->>'format'='tekdocs-repository-publication-package/v1'
      AND NEW.manifest->>'package_id'=NEW.id::text
      AND NEW.manifest->>'decision_id'=decision.id::text
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'source_commit'=evidence.manifest->>'source_commit'
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN RAISE EXCEPTION 'repository package requires exact accepted evidence' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_package() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository publication package is append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositorypublicationpackage_validate
BEFORE INSERT ON core_repositorypublicationpackage
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_package();
CREATE TRIGGER core_repositorypublicationpackage_immutable
BEFORE UPDATE OR DELETE ON core_repositorypublicationpackage
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_package();
ALTER TABLE core_repositorypublicationpackage ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositorypublicationpackage FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositorypublicationpackage_runtime_scope ON core_repositorypublicationpackage
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositorypublicationpackage_runtime_scope ON core_repositorypublicationpackage;
ALTER TABLE core_repositorypublicationpackage NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositorypublicationpackage DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositorypublicationpackage_immutable ON core_repositorypublicationpackage;
DROP TRIGGER IF EXISTS core_repositorypublicationpackage_validate ON core_repositorypublicationpackage;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_package();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_package();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0171_repository_evidence_review_decision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryPublicationPackage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("manifest", models.JSONField()),
                ("manifest_digest", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
                ),
                (
                    "decision",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="package",
                        to="core.repositoryevidencereviewdecision",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.organization"),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={
                "ordering": ("-created_at", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(manifest_digest__regex=r"^[0-9a-f]{64}$"),
                        name="repository_package_digest_valid",
                    ),
                ],
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
