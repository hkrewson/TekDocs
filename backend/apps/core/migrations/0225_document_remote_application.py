import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_document_remote_application() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN RAISE EXCEPTION 'remote document applications are immutable'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_documentremoteobservation observation
    WHERE observation.id=NEW.observation_id AND observation.source_id=NEW.source_id
      AND observation.tenant_id=NEW.tenant_id
      AND observation.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'remote application observation scope mismatch'; END IF;
  IF current_user='tekdocs_runtime' AND NEW.actor_id IS DISTINCT FROM
    NULLIF(current_setting('tekdocs.user_id', true), '')::uuid
  THEN RAISE EXCEPTION 'remote application actor mismatch'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_docapplication_validate
BEFORE INSERT OR UPDATE OR DELETE ON core_documentremoteapplication
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_remote_application();
ALTER TABLE core_documentremoteapplication ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documentremoteapplication FORCE ROW LEVEL SECURITY;
CREATE POLICY core_documentremoteapplication_runtime_scope ON core_documentremoteapplication
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM core_documentremoteapplication) THEN
    RAISE EXCEPTION 'remote source application history prevents schema rollback';
  END IF;
END $$;
DROP POLICY IF EXISTS core_documentremoteapplication_runtime_scope ON core_documentremoteapplication;
ALTER TABLE core_documentremoteapplication DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_docapplication_validate ON core_documentremoteapplication;
DROP FUNCTION IF EXISTS tekdocs_validate_document_remote_application();
"""


def retain_existing_applications(apps, schema_editor):
    Source = apps.get_model("core", "DocumentRemoteSource")
    Observation = apps.get_model("core", "DocumentRemoteObservation")
    Application = apps.get_model("core", "DocumentRemoteApplication")
    AuditEvent = apps.get_model("core", "AuditEvent")
    for event in AuditEvent.objects.filter(action="document.remote_source_applied").iterator():
        observation_id = event.metadata.get("observation_id") if isinstance(event.metadata, dict) else None
        observation = Observation.objects.filter(pk=observation_id).select_related("source").first()
        if observation is None:
            continue
        application, _ = Application.objects.get_or_create(
            observation_id=observation.id,
            defaults={
                "tenant_id": observation.tenant_id, "organization_id": observation.organization_id,
                "source_id": observation.source_id, "actor_id": event.actor_id,
            },
        )
        Application.objects.filter(pk=application.pk).update(applied_at=event.occurred_at)
    for source in Source.objects.exclude(last_applied_observation_id=None).iterator():
        application, _ = Application.objects.get_or_create(
            observation_id=source.last_applied_observation_id,
            defaults={
                "tenant_id": source.tenant_id, "organization_id": source.organization_id,
                "source_id": source.id, "actor_id": None,
            },
        )
        Application.objects.filter(pk=application.pk).update(applied_at=source.updated_at)


class Migration(migrations.Migration):
    dependencies = [("core", "0224_integration_observation_projection_fingerprint")]

    operations = [
        migrations.CreateModel(
            name="DocumentRemoteApplication",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="document_remote_applications",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("organization", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="document_remote_applications", to="core.organization",
                )),
                ("observation", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="application",
                    to="core.documentremoteobservation",
                )),
                ("source", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="applications", to="core.documentremotesource",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="document_remote_applications", to="core.tenant",
                )),
            ],
        ),
        migrations.RunPython(retain_existing_applications, migrations.RunPython.noop),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
