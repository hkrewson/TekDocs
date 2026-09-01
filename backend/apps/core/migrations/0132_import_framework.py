import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_import_batch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'import batch workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) THEN RAISE EXCEPTION 'import batch creator scope mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_import_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_importbatch batch
    WHERE batch.id=NEW.batch_id AND batch.tenant_id=NEW.tenant_id
      AND batch.workspace_id=NEW.workspace_id
      AND batch.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'import row batch scope mismatch'; END IF;
  IF NEW.local_entity_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.local_entity_id AND entity.tenant_id=NEW.tenant_id
      AND (
        (NEW.record_type='people' AND entity.entity_type='person' AND entity.organization_id IS NULL)
        OR (entity.workspace_id=NEW.workspace_id AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id)
      )
  ) THEN RAISE EXCEPTION 'import row entity scope mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_import_external_key() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_workspace workspace
    WHERE workspace.id=NEW.workspace_id AND workspace.tenant_id=NEW.tenant_id
      AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
  ) THEN RAISE EXCEPTION 'import key workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity entity
    WHERE entity.id=NEW.local_entity_id AND entity.tenant_id=NEW.tenant_id
      AND (
        (NEW.record_type='people' AND entity.entity_type='person' AND entity.organization_id IS NULL)
        OR (entity.workspace_id=NEW.workspace_id AND entity.organization_id IS NOT DISTINCT FROM NEW.organization_id)
      )
  ) THEN RAISE EXCEPTION 'import key entity scope mismatch'; END IF;
  IF TG_OP='UPDATE' AND (
    NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
    NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR
    NEW.organization_id IS DISTINCT FROM OLD.organization_id OR
    NEW.source_system IS DISTINCT FROM OLD.source_system OR
    NEW.record_type IS DISTINCT FROM OLD.record_type OR
    NEW.external_key IS DISTINCT FROM OLD.external_key OR
    NEW.local_entity_id IS DISTINCT FROM OLD.local_entity_id
  ) THEN RAISE EXCEPTION 'import key identity is immutable'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER core_importbatch_validate BEFORE INSERT OR UPDATE ON core_importbatch
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_import_batch();
CREATE TRIGGER core_importrow_validate BEFORE INSERT OR UPDATE ON core_importrow
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_import_row();
CREATE TRIGGER core_importkey_validate BEFORE INSERT OR UPDATE ON core_importexternalkey
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_import_external_key();

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_importbatch', 'core_importrow', 'core_importexternalkey'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I_runtime_scope ON %I '
      'USING (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id)) '
      'WITH CHECK (workspace_id=tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))',
      table_name, table_name);
  END LOOP;
END $$;
"""

REVERSE_SQL = r"""
DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['core_importbatch', 'core_importrow', 'core_importexternalkey'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_runtime_scope ON %I', table_name, table_name);
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS core_importkey_validate ON core_importexternalkey;
DROP TRIGGER IF EXISTS core_importrow_validate ON core_importrow;
DROP TRIGGER IF EXISTS core_importbatch_validate ON core_importbatch;
DROP FUNCTION IF EXISTS tekdocs_validate_import_external_key();
DROP FUNCTION IF EXISTS tekdocs_validate_import_row();
DROP FUNCTION IF EXISTS tekdocs_validate_import_batch();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0131_flexible_invoice_numbering"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_format", models.CharField(max_length=32)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("source_filename", models.CharField(max_length=240)),
                ("source_digest", models.CharField(max_length=64)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("preview_ready", "Preview ready"),
                            ("applying", "Applying"),
                            ("applied", "Applied"),
                            ("cancelled", "Cancelled"),
                            ("failed", "Failed"),
                        ],
                        default="preview_ready",
                        max_length=20,
                    ),
                ),
                ("result_counts", models.JSONField(default=dict)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_import_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_batches",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="import_batches", to="core.tenant"
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="import_batches", to="core.workspace"
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "id")},
        ),
        migrations.CreateModel(
            name="ImportRow",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("row_number", models.PositiveIntegerField()),
                ("record_type", models.CharField(max_length=40)),
                ("external_key", models.CharField(max_length=160)),
                ("fingerprint", models.CharField(max_length=64)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "Create"),
                            ("update", "Update"),
                            ("unchanged", "Unchanged"),
                            ("conflict", "Conflict"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=16,
                    ),
                ),
                ("reason_code", models.CharField(blank=True, max_length=64)),
                ("normalized_data", models.JSONField(default=dict)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="rows", to="core.importbatch"
                    ),
                ),
                (
                    "local_entity",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_rows",
                        to="core.entity",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_rows",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="import_rows", to="core.tenant"
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="import_rows", to="core.workspace"
                    ),
                ),
            ],
            options={"ordering": ("row_number", "id")},
        ),
        migrations.CreateModel(
            name="ImportExternalKey",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_system", models.CharField(max_length=32)),
                ("record_type", models.CharField(max_length=40)),
                ("external_key", models.CharField(max_length=160)),
                ("last_fingerprint", models.CharField(max_length=64)),
                (
                    "local_entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_external_keys",
                        to="core.entity",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_external_keys",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_external_keys",
                        to="core.tenant",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_external_keys",
                        to="core.workspace",
                    ),
                ),
            ],
            options={"ordering": ("source_system", "record_type", "external_key", "id")},
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                condition=models.Q(state__in=["preview_ready", "applying", "applied", "cancelled", "failed"]),
                name="import_batch_state_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(condition=models.Q(schema_version=1), name="import_batch_schema_v1"),
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.CheckConstraint(
                condition=models.Q(source_digest__regex="^[0-9a-f]{64}$"), name="import_batch_digest_valid"
            ),
        ),
        migrations.AddIndex(
            model_name="importbatch",
            index=models.Index(fields=["workspace", "created_at"], name="core_importbatch_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.UniqueConstraint(fields=("batch", "row_number"), name="import_row_number_unique"),
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.CheckConstraint(
                condition=models.Q(action__in=["create", "update", "unchanged", "conflict", "rejected"]),
                name="import_row_action_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.CheckConstraint(
                condition=models.Q(fingerprint__regex="^[0-9a-f]{64}$"), name="import_row_digest_valid"
            ),
        ),
        migrations.AddIndex(
            model_name="importrow",
            index=models.Index(fields=["workspace", "batch", "action"], name="core_importrow_scope_idx"),
        ),
        migrations.AddConstraint(
            model_name="importexternalkey",
            constraint=models.UniqueConstraint(
                fields=("workspace", "source_system", "record_type", "external_key"), name="import_external_key_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="importexternalkey",
            constraint=models.CheckConstraint(
                condition=models.Q(last_fingerprint__regex="^[0-9a-f]{64}$"), name="import_external_key_digest_valid"
            ),
        ),
        migrations.AddIndex(
            model_name="importexternalkey",
            index=models.Index(fields=["workspace", "source_system", "record_type"], name="core_importkey_scope_idx"),
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
