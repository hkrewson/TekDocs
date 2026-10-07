"""Explicit, preview-bound first-wave import; never switches legacy authority."""

from __future__ import annotations

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.core.document_migration_import import DocumentMigrationBlocked, apply_document_import
from apps.core.models import InstallationState, Workspace
from apps.core.repository_service import RepositoryInputError


class Command(BaseCommand):
    help = "Copy one previewed legacy document to its workspace repository without switching authority."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True, help="Exact Workspace UUID")
        parser.add_argument("--document", required=True, help="Exact legacy Document UUID")
        parser.add_argument("--base-commit", required=True, help="Accepted commit from preview")
        parser.add_argument("--plan-sha256", required=True, help="Exact plan fingerprint from preview")
        parser.add_argument("--actor", required=True, help="Tenant operator UUID for audit attribution")
        parser.add_argument("--apply", action="store_true", help="Required acknowledgement of Git write")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if not options["apply"]:
            raise CommandError("Pass --apply after reviewing an eligible preview.")
        try:
            workspace_id = UUID(options["workspace"])
            document_id = UUID(options["document"])
            actor_id = UUID(options["actor"])
        except (TypeError, ValueError) as exc:
            raise CommandError("Valid workspace, document and actor UUIDs are required.") from exc
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        workspace = Workspace.objects.filter(tenant=installation.tenant, id=workspace_id).first()
        if workspace is None:
            raise CommandError("The workspace is unavailable.")
        try:
            result = apply_document_import(
                workspace=workspace,
                document_id=document_id,
                expected_base=options["base_commit"],
                plan_sha256=options["plan_sha256"],
                actor_id=actor_id,
            )
        except DocumentMigrationBlocked as exc:
            self.stdout.write(
                json.dumps(
                    {
                        "workspace_id": str(workspace.id),
                        "document_id": str(document_id),
                        "status": "blocked",
                        "blockers": exc.codes,
                    },
                    sort_keys=True,
                )
            )
            return
        except RepositoryInputError:
            self.stdout.write(
                json.dumps(
                    {
                        "workspace_id": str(workspace.id),
                        "document_id": str(document_id),
                        "status": "blocked",
                        "blockers": ["repository_input_rejected"],
                    },
                    sort_keys=True,
                )
            )
            return
        self.stdout.write(
            json.dumps(
                {
                    "workspace_id": str(workspace.id),
                    "document_id": str(document_id),
                    "status": result.status,
                    "commit": result.commit,
                    "indexed": result.indexed,
                    "legacy_authoritative": True,
                },
                sort_keys=True,
            )
        )
