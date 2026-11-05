"""Review ordinary library history or one explicit source/consumer authority cohort."""

from __future__ import annotations

import json
import re
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
from apps.core.document_template_migration import TemplateMigrationError
from apps.core.models import Document, InstallationState, Workspace
from apps.core.repository_service import RepositoryServiceError, coordinated_repository_transaction
from apps.core.shared_library_history import prepare_shared_library_history, retain_shared_library_history
from apps.core.shared_library_migration import prepare_shared_library_handoff, transition_shared_library_authority
from apps.core.template_library_scope import editable_template_workspace_scope


class Command(BaseCommand):
    help = "Review and apply ordinary MSP library history retention, promotion or rollback."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--operation", choices=("history", "promote", "rollback"), required=True)
        parser.add_argument("--document", action="append", default=[])
        parser.add_argument("--plan-sha256", default="")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id, source_id, actor_id = (UUID(options[key]) for key in ("workspace", "source", "actor"))
            destinations = tuple(UUID(value) for value in options["document"])
        except (ValueError, TypeError) as exc:
            raise CommandError("Valid Workspace, source, consumer Document and actor UUIDs are required.") from exc
        if options["operation"] == "history" and destinations:
            raise CommandError("History retention accepts only the source Document.")
        if options["operation"] != "history" and not destinations:
            raise CommandError("Authority transitions require the explicit consumer Document list.")
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", options["plan_sha256"]):
            raise CommandError("Apply requires the SHA-256 from the reviewed preview.")
        installation = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant_id is None:
            raise CommandError("Installation setup must be completed before migration.")
        workspace = Workspace.objects.select_related("tenant").filter(
            pk=workspace_id, tenant_id=installation.tenant_id, organization__isnull=True,
        ).first()
        if workspace is None:
            raise CommandError("The source Workspace is unavailable in this installation.")
        result: dict[str, object]
        try:
            if options["operation"] == "history":
                with coordinated_repository_transaction(), editable_template_workspace_scope(workspace, actor_id):
                    source = Document.objects.select_related("entity__workspace").get(
                        pk=source_id, tenant_id=workspace.tenant_id, entity__workspace=workspace,
                    )
                    if options["apply"]:
                        commit = retain_shared_library_history(
                            source=source, actor_id=actor_id, plan_sha256=options["plan_sha256"],
                        )
                        result = {"status": "retained", "commit": commit, "indexed": True}
                    else:
                        history = prepare_shared_library_history(source=source, actor_id=actor_id)
                        result = {"status": "prepared", "base_commit": history.base_commit,
                                  "missing_files": len(history.missing_paths), "plan_sha256": history.plan_sha256}
            else:
                target = "repository" if options["operation"] == "promote" else "legacy"
                if options["apply"]:
                    result = {"status": transition_shared_library_authority(
                        source_workspace=workspace, source_document_id=source_id,
                        destination_document_ids=destinations, actor_id=actor_id, target=target,
                        plan_sha256=options["plan_sha256"],
                    ), "authority": target}
                else:
                    cohort = prepare_shared_library_handoff(
                        source_workspace=workspace, source_document_id=source_id,
                        destination_document_ids=destinations, actor_id=actor_id, target=target,
                    )
                    result = {"status": "prepared", "authority": target, "plan_sha256": cohort.plan_sha256,
                              "destination_document_ids": [str(value) for value in cohort.destination_document_ids]}
        except TemplateMigrationError as exc:
            result = {"status": "blocked", "blockers": str(exc).split(", ")}
        except DocumentAuthorityHandoffError as exc:
            result = {"status": "blocked", "blockers": list(exc.codes)}
        except (RepositoryServiceError, ObjectDoesNotExist, ValueError, IntegrityError):
            result = {"status": "blocked", "blockers": ["library_sources_or_database_guard_unavailable"]}
        self.stdout.write(json.dumps(result, sort_keys=True))
