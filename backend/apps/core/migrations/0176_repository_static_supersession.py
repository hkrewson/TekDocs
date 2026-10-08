import django.db.models.deletion
from django.db import migrations, models


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_static_control() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_content uuid;
DECLARE source_audience text;
DECLARE source_creator uuid;
DECLARE active_count integer;
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
  IF source_content IS NULL THEN
    RAISE EXCEPTION 'repository STATIC control scope mismatch' USING ERRCODE='23514';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'repository-static-content:' || NEW.workspace_id::text || ':' || source_content::text, 0
  ));
  IF NEW.action='released' THEN
    IF NEW.actor_id=source_creator OR NEW.publication_id=NEW.supersedes_id THEN
      RAISE EXCEPTION 'invalid repository STATIC release actor or predecessor' USING ERRCODE='23514';
    END IF;
    IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM core_repositorystaticpublication predecessor
      JOIN core_repositorypackageauthorization predecessor_authz ON predecessor_authz.id=predecessor.authorization_id
      JOIN core_repositorypublicationpackage predecessor_package ON predecessor_package.id=predecessor_authz.package_id
      JOIN core_repositoryevidencereviewdecision predecessor_decision
        ON predecessor_decision.id=predecessor_package.decision_id
      JOIN core_repositorypublicationevidence predecessor_evidence
        ON predecessor_evidence.id=predecessor_decision.evidence_id
      WHERE predecessor.id=NEW.supersedes_id AND predecessor.tenant_id=NEW.tenant_id
        AND predecessor.organization_id=NEW.organization_id AND predecessor.workspace_id=NEW.workspace_id
        AND predecessor_evidence.content_id=source_content
        AND predecessor_evidence.audience=source_audience
    ) THEN
      RAISE EXCEPTION 'repository STATIC predecessor scope mismatch' USING ERRCODE='23514';
    END IF;
    SELECT count(*) INTO active_count
    FROM core_repositorystaticpublicationcontrolevent active
    JOIN core_repositorystaticpublication current_pub ON current_pub.id=active.publication_id
    JOIN core_repositorypackageauthorization current_authz ON current_authz.id=current_pub.authorization_id
    JOIN core_repositorypublicationpackage current_package ON current_package.id=current_authz.package_id
    JOIN core_repositoryevidencereviewdecision current_decision ON current_decision.id=current_package.decision_id
    JOIN core_repositorypublicationevidence current_evidence ON current_evidence.id=current_decision.evidence_id
    WHERE active.action='released' AND current_pub.workspace_id=NEW.workspace_id
      AND current_evidence.content_id=source_content
      AND NOT EXISTS (
        SELECT 1 FROM core_repositorystaticpublicationcontrolevent withdrawal
        WHERE withdrawal.publication_id=current_pub.id AND withdrawal.action='withdrawn'
      )
      AND NOT EXISTS (
        SELECT 1 FROM core_repositorystaticpublicationcontrolevent successor
        WHERE successor.supersedes_id=current_pub.id AND successor.action='released'
      );
    IF (NEW.supersedes_id IS NULL AND active_count <> 0)
       OR (NEW.supersedes_id IS NOT NULL AND (
         active_count <> 1 OR NOT EXISTS (
           SELECT 1 FROM core_repositorystaticpublicationcontrolevent predecessor_release
           WHERE predecessor_release.publication_id=NEW.supersedes_id AND predecessor_release.action='released'
             AND NOT EXISTS (
               SELECT 1 FROM core_repositorystaticpublicationcontrolevent withdrawal
               WHERE withdrawal.publication_id=NEW.supersedes_id AND withdrawal.action='withdrawn'
             )
             AND NOT EXISTS (
               SELECT 1 FROM core_repositorystaticpublicationcontrolevent successor
               WHERE successor.supersedes_id=NEW.supersedes_id AND successor.action='released'
             )
         )
       )) THEN
      RAISE EXCEPTION 'supersession must name the current active release' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.action='withdrawn' THEN
    IF NEW.supersedes_id IS NOT NULL OR NOT EXISTS (
      SELECT 1 FROM core_repositorystaticpublicationcontrolevent release_event
      WHERE release_event.publication_id=NEW.publication_id AND release_event.action='released'
    ) OR EXISTS (
      SELECT 1 FROM core_repositorystaticpublicationcontrolevent successor
      WHERE successor.supersedes_id=NEW.publication_id AND successor.action='released'
    ) THEN
      RAISE EXCEPTION 'only an active release can be withdrawn' USING ERRCODE='23514';
    END IF;
  ELSE
    RAISE EXCEPTION 'invalid repository STATIC control action' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""

# Roll back the validator before removing the supersedes column.
REVERSE_SQL = """
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_static_control() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_content uuid;
DECLARE source_creator uuid;
BEGIN
  SELECT evidence.content_id, publication.created_by_id INTO source_content, source_creator
  FROM core_repositorystaticpublication publication
  JOIN core_repositorypackageauthorization authz ON authz.id=publication.authorization_id
  JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
  JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
  JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
  WHERE publication.id=NEW.publication_id AND publication.tenant_id=NEW.tenant_id
    AND publication.organization_id=NEW.organization_id AND publication.workspace_id=NEW.workspace_id;
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
      JOIN core_repositoryevidencereviewdecision current_decision ON current_decision.id=current_package.decision_id
      JOIN core_repositorypublicationevidence current_evidence ON current_evidence.id=current_decision.evidence_id
      WHERE active.action='released' AND current_pub.workspace_id=NEW.workspace_id
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
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0175_repository_static_controls")]

    operations = [
        migrations.AddField(
            model_name="repositorystaticpublicationcontrolevent",
            name="supersedes",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="supersession_event", to="core.repositorystaticpublication",
            ),
        ),
        migrations.AddConstraint(
            model_name="repositorystaticpublicationcontrolevent",
            constraint=models.CheckConstraint(
                condition=models.Q(action="released") | models.Q(supersedes__isnull=True),
                name="repository_static_control_supersedes_on_release",
            ),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
