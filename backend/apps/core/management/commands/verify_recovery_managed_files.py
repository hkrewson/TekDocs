"""Check retained document-file custody before backup and after restore."""

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from apps.core.document_attachments import copy_attachment_content
from apps.core.models import DocumentAttachment, InstallationState, Workspace
from apps.core.rls import OrganizationRLSMode, system_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Verify every retained document attachment and primary-file version against private storage."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def handle(self, *args: object, **options: object) -> None:
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant is None:
            self.stdout.write("Retained managed-file recovery verified: 0 files.")
            return
        tenant = installation.tenant
        verified = 0
        for workspace_id, organization_id in Workspace.objects.filter(tenant=tenant).order_by("id").values_list(
            "id", "organization_id"
        ):
            scope = DataScope(tenant.id, workspace_id, organization_id)
            mode = OrganizationRLSMode.ORGANIZATION if organization_id else OrganizationRLSMode.MSP_ONLY
            with system_rls_scope(scope, organization_mode=mode):
                files = DocumentAttachment.objects.filter(
                    tenant=tenant,
                    organization_id=organization_id,
                    owner_workspace_id=workspace_id,
                    entity__workspace_id=workspace_id,
                ).order_by("id")
                for attachment in files.iterator(chunk_size=50):
                    try:
                        copy_attachment_content(attachment)
                    except ValidationError as exc:
                        raise CommandError("Retained managed-file integrity check failed.") from exc
                    verified += 1
        noun = "file" if verified == 1 else "files"
        self.stdout.write(f"Retained managed-file recovery verified: {verified} {noun}.")
