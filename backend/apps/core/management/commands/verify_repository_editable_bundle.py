"""Verify a repository editable ZIP without consulting live custody."""

from pathlib import Path
from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.repository_editable_bundle_validation import (
    RepositoryEditableBundleValidationError,
    verify_repository_editable_bundle,
)
from apps.core.repository_editable_bundles import MAX_EDITABLE_BUNDLE_BYTES


class Command(BaseCommand):
    help = "Check an editable repository ZIP's Markdown and managed-file closure offline."
    requires_system_checks: list[str] = []
    requires_migrations_checks = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("archive", type=Path)

    def handle(self, *args: object, **options: object) -> None:
        archive = options["archive"]
        if not isinstance(archive, Path):
            raise CommandError("The editable bundle path is invalid.")
        try:
            if archive.stat().st_size > MAX_EDITABLE_BUNDLE_BYTES:
                raise RepositoryEditableBundleValidationError("The editable bundle exceeds its ZIP size limit.")
            manifest = verify_repository_editable_bundle(archive.read_bytes())
        except OSError as exc:
            raise CommandError("The editable bundle cannot be read.") from exc
        except RepositoryEditableBundleValidationError as exc:
            raise CommandError(str(exc)) from exc
        attachments = cast(list[object], manifest["attachments"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Editable bundle is internally consistent: {len(attachments)} managed files. "
                "Git authenticity, database custody, and backup completeness were not verified."
            )
        )
