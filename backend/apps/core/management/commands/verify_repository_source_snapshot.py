"""Offline structural and checksum validation for a downloaded Markdown ZIP."""

from pathlib import Path
from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.repository_source_exports import MAX_SOURCE_ZIP_BYTES
from apps.core.repository_source_validation import RepositorySourceValidationError, verify_repository_source_snapshot


class Command(BaseCommand):
    help = "Check a Markdown source snapshot ZIP without a database or Git connection."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("archive", type=Path)

    def handle(self, *args: object, **options: object) -> None:
        archive = options["archive"]
        if not isinstance(archive, Path):
            raise CommandError("The source snapshot path is invalid.")
        try:
            if archive.stat().st_size > MAX_SOURCE_ZIP_BYTES:
                raise RepositorySourceValidationError("The source snapshot exceeds the ZIP size limit.")
            manifest = verify_repository_source_snapshot(archive.read_bytes())
        except OSError as exc:
            raise CommandError("The source snapshot cannot be read.") from exc
        except RepositorySourceValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Source snapshot is internally consistent: "
                f"{len(cast(list[object], manifest['files']))} current and "
                f"{len(cast(list[object], manifest['historical_files']))} historical Markdown files. "
                "Git authenticity and attachment completeness were not verified."
            )
        )
