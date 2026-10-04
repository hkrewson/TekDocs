from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.repository_recovery import (
    RepositoryRecoveryError,
    create_repository_recovery_archive,
    restore_repository_recovery_archive,
    validate_repository_recovery_archive,
    verify_repository_recovery_database,
)
from apps.core.repository_service import reconcile_all_workspace_repositories


class Command(BaseCommand):
    help = "Create, validate, restore, or database-verify the managed repository recovery artifact."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("operation", choices=("create", "validate", "restore", "verify"))
        parser.add_argument("--archive", type=Path, required=True)
        parser.add_argument("--destination", type=Path)

    def handle(self, *args: object, **options: object) -> None:
        operation = str(options["operation"])
        archive = options["archive"]
        destination = options["destination"]
        if not isinstance(archive, Path):
            raise CommandError("The repository recovery archive path is invalid.")
        try:
            if operation == "create":
                manifest = create_repository_recovery_archive(archive)
            elif operation == "validate":
                manifest = validate_repository_recovery_archive(archive)
            elif operation == "restore":
                if destination is not None and not isinstance(destination, Path):
                    raise RepositoryRecoveryError("The repository recovery destination is invalid.")
                root = destination or Path(settings.TEKDOCS_REPOSITORY_ROOT)
                manifest = restore_repository_recovery_archive(archive, root)
            else:
                manifest = verify_repository_recovery_database(archive)
                results = reconcile_all_workspace_repositories()
                if any(result.state != "matched" for result in results):
                    raise RepositoryRecoveryError("A restored repository does not match its accepted head.")
        except RepositoryRecoveryError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Repository recovery {operation} complete: {len(manifest['repositories'])} repositories."
            )
        )
