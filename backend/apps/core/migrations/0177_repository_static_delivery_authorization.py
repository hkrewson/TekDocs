import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_static_delivery_authorization()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_content uuid;
DECLARE source_audience text;
DECLARE source_creator uuid;
BEGIN
  SELECT evidence.content_id, evidence.audience, publication.created_by_id
    INTO source_content, source_audience, source_creator
  FROM core_repositorystaticpublication publication
  JOIN core_repositorypackageauthorization authz ON authz.id=publication.authorization_id
  JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
  JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
  JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
  WHERE publication.id=NEW.publication_id
    AND publication.tenant_id=NEW.tenant_id
    AND publication.organization_id=NEW.organization_id
    AND publication.workspace_id=NEW.workspace_id;
  IF source_content IS NULL OR source_audience <> 'client_visible' OR NEW.actor_id=source_creator THEN
    RAISE EXCEPTION 'repository STATIC delivery authorization scope or actor mismatch' USING ERRCODE='23514';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'repository-static-content:' || NEW.workspace_id::text || ':' || source_content::text, 0
  ));
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorystaticpublicationcontrolevent release_event
    WHERE release_event.publication_id=NEW.publication_id AND release_event.action='released'
  ) OR EXISTS (
    SELECT 1 FROM core_repositorystaticpublicationcontrolevent withdrawal
    WHERE withdrawal.publication_id=NEW.publication_id AND withdrawal.action='withdrawn'
  ) OR EXISTS (
    SELECT 1 FROM core_repositorystaticpublicationcontrolevent successor
    WHERE successor.supersedes_id=NEW.publication_id AND successor.action='released'
  ) THEN
    RAISE EXCEPTION 'only an active release can be authorized for future client delivery'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_static_delivery_authorization()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository STATIC delivery authorizations are append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositorystaticdeliveryauthorization_validate
BEFORE INSERT ON core_repositorystaticdeliveryauthorization
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_static_delivery_authorization();
CREATE TRIGGER core_repositorystaticdeliveryauthorization_immutable
BEFORE UPDATE OR DELETE ON core_repositorystaticdeliveryauthorization
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_static_delivery_authorization();
ALTER TABLE core_repositorystaticdeliveryauthorization ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticdeliveryauthorization FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositorystaticdeliveryauthorization_runtime_scope
ON core_repositorystaticdeliveryauthorization
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositorystaticdeliveryauthorization_runtime_scope
ON core_repositorystaticdeliveryauthorization;
ALTER TABLE core_repositorystaticdeliveryauthorization NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticdeliveryauthorization DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositorystaticdeliveryauthorization_immutable
ON core_repositorystaticdeliveryauthorization;
DROP TRIGGER IF EXISTS core_repositorystaticdeliveryauthorization_validate
ON core_repositorystaticdeliveryauthorization;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_static_delivery_authorization();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_static_delivery_authorization();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0176_repository_static_supersession"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryStaticDeliveryAuthorization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.CharField(max_length=500)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.organization"),
                ),
                (
                    "publication",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="delivery_authorization",
                        to="core.repositorystaticpublication",
                    ),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={
                "ordering": ("-occurred_at", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=~models.Q(reason=""), name="repository_static_delivery_reason_required"
                    ),
                ],
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
