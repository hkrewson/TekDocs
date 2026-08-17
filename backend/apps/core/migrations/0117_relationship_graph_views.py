import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_relationship_graph_view() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'relationship graph view workspace mismatch'; END IF;
  IF NEW.root_entity_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.root_entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.workspace_id=NEW.workspace_id
  ) THEN RAISE EXCEPTION 'relationship graph root workspace mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_relationship_graph_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN RAISE EXCEPTION 'relationship graph snapshots are immutable'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_relationshipgraphview graph_view
    WHERE graph_view.id=NEW.view_id AND graph_view.tenant_id=NEW.tenant_id
      AND graph_view.workspace_id=NEW.workspace_id
      AND graph_view.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'relationship graph snapshot workspace mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_graphview_validate BEFORE INSERT OR UPDATE ON core_relationshipgraphview
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_relationship_graph_view();
CREATE TRIGGER core_graphsnapshot_validate BEFORE INSERT OR UPDATE OR DELETE ON core_relationshipgraphsnapshot
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_relationship_graph_snapshot();

ALTER TABLE core_relationshipgraphview ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_relationshipgraphview FORCE ROW LEVEL SECURITY;
CREATE POLICY core_relationshipgraphview_runtime_scope ON core_relationshipgraphview
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
ALTER TABLE core_relationshipgraphsnapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_relationshipgraphsnapshot FORCE ROW LEVEL SECURITY;
CREATE POLICY core_relationshipgraphsnapshot_runtime_scope ON core_relationshipgraphsnapshot
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_relationshipgraphsnapshot_runtime_scope ON core_relationshipgraphsnapshot;
ALTER TABLE core_relationshipgraphsnapshot DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_relationshipgraphview_runtime_scope ON core_relationshipgraphview;
ALTER TABLE core_relationshipgraphview DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_graphsnapshot_validate ON core_relationshipgraphsnapshot;
DROP TRIGGER IF EXISTS core_graphview_validate ON core_relationshipgraphview;
DROP FUNCTION IF EXISTS tekdocs_validate_relationship_graph_snapshot();
DROP FUNCTION IF EXISTS tekdocs_validate_relationship_graph_view();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0116_remove_documentpublicationartifact_publication_artifact_kind_valid_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="RelationshipGraphView",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("family", models.CharField(choices=[("network", "Network"), ("asset", "Asset"), ("document", "Document")], max_length=16)),
                ("depth", models.PositiveSmallIntegerField(default=2)),
                ("edge_limit", models.PositiveSmallIntegerField(default=100)),
                ("positions", models.JSONField(blank=True, default=dict)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_relationship_graph_views", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_views", to="core.organization")),
                ("root_entity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_views", to="core.entity")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_views", to="core.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_views", to="core.workspace")),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.CreateModel(
            name="RelationshipGraphSnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("graph", models.JSONField()),
                ("content_digest", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_relationship_graph_snapshots", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_snapshots", to="core.organization")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_snapshots", to="core.tenant")),
                ("view", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="snapshots", to="core.relationshipgraphview")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="relationship_graph_snapshots", to="core.workspace")),
            ],
            options={"ordering": ("-created_at", "id")},
        ),
        migrations.AddConstraint(model_name="relationshipgraphview", constraint=models.CheckConstraint(condition=models.Q(family__in=("network", "asset", "document")), name="graph_view_family_valid")),
        migrations.AddConstraint(model_name="relationshipgraphview", constraint=models.CheckConstraint(condition=models.Q(depth__gte=1, depth__lte=3), name="graph_view_depth_bounded")),
        migrations.AddConstraint(model_name="relationshipgraphview", constraint=models.CheckConstraint(condition=models.Q(edge_limit__gte=1, edge_limit__lte=200), name="graph_view_limit_bounded")),
        migrations.AddConstraint(model_name="relationshipgraphview", constraint=models.UniqueConstraint(condition=models.Q(archived_at__isnull=True), fields=("workspace", "name"), name="graph_view_workspace_name_unique")),
        migrations.AddIndex(model_name="relationshipgraphsnapshot", index=models.Index(fields=["view", "created_at"], name="core_graphsnapshot_idx")),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
