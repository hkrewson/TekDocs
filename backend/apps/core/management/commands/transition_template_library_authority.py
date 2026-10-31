"""Preview/apply one explicit source-and-enrollment authority cohort."""

from __future__ import annotations

import json
import re
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
from apps.core.document_template_migration import (
    TemplateMigrationError,
    prepare_template_library_handoff,
    transition_template_library_authority,
)
from apps.core.models import InstallationState, Workspace
from apps.core.repository_service import RepositoryServiceError


class Command(BaseCommand):
    help = "Review and transition one MSP template source and its explicitly listed client documents together."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True, help="Exact MSP source Workspace UUID")
        parser.add_argument("--source", required=True, help="Exact source Document UUID")
        parser.add_argument("--document", action="append", required=True, help="Repeat for each client Document UUID")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--authority", required=True, choices=("repository", "legacy"))
        parser.add_argument("--plan-sha256", default="")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id, source_id, actor_id = (UUID(options[key]) for key in ("workspace", "source", "actor"))
            destinations = tuple(UUID(value) for value in options["document"])
        except (ValueError, TypeError) as exc:
            raise CommandError("Valid Workspace, source, client Document and actor UUIDs are required.") from exc
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", options["plan_sha256"]):
            raise CommandError("Apply requires the SHA-256 from the reviewed cohort preview.")
        installation = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant_id is None:
            raise CommandError("Installation setup must be completed before migration.")
        workspace = Workspace.objects.filter(
            pk=workspace_id, tenant_id=installation.tenant_id, organization__isnull=True,
        ).first()
        if workspace is None:
            raise CommandError("The source Workspace is unavailable in this installation.")
        arguments = dict(
            source_workspace=workspace, source_document_id=source_id, destination_document_ids=destinations,
            actor_id=actor_id, target=options["authority"],
        )
        result: dict[str, object]
        try:
            if options["apply"]:
                result = {"status": transition_template_library_authority(
                    **arguments, plan_sha256=options["plan_sha256"],
                ), "authority": options["authority"]}
            else:
                plan = prepare_template_library_handoff(**arguments)
                result = {
                    "status": "prepared", "source_document_id": str(plan.source_document_id),
                    "destination_document_ids": [str(value) for value in plan.destination_document_ids],
                    "authority": plan.target, "plan_sha256": plan.plan_sha256,
                }
        except TemplateMigrationError as exc:
            result = {"status": "blocked", "blockers": str(exc).split(", ")}
        except DocumentAuthorityHandoffError as exc:
            result = {"status": "blocked", "blockers": list(exc.codes)}
        except (RepositoryServiceError, ObjectDoesNotExist, ValueError, IntegrityError):
            result = {"status": "blocked", "blockers": ["template_cohort_sources_or_database_guard_unavailable"]}
        self.stdout.write(json.dumps(result, sort_keys=True))
