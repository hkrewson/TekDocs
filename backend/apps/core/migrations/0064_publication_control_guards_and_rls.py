import uuid
from datetime import timedelta

from django.db import migrations


def backfill_publication_control_events(apps, schema_editor):
    Publication = apps.get_model("core", "DocumentPublication")
    ControlEvent = apps.get_model("core", "DocumentPublicationControlEvent")
    events = []
    for publication in Publication.objects.all().iterator(chunk_size=500):
        events.extend(
            (
                ControlEvent(
                    id=uuid.uuid4(),
                    tenant_id=publication.tenant_id,
                    organization_id=publication.organization_id,
                    publication_id=publication.id,
                    action="submitted",
                    reason=publication.reason,
                    actor_id=publication.published_by_id,
                    occurred_at=publication.published_at,
                ),
                ControlEvent(
                    id=uuid.uuid4(),
                    tenant_id=publication.tenant_id,
                    organization_id=publication.organization_id,
                    publication_id=publication.id,
                    action="approved",
                    reason="Approved before the controlled publication workflow was introduced.",
                    actor_id=publication.published_by_id,
                    occurred_at=publication.published_at + timedelta(microseconds=1),
                ),
            )
        )
        if len(events) >= 1000:
            ControlEvent.objects.bulk_create(events)
            events.clear()
    if events:
        ControlEvent.objects.bulk_create(events)


def remove_backfilled_events(apps, schema_editor):
    apps.get_model("core", "DocumentPublicationControlEvent").objects.all().delete()


def enable_publication_control_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            r"""
            CREATE FUNCTION tekdocs_validate_publication_control_event() RETURNS trigger
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

            CREATE FUNCTION tekdocs_guard_publication_control_immutability() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'publication control events are append-only';
            END $$;

            CREATE TRIGGER core_publication_control_validate
              BEFORE INSERT ON core_documentpublicationcontrolevent
              FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_publication_control_event();
            CREATE TRIGGER core_publication_control_immutable
              BEFORE UPDATE OR DELETE ON core_documentpublicationcontrolevent
              FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_publication_control_immutability();

            ALTER TABLE core_documentpublicationcontrolevent ENABLE ROW LEVEL SECURITY;
            ALTER TABLE core_documentpublicationcontrolevent FORCE ROW LEVEL SECURITY;
            CREATE POLICY core_documentpublicationcontrolevent_runtime_scope
              ON core_documentpublicationcontrolevent
              USING (
                tekdocs_scope_matches(tenant_id, organization_id)
                OR EXISTS (
                  SELECT 1 FROM core_documentpublication publication
                  WHERE publication.id=core_documentpublicationcontrolevent.publication_id
                    AND publication.tenant_id=core_documentpublicationcontrolevent.tenant_id
                )
              )
              WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id));
            """
        )


def disable_publication_control_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            r"""
            DROP POLICY IF EXISTS core_documentpublicationcontrolevent_runtime_scope
              ON core_documentpublicationcontrolevent;
            ALTER TABLE core_documentpublicationcontrolevent DISABLE ROW LEVEL SECURITY;
            DROP TRIGGER IF EXISTS core_publication_control_immutable
              ON core_documentpublicationcontrolevent;
            DROP TRIGGER IF EXISTS core_publication_control_validate
              ON core_documentpublicationcontrolevent;
            DROP FUNCTION IF EXISTS tekdocs_guard_publication_control_immutability();
            DROP FUNCTION IF EXISTS tekdocs_validate_publication_control_event();
            """
        )


class Migration(migrations.Migration):
    # The historical event backfill must commit before PostgreSQL can ALTER the
    # new table for forced RLS; retained publication foreign-key events are
    # deferred until that transaction boundary.
    atomic = False
    dependencies = [("core", "0063_alter_documentpublication_supersedes_and_more")]
    operations = [
        migrations.RunPython(backfill_publication_control_events, remove_backfilled_events),
        migrations.RunPython(enable_publication_control_guards, disable_publication_control_guards),
    ]
