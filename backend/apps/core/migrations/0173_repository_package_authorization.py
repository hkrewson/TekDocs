import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_package_authorization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypublicationpackage package
    WHERE package.id=NEW.package_id
      AND package.tenant_id=NEW.tenant_id
      AND package.organization_id=NEW.organization_id
      AND package.workspace_id=NEW.workspace_id
  ) THEN RAISE EXCEPTION 'repository package authorization scope mismatch' USING ERRCODE='23514'; END IF;
  IF NEW.outcome='authorized_for_publication' AND EXISTS (
    SELECT 1 FROM core_repositorypublicationpackage package
    WHERE package.id=NEW.package_id AND package.created_by_id=NEW.actor_id
  ) THEN RAISE EXCEPTION 'package creator cannot authorize own package' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_package_authorization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository package authorization is append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositorypackageauthorization_validate
BEFORE INSERT ON core_repositorypackageauthorization
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_package_authorization();
CREATE TRIGGER core_repositorypackageauthorization_immutable
BEFORE UPDATE OR DELETE ON core_repositorypackageauthorization
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_package_authorization();
ALTER TABLE core_repositorypackageauthorization ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositorypackageauthorization FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositorypackageauthorization_runtime_scope ON core_repositorypackageauthorization
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositorypackageauthorization_runtime_scope ON core_repositorypackageauthorization;
ALTER TABLE core_repositorypackageauthorization NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositorypackageauthorization DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositorypackageauthorization_immutable ON core_repositorypackageauthorization;
DROP TRIGGER IF EXISTS core_repositorypackageauthorization_validate ON core_repositorypackageauthorization;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_package_authorization();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_package_authorization();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0172_repository_publication_package"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryPackageAuthorization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("authorized_for_publication", "Authorized for publication"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=28,
                    ),
                ),
                ("reason", models.CharField(max_length=500)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.organization"),
                ),
                (
                    "package",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="authorization",
                        to="core.repositorypublicationpackage",
                    ),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={
                "ordering": ("-occurred_at", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(outcome__in=["authorized_for_publication", "rejected"]),
                        name="repository_package_authorization_outcome_valid",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(reason=""), name="repository_package_authorization_reason_required"
                    ),
                ],
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
