import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


FORWARD_SQL = r"""
CREATE FUNCTION tekdocs_validate_template_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_document template
    WHERE template.id=NEW.template_id AND template.tenant_id=NEW.tenant_id
      AND template.organization_id IS NULL AND template.is_template=TRUE
  ) THEN RAISE EXCEPTION 'template revision source mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) THEN RAISE EXCEPTION 'template revision creator mismatch'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_validate_template_enrollment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'template enrollment organization mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_document source
    WHERE source.id=NEW.source_template_id AND source.tenant_id=NEW.tenant_id
      AND source.organization_id IS NULL AND source.is_template=TRUE AND source.archived_at IS NULL
  ) THEN RAISE EXCEPTION 'template enrollment source mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_document destination
    WHERE destination.id=NEW.destination_document_id AND destination.tenant_id=NEW.tenant_id
      AND destination.organization_id=NEW.organization_id AND destination.archived_at IS NULL
  ) THEN RAISE EXCEPTION 'template enrollment destination mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_documenttemplaterevision revision
    WHERE revision.id=NEW.applied_revision_id AND revision.tenant_id=NEW.tenant_id
      AND revision.template_id=NEW.source_template_id
  ) THEN RAISE EXCEPTION 'template enrollment revision mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.created_by_id
  ) OR NOT EXISTS (
    SELECT 1 FROM accounts_tenantmembership membership
    WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.last_applied_by_id
  ) THEN RAISE EXCEPTION 'template enrollment actor mismatch'; END IF;
  IF TG_OP='UPDATE' AND (
    OLD.tenant_id, OLD.organization_id, OLD.source_template_id,
    OLD.destination_document_id, OLD.created_by_id
  ) IS DISTINCT FROM (
    NEW.tenant_id, NEW.organization_id, NEW.source_template_id,
    NEW.destination_document_id, NEW.created_by_id
  ) THEN RAISE EXCEPTION 'template enrollment identity is immutable'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tekdocs_guard_template_revision_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'template revisions are immutable'; END $$;

CREATE TRIGGER core_tplrev_validate BEFORE INSERT ON core_documenttemplaterevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_template_revision();
CREATE TRIGGER core_tplrev_immutable BEFORE UPDATE OR DELETE ON core_documenttemplaterevision
  FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_template_revision_immutable();
CREATE TRIGGER core_tplenroll_validate BEFORE INSERT OR UPDATE ON core_documenttemplateenrollment
  FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_template_enrollment();

ALTER TABLE core_documenttemplaterevision ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documenttemplaterevision FORCE ROW LEVEL SECURITY;
CREATE POLICY core_document_template_library_select ON core_document FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND is_template=TRUE AND library_visible=TRUE AND archived_at IS NULL
);
CREATE POLICY core_block_template_library_select ON core_block FOR SELECT
USING (
  tenant_id=tekdocs_current_tenant_id() AND organization_id IS NULL
  AND library_visible=TRUE AND EXISTS (
    SELECT 1 FROM core_document template
    WHERE template.id=core_block.source_document_id
      AND template.tenant_id=core_block.tenant_id
      AND template.organization_id IS NULL AND template.is_template=TRUE
      AND template.library_visible=TRUE AND template.archived_at IS NULL
  )
);
CREATE POLICY core_documenttemplaterevision_runtime_scope ON core_documenttemplaterevision
USING (
  tenant_id=tekdocs_current_tenant_id() AND (
    tekdocs_scope_matches(tenant_id, NULL) OR EXISTS (
      SELECT 1 FROM core_document template
      WHERE template.id=core_documenttemplaterevision.template_id
        AND template.tenant_id=core_documenttemplaterevision.tenant_id
        AND template.organization_id IS NULL AND template.is_template=TRUE
        AND template.library_visible=TRUE AND template.archived_at IS NULL
    )
  )
)
WITH CHECK (
  tenant_id=tekdocs_current_tenant_id() AND (
    tekdocs_scope_matches(tenant_id, NULL) OR EXISTS (
      SELECT 1 FROM core_document template
      WHERE template.id=core_documenttemplaterevision.template_id
        AND template.tenant_id=core_documenttemplaterevision.tenant_id
        AND template.organization_id IS NULL AND template.is_template=TRUE
        AND template.library_visible=TRUE AND template.archived_at IS NULL
    )
  )
);

ALTER TABLE core_documenttemplateenrollment ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_documenttemplateenrollment FORCE ROW LEVEL SECURITY;
CREATE POLICY core_documenttemplateenrollment_runtime_scope ON core_documenttemplateenrollment
USING (tekdocs_scope_matches(tenant_id, organization_id))
WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
"""


REVERSE_SQL = r"""
DROP POLICY IF EXISTS core_documenttemplateenrollment_runtime_scope ON core_documenttemplateenrollment;
ALTER TABLE core_documenttemplateenrollment DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_documenttemplaterevision_runtime_scope ON core_documenttemplaterevision;
ALTER TABLE core_documenttemplaterevision DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS core_block_template_library_select ON core_block;
DROP POLICY IF EXISTS core_document_template_library_select ON core_document;
DROP TRIGGER IF EXISTS core_tplenroll_validate ON core_documenttemplateenrollment;
DROP TRIGGER IF EXISTS core_tplrev_immutable ON core_documenttemplaterevision;
DROP TRIGGER IF EXISTS core_tplrev_validate ON core_documenttemplaterevision;
DROP FUNCTION IF EXISTS tekdocs_guard_template_revision_immutable();
DROP FUNCTION IF EXISTS tekdocs_validate_template_enrollment();
DROP FUNCTION IF EXISTS tekdocs_validate_template_revision();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0112_document_block_library_visibility"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentTemplateRevision",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("revision_number", models.PositiveIntegerField()),
                ("manifest", models.JSONField(default=dict)),
                ("checksum", models.CharField(max_length=64)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_template_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="template_revisions",
                        to="core.document",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_template_revisions",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ("template_id", "revision_number"),
                "indexes": [
                    models.Index(
                        fields=["tenant", "template", "revision_number"], name="core_tplrev_lookup_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("template", "revision_number"), name="unique_template_revision_number"
                    ),
                    models.UniqueConstraint(
                        fields=("template", "checksum"), name="unique_template_revision_checksum"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DocumentTemplateEnrollment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("placement_map", models.JSONField(default=list)),
                ("last_applied_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "applied_revision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="enrollments",
                        to="core.documenttemplaterevision",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_template_enrollments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "destination_document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="template_enrollment",
                        to="core.document",
                    ),
                ),
                (
                    "last_applied_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="applied_document_template_enrollments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_template_enrollments",
                        to="core.organization",
                    ),
                ),
                (
                    "source_template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="template_enrollments",
                        to="core.document",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_template_enrollments",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["tenant", "organization", "source_template", "archived_at"],
                        name="core_tplenroll_scope_idx",
                    )
                ]
            },
        ),
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
