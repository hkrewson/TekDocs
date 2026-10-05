from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.content_index import ContentIndexError, ContentIndexValidationError, index_repository_content
from apps.core.models import WorkspaceRepository


class Command(BaseCommand):
    help = "Build the disposable content graph from accepted workspace repository commits."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--repository", dest="repository_id")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        repositories = WorkspaceRepository.objects.order_by("id")
        if options["repository_id"]:
            repositories = repositories.filter(id=options["repository_id"])
            if not repositories.exists():
                raise CommandError("Workspace repository does not exist")
        indexed = unchanged = rejected = 0
        for repository in repositories:
            if repository.accepted_commit_id is None:
                continue
            try:
                result = index_repository_content(repository_id=repository.id, force=options["force"])
            except ContentIndexValidationError as exc:
                rejected += 1
                self.stderr.write(
                    f"Rejected repository {repository.id}: {len(exc.diagnostics)} validation diagnostic(s)."
                )
            except ContentIndexError as exc:
                raise CommandError(str(exc)) from exc
            else:
                indexed += int(result.changed)
                unchanged += int(not result.changed)
        if rejected:
            raise CommandError(
                f"Content index rejected {rejected} repository commit(s); last-known-good projections retained."
            )
        self.stdout.write(f"Content index complete: {indexed} rebuilt, {unchanged} unchanged.")
