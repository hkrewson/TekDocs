from django.db import migrations


POSTGRES_AUDIT_IMMUTABILITY_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_reject_audit_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit events are insert-only' USING ERRCODE = '55000';
END $$;

CREATE TRIGGER core_audit_event_immutable
BEFORE UPDATE OR DELETE ON core_auditevent
FOR EACH ROW EXECUTE FUNCTION tekdocs_reject_audit_event_mutation();

"""


POSTGRES_AUDIT_IMMUTABILITY_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS core_audit_event_immutable ON core_auditevent;
DROP FUNCTION IF EXISTS tekdocs_reject_audit_event_mutation();
"""


def install_audit_immutability(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_AUDIT_IMMUTABILITY_SQL)


def remove_audit_immutability(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(POSTGRES_AUDIT_IMMUTABILITY_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0017_entity_visibility_and_more")]

    operations = [migrations.RunPython(install_audit_immutability, remove_audit_immutability)]
