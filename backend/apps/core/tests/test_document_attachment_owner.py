"""Stable managed-file ownership before enabling repository-native uploads."""

from __future__ import annotations

import uuid
from hashlib import sha256

import psycopg
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import override_settings
from django.utils import timezone

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_storage
from apps.core.content_authoring import author_content
from apps.core.document_attachments import archive_document_attachment, create_document_attachment
from apps.core.documents import create_document
from apps.core.models import (
    ContentNode,
    DocumentAttachment,
    Entity,
    InstallationState,
    Workspace,
    WorkspaceKind,
    document_attachment_upload_to,
)
from apps.core.organizations import create_organization
from apps.core.rls_contract import RUNTIME_ROLE

pytestmark = pytest.mark.django_db(transaction=True)


def test_legacy_attachment_dual_writes_exact_content_owner_and_database_rejects_sibling(tmp_path):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="File owner MSP",
        owner_email=f"file-owner-{uuid.uuid4()}@example.invalid",
        owner_display_name="File Owner",
        password="FileOwnerPassword-2026!",
    )
    selected = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Selected client",
        legal_name="Selected client",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling client",
        legal_name="Sibling client",
        website="",
        classifications=["client"],
    )
    document = create_document(
        tenant=installation.tenant,
        organization=selected,
        actor_id=installation.owner.id,
        title="File owner guide",
        markdown="Read this.\n",
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("steps.txt", b"Safe steps\n"),
        )
    attachment.refresh_from_db()
    assert attachment.owner_workspace_id == document.entity.workspace_id
    assert attachment.owner_content_id == document.id

    # Legacy writers that omit the expanded fields remain safe during rollout.
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE core_documentattachment SET owner_workspace_id=NULL, owner_content_id=NULL WHERE id=%s",
            [attachment.id],
        )
    attachment.refresh_from_db()
    assert attachment.owner_workspace_id == document.entity.workspace_id
    assert attachment.owner_content_id == document.id

    sibling_workspace = Workspace.objects.get(tenant=installation.tenant, organization=sibling)
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_documentattachment SET owner_workspace_id=%s WHERE id=%s",
                [sibling_workspace.id, attachment.id],
            )
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_documentattachment SET owner_content_id=%s WHERE id=%s",
                [uuid.uuid4(), attachment.id],
            )
    attachment.refresh_from_db()
    assert attachment.owner_workspace_id == document.entity.workspace_id
    assert attachment.owner_content_id == document.id


def test_native_owner_requires_indexed_document_and_exact_workspace(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Native file owner MSP",
            owner_email=f"native-owner-{uuid.uuid4()}@example.invalid",
            owner_display_name="Native File Owner",
            password="NativeFileOwner-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        sibling = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Other client",
            legal_name="Other client",
            website="",
            classifications=["client"],
        )
        sibling_workspace = Workspace.objects.get(tenant=installation.tenant, organization=sibling)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        content_id = uuid.uuid4()
        author_content(
            repository=repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="create",
            content_id=content_id,
            base_commit=repository.accepted_commit.object_id if repository.accepted_commit_id else None,
            base_blob=None,
            kind="document",
            path=None,
            title="Native file guide",
            markdown="Native file instructions.\n",
            metadata_patch={"properties": {"lifecycle": "active"}},
        )
        entity = Entity.objects.create(
            tenant=installation.tenant,
            workspace=workspace,
            organization=None,
            entity_type="document_attachment",
            display_name="native.txt",
        )
        content = b"native file bytes\n"
        attachment = DocumentAttachment.objects.create(
            tenant=installation.tenant,
            organization=None,
            document=None,
            owner_workspace=workspace,
            owner_content_id=content_id,
            entity=entity,
            file=f"document-attachments/{installation.tenant.id}/{content_id}/{uuid.uuid4()}",
            original_filename="native.txt",
            media_type="text/plain",
            size=len(content),
            checksum=sha256(content).hexdigest(),
            scan_status="clean",
            scan_engine="test-scanner",
            scanned_at=timezone.now(),
        )
        assert attachment.document_id is None
        assert attachment.owner_content_id == content_id
        assert document_attachment_upload_to(attachment, "native.txt") == (
            f"document-attachments/{installation.tenant.id}/{content_id}/{attachment.id}"
        )
        attachment.full_clean()
        with pytest.raises(CommandError, match="Retained managed-file integrity check failed"):
            call_command("verify_recovery_managed_files", verbosity=0)

        with psycopg.connect(
            dbname=connection.settings_dict["NAME"],
            user=RUNTIME_ROLE,
            password=settings.TEKDOCS_DATABASE_RUNTIME_PASSWORD,
            host=connection.settings_dict["HOST"],
            port=connection.settings_dict["PORT"],
            autocommit=True,
        ) as runtime, runtime.cursor() as cursor:
            for tenant_id, selected_workspace, organization_id, mode, visible in (
                (installation.tenant.id, workspace.id, None, "msp", True),
                (installation.tenant.id, sibling_workspace.id, sibling.id, "organization", False),
                (uuid.uuid4(), workspace.id, None, "msp", False),
            ):
                with runtime.transaction():
                    cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(tenant_id)])
                    cursor.execute("SELECT set_config('tekdocs.workspace_id', %s, true)", [str(selected_workspace)])
                    cursor.execute(
                        "SELECT set_config('tekdocs.organization_id', %s, true)",
                        [str(organization_id or "")],
                    )
                    cursor.execute("SELECT set_config('tekdocs.organization_mode', %s, true)", [mode])
                    cursor.execute("SELECT set_config('tekdocs.principal_mode', 'system', true)")
                    cursor.execute("SELECT id FROM core_documentattachment WHERE id=%s", [attachment.id])
                    assert bool(cursor.fetchall()) is visible

        with pytest.raises(DatabaseError), transaction.atomic():
            DocumentAttachment.objects.filter(pk=attachment.pk).update(owner_workspace=sibling_workspace)
        with pytest.raises(DatabaseError), transaction.atomic():
            DocumentAttachment.objects.filter(pk=attachment.pk).update(owner_content_id=uuid.uuid4())

        missing_entity = Entity.objects.create(
            tenant=installation.tenant,
            workspace=workspace,
            organization=None,
            entity_type="document_attachment",
            display_name="missing.txt",
        )
        with pytest.raises(DatabaseError), transaction.atomic():
            DocumentAttachment.objects.create(
                tenant=installation.tenant,
                organization=None,
                document=None,
                owner_workspace=workspace,
                owner_content_id=uuid.uuid4(),
                entity=missing_entity,
                file="document-attachments/missing",
                original_filename="missing.txt",
                media_type="text/plain",
                size=len(content),
                checksum=sha256(content).hexdigest(),
                scan_status="clean",
                scan_engine="test-scanner",
                scanned_at=timezone.now(),
            )

        with pytest.raises(DatabaseError), transaction.atomic():
            DocumentAttachment.objects.filter(pk=attachment.pk).update(organization=sibling)

        ContentNode.objects.filter(repository=repository, content_id=content_id).delete()
        assert DocumentAttachment.objects.filter(pk=attachment.pk).exists()
        archive_document_attachment(attachment=attachment, actor_id=installation.owner.id)
        attachment.refresh_from_db()
        assert attachment.archived_at is not None
