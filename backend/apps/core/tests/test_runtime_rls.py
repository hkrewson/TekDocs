import uuid
from hashlib import sha256

import psycopg
import pytest
from django.conf import settings
from django.db import connection, transaction

from apps.core.certification import CONTROL_PLANE_GUARD_TRIGGERS
from apps.core.models import (
    Block,
    BlockRevision,
    CredentialReference,
    Document,
    DocumentationListingReference,
    DocumentAttachment,
    DocumentPlacement,
    DocumentPublication,
    DocumentPublicationArtifact,
    Entity,
    Organization,
    Tenant,
)
from apps.core.rls_contract import RLS_TABLES, RUNTIME_ROLE


def _organization(tenant: Tenant, name: str) -> Organization:
    anchor = Entity.objects.create_owned(tenant=tenant, entity_type="organization", display_name=name)
    return Organization.objects.create(tenant=tenant, entity=anchor)


def _runtime_connection():
    return psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        user=RUNTIME_ROLE,
        password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
        host=connection.settings_dict["HOST"],
        port=connection.settings_dict["PORT"],
    )


def _bind(cursor, tenant_id, mode, organization_id=None):
    cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(tenant_id)])
    cursor.execute(
        "SELECT id FROM core_workspace WHERE tenant_id = %s AND organization_id IS NOT DISTINCT FROM %s",
        [tenant_id, organization_id],
    )
    workspace_id = cursor.fetchone()[0]
    cursor.execute("SELECT set_config('tekdocs.workspace_id', %s, true)", [str(workspace_id)])
    cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [str(organization_id or "")])
    cursor.execute("SELECT set_config('tekdocs.organization_mode', %s, true)", [mode])


@pytest.mark.django_db(transaction=True)
def test_runtime_credential_references_are_forced_to_the_selected_workspace():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

    tenant = Tenant.objects.create(name="Credential RLS tenant", slug=f"credential-{uuid.uuid4()}")
    first_org = _organization(tenant, "First credential client")
    sibling_org = _organization(tenant, "Sibling credential client")
    entity = Entity.objects.create_owned(
        tenant=tenant,
        organization=first_org,
        entity_type="credential_reference",
        display_name="Firewall administrator",
    )
    reference = CredentialReference.objects.create(
        tenant=tenant,
        organization=first_org,
        entity=entity,
        provider="onepassword",
        reference_url=(
            "https://start.1password.com/open/i?"
            "a=aaaaaaaaaaaaaaaaaaaaaaaaaa&v=vvvvvvvvvvvvvvvvvvvvvvvvvv&"
            "i=iiiiiiiiiiiiiiiiiiiiiiiiii&h=example.1password.com"
        ),
    )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, tenant.id, "organization", first_org.id)
        cursor.execute("SELECT id FROM core_credentialreference")
        assert cursor.fetchall() == [(reference.id,)]
        runtime.commit()

        _bind(cursor, tenant.id, "organization", sibling_org.id)
        cursor.execute("SELECT id FROM core_credentialreference")
        assert cursor.fetchall() == []
        cursor.execute(
            "UPDATE core_credentialreference SET organization_id = %s WHERE id = %s",
            [sibling_org.id, reference.id],
        )
        assert cursor.rowcount == 0


@pytest.mark.django_db(transaction=True)
def test_runtime_role_is_constrained_and_forced_rls_inventory_is_complete():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        assert cursor.fetchone() == (RUNTIME_ROLE, False, False, False, False)
        cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        assert cursor.fetchone() == (False,)
        cursor.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND c.relrowsecurity AND c.relforcerowsecurity",
            [list(RLS_TABLES)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(RLS_TABLES)
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY(%s)",
            [list(CONTROL_PLANE_GUARD_TRIGGERS)],
        )
        assert {row[0] for row in cursor.fetchall()} == set(CONTROL_PLANE_GUARD_TRIGGERS)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("CREATE TABLE runtime_role_escape (id integer)")
        runtime.rollback()


@pytest.mark.django_db(transaction=True)
def test_runtime_raw_sql_denies_missing_cross_tenant_sibling_write_and_all_mode():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

    first = Tenant.objects.create(name="First runtime tenant", slug=f"first-{uuid.uuid4()}")
    second = Tenant.objects.create(name="Second runtime tenant", slug=f"second-{uuid.uuid4()}")
    first_org = _organization(first, "First client")
    sibling_org = _organization(first, "Sibling client")
    foreign_org = _organization(second, "Foreign client")
    msp = Entity.objects.create_owned(tenant=first, entity_type="document", display_name="MSP runbook")
    selected = Entity.objects.create_owned(
        tenant=first,
        organization=first_org,
        entity_type="document",
        display_name="Selected client runbook",
    )
    Entity.objects.create_owned(
        tenant=first,
        organization=sibling_org,
        entity_type="document",
        display_name="Sibling client runbook",
    )
    Entity.objects.create_owned(
        tenant=second,
        organization=foreign_org,
        entity_type="document",
        display_name="Foreign client runbook",
    )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM core_entity")
        assert cursor.fetchone() == (0,)

        _bind(cursor, first.id, "msp")
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert {row[0] for row in cursor.fetchall()} == {msp.id}
        runtime.commit()

        cursor.execute("SELECT COALESCE(current_setting('tekdocs.tenant_id', true), '')")
        assert cursor.fetchone() == ("",)
        _bind(cursor, first.id, "organization", first_org.id)
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert {row[0] for row in cursor.fetchall()} == {selected.id}
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.CheckViolation)):
            cursor.execute(
                "UPDATE core_entity SET organization_id = %s WHERE id = %s",
                [sibling_org.id, selected.id],
            )
        runtime.rollback()

        _bind(cursor, first.id, "all")
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document'")
        assert cursor.fetchall() == []


@pytest.mark.django_db(transaction=True)
def test_runtime_document_projection_exposes_only_the_referenced_client():
    if connection.vendor != "postgresql":
        pytest.skip("Runtime-role certification requires PostgreSQL")

    tenant = Tenant.objects.create(name="Document RLS tenant", slug=f"documents-{uuid.uuid4()}")
    selected_org = _organization(tenant, "Selected client")
    sibling_org = _organization(tenant, "Sibling client")
    document_entity = Entity.objects.create_owned(
        tenant=tenant, entity_type="document", display_name="Shared runbook"
    )
    document = Document.objects.create(tenant=tenant, entity=document_entity)
    block_entity = Entity.objects.create_owned(
        tenant=tenant, entity_type="document_block", display_name="Shared block"
    )
    block = Block.objects.create(tenant=tenant, entity=block_entity)
    revision = BlockRevision.objects.create(
        tenant=tenant,
        block=block,
        revision_number=1,
        markdown="Reference content",
        checksum=sha256(b"Reference content").hexdigest(),
    )
    block.current_revision = revision
    block.save(update_fields=("current_revision", "updated_at"))
    placement = DocumentPlacement.objects.create(tenant=tenant, document=document, block=block, position=0)
    reference = DocumentationListingReference.objects.create(
        tenant=tenant, organization=selected_org, document=document
    )
    attachment_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_attachment",
        display_name="reference.txt",
    )
    attachment = DocumentAttachment.objects.create(
        tenant=tenant,
        document=document,
        entity=attachment_entity,
        file="document-attachments/fixture",
        original_filename="reference.txt",
        media_type="text/plain",
        size=1,
        checksum=sha256(b"x").hexdigest(),
    )
    publication_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_publication",
        display_name="Shared runbook STATIC",
    )
    publication_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    artifact_entity = Entity.objects.create_owned(
        tenant=tenant,
        entity_type="document_publication_artifact",
        display_name="Shared runbook STATIC.pdf",
    )
    artifact_checksum = sha256(b"%PDF-fixture").hexdigest()
    with transaction.atomic():
        publication = DocumentPublication.objects.create(
            id=publication_id,
            tenant=tenant,
            document=document,
            entity=publication_entity,
            title="Shared runbook",
            category="reference",
            reason="RLS fixture",
            audience="msp_internal",
            retention="permanent",
            canonical_markdown="Reference content\n",
            sanitized_html="<p>Reference content</p>",
            manifest={
                "format": "tekdocs-static-publication/v2",
                "publication_id": str(publication_id),
                "publication_entity_id": str(publication_entity.id),
                "source_document_id": str(document.entity_id),
                "workspace": {"kind": "msp", "id": None},
                "reason": "RLS fixture",
                "audience": "msp_internal",
                "retention": "permanent",
                "retention_review_on": None,
                "supersedes_id": None,
                "artifacts": [
                    {
                        "id": str(artifact_id),
                        "entity_id": str(artifact_entity.id),
                        "kind": "pdf",
                        "filename": "shared-runbook-static.pdf",
                        "media_type": "application/pdf",
                        "size": 12,
                        "checksum": artifact_checksum,
                        "source_attachment_id": None,
                    }
                ],
            },
            content_digest="a" * 64,
            signature="fixture",
            public_key="fixture",
            key_fingerprint="b" * 64,
            published_at="2026-08-09T12:00:00Z",
        )
        artifact = DocumentPublicationArtifact.objects.create(
            id=artifact_id,
            tenant=tenant,
            publication=publication,
            entity=artifact_entity,
            kind="pdf",
            file="publication-artifacts/fixture",
            original_filename="shared-runbook-static.pdf",
            media_type="application/pdf",
            size=12,
            checksum=artifact_checksum,
            created_at="2026-08-09T12:00:00Z",
        )

    with _runtime_connection() as runtime, runtime.cursor() as cursor:
        _bind(cursor, tenant.id, "organization", selected_org.id)
        cursor.execute("SELECT id FROM core_document")
        assert cursor.fetchall() == [(document.id,)]
        cursor.execute("SELECT id FROM core_block")
        assert cursor.fetchall() == [(block.id,)]
        cursor.execute("SELECT id FROM core_blockrevision")
        assert cursor.fetchall() == [(revision.id,)]
        cursor.execute("SELECT id FROM core_documentplacement")
        assert cursor.fetchall() == [(placement.id,)]
        cursor.execute("SELECT id FROM core_documentationlistingreference")
        assert cursor.fetchall() == [(reference.id,)]
        cursor.execute("SELECT id FROM core_documentattachment")
        assert cursor.fetchall() == [(attachment.id,)]
        cursor.execute("SELECT id FROM core_documentpublication")
        assert cursor.fetchall() == [(publication.id,)]
        cursor.execute("SELECT id FROM core_documentpublicationartifact")
        assert cursor.fetchall() == [(artifact.id,)]
        cursor.execute("SELECT id FROM core_entity WHERE entity_type = 'document_publication'")
        assert cursor.fetchall() == [(publication_entity.id,)]
        runtime.commit()

        _bind(cursor, tenant.id, "organization", sibling_org.id)
        for table in (
            "core_document",
            "core_block",
            "core_blockrevision",
            "core_documentplacement",
            "core_documentationlistingreference",
            "core_documentattachment",
            "core_documentpublication",
        ):
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed test allowlist
            assert cursor.fetchone() == (0,)
