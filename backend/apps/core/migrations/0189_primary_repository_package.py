"""Permit complete primary-file packages while keeping STATIC v1 delivery closed."""

from django.db import migrations

PACKAGE_VALIDATOR = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_package() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositoryevidencereviewdecision decision
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE decision.id=NEW.decision_id
      AND decision.outcome='accepted_for_packaging'
      AND decision.tenant_id=NEW.tenant_id
      AND decision.organization_id=NEW.organization_id
      AND decision.workspace_id=NEW.workspace_id
      AND evidence.tenant_id=NEW.tenant_id
      AND evidence.organization_id=NEW.organization_id
      AND evidence.workspace_id=NEW.workspace_id
      AND (
        (NEW.manifest->>'format'='tekdocs-repository-publication-package/v1'
          AND evidence.manifest->>'format'='tekdocs-repository-publication-evidence/v1'
          AND NOT (NEW.manifest ? 'primary_file'))
        OR
        (NEW.manifest->>'format'='tekdocs-repository-publication-package/v2'
          AND evidence.manifest->>'format'='tekdocs-repository-publication-evidence/v2'
          AND NEW.manifest->'primary_file'=evidence.manifest->'primary_file')
      )
      AND NEW.manifest->>'package_id'=NEW.id::text
      AND NEW.manifest->>'decision_id'=decision.id::text
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'source_commit'=evidence.manifest->>'source_commit'
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN RAISE EXCEPTION 'repository package requires exact accepted evidence' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""

OLD_PACKAGE_VALIDATOR = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_package() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositoryevidencereviewdecision decision
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE decision.id=NEW.decision_id
      AND decision.outcome='accepted_for_packaging'
      AND decision.tenant_id=NEW.tenant_id
      AND decision.organization_id=NEW.organization_id
      AND decision.workspace_id=NEW.workspace_id
      AND evidence.tenant_id=NEW.tenant_id
      AND evidence.organization_id=NEW.organization_id
      AND evidence.workspace_id=NEW.workspace_id
      AND NEW.manifest->>'format'='tekdocs-repository-publication-package/v1'
      AND NEW.manifest->>'package_id'=NEW.id::text
      AND NEW.manifest->>'decision_id'=decision.id::text
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'source_commit'=evidence.manifest->>'source_commit'
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN RAISE EXCEPTION 'repository package requires exact accepted evidence' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""

STATIC_VALIDATOR = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_static_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypackageauthorization authz
    JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
    JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE authz.id=NEW.authorization_id
      AND authz.outcome='authorized_for_publication'
      AND authz.tenant_id=NEW.tenant_id
      AND authz.organization_id=NEW.organization_id
      AND authz.workspace_id=NEW.workspace_id
      AND package.tenant_id=NEW.tenant_id
      AND package.organization_id=NEW.organization_id
      AND package.workspace_id=NEW.workspace_id
      AND package.manifest->>'format'='tekdocs-repository-publication-package/v1'
      AND evidence.manifest->>'format'='tekdocs-repository-publication-evidence/v1'
      AND NEW.manifest->>'format'='tekdocs-repository-static-publication/v1'
      AND NEW.manifest->>'publication_id'=NEW.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'organization_id'=NEW.organization_id::text
      AND NEW.manifest->>'authorization_id'=authz.id::text
      AND NEW.manifest->>'authorization_outcome'=authz.outcome
      AND NEW.manifest->>'package_id'=package.id::text
      AND NEW.manifest->>'package_digest'=package.manifest_digest
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'source_commit'=package.manifest->>'source_commit'
      AND NEW.manifest->>'html_sha256'=package.manifest->>'html_sha256'
      AND NEW.manifest->>'pdf_sha256'=package.manifest->>'pdf_sha256'
      AND NEW.manifest->'attachments'=package.manifest->'attachments'
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN
    RAISE EXCEPTION 'repository STATIC publication requires exact authorized package' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""

OLD_STATIC_VALIDATOR = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_repository_static_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM core_repositorypackageauthorization authz
    JOIN core_repositorypublicationpackage package ON package.id=authz.package_id
    JOIN core_repositoryevidencereviewdecision decision ON decision.id=package.decision_id
    JOIN core_repositorypublicationevidence evidence ON evidence.id=decision.evidence_id
    WHERE authz.id=NEW.authorization_id
      AND authz.outcome='authorized_for_publication'
      AND authz.tenant_id=NEW.tenant_id
      AND authz.organization_id=NEW.organization_id
      AND authz.workspace_id=NEW.workspace_id
      AND package.tenant_id=NEW.tenant_id
      AND package.organization_id=NEW.organization_id
      AND package.workspace_id=NEW.workspace_id
      AND NEW.manifest->>'format'='tekdocs-repository-static-publication/v1'
      AND NEW.manifest->>'publication_id'=NEW.id::text
      AND NEW.manifest->>'workspace_id'=NEW.workspace_id::text
      AND NEW.manifest->>'organization_id'=NEW.organization_id::text
      AND NEW.manifest->>'authorization_id'=authz.id::text
      AND NEW.manifest->>'authorization_outcome'=authz.outcome
      AND NEW.manifest->>'package_id'=package.id::text
      AND NEW.manifest->>'package_digest'=package.manifest_digest
      AND NEW.manifest->>'evidence_id'=evidence.id::text
      AND NEW.manifest->>'evidence_digest'=evidence.content_digest
      AND NEW.manifest->>'source_commit'=package.manifest->>'source_commit'
      AND NEW.manifest->>'html_sha256'=package.manifest->>'html_sha256'
      AND NEW.manifest->>'pdf_sha256'=package.manifest->>'pdf_sha256'
      AND NEW.manifest->'attachments'=package.manifest->'attachments'
      AND NEW.manifest->>'created_by'=NEW.created_by_id::text
      AND NEW.manifest->>'created_at'=to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ) THEN
    RAISE EXCEPTION 'repository STATIC publication requires exact authorized package' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0188_repository_primary_publication_evidence")]

    operations = [
        migrations.RunSQL(PACKAGE_VALIDATOR, OLD_PACKAGE_VALIDATOR),
        migrations.RunSQL(STATIC_VALIDATOR, OLD_STATIC_VALIDATOR),
    ]
