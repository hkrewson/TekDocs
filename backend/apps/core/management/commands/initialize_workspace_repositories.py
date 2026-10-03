from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Workspace
from apps.core.repository_storage import (
    RepositoryStorageError,
    configured_repository_root,
    ensure_repository_root,
    ensure_workspace_repository,
)


class Command(BaseCommand):
    help = "Create or repair the private local Git repository for every Workspace."

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        initialized = 0
        retained = 0
        try:
            root = configured_repository_root()
            if root is None:
                self.stdout.write("Workspace repository custody is disabled.")
                return
            ensure_repository_root(root)
            for workspace in Workspace.objects.select_related("tenant").order_by("id").iterator():
                result = ensure_workspace_repository(workspace)
                if result is None:  # pragma: no cover - configuration cannot change during the command
                    raise CommandError("TEKDOCS_REPOSITORY_ROOT became unavailable.")
                if result.storage_created:
                    initialized += 1
                else:
                    retained += 1
        except RepositoryStorageError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Workspace repository custody verified: {initialized} initialized, {retained} retained."
        )
