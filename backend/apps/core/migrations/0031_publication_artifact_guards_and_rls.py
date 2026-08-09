from django.db import migrations


PUBLICATION_V1_GUARD = """
CREATE OR REPLACE FUNCTION tekdocs_validate_document_publication() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_document d
    WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
      AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND NEW.manifest->>'source_document_id' = d.entity_id::text
  ) THEN RAISE EXCEPTION 'publication document workspace mismatch'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM core_entity e
    WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
      AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND e.entity_type = 'document_publication'
  ) THEN RAISE EXCEPTION 'publication entity workspace mismatch'; END IF;
  IF NEW.content_digest !~ '^[0-9a-f]{64}$'
     OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
     OR NEW.signature_algorithm <> 'Ed25519'
     OR jsonb_typeof(NEW.manifest) <> 'object'
     OR NEW.manifest->>'format' <> 'tekdocs-static-publication/v1'
     OR NEW.manifest->>'publication_id' <> NEW.id::text
     OR NEW.manifest->>'publication_entity_id' <> NEW.entity_id::text
  THEN RAISE EXCEPTION 'publication integrity metadata is invalid'; END IF;
  IF NOT (
    (NEW.organization_id IS NULL AND NEW.manifest->'workspace'->>'kind' = 'msp'
      AND NEW.manifest->'workspace'->>'id' IS NULL)
    OR EXISTS (
      SELECT 1 FROM core_organization o WHERE o.id = NEW.organization_id
        AND NEW.manifest->'workspace'->>'kind' = 'organization'
        AND NEW.manifest->'workspace'->>'id' = o.entity_id::text)
  ) THEN RAISE EXCEPTION 'publication manifest workspace mismatch'; END IF;
  RETURN NEW;
END $$
"""


def enable_publication_artifact_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION tekdocs_validate_document_publication() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_document d
                WHERE d.id = NEW.document_id AND d.tenant_id = NEW.tenant_id
                  AND d.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND NEW.manifest->>'source_document_id' = d.entity_id::text
              ) THEN RAISE EXCEPTION 'publication document workspace mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND e.entity_type = 'document_publication'
              ) THEN RAISE EXCEPTION 'publication entity workspace mismatch'; END IF;
              IF NEW.content_digest !~ '^[0-9a-f]{64}$'
                 OR NEW.key_fingerprint !~ '^[0-9a-f]{64}$'
                 OR NEW.signature_algorithm <> 'Ed25519'
                 OR jsonb_typeof(NEW.manifest) <> 'object'
                 OR NEW.manifest->>'format' <> 'tekdocs-static-publication/v2'
                 OR NEW.manifest->>'publication_id' <> NEW.id::text
                 OR NEW.manifest->>'publication_entity_id' <> NEW.entity_id::text
                 OR NEW.manifest->>'reason' <> NEW.reason
                 OR NEW.manifest->>'audience' <> NEW.audience
                 OR NEW.manifest->>'retention' <> NEW.retention
                 OR (NEW.manifest->>'retention_review_on') IS DISTINCT FROM
                    (CASE WHEN NEW.retention_review_on IS NULL THEN NULL ELSE NEW.retention_review_on::text END)
                 OR (NEW.manifest->>'supersedes_id') IS DISTINCT FROM
                    (CASE WHEN NEW.supersedes_id IS NULL THEN NULL ELSE
                      (SELECT prior.entity_id::text FROM core_documentpublication prior
                       WHERE prior.id = NEW.supersedes_id) END)
                 OR jsonb_typeof(NEW.manifest->'artifacts') <> 'array'
              THEN RAISE EXCEPTION 'publication integrity metadata is invalid'; END IF;
              IF NOT (
                (NEW.organization_id IS NULL AND NEW.manifest->'workspace'->>'kind' = 'msp'
                  AND NEW.manifest->'workspace'->>'id' IS NULL)
                OR EXISTS (
                  SELECT 1 FROM core_organization o WHERE o.id = NEW.organization_id
                    AND NEW.manifest->'workspace'->>'kind' = 'organization'
                    AND NEW.manifest->'workspace'->>'id' = o.entity_id::text)
              ) THEN RAISE EXCEPTION 'publication manifest workspace mismatch'; END IF;
              IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_documentpublication prior
                WHERE prior.id = NEW.supersedes_id AND prior.tenant_id = NEW.tenant_id
                  AND prior.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND prior.document_id = NEW.document_id
              ) THEN RAISE EXCEPTION 'publication supersession mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_publication_artifact() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM core_documentpublication p
                WHERE p.id = NEW.publication_id AND p.tenant_id = NEW.tenant_id
                  AND p.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'publication artifact workspace mismatch'; END IF;
              IF NOT EXISTS (
                SELECT 1 FROM core_entity e
                WHERE e.id = NEW.entity_id AND e.tenant_id = NEW.tenant_id
                  AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
                  AND e.entity_type = 'document_publication_artifact'
              ) THEN RAISE EXCEPTION 'publication artifact entity mismatch'; END IF;
              IF NEW.source_attachment_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM core_documentattachment a
                JOIN core_documentpublication p ON p.document_id = a.document_id
                WHERE a.id = NEW.source_attachment_id AND p.id = NEW.publication_id
                  AND a.tenant_id = NEW.tenant_id
                  AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
              ) THEN RAISE EXCEPTION 'publication artifact source mismatch'; END IF;
              IF NEW.checksum !~ '^[0-9a-f]{64}$' OR NEW.size < 1 OR NOT EXISTS (
                SELECT 1 FROM core_documentpublication p,
                  jsonb_array_elements(p.manifest->'artifacts') item
                WHERE p.id = NEW.publication_id AND item->>'id' = NEW.id::text
                  AND item->>'entity_id' = NEW.entity_id::text
                  AND item->>'kind' = NEW.kind
                  AND item->>'filename' = NEW.original_filename
                  AND item->>'media_type' = NEW.media_type
                  AND (item->>'size')::bigint = NEW.size
                  AND item->>'checksum' = NEW.checksum
                  AND (item->>'source_attachment_id') IS NOT DISTINCT FROM
                    (CASE WHEN NEW.source_attachment_id IS NULL THEN NULL ELSE
                      (SELECT a.entity_id::text FROM core_documentattachment a
                       WHERE a.id = NEW.source_attachment_id) END)
              ) THEN RAISE EXCEPTION 'publication artifact manifest mismatch'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE TRIGGER core_publicationartifact_scope_guard BEFORE INSERT ON core_documentpublicationartifact "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_publication_artifact()"
        )
        cursor.execute(
            "CREATE TRIGGER core_publicationartifact_immutable BEFORE UPDATE OR DELETE ON core_documentpublicationartifact "
            "FOR EACH ROW EXECUTE FUNCTION tekdocs_guard_document_publication_immutability()"
        )
        cursor.execute(
            """
            CREATE FUNCTION tekdocs_validate_publication_artifact_set() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF (SELECT count(*) FROM core_documentpublicationartifact a WHERE a.publication_id = NEW.id)
                   <> jsonb_array_length(NEW.manifest->'artifacts')
                 OR (SELECT count(*) FROM core_documentpublicationartifact a
                     WHERE a.publication_id = NEW.id AND a.kind = 'pdf') <> 1
              THEN RAISE EXCEPTION 'publication retained artifact set is incomplete'; END IF;
              RETURN NEW;
            END $$
            """
        )
        cursor.execute(
            "CREATE CONSTRAINT TRIGGER core_publication_artifact_set_complete AFTER INSERT ON core_documentpublication "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tekdocs_validate_publication_artifact_set()"
        )
        cursor.execute("ALTER TABLE core_documentpublicationartifact ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE core_documentpublicationartifact FORCE ROW LEVEL SECURITY")
        cursor.execute(
            "CREATE POLICY core_publicationartifact_runtime_select ON core_documentpublicationartifact FOR SELECT "
            "USING (tenant_id = tekdocs_current_tenant_id() AND EXISTS ("
            "SELECT 1 FROM core_documentpublication p WHERE p.id = publication_id))"
        )
        cursor.execute(
            "CREATE POLICY core_publicationartifact_runtime_write ON core_documentpublicationartifact FOR INSERT "
            "WITH CHECK (tekdocs_scope_matches(tenant_id, organization_id))"
        )
        cursor.execute("DROP POLICY core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')) OR EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentpublicationartifact a WHERE a.entity_id = core_entity.id))"
        )


def disable_publication_artifact_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS core_entity_runtime_select ON core_entity")
        cursor.execute(
            "CREATE POLICY core_entity_runtime_select ON core_entity FOR SELECT USING ("
            "tekdocs_scope_matches(tenant_id, organization_id) OR ("
            "tenant_id = tekdocs_current_tenant_id() AND organization_id IS NULL "
            "AND entity_type IN ('organization', 'person')) OR EXISTS ("
            "SELECT 1 FROM core_document d WHERE d.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_block b WHERE b.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentattachment a WHERE a.entity_id = core_entity.id) OR EXISTS ("
            "SELECT 1 FROM core_documentpublication p WHERE p.entity_id = core_entity.id))"
        )
        cursor.execute("DROP POLICY IF EXISTS core_publicationartifact_runtime_select ON core_documentpublicationartifact")
        cursor.execute("DROP POLICY IF EXISTS core_publicationartifact_runtime_write ON core_documentpublicationartifact")
        cursor.execute("ALTER TABLE core_documentpublicationartifact DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP TRIGGER IF EXISTS core_publication_artifact_set_complete ON core_documentpublication")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_publication_artifact_set()")
        cursor.execute("DROP TRIGGER IF EXISTS core_publicationartifact_immutable ON core_documentpublicationartifact")
        cursor.execute("DROP TRIGGER IF EXISTS core_publicationartifact_scope_guard ON core_documentpublicationartifact")
        cursor.execute("DROP FUNCTION IF EXISTS tekdocs_validate_publication_artifact()")
        cursor.execute(PUBLICATION_V1_GUARD)


class Migration(migrations.Migration):
    dependencies = [("core", "0030_publication_artifacts_and_lifecycle")]
    operations = [migrations.RunPython(enable_publication_artifact_guards, disable_publication_artifact_guards)]
