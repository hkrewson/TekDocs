"""Check retained repository publication custody before accepting a restore."""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import DocumentPublication, InstallationState, RepositoryStaticPublication, Workspace
from apps.core.publications import verify_retained_publication_custody
from apps.core.repository_static_publications import verify_repository_static_publication
from apps.core.rls import OrganizationRLSMode, system_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Verify retained legacy and repository STATIC records and their private artifacts after recovery."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def handle(self, *args: object, **options: object) -> None:
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant is None:
            self.stdout.write("Retained publication recovery verified: 0 legacy, 0 repository records.")
            return
        tenant = installation.tenant
        legacy_verified = 0
        repository_verified = 0
        for workspace_id, organization_id in Workspace.objects.filter(tenant=tenant).order_by("id").values_list(
            "id", "organization_id"
        ):
            scope = DataScope(tenant.id, workspace_id, organization_id)
            mode = OrganizationRLSMode.ORGANIZATION if organization_id else OrganizationRLSMode.MSP_ONLY
            with system_rls_scope(scope, organization_mode=mode):
                legacy_publications = DocumentPublication.objects.filter(
                    tenant=tenant, organization_id=organization_id, entity__workspace_id=workspace_id
                ).order_by("id")
                for legacy_publication in legacy_publications.iterator(chunk_size=50):
                    if not verify_retained_publication_custody(legacy_publication):
                        raise CommandError("Retained legacy publication integrity check failed.")
                    legacy_verified += 1
                publications = RepositoryStaticPublication.objects.filter(
                    tenant=tenant, workspace_id=workspace_id, organization_id=organization_id
                ).order_by("id")
                for repository_publication in publications.iterator(chunk_size=50):
                    if not verify_repository_static_publication(repository_publication):
                        raise CommandError("Retained repository publication integrity check failed.")
                    repository_verified += 1
        self.stdout.write(
            f"Retained publication recovery verified: {legacy_verified} legacy, "
            f"{repository_verified} repository records."
        )
