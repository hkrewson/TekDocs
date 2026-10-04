from django.core.management.base import BaseCommand, CommandError

from apps.core.models import RepositoryReconciliationState
from apps.core.repository_service import RepositoryServiceError, reconcile_all_workspace_repositories


class Command(BaseCommand):
    help = "Diagnose managed Git repositories and optionally restore their refs to accepted commits."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--repair-to-accepted",
            action="store_true",
            help="Restore repository refs to PostgreSQL accepted commits; never advances accepted commits.",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            results = reconcile_all_workspace_repositories(
                repair_to_accepted=options["repair_to_accepted"]
            )
        except RepositoryServiceError as exc:
            raise CommandError(str(exc)) from exc
        counts = {state: 0 for state in RepositoryReconciliationState.values}
        repaired = 0
        for result in results:
            counts[result.state] += 1
            repaired += int(result.repaired)
        summary = ", ".join(f"{state}={counts[state]}" for state in RepositoryReconciliationState.values)
        self.stdout.write(
            f"Workspace repository reconciliation: total={len(results)}, repaired={repaired}, {summary}."
        )
