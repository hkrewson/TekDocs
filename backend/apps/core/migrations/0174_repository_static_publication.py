import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_static_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypackageauthorization authz
    JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
    JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE authz.id=NEW.authorization_id
      AND authz.outcome='authorized_for_publication'
      AND authz.tenant_id=NEW.tenant_id
      AND authz.organization_id=NEW.organization_id
      AND authz.workspace_id=NEW.workspace_id
      AND package.tenant_id=NEW.tenant_id
      AND package.organization_id=NEW.organization_id
      AND package.workspace_id=NEW.workspace_id
      AND NEW.manifest->>'format'='tekdocs-repository-static-publication/v1'
      AND NEW.manifest->>'publication_id'=NEW.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'organization_id'=NEW.organization_id::text
      AND NEW.manifest->>'authorization_id'=authz.id::text
      AND NEW.manifest->>'authorization_outcome'=authz.outcome
      AND NEW.manifest->>'package_id'=package.id::text
      AND NEW.manifest->>'package_digest'=package.manifest_digest
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'source_commit'=package.manifest->>'source_commit'
      AND NEW.manifest->>'html_sha256'=package.manifest->>'html_sha256'
      AND NEW.manifest->>'pdf_sha256'=package.manifest->>'pdf_sha256'
      AND NEW.manifest->'attachments'=package.manifest->'attachments'
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN
    RAISE EXCEPTION 'repository STATIC publication requires exact authorized package' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_static_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository STATIC publication is append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositorystaticpublication_validate
BEFORE INSERT ON core_repositorystaticpublication
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_static_publication();
CREATE TRIGGER core_repositorystaticpublication_immutable
BEFORE UPDATE OR DELETE ON core_repositorystaticpublication
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_static_publication();
ALTER TABLE core_repositorystaticpublication ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticpublication FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositorystaticpublication_runtime_scope ON core_repositorystaticpublication
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositorystaticpublication_runtime_scope ON core_repositorystaticpublication;
ALTER TABLE core_repositorystaticpublication NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticpublication DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositorystaticpublication_immutable ON core_repositorystaticpublication;
DROP TRIGGER IF EXISTS core_repositorystaticpublication_validate ON core_repositorystaticpublication;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_static_publication();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_static_publication();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0173_repository_package_authorization"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryStaticPublication",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("manifest", models.JSONField()),
                ("content_digest", models.CharField(max_length=64)),
                ("signature", models.TextField()),
                ("signature_algorithm", models.CharField(default="Ed25519", max_length=20)),
                ("public_key", models.TextField()),
                ("key_fingerprint", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "authorization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="static_publication",
                        to="core.repositorypackageauthorization",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.organization"),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={"ordering": ("-created_at", "id")},
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
