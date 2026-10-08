from django.db import migrations


VALIDATOR_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_outbox_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.organization_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_organization organization
    WHERE organization.id=NEW.organization_id AND organization.tenant_id=NEW.tenant_id
  ) THEN RAISE EXCEPTION 'outbox organization tenant mismatch'; END IF;
  IF NEW.organization_id IS NULL
  THEN RAISE EXCEPTION 'outbox topic requires organization scope'; END IF;
  IF NEW.topic IN ('client_invitation.issued', 'client_invitation.accepted') THEN
    IF NEW.payload IS DISTINCT FROM jsonb_build_object('role', NEW.payload->>'role')
       OR NEW.payload->>'role' NOT IN ('client_administrator', 'client_user')
    THEN RAISE EXCEPTION 'outbox payload contract mismatch'; END IF;
  ELSIF NEW.topic IN (__PUBLICATION_TOPICS__) THEN
    IF NEW.payload IS DISTINCT FROM jsonb_build_object('audience', NEW.payload->>'audience')
       OR NEW.payload->>'audience' <> 'client_visible'
    THEN RAISE EXCEPTION 'outbox payload contract mismatch'; END IF;
  ELSE
    RAISE EXCEPTION 'outbox topic is not allowlisted';
  END IF;
  IF NEW.state <> 'pending' OR NEW.attempts <> 0 OR NEW.locked_at IS NOT NULL
     OR NEW.delivered_at IS NOT NULL OR NEW.last_error_code <> ''
  THEN RAISE EXCEPTION 'outbox event must begin pending'; END IF;
  RETURN NEW;
END $$;
"""


OLD_TOPICS = "'document_publication.available', 'document_publication.withdrawn'"
NEW_TOPICS = (
    "'document_publication.available', 'document_publication.withdrawn', "
    "'repository_publication.available', 'repository_publication.access_changed'"
)


class Migration(migrations.Migration):
    dependencies = [("core", "0177_repository_static_delivery_authorization")]
    operations = [
        migrations.RunSQL(
            VALIDATOR_SQL.replace("__PUBLICATION_TOPICS__", NEW_TOPICS),
            VALIDATOR_SQL.replace("__PUBLICATION_TOPICS__", OLD_TOPICS),
        ),
    ]
