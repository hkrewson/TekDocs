from django.db import migrations


def refresh_publication_control_validation(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            r"""
            CREATE OR REPLACE FUNCTION tekdocs_validate_publication_control_event() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE publication_row core_documentpublication%ROWTYPE;
            BEGIN
              PERFORM pg_advisory_xact_lock(hashtextextended(
                'publication-control:' || NEW.publication_id::text, 0
              ));
              SELECT * INTO publication_row FROM core_documentpublication
              WHERE id=NEW.publication_id;
              IF NOT FOUND
                 OR publication_row.tenant_id<>NEW.tenant_id
                 OR publication_row.organization_id IS DISTINCT FROM NEW.organization_id
              THEN RAISE EXCEPTION 'publication control event workspace mismatch'; END IF;
              IF btrim(NEW.reason)='' OR length(NEW.reason)>500
              THEN RAISE EXCEPTION 'publication control reason invalid'; END IF;
              IF NEW.actor_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM accounts_tenantmembership membership
                WHERE membership.tenant_id=NEW.tenant_id AND membership.user_id=NEW.actor_id
              ) THEN RAISE EXCEPTION 'publication control actor tenant mismatch'; END IF;
              IF NEW.action IN ('approved', 'withdrawn') AND NEW.actor_id IS NULL
              THEN RAISE EXCEPTION 'publication control decision requires an actor'; END IF;
              IF NEW.action='submitted' AND EXISTS (
                SELECT 1 FROM core_documentpublicationcontrolevent e
                WHERE e.publication_id=NEW.publication_id
              ) THEN RAISE EXCEPTION 'publication was already submitted'; END IF;
              IF NEW.action IN ('approved', 'withdrawn') AND NOT EXISTS (
                SELECT 1 FROM core_documentpublicationcontrolevent e
                WHERE e.publication_id=NEW.publication_id AND e.action='submitted'
              ) THEN RAISE EXCEPTION 'publication must be submitted first'; END IF;
              IF NEW.action='approved' THEN
                IF publication_row.supersedes_id IS NOT NULL THEN
                  PERFORM pg_advisory_xact_lock(hashtextextended(
                    'publication-control:' || publication_row.supersedes_id::text, 0
                  ));
                END IF;
                IF EXISTS (
                  SELECT 1 FROM core_documentpublicationcontrolevent e
                  WHERE e.publication_id=NEW.publication_id AND e.action IN ('approved', 'withdrawn')
                ) THEN RAISE EXCEPTION 'publication approval state conflict'; END IF;
                IF publication_row.audience='client_visible' AND
                   (NEW.actor_id IS NULL OR NEW.actor_id=publication_row.published_by_id)
                THEN RAISE EXCEPTION 'client-visible approval requires a different actor'; END IF;
                IF publication_row.audience='msp_internal' AND
                   (NEW.actor_id IS NULL OR NEW.actor_id IS DISTINCT FROM publication_row.published_by_id)
                THEN RAISE EXCEPTION 'MSP-internal approval must be created by the publisher'; END IF;
                IF publication_row.supersedes_id IS NOT NULL AND EXISTS (
                  SELECT 1 FROM core_documentpublication successor
                  JOIN core_documentpublicationcontrolevent approved
                    ON approved.publication_id=successor.id AND approved.action='approved'
                  WHERE successor.supersedes_id=publication_row.supersedes_id
                    AND successor.id<>publication_row.id
                ) THEN RAISE EXCEPTION 'another correction already superseded this publication'; END IF;
              END IF;
              IF NEW.action='withdrawn' THEN
                IF EXISTS (
                  SELECT 1 FROM core_documentpublicationcontrolevent e
                  WHERE e.publication_id=NEW.publication_id AND e.action='withdrawn'
                ) THEN RAISE EXCEPTION 'publication was already withdrawn'; END IF;
                IF EXISTS (
                  SELECT 1 FROM core_documentpublication successor
                  JOIN core_documentpublicationcontrolevent approved
                    ON approved.publication_id=successor.id AND approved.action='approved'
                  WHERE successor.supersedes_id=publication_row.id
                ) THEN RAISE EXCEPTION 'superseded publication cannot be withdrawn'; END IF;
              END IF;
              RETURN NEW;
            END $$;
            """
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0064_publication_control_guards_and_rls")]
    operations = [
        migrations.RunPython(
            refresh_publication_control_validation,
            refresh_publication_control_validation,
        )
    ]
