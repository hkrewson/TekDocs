import uuid

import django.db.models.deletion
from django.db import migrations, models

WORKSPACE_UUID_NAMESPACE = uuid.UUID("6890dc87-8d91-4f76-a6eb-99dfd06904a5")


def workspace_identity_uuid(*, tenant_id, organization_id):
    owner = "msp" if organization_id is None else f"organization:{organization_id}"
    return uuid.uuid5(WORKSPACE_UUID_NAMESPACE, f"tenant:{tenant_id}:{owner}")


def backfill_workspaces(apps, schema_editor):
    Tenant = apps.get_model("core", "Tenant")
    Organization = apps.get_model("core", "Organization")
    Workspace = apps.get_model("core", "Workspace")
    Entity = apps.get_model("core", "Entity")

    for tenant in Tenant.objects.all().iterator():
        msp_workspace, _ = Workspace.objects.get_or_create(
            id=workspace_identity_uuid(tenant_id=tenant.id, organization_id=None),
            tenant_id=tenant.id,
            kind="msp",
            organization_id=None,
        )
        Entity.objects.filter(tenant_id=tenant.id, organization_id__isnull=True).update(
            workspace_id=msp_workspace.id
        )
        for organization in Organization.objects.filter(tenant_id=tenant.id).iterator():
            workspace, _ = Workspace.objects.get_or_create(
                id=workspace_identity_uuid(tenant_id=tenant.id, organization_id=organization.id),
                tenant_id=tenant.id,
                kind="organization",
                organization_id=organization.id,
            )
            Entity.objects.filter(
                tenant_id=tenant.id,
                organization_id=organization.id,
            ).update(workspace_id=workspace.id)


POSTGRES_OWNERSHIP_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_current_workspace_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(current_setting('tekdocs.workspace_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION tekdocs_validate_workspace_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'workspace ownership identities cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.kind <> OLD.kind
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    ) THEN
        RAISE EXCEPTION 'workspace ownership identity is immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.kind = 'msp' AND NEW.organization_id IS NOT NULL THEN
        RAISE EXCEPTION 'MSP workspace cannot have an organization' USING ERRCODE = '23514';
    END IF;
    IF NEW.kind = 'organization' AND (
        NEW.organization_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM core_organization o
            WHERE o.id = NEW.organization_id AND o.tenant_id = NEW.tenant_id
        )
    ) THEN
        RAISE EXCEPTION 'organization workspace must match its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER core_workspace_identity_guard
BEFORE INSERT OR UPDATE OR DELETE ON core_workspace
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_workspace_identity();

CREATE OR REPLACE FUNCTION tekdocs_validate_entity_organization_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.tenant_id <> OLD.tenant_id OR NEW.workspace_id <> OLD.workspace_id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
    ) THEN
        RAISE EXCEPTION 'entity ownership identity is immutable' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM core_workspace workspace
        WHERE workspace.id = NEW.workspace_id
          AND workspace.tenant_id = NEW.tenant_id
          AND workspace.organization_id IS NOT DISTINCT FROM NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'entity workspace must match its tenant and organization scope' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.entity_id = NEW.id
          AND (organization.tenant_id <> NEW.tenant_id OR NEW.organization_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'organization anchor must remain MSP-scoped in its tenant' USING ERRCODE = '23514';
    END IF;
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM core_organization organization
        WHERE organization.id = NEW.organization_id
          AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'entity organization scope must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS core_entity_organization_scope_guard ON core_entity;
CREATE TRIGGER core_entity_organization_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, workspace_id, organization_id ON core_entity
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_organization_scope();

DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity;
CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
    OR EXISTS (SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id)
);
DROP POLICY IF EXISTS core_entity_runtime_insert ON core_entity;
CREATE POLICY core_entity_runtime_insert ON core_entity FOR INSERT WITH CHECK (
    workspace_id = tekdocs_current_workspace_id() AND (
        tekdocs_scope_matches(tenant_id, organization_id)
        OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
            AND entity_type IN ('organization', 'person'))
    )
);
DROP POLICY IF EXISTS core_entity_runtime_update ON core_entity;
CREATE POLICY core_entity_runtime_update ON core_entity FOR UPDATE USING (
    (workspace_id = tekdocs_current_workspace_id() AND tekdocs_scope_matches(tenant_id, organization_id))
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
) WITH CHECK (
    workspace_id = tekdocs_current_workspace_id() AND (
        tekdocs_scope_matches(tenant_id, organization_id)
        OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
            AND entity_type IN ('organization', 'person'))
    )
);
DROP POLICY IF EXISTS core_entity_runtime_delete ON core_entity;
CREATE POLICY core_entity_runtime_delete ON core_entity FOR DELETE USING (
    workspace_id = tekdocs_current_workspace_id() AND (
        tekdocs_scope_matches(tenant_id, organization_id)
        OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
            AND entity_type IN ('organization', 'person'))
    )
);
"""


def install_postgres_ownership(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_OWNERSHIP_SQL)


POSTGRES_OWNERSHIP_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_workspace_identity_guard ON core_workspace;
DROP FUNCTION IF EXISTS tekdocs_validate_workspace_identity();
DROP TRIGGER IF EXISTS core_entity_organization_scope_guard ON core_entity;
CREATE OR REPLACE FUNCTION tekdocs_validate_entity_organization_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.entity_id = NEW.id
          AND (organization.tenant_id <> NEW.tenant_id OR NEW.organization_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'organization anchor must remain MSP-scoped in its tenant' USING ERRCODE = '23514';
    END IF;
    IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM core_organization organization
        WHERE organization.id = NEW.organization_id AND organization.tenant_id = NEW.tenant_id
    ) THEN
        RAISE EXCEPTION 'entity organization scope must belong to its tenant' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER core_entity_organization_scope_guard
BEFORE INSERT OR UPDATE OF tenant_id, organization_id ON core_entity
FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_entity_organization_scope();

DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity;
CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING (
    tekdocs_scope_matches(tenant_id, organization_id)
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
    OR EXISTS (SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id)
    OR EXISTS (SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id)
);
DROP POLICY IF EXISTS core_entity_runtime_insert ON core_entity;
CREATE POLICY core_entity_runtime_insert ON core_entity FOR INSERT WITH CHECK (
    tekdocs_scope_matches(tenant_id, organization_id)
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
);
DROP POLICY IF EXISTS core_entity_runtime_update ON core_entity;
CREATE POLICY core_entity_runtime_update ON core_entity FOR UPDATE USING (
    tekdocs_scope_matches(tenant_id, organization_id)
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
) WITH CHECK (
    tekdocs_scope_matches(tenant_id, organization_id)
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
);
DROP POLICY IF EXISTS core_entity_runtime_delete ON core_entity;
CREATE POLICY core_entity_runtime_delete ON core_entity FOR DELETE USING (
    tekdocs_scope_matches(tenant_id, organization_id)
    OR (tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL
        AND entity_type IN ('organization', 'person'))
);
DROP FUNCTION IF EXISTS tekdocs_current_workspace_id();
"""


def remove_postgres_ownership(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_OWNERSHIP_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0044_msp_operational_parity")]

    operations = [
        migrations.CreateModel(
            name="Workspace",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("msp", "MSP"), ("organization", "Organization")], max_length=20)),
                (
                    "organization",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ownership_workspace",
                        to="core.organization",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workspaces",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["tenant", "kind"], name="core_workspace_tenant_kind_idx")],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(("kind", "msp"), ("organization__isnull", True))
                            | models.Q(("kind", "organization"), ("organization__isnull", False))
                        ),
                        name="workspace_kind_owner_shape",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("kind", "msp")),
                        fields=("tenant",),
                        name="one_msp_workspace_per_tenant",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="entity",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entities",
                to="core.workspace",
            ),
        ),
        migrations.RunPython(backfill_workspaces, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="entity",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entities",
                to="core.workspace",
            ),
        ),
        migrations.RunPython(install_postgres_ownership, remove_postgres_ownership),
    ]
