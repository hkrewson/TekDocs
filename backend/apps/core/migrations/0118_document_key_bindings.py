import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_document_key_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'document key binding workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_document document
    WHERE document.id=NEW.document_id AND document.tenant_id=NEW.tenant_id
      AND document.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'document key binding document scope mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.target_entity_id AND entity.tenant_id=NEW.tenant_id
      AND entity.workspace_id=NEW.workspace_id
  ) THEN RAISE EXCEPTION 'document key binding target workspace mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_documentkeybinding_validate BEFORE INSERT OR UPDATE ON core_documentkeybinding
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_document_key_binding();

ALTER TABLE core_documentkeybinding ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documentkeybinding FORCE ROW LEVEL SECURITY;
CREATE POLICY core_documentkeybinding_runtime_scope ON core_documentkeybinding
USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id));
"""

REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_documentkeybinding_runtime_scope ON core_documentkeybinding;
ALTER TABLE core_documentkeybinding DISABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS core_documentkeybinding_validate ON core_documentkeybinding;
DROP FUNCTION IF EXISTS tekdocs_validate_document_key_binding();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0117_relationship_graph_views"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentKeyBinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=40)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_key_bindings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="key_bindings",
                        to="core.document",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_key_bindings",
                        to="core.organization",
                    ),
                ),
                (
                    "target_entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_key_bindings",
                        to="core.entity",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_key_bindings",
                        to="core.tenant",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_key_bindings",
                        to="core.workspace",
                    ),
                ),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.AddConstraint(
            model_name="documentkeybinding",
            constraint=models.CheckConstraint(
                condition=models.Q(name__regex="^[a-z][a-z0-9_]{0,39}$"),
                name="document_key_binding_name_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentkeybinding",
            constraint=models.UniqueConstraint(fields=("document", "name"), name="document_key_binding_name_unique"),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
