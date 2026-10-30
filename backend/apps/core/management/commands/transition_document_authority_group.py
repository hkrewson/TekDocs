"""Preview/apply an explicitly listed, same-Workspace shared dependency group."""

from __future__ import annotations

import json
import re
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.accounts.models import User
from apps.core.document_authority_groups import prepare_authority_group, transition_authority_group
from apps.core.document_authority_handoff import DocumentAuthorityHandoffError
from apps.core.models import InstallationState, Workspace
from apps.core.repository_service import RepositoryServiceError
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace


class Command(BaseCommand):
    help = "Preview/apply one explicit shared live dependency group without partial authority changes."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--document", action="append", required=True, help="Repeat for each exact Document UUID")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--authority", required=True, choices=("repository", "legacy"))
        parser.add_argument("--plan-sha256", default="")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id = UUID(options["workspace"])
            actor_id = UUID(options["actor"])
            document_ids = tuple(UUID(value) for value in options["document"])
        except (TypeError, ValueError) as exc:
            raise CommandError("Valid Workspace, Document and actor UUIDs are required.") from exc
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", options["plan_sha256"]):
            raise CommandError("Apply requires the SHA-256 from the reviewed group preview.")
        installation = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
        if installation.tenant_id is None:
            raise CommandError("Installation setup must be completed before migration.")
        workspace = (
            Workspace.objects.select_related("organization")
            .filter(
                tenant_id=installation.tenant_id,
                id=workspace_id,
            )
            .first()
        )
        actor = User.objects.filter(pk=actor_id, is_active=True).first()
        if workspace is None or actor is None:
            raise CommandError("Workspace or active operator is unavailable.")
        try:
            reader = (
                resolve_organization_workspace(actor, entity_id=workspace.organization.entity_id)
                if workspace.organization is not None
                else resolve_msp_workspace(actor)
            )
        except Exception as exc:
            raise CommandError("The operator cannot resolve this Workspace.") from exc
        result: dict[str, object]
        try:
            arguments = dict(
                workspace=workspace,
                document_ids=document_ids,
                actor_id=actor.id,
                target=options["authority"],
                reader_workspace=reader,
            )
            if options["apply"]:
                result = {"status": transition_authority_group(**arguments, plan_sha256=options["plan_sha256"])}
            else:
                plan = prepare_authority_group(**arguments)
                result = {
                    "status": "prepared",
                    "document_ids": [str(value) for value in plan.document_ids],
                    "base_commit": plan.base_commit,
                    "plan_sha256": plan.plan_sha256,
                }
        except DocumentAuthorityHandoffError as exc:
            result = {"status": "blocked", "blockers": list(exc.codes)}
        except (RepositoryServiceError, ObjectDoesNotExist, ValueError, IntegrityError):
            result = {"status": "blocked", "blockers": ["group_sources_or_database_guard_unavailable"]}
        self.stdout.write(json.dumps(result, sort_keys=True))
