import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = """
CREATE FUNCTION tekdocs_validate_repository_static_control() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_content uuid;
DECLARE source_creator uuid;
BEGIN
  SELECT evidence.content_id, publication.created_by_id INTO source_content, source_creator
  FROM core_repositorystaticpublication publication
  JOIN core_repositorypackageauthorization authz ON authz.id=publication.authorization_id
  JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
  JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
  JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
  WHERE publication.id=NEW.publication_id
    AND publication.tenant_id=NEW.tenant_id
    AND publication.organization_id=NEW.organization_id
    AND publication.workspace_id=NEW.workspace_id;
  IF source_content IS NULL THEN
    RAISE EXCEPTION 'repository STATIC control scope mismatch' USING ERRCODE='23514';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'repository-static-content:' || NEW.workspace_id::text || ':' || source_content::text, 0
  ));
  IF NEW.action='released' THEN
    IF NEW.actor_id=source_creator THEN
      RAISE EXCEPTION 'publication creator cannot release own record' USING ERRCODE='23514';
    END IF;
    IF EXISTS (
      SELECT 1 FROM core_repositorystaticpublicationcontrolevent active
      JOIN core_repositorystaticpublication current_pub ON current_pub.id=active.publication_id
      JOIN core_repositorypackageauthorization current_authz ON current_authz.id=current_pub.authorization_id
      JOIN core_repositorypublicationpackage current_package ON current_package.id=current_authz.package_id
      JOIN core_repositoryevidencereviewdecision current_decision
        ON current_decision.id=current_package.decision_id
      JOIN core_repositorypublicationevidence current_evidence
        ON current_evidence.id=current_decision.evidence_id
      WHERE active.action='released'
        AND current_pub.workspace_id=NEW.workspace_id
        AND current_evidence.content_id=source_content
        AND NOT EXISTS (
          SELECT 1 FROM core_repositorystaticpublicationcontrolevent withdrawal
          WHERE withdrawal.publication_id=current_pub.id AND withdrawal.action='withdrawn'
        )
    ) THEN
      RAISE EXCEPTION 'active repository STATIC release already exists' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.action='withdrawn' THEN
    IF NOT EXISTS (
      SELECT 1 FROM core_repositorystaticpublicationcontrolevent release_event
      WHERE release_event.publication_id=NEW.publication_id AND release_event.action='released'
    ) THEN
      RAISE EXCEPTION 'repository STATIC publication was not released' USING ERRCODE='23514';
    END IF;
  ELSE
    RAISE EXCEPTION 'invalid repository STATIC control action' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION tekdocs_guard_repository_static_control() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'repository STATIC controls are append-only' USING ERRCODE='23514';
END $$;
CREATE TRIGGER core_repositorystaticpublicationcontrolevent_validate
BEFORE INSERT ON core_repositorystaticpublicationcontrolevent
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_repository_static_control();
CREATE TRIGGER core_repositorystaticpublicationcontrolevent_immutable
BEFORE UPDATE OR DELETE ON core_repositorystaticpublicationcontrolevent
FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_repository_static_control();
ALTER TABLE core_repositorystaticpublicationcontrolevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticpublicationcontrolevent FORCE ROW LEVEL SECURITY;
CREATE POLICY core_repositorystaticpublicationcontrolevent_runtime_scope
ON core_repositorystaticpublicationcontrolevent
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = """
DROP POLICY IF EXISTS core_repositorystaticpublicationcontrolevent_runtime_scope
ON core_repositorystaticpublicationcontrolevent;
ALTER TABLE core_repositorystaticpublicationcontrolevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE core_repositorystaticpublicationcontrolevent DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_repositorystaticpublicationcontrolevent_immutable
ON core_repositorystaticpublicationcontrolevent;
DROP TRIGGER IF EXISTS core_repositorystaticpublicationcontrolevent_validate
ON core_repositorystaticpublicationcontrolevent;
DROP FUNCTION IF EXISTS tekdocs_guard_repository_static_control();
DROP FUNCTION IF EXISTS tekdocs_validate_repository_static_control();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0174_repository_static_publication"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RepositoryStaticPublicationControlEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "action",
                    models.CharField(
                        choices=[("released", "Released for future delivery"), ("withdrawn", "Withdrawn")],
                        max_length=16,
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
                    "publication",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="control_events",
                        to="core.repositorystaticpublication",
                    ),
                ),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.workspace")),
            ],
            options={
                "ordering": ("occurred_at", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(action__in=["released", "withdrawn"]),
                        name="repository_static_control_action_valid",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(reason=""), name="repository_static_control_reason_required"
                    ),
                    models.UniqueConstraint(
                        fields=("publication", "action"), name="repository_static_control_one_action"
                    ),
                ],
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
