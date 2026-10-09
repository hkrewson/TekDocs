"""Stable managed-file ownership before enabling repository-native uploads."""

from __future__ import annotations

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_attachments import create_document_attachment
from apps.core.documents import create_document
from apps.core.models import InstallationState, Workspace
from apps.core.organizations import create_organization

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
