"""Preview one deterministic first-wave export without accepting a Git commit."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.core.content_index import ContentIndexValidationError, validate_candidate_snapshot
from apps.core.content_profile import ContentProfileError
from apps.core.document_migration_export import (
    DocumentMigrationBindingError,
    DocumentMigrationExportError,
    DocumentMigrationFileError,
    DocumentMigrationReferenceError,
    DocumentMigrationTopicError,
    build_simple_document_export,
)
from apps.core.document_migration_import import fingerprint_document_import
from apps.core.document_migration_inventory import inventory_legacy_documents
from apps.core.models import Document, InstallationState, Workspace, WorkspaceRepository
from apps.core.repository_service import RepositoryServiceError, read_accepted_repository_markdown_files
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Preview exact source digests and parity for one owned-placement legacy document; never commit Git."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--workspace", required=True, help="Exact Workspace UUID")
        parser.add_argument("--document", required=True, help="Exact legacy Document UUID")

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            workspace_id = UUID(options["workspace"])
            document_id = UUID(options["document"])
        except (TypeError, ValueError) as exc:
            raise CommandError("Valid workspace and document UUIDs are required.") from exc
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
            bind_local_rls_scope(
                DataScope.owner(workspace.tenant, workspace.organization),
                organization_mode=(
                    OrganizationRLSMode.ORGANIZATION if workspace.organization_id else OrganizationRLSMode.MSP_ONLY
                ),
                actor_user_id=None,
                principal_mode=RLSPrincipalMode.SYSTEM,
            )
        inventory = inventory_legacy_documents(workspace)
        row = next((item for item in inventory["documents"] if item["document_id"] == str(document_id)), None)
        if row is None:
            raise CommandError("The document is unavailable in this workspace.")
        blockers = list(inventory["repository_blockers"]) + list(row["reasons"])
        result = {"workspace_id": str(workspace.id), "document_id": str(document_id), "read_only": True}
        if blockers:
            result.update({"eligible": False, "blockers": sorted(blockers)})
        else:
            repository = WorkspaceRepository.objects.get(workspace=workspace)
            document = Document.objects.select_related("entity").get(id=document_id)
            try:
                export = build_simple_document_export(document, verify_attachments=True)
                if repository.accepted_commit_id is None:
                    raise DocumentMigrationExportError("Repository has no accepted commit")
                accepted, current = read_accepted_repository_markdown_files(repository_id=repository.id)
                if export.reference_commit is not None and export.reference_commit != accepted.object_id:
                    raise DocumentMigrationReferenceError("repository_changed")
                candidate = dict(current)
                if any(path in candidate for path, _source in export.files):
                    raise DocumentMigrationExportError("Export destination already exists")
                candidate.update(export.files)
                validate_candidate_snapshot(repository=repository, files=tuple(sorted(candidate.items())))
            except ContentProfileError as exc:
                result.update({"eligible": False, "blockers": [exc.code]})
            except (
                DocumentMigrationReferenceError,
                DocumentMigrationTopicError,
                DocumentMigrationFileError,
                DocumentMigrationBindingError,
            ) as exc:
                result.update({"eligible": False, "blockers": [exc.code]})
            except ContentIndexValidationError as exc:
                result.update(
                    {
                        "eligible": False,
                        "blockers": sorted({str(item["code"]) for item in exc.diagnostics}),
                    }
                )
            except (DocumentMigrationExportError, RepositoryServiceError) as exc:
                result.update({"eligible": False, "blockers": [type(exc).__name__]})
            else:
                pinned_commits = dict(export.pinned_commits)
                result.update(
                    {
                        "eligible": True,
                        "base_commit": accepted.object_id,
                        "plan_sha256": fingerprint_document_import(base_commit=accepted.object_id, export=export),
                        "block_id": str(export.block_id),
                        "revision_id": str(export.revision_id),
                        "blocks": [
                            {"block_id": str(block_id), "revision_id": str(revision_id)}
                            for block_id, revision_id in export.blocks
                        ],
                        "referenced_blocks": [
                            {
                                "block_id": str(content_id),
                                "content_digest": digest,
                                **(
                                    {"pinned_commit": pinned_commits[content_id]}
                                    if content_id in pinned_commits
                                    else {}
                                ),
                            }
                            for content_id, digest in export.referenced_digests
                        ],
                        "resolved_markdown_sha256": export.resolved_markdown_sha256,
                        "attachment_count": len(export.attachment_digests),
                        "key_binding_count": len(export.key_binding_ids),
                        "files": [
                            {"path": path, "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source)}
                            for path, source in export.files
                        ],
                    }
                )
        self.stdout.write(json.dumps(result, sort_keys=True))
