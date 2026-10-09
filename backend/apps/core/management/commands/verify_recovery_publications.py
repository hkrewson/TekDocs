"""Check retained repository publication custody before accepting a restore."""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import InstallationState, RepositoryStaticPublication, Workspace
from apps.core.repository_static_publications import verify_repository_static_publication
from apps.core.rls import OrganizationRLSMode, system_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Verify every retained repository STATIC record and its private artifacts after recovery."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def handle(self, *args: object, **options: object) -> None:
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant is None:
            self.stdout.write("Retained repository publication recovery verified: 0 records.")
            return
        tenant = installation.tenant
        verified = 0
        for workspace_id, organization_id in Workspace.objects.filter(tenant=tenant).order_by("id").values_list(
            "id", "organization_id"
        ):
            scope = DataScope(tenant.id, workspace_id, organization_id)
            mode = OrganizationRLSMode.ORGANIZATION if organization_id else OrganizationRLSMode.MSP_ONLY
            with system_rls_scope(scope, organization_mode=mode):
                publications = RepositoryStaticPublication.objects.filter(
                    tenant=tenant, workspace_id=workspace_id, organization_id=organization_id
                ).order_by("id")
                for publication in publications.iterator(chunk_size=50):
                    if not verify_repository_static_publication(publication):
                        raise CommandError("Retained repository publication integrity check failed.")
                    verified += 1
        self.stdout.write(f"Retained repository publication recovery verified: {verified} records.")
