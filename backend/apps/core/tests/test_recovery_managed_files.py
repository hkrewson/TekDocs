from __future__ import annotations

import io
import secrets
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.document_attachments import archive_document_attachment, create_document_attachment
from apps.core.documents import create_document
from apps.core.models import DocumentAttachmentPurpose, InstallationState
from apps.core.organizations import create_organization

pytestmark = pytest.mark.django_db(transaction=True)


def test_recovery_managed_files_checks_msp_and_client_bytes_without_disclosing_names(tmp_path: Path) -> None:
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    installation = bootstrap_owner(
        tenant_name="Recovery File MSP",
        owner_email="recovery-file-owner@example.invalid",
        owner_display_name="Recovery File Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    organization = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Recovery File Client",
        legal_name="Recovery File Client",
        website="",
        classifications=["client"],
    )
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        for owner in (None, organization):
            document = create_document(
                tenant=installation.tenant,
                organization=owner,
                actor_id=installation.owner.id,
                title="Recovery file",
                markdown="Retained file.\n",
            )
            attachment = create_document_attachment(
                document=document,
                actor_id=installation.owner.id,
                upload=SimpleUploadedFile("retained.txt", b"Exact retained bytes\n"),
                purpose=(
                    DocumentAttachmentPurpose.PRIMARY_FILE
                    if owner is None
                    else DocumentAttachmentPurpose.ATTACHMENT
                ),
                version_number=1 if owner is None else None,
            )
            if owner is organization:
                client_attachment = attachment
        archive_document_attachment(attachment=client_attachment, actor_id=installation.owner.id)
        output = io.StringIO()
        call_command("verify_recovery_managed_files", stdout=output)
        assert "2 files" in output.getvalue()

        retained_path = Path(client_attachment.file.path)
        retained_path.write_bytes(b"Changed retained bytes\n")
        with pytest.raises(CommandError, match="Retained managed-file integrity check failed") as changed:
            call_command("verify_recovery_managed_files")
        assert "retained.txt" not in str(changed.value)

        retained_path.unlink()
        with pytest.raises(CommandError, match="Retained managed-file integrity check failed"):
            call_command("verify_recovery_managed_files")
