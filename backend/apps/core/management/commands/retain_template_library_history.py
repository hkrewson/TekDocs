"""Retain reviewed immutable template definitions before the authority handoff."""

from __future__ import annotations

import json
import re
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from apps.core.document_template_migration import TemplateMigrationError
from apps.core.models import Document, InstallationState, Workspace
from apps.core.repository_service import RepositoryServiceError, coordinated_repository_transaction
from apps.core.template_library_history import prepare_template_library_history, retain_template_library_history
from apps.core.template_library_scope import editable_template_workspace_scope


class Command(BaseCommand):
    help = "Prepare or retain exact immutable template snapshots without changing document authority."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--plan-sha256", default="")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id, source_id, actor_id = (UUID(options[key]) for key in ("workspace", "source", "actor"))
        except (ValueError, TypeError) as exc:
            raise CommandError("Valid Workspace, source Document and actor UUIDs are required.") from exc
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", options["plan_sha256"]):
            raise CommandError("Apply requires the SHA-256 from the reviewed history preview.")
        installation = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant_id is None:
            raise CommandError("Installation setup must be completed before migration.")
        workspace = Workspace.objects.filter(
            tenant_id=installation.tenant_id, pk=workspace_id, organization__isnull=True,
        ).first()
        if workspace is None:
            raise CommandError("The source Workspace is unavailable in this installation.")
        result: dict[str, object]
        try:
            with coordinated_repository_transaction(), editable_template_workspace_scope(workspace, actor_id):
                source = Document.objects.select_related("entity").get(
                    tenant_id=installation.tenant_id, entity__workspace=workspace, pk=source_id,
                )
                if options["apply"]:
                    retained = retain_template_library_history(
                        source=source, actor_id=actor_id, plan_sha256=options["plan_sha256"],
                    )
                    result = {"status": "retained", "commit": retained.commit, "indexed": retained.indexed}
                else:
                    plan = prepare_template_library_history(source=source, actor_id=actor_id)
                    result = {
                        "status": "prepared", "source_document_id": str(source.id), "base_commit": plan.base_commit,
                        "revisions": len(plan.revision_ids), "missing_files": len(plan.missing_paths),
                        "plan_sha256": plan.plan_sha256,
                    }
        except TemplateMigrationError as exc:
            result = {"status": "blocked", "blockers": str(exc).split(", ")}
        except (RepositoryServiceError, ObjectDoesNotExist, ValueError):
            result = {"status": "blocked", "blockers": ["template_history_unavailable"]}
        self.stdout.write(json.dumps(result, sort_keys=True))
