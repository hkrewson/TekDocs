"""Operator dry run for the legacy-to-Git document migration."""

from __future__ import annotations

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.core.document_migration_inventory import inventory_legacy_documents
from apps.core.models import InstallationState, Workspace
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Read-only, exact-workspace inventory of legacy documents before Git migration."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True, help="Exact Workspace UUID")

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id = UUID(options["workspace"])
        except (TypeError, ValueError) as exc:
            raise CommandError("A valid workspace UUID is required.") from exc
        installation = InstallationState.objects.select_related("tenant").get(pk=InstallationState.SINGLETON_ID)
        if connection.vendor == "postgresql":
            bind_local_rls_scope(
                DataScope.tenant(installation.tenant),
                organization_mode=OrganizationRLSMode.MSP_ONLY,
                actor_user_id=None,
                principal_mode=RLSPrincipalMode.SYSTEM,
            )
        workspace = Workspace.objects.filter(tenant=installation.tenant, id=workspace_id).first()
        if workspace is None:
            raise CommandError("The workspace is unavailable.")
        if connection.vendor == "postgresql":
            scope = DataScope.owner(workspace.tenant, workspace.organization)
            bind_local_rls_scope(
                scope,
                organization_mode=(
                    OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
                ),
                actor_user_id=None,
                principal_mode=RLSPrincipalMode.SYSTEM,
            )
        self.stdout.write(json.dumps(inventory_legacy_documents(workspace), sort_keys=True))
