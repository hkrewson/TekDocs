"""Operator-only, explicitly acknowledged document authority transition."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.core.document_authority_handoff import (
    DocumentAuthorityHandoffError,
    prepare_rollback_markdown_projection,
    transition_document_authority,
)
from apps.core.document_migration_coexistence import document_coexistence_status
from apps.core.models import Document, DocumentAuthorityMode, InstallationState, Workspace
from apps.core.workspaces import resolve_msp_workspace, resolve_organization_workspace


class Command(BaseCommand):
    help = "Preview or explicitly switch one imported document between PostgreSQL and Git authority."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True, help="Exact Workspace UUID")
        parser.add_argument("--document", required=True, help="Exact Document UUID")
        parser.add_argument("--actor", required=True, help="Installation member UUID for audit attribution")
        parser.add_argument(
            "--authority", required=True, choices=(DocumentAuthorityMode.LEGACY, DocumentAuthorityMode.REPOSITORY)
        )
        parser.add_argument("--apply", action="store_true", help="Apply the reviewed, parity-gated transition")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id, document_id, actor_id = (
                UUID(options[name]) for name in ("workspace", "document", "actor")
            )
        except (TypeError, ValueError) as exc:
            raise CommandError("Valid workspace, document and actor UUIDs are required.") from exc
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        workspace = Workspace.objects.filter(tenant=installation.tenant, id=workspace_id).first()
        document = (
            Document.objects.select_related("organization")
            .filter(id=document_id, entity__workspace_id=workspace_id, tenant=installation.tenant)
            .first()
        )
        actor = User.objects.filter(pk=actor_id, is_active=True).first()
        if workspace is None or document is None or actor is None:
            raise CommandError("Workspace, document or active operator is unavailable.")
        try:
            if document.organization_id is None:
                reader_workspace = resolve_msp_workspace(actor)
            elif document.organization is None:
                raise CommandError("The document's organization is unavailable.")
            else:
                reader_workspace = resolve_organization_workspace(
                    actor, entity_id=document.organization.entity_id
                )
        except Exception as exc:
            raise CommandError("The operator cannot resolve this document's Workspace.") from exc
        if reader_workspace.member.tenant.id != installation.tenant_id:
            raise CommandError("The operator belongs to another installation.")
        status = document_coexistence_status(
            workspace=workspace, document=document, reader_workspace=reader_workspace
        )
        target = options["authority"]
        blockers = cast(list[str], status["handoff_blockers"])
        if target == DocumentAuthorityMode.REPOSITORY:
            if not status["cutover_ready"]:
                blockers = blockers or ["document_not_legacy_authoritative"]
        elif status["authority_state"] != DocumentAuthorityMode.REPOSITORY:
            blockers = ["document_not_repository_authoritative"]
        elif status["content_copy_state"] != "in_sync" or status["read_projection_state"] != "matched":
            try:
                prepare_rollback_markdown_projection(workspace=workspace, document=document)
            except DocumentAuthorityHandoffError as exc:
                blockers.extend(exc.codes)
            else:
                blockers = [
                    blocker
                    for blocker in blockers
                    if blocker not in {"content_copy_not_in_sync", "repository_read_projection_not_matched"}
                ]
        if blockers:
            self.stdout.write(json.dumps({"status": "blocked", "blockers": sorted(set(blockers))}, sort_keys=True))
            return
        if not options["apply"]:
            self.stdout.write(json.dumps({"status": "ready", "authority": target}, sort_keys=True))
            return
        try:
            result = transition_document_authority(
                workspace=workspace,
                document_id=document_id,
                actor_id=actor_id,
                target=target,
                reader_workspace=reader_workspace,
            )
        except DocumentAuthorityHandoffError as exc:
            self.stdout.write(json.dumps({"status": "blocked", "blockers": exc.codes}, sort_keys=True))
            return
        self.stdout.write(json.dumps({"status": result, "authority": target}, sort_keys=True))
