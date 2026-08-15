import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_document_remote_source() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE FUNCTION tekdocs_validate_document_remote_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN RAISE EXCEPTION 'remote document observations are immutable'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_documentremotesource source
    WHERE source.id=NEW.source_id AND source.tenant_id=NEW.tenant_id
      AND source.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'remote observation source workspace mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_docsource_validate BEFORE INSERT OR UPDATE ON core_documentremotesource
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_remote_source();
CREATE TRIGGER core_docobservation_validate BEFORE INSERT OR UPDATE OR DELETE ON core_documentremoteobservation
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_remote_observation();

ALTER TABLE core_documentremotesource ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documentremotesource FORCE ROW LEVEL SECURITY;
CREATE POLICY core_documentremotesource_runtime_scope ON core_documentremotesource
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
ALTER TABLE core_documentremoteobservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documentremoteobservation FORCE ROW LEVEL SECURITY;
CREATE POLICY core_documentremoteobservation_runtime_scope ON core_documentremoteobservation
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_documentremoteobservation_runtime_scope ON core_documentremoteobservation;
ALTER TABLE core_documentremoteobservation DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_documentremotesource_runtime_scope ON core_documentremotesource;
ALTER TABLE core_documentremotesource DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_docobservation_validate ON core_documentremoteobservation;
DROP TRIGGER IF EXISTS core_docsource_validate ON core_documentremotesource;
DROP FUNCTION IF EXISTS tekdocs_validate_document_remote_observation();
DROP FUNCTION IF EXISTS tekdocs_validate_document_remote_source();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0113_versioned_client_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentRemoteObservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "state",
                    models.CharField(
                        choices=[("unchanged", "Unchanged"), ("changed", "Changed"), ("failed", "Failed")],
                        max_length=16,
                    ),
                ),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("etag_digest", models.CharField(blank=True, max_length=64)),
                ("last_modified_digest", models.CharField(blank=True, max_length=64)),
                ("content_digest", models.CharField(blank=True, max_length=64)),
                ("canonical_markdown", models.TextField(blank=True)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_remote_observations",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_remote_observations",
                        to="core.tenant",
                    ),
                ),
            ],
            options={"ordering": ("-fetched_at", "id")},
        ),
        migrations.CreateModel(
            name="DocumentRemoteSource",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("url", models.URLField(max_length=500)),
                (
                    "source_kind",
                    models.CharField(
                        choices=[("markdown", "Markdown"), ("html", "HTML"), ("auto", "Automatic")],
                        default="auto",
                        max_length=12,
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("check_interval_minutes", models.PositiveIntegerField(default=1440)),
                ("next_check_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_remote_sources",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT, related_name="remote_source", to="core.document"
                    ),
                ),
                (
                    "last_applied_observation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="applied_to_sources",
                        to="core.documentremoteobservation",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_remote_sources",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_remote_sources",
                        to="core.tenant",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="documentremoteobservation",
            name="source",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="core.documentremotesource"
            ),
        ),
        migrations.AddIndex(
            model_name="documentremotesource",
            index=models.Index(
                fields=["tenant", "organization", "enabled", "next_check_at"], name="core_docsource_due_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="documentremotesource",
            constraint=models.CheckConstraint(
                condition=models.Q(("check_interval_minutes__gte", 15), ("check_interval_minutes__lte", 10080)),
                name="document_source_interval_bounded",
            ),
        ),
        migrations.AddIndex(
            model_name="documentremoteobservation",
            index=models.Index(fields=["source", "fetched_at"], name="core_docobservation_idx"),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
