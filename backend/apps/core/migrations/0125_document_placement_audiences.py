from importlib import import_module

from django.db import migrations, models

PRE_AUDIENCE_GUARD = import_module(
    "apps.core.migrations.0112_document_block_library_visibility"
).PLACEMENT_SCOPE_GUARD
PUBLICATION_V3_GUARD = import_module("apps.core.migrations.0124_publication_manifest_v3").PUBLICATION_V3_GUARD


AUDIENCE_GUARD = PRE_AUDIENCE_GUARD.replace(
    "    IF NEW.pinned_revision_id IS NOT NULL AND NOT EXISTS (",
    """    IF NEW.audience_profile NOT IN ('shared', 'msp_internal', 'client_visible')
    THEN RAISE EXCEPTION 'document placement audience profile mismatch'; END IF;
    IF NEW.parent_id IS NULL AND NEW.position = 0 AND NEW.audience_profile <> 'shared'
    THEN RAISE EXCEPTION 'primary document placement must remain shared'; END IF;
    IF NEW.parent_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM core_documentplacement p WHERE p.id = NEW.parent_id
        AND (p.audience_profile = 'shared' OR p.audience_profile = NEW.audience_profile)
    ) THEN RAISE EXCEPTION 'child placement cannot widen parent audience'; END IF;
    IF TG_OP = 'UPDATE' AND NEW.audience_profile IS DISTINCT FROM OLD.audience_profile
       AND NEW.audience_profile <> 'shared' AND EXISTS (
         SELECT 1 FROM core_documentplacement child WHERE child.parent_id = NEW.id
           AND child.audience_profile <> NEW.audience_profile
       )
    THEN RAISE EXCEPTION 'placement audience cannot exclude nested placements'; END IF;
    IF NEW.pinned_revision_id IS NOT NULL AND NOT EXISTS (""",
)

PUBLICATION_V4_GUARD = PUBLICATION_V3_GUARD.replace(
    "NEW.manifest->>'format' <> 'tekdocs-static-publication/v3'",
    "NEW.manifest->>'format' <> 'tekdocs-static-publication/v4'",
).replace(
    "  RETURN NEW;",
    """  IF jsonb_typeof(NEW.manifest->'placements') <> 'array'
     OR jsonb_array_length(NEW.manifest->'placements') = 0
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(NEW.manifest->'placements') placement
       WHERE jsonb_typeof(placement) <> 'object'
          OR jsonb_typeof(placement->'audience_profile') <> 'string'
          OR placement->>'audience_profile' NOT IN ('shared', NEW.audience)
     )
  THEN RAISE EXCEPTION 'publication placement audience metadata is invalid'; END IF;
  RETURN NEW;""",
)


def install_publication_v4_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(PUBLICATION_V4_GUARD)


def restore_publication_v3_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(PUBLICATION_V3_GUARD)


class Migration(migrations.Migration):
    dependencies = [("core", "0124_publication_manifest_v3")]

    operations = [
        migrations.AddField(
            model_name="documentplacement",
            name="audience_profile",
            field=models.CharField(
                choices=[
                    ("shared", "Shared"),
                    ("msp_internal", "MSP internal"),
                    ("client_visible", "Client visible"),
                ],
                default="shared",
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="documentplacement",
            constraint=models.CheckConstraint(
                condition=models.Q(audience_profile__in=("shared", "msp_internal", "client_visible")),
                name="document_placement_audience_profile",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentplacement",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(parent__isnull=False)
                    | ~models.Q(position=0)
                    | models.Q(audience_profile="shared")
                ),
                name="document_primary_placement_shared",
            ),
        ),
        migrations.RunSQL(AUDIENCE_GUARD, PRE_AUDIENCE_GUARD),
        migrations.RunPython(install_publication_v4_guard, restore_publication_v3_guard),
    ]
