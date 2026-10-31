from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import (
    document_migration_attachments,
    document_migration_coexistence,
    document_migration_import,
    repository_storage,
)
from apps.core.content_authoring import _replace_fields, author_content, read_authored_content
from apps.core.content_index import ContentIndexError, index_repository_content
from apps.core.content_profile import parse_content
from apps.core.document_attachments import (
    append_repository_primary_document_file,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.document_exports import resolve_export_snapshot
from apps.core.document_migration_export import DocumentMigrationExportError, build_simple_document_export
from apps.core.document_migration_inventory import inventory_legacy_documents
from apps.core.document_operations import (
    DocumentOperationsError,
    decide_document_review,
    request_document_review,
    update_document_operations,
)
from apps.core.documents import (
    PlacementConflict,
    add_document_placement,
    create_document,
    create_document_block,
    resolve_document,
    update_document,
)
from apps.core.models import (
    BlockKind,
    BlockRevision,
    ContentEntityLink,
    ContentFinding,
    ContentInclude,
    ContentLink,
    ContentNode,
    ContentProperty,
    DocumentAttachmentPurpose,
    DocumentAuthority,
    DocumentAuthorityMode,
    DocumentKeyBinding,
    DocumentReviewState,
    DocumentTopicType,
    Entity,
    EntityLink,
    EntityLinkType,
    InstallationState,
    PlacementResolutionMode,
    TaxonomyBinding,
    Workspace,
    WorkspaceKind,
    WorkspaceRepository,
)
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, verify_retained_publication_custody
from apps.core.repository_editable_bundle_validation import verify_repository_editable_bundle
from apps.core.repository_editable_bundles import export_repository_editable_bundle
from apps.core.repository_primary_publication import prepare_repository_primary_publication
from apps.core.repository_publication_evidence import (
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from apps.core.repository_service import (
    RepositoryAuditAttribution,
    RepositoryConflictError,
    RepositoryInputError,
    RepositoryServiceError,
    commit_repository_files,
    pin_accepted_repository_for_publication,
)
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.taxonomies import assign_document_terms, create_local_term, create_taxonomy, revise_taxonomy
from apps.core.tests.network_asset_fixtures import create_network_hardware_asset
from apps.core.topic_schemas import inspect_markdown
from apps.core.workspaces import resolve_msp_workspace

pytestmark = pytest.mark.django_db(transaction=True)


def _preview_document_migration(**options):
    """Exercise every preview shape with PostgreSQL refusing database writes."""
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
        return call_command("preview_document_migration", **options)


def test_mixed_authority_browse_retains_legacy_documents(tmp_path, django_runtime_role):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Mixed Authority MSP",
            owner_email=f"mixed-{uuid.uuid4()}@example.invalid",
            owner_display_name="Mixed Owner",
            password="MigrationPassword-2026!",
        )
        other = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id,
            name="Other client", legal_name="", website="", classifications=[],
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=WorkspaceRepository.objects.get(workspace=workspace).id)
        documents = [
            create_document(
                tenant=installation.tenant, organization=None, actor_id=installation.owner.id,
                title=title, markdown="Synthetic setup instructions.\n",
            )
            for title in ("Alpha repository guide", "Zulu legacy guide")
        ]
        browser = Client()
        browser.force_login(installation.owner)
        url = reverse("msp-document-search")
        assert browser.get(url).json()["count"] == 2
        prepared = document_migration_import.prepare_document_import(
            workspace=workspace, document_id=documents[0].id,
        )
        imported = document_migration_import.apply_document_import(
            workspace=workspace, document_id=documents[0].id,
            expected_base=prepared.base_commit, plan_sha256=prepared.plan_sha256,
            actor_id=installation.owner.id,
        )
        assert imported.indexed
        output = io.StringIO()
        call_command(
            "transition_document_authority", workspace=str(workspace.id),
            document=str(documents[0].id), actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.REPOSITORY, apply=True, stdout=output,
        )
        assert json.loads(output.getvalue())["status"] == "transitioned"
        # Replay the Documentation client: its public ID comes from the list.
        listed = browser.get(url).json()["results"]
        promoted = next(item for item in listed if item["content_authority"] == "repository")
        assert promoted["content_id"] == str(documents[0].id)
        assert promoted["content_id"] != promoted["id"]
        detail = browser.get(f"/api/v1/workspaces/msp/content-graph/documents/{promoted['content_id']}")
        assert detail.status_code == 200, detail.content
        assert "Synthetic setup instructions." in detail.json()["sanitized_html"]
        root = ContentNode.objects.get(repository__workspace=workspace, content_id=documents[0].id)
        assert root.markdown.strip() == ""
        assert ContentInclude.objects.filter(source=root).exists()
        # Raw root Markdown may be empty; the reader must resolve its fragments.
        assert detail.json()["id"] == str(documents[0].id)
        assert browser.get(f"/api/v1/workspaces/msp/content-graph/documents/{promoted['id']}").status_code == 404
        assert browser.get(
            f"/api/v1/workspaces/organizations/{other.entity_id}/content-graph/documents/{promoted['content_id']}"
        ).status_code == 404
        repository = WorkspaceRepository.objects.get(workspace=workspace)
        indexed_commit = repository.indexed_commit
        repository.indexed_commit = None
        repository.save(update_fields=["indexed_commit"])
        try:
            stale = browser.get(f"/api/v1/workspaces/msp/content-graph/documents/{promoted['content_id']}")
            assert stale.status_code == 409
            assert "Synthetic setup instructions." not in stale.content.decode()
        finally:
            repository.indexed_commit = indexed_commit
            repository.save(update_fields=["indexed_commit"])
        search = browser.get(url, {"q": "Zulu"}).json()
        assert search["count"] == 1
        assert search["results"][0]["id"] == str(documents[1].entity_id)
        browse = browser.get(url).json()
        assert browse["count"] == 2
        assert {item["id"] for item in browse["results"]} == {
            str(document.entity_id) for document in documents
        }
        assert {item["content_authority"] for item in browse["results"]} == {"legacy", "repository"}
        page = browser.get(url, {"page_size": 1, "page": 2}).json()
        assert page["count"] == 2
        assert page["results"][0]["id"] == str(documents[1].entity_id)
        excluded = browser.get(url, {"exclude_document": str(documents[0].entity_id)}).json()
        assert excluded["count"] == 1
        assert excluded["results"][0]["id"] == str(documents[1].entity_id)
        assert browser.get(url, {"q": "absent phrase"}).json()["count"] == 0
        assert browser.get(url, {"template": "templates"}).json()["count"] == 0


def test_repository_authority_allows_git_edits_for_a_migrated_document(tmp_path, django_runtime_role):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"), MEDIA_ROOT=str(tmp_path / "media")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Authority Write MSP",
            owner_email=f"authority-write-{uuid.uuid4()}@example.invalid",
            owner_display_name="Authority Write Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        repository = WorkspaceRepository.objects.get(workspace=workspace)
        repository.refresh_from_db()
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Device repair guide",
            markdown="Legacy-only body.\n",
        )
        document.collection = "Device setup"
        document.tags = ["enrollment", "repair"]
        document.save(update_fields=("collection", "tags", "updated_at"))
        original_primary = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("setup.txt", b"Original setup file.\n"),
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
            version_number=1,
        )
        original_attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("checklist.txt", b"Original checklist.\n"),
        )
        export = build_simple_document_export(document)
        copied = commit_repository_files(
            repository_id=repository.id,
            expected_base=repository.accepted_commit.object_id if repository.accepted_commit else None,
            changes=dict(export.files),
            message="Copy document for authority test",
        )
        index_repository_content(repository_id=repository.id)
        legacy_primary_snapshot = prepare_repository_primary_publication(
            repository=repository,
            content_id=document.id,
            expected_current_entity_id=original_primary.entity_id,
        )
        assert legacy_primary_snapshot.versions[-1].descriptor["owner"] == {
            "type": "legacy_document",
            "id": str(document.id),
        }
        browser = Client()
        browser.force_login(installation.owner)
        repository_download_url = reverse(
            "msp-content-document-attachment-download",
            kwargs={"content_id": document.id, "attachment_entity_id": original_primary.entity_id},
        )
        assert browser.get(repository_download_url).status_code == 404
        reviewed_at = timezone.now()
        document.review_state = DocumentReviewState.APPROVED
        document.reviewer_id = installation.owner.id
        document.review_decided_at = reviewed_at
        document.review_note = "Historical approval from before Git reconciliation."
        document.last_reviewed_by_id = installation.owner.id
        document.last_reviewed_at = reviewed_at
        document.review_content_sha256 = "0" * 64
        document.save(
            update_fields=(
                "review_state",
                "reviewer",
                "review_decided_at",
                "review_note",
                "last_reviewed_by",
                "last_reviewed_at",
                "review_content_sha256",
                "updated_at",
            )
        )
        handoff_preview = io.StringIO()
        call_command(
            "transition_document_authority",
            workspace=str(workspace.id),
            document=str(document.id),
            actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.REPOSITORY,
            stdout=handoff_preview,
        )
        assert json.loads(handoff_preview.getvalue()) == {
            "blockers": ["review_workflow_parity_not_verified"],
            "status": "blocked",
        }
        refreshed_review = request_document_review(
            workspace=resolve_msp_workspace(installation.owner),
            document=document,
            actor_id=installation.owner.id,
            reviewer_id=installation.owner.id,
            note="Re-review the current indexed Git composition.",
        )
        assert refreshed_review.review_content_sha256 == hashlib.sha256(
            ContentNode.objects.get(repository=repository, content_id=document.id)
            .composition_variants["all"]["markdown"]
            .encode("utf-8")
        ).hexdigest()
        decide_document_review(
            document=refreshed_review,
            actor_id=installation.owner.id,
            decision=DocumentReviewState.APPROVED,
            note="Reviewed and approved against the current Git composition.",
        )
        handoff_preview = io.StringIO()
        call_command(
            "transition_document_authority",
            workspace=str(workspace.id),
            document=str(document.id),
            actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.REPOSITORY,
            stdout=handoff_preview,
        )
        assert json.loads(handoff_preview.getvalue()) == {
            "authority": DocumentAuthorityMode.REPOSITORY,
            "status": "ready",
        }
        handoff_output = io.StringIO()
        call_command(
            "transition_document_authority",
            workspace=str(workspace.id),
            document=str(document.id),
            actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.REPOSITORY,
            apply=True,
            stdout=handoff_output,
        )
        assert json.loads(handoff_output.getvalue())["status"] == "transitioned"
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == (
            DocumentAuthorityMode.REPOSITORY
        )
        replacement_primary = append_repository_primary_document_file(
            repository=repository,
            content_id=document.id,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("updated-setup.txt", b"Updated setup file.\n"),
            expected_current_entity_id=original_primary.entity_id,
        )
        prepared_primary = prepare_repository_primary_publication(
            repository=repository,
            content_id=document.id,
            expected_current_entity_id=replacement_primary.entity_id,
        )
        assert [version.content for version in prepared_primary.versions] == [
            b"Original setup file.\n",
            b"Updated setup file.\n",
        ]
        assert [version.descriptor["owner"] for version in prepared_primary.versions] == [
            {"type": "repository_document", "id": str(document.id)},
            {"type": "repository_document", "id": str(document.id)},
        ]
        files = browser.get(reverse("msp-document-file-list")).json()["results"]
        git_owned_file = next(item for item in files if item["id"] == str(replacement_primary.entity_id))
        assert git_owned_file["source"] == "repository"
        assert git_owned_file["download_url"] == reverse(
            "msp-content-document-attachment-download",
            kwargs={"content_id": document.id, "attachment_entity_id": replacement_primary.entity_id},
        )
        assert b"".join(browser.get(git_owned_file["download_url"]).streaming_content) == b"Updated setup file.\n"
        git_owned_attachment = next(item for item in files if item["id"] == str(original_attachment.entity_id))
        assert git_owned_attachment["source"] == "repository"
        assert b"".join(browser.get(git_owned_attachment["download_url"]).streaming_content) == b"Original checklist.\n"
        Authenticator.objects.create(
            user=installation.owner,
            type=Authenticator.Type.TOTP,
            data={"secret": generate_totp_secret()},
        )
        evidence = retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=document.id,
            audience="msp_internal",
            actor=installation.owner,
        )
        assert {
            (item["owner"]["type"], item["owner"]["id"])
            for item in evidence.manifest["primary_file"]["versions"]
        } == {("repository_document", str(document.id))}
        assert verify_repository_publication_evidence(evidence)["valid"]
        repository_owned_detail = browser.get(
            reverse("msp-document-detail", kwargs={"document_entity_id": document.entity_id})
        ).json()
        assert repository_owned_detail["collection"] == "Device setup"
        assert repository_owned_detail["tags"] == ["enrollment", "repair"]
        with pytest.raises(DocumentOperationsError, match="indexed Git metadata"):
            update_document_operations(
                workspace=resolve_msp_workspace(installation.owner),
                document=document,
                actor_id=installation.owner.id,
                owner_id=None,
                review_due_on=None,
                collection="Stale collection",
                tags=["stale"],
            )
        canonical_review_markdown = ContentNode.objects.get(
            repository=repository, content_id=document.id
        ).composition_variants["all"]["markdown"]
        reviewed = request_document_review(
            workspace=resolve_msp_workspace(installation.owner),
            document=document,
            actor_id=installation.owner.id,
            reviewer_id=installation.owner.id,
            note="Review the Git-authoritative copy",
        )
        assert reviewed.review_content_sha256 == hashlib.sha256(canonical_review_markdown.encode("utf-8")).hexdigest()
        decide_document_review(
            document=reviewed,
            actor_id=installation.owner.id,
            decision=DocumentReviewState.APPROVED,
            note="Approved after reviewing canonical Git content",
        )
        document.refresh_from_db()
        document.review_state = DocumentReviewState.UNREVIEWED
        document.review_requested_by = None
        document.review_requested_at = None
        document.review_content_sha256 = None
        document.reviewer = None
        document.review_decided_at = None
        document.review_note = ""
        document.last_reviewed_by = None
        document.last_reviewed_at = None
        document.save(
            update_fields=(
                "review_state",
                "review_requested_by",
                "review_requested_at",
                "review_content_sha256",
                "reviewer",
                "review_decided_at",
                "review_note",
                "last_reviewed_by",
                "last_reviewed_at",
                "updated_at",
            )
        )
        publication = publish_document(
            workspace=resolve_msp_workspace(installation.owner),
            document=document,
            actor_id=installation.owner.id,
            reason="Verify file-bearing Git authority",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v6"
        assert {item["id"] for item in publication.manifest["managed_files"]} == {
            str(original_primary.entity_id), str(replacement_primary.entity_id), str(original_attachment.entity_id),
        }
        assert verify_retained_publication_custody(publication)
        repository_export = resolve_export_snapshot(
            workspace=resolve_msp_workspace(installation.owner), document=document
        )
        assert repository_export.markdown == canonical_review_markdown
        assert repository_export.manifest["repository_source"]["accepted_commit"] == (
            workspace.repository.accepted_commit.object_id
        )
        assert repository_export.manifest["placements"] == []
        fragment = read_authored_content(repository=repository, content_id=export.block_id)
        # A migrated owner in this repository must not freeze native Git files.
        native = author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="create", content_id=uuid.uuid4(), base_commit=fragment.accepted_commit,
            base_blob=None, kind="document", path="docs/native-during-handoff.md",
            title="Native guide", markdown="Native body.\n", metadata_patch={},
        )
        native = author_content(
            repository=repository, actor_id=installation.owner.id, request_id=None,
            operation="update", content_id=native.content_id, base_commit=native.accepted_commit,
            base_blob=native.source_blob, kind=None, path=None, title="Renamed native guide",
            markdown="Updated native body.\n", metadata_patch={"properties": {"collection": "Native"}},
        )
        assert native.title == "Renamed native guide"
        assert native.markdown == "Updated native body.\n"
        sibling = create_organization(
            tenant=installation.tenant, actor_id=installation.owner.id, name="Other handoff workspace",
            legal_name="", website="", classifications=["client"],
        )
        sibling_workspace = Workspace.objects.get(tenant=installation.tenant, organization=sibling)
        sibling_repository = repository_storage.ensure_workspace_repository(sibling_workspace).repository
        sibling_repository.refresh_from_db()
        with django_runtime_role(), transaction.atomic():
            bind_local_rls_scope(
                DataScope.organization(installation.tenant, sibling),
                organization_mode=OrganizationRLSMode.ORGANIZATION,
                actor_user_id=installation.owner.id, principal_mode=RLSPrincipalMode.USER,
            )
            sibling_native = author_content(
                repository=sibling_repository, actor_id=installation.owner.id, request_id=None,
                operation="create", content_id=uuid.uuid4(),
                base_commit=(sibling_repository.accepted_commit.object_id
                             if sibling_repository.accepted_commit else None),
                base_blob=None, kind="document", path=None, title="Sibling native guide",
                markdown="Unrelated workspace remains editable.\n", metadata_patch={},
            )
            assert sibling_native.markdown == "Unrelated workspace remains editable.\n"
        # Organization creation updates the MSP directory manifest; index that
        # accepted commit before exercising the authority transition pin.
        index_repository_content(repository_id=repository.id)
        fragment = read_authored_content(repository=repository, content_id=export.block_id)
        # Unsupported writes must fail before accepting any Git commit.
        root_source = read_authored_content(repository=repository, content_id=document.id)
        # A transition pin excludes a writer before it can acquire the row lock
        # or advance Git; releasing the pin makes normal validation available.
        with pin_accepted_repository_for_publication(repository.id):
            with patch("apps.core.repository_service.LOCK_TIMEOUT_SECONDS", 0.01):
                with pytest.raises(RepositoryConflictError, match="busy"):
                    commit_repository_files(
                        repository_id=repository.id, expected_base=root_source.accepted_commit,
                        changes={f"docs/{document.id}.md": root_source.source.encode()},
                        message="Writer cannot race a pinned authority transition",
                    )
        root_path = f"docs/{document.id}.md"
        fragment_path = f"fragments/{export.block_id}.md"
        root_bytes, fragment_bytes = root_source.source.encode(), fragment.source.encode()
        rejected_changes = [
            {root_path: _replace_fields(root_bytes, {"title": "Would strand rollback"}, None)},
            {root_path: _replace_fields(root_bytes, {"id": str(uuid.uuid4())}, None)},
            {fragment_path: _replace_fields(fragment_bytes, {"id": str(uuid.uuid4())}, None)},
            {root_path: _replace_fields(root_bytes, {}, "Root body is not reversible.\n")},
            {root_path: _replace_fields(root_bytes, {"properties": {"collection": "Changed"}}, None)},
            {root_path: _replace_fields(root_bytes, {"includes": None}, None)},
            {fragment_path: _replace_fields(fragment_bytes, {"title": "Changed fragment"}, None)},
            {fragment_path: None},
            {root_path: None, "docs/moved.md": root_bytes},
            {"fragments/duplicate.md": fragment_bytes},
            {"fragments/duplicate.MD": fragment_bytes},
        ]
        for changes in rejected_changes:
            with django_runtime_role(), transaction.atomic():
                bind_local_rls_scope(
                    DataScope.tenant(installation.tenant),
                    organization_mode=OrganizationRLSMode.MSP_ONLY,
                    actor_user_id=installation.owner.id,
                    principal_mode=RLSPrincipalMode.USER,
                )
                with pytest.raises(RepositoryInputError, match="reversible"):
                    commit_repository_files(
                        repository_id=repository.id,
                        expected_base=root_source.accepted_commit,
                        changes=changes,
                        message="Reject unsupported migrated content edit",
                    )
            repository.refresh_from_db()
            assert repository.accepted_commit.object_id == root_source.accepted_commit
            assert read_authored_content(repository=repository, content_id=document.id).source == root_source.source
            assert read_authored_content(repository=repository, content_id=export.block_id).source == fragment.source

        # The session route exposes the same actionable denial under runtime RLS.
        with django_runtime_role():
            denied = browser.post(reverse("msp-content-authoring"), data=json.dumps({
                "operation": "update", "content_id": str(document.id),
                "base_commit": root_source.accepted_commit, "base_blob": root_source.source_blob,
                "title": "Unsupported root title", "metadata_patch": {},
            }), content_type="application/json")
        assert denied.status_code == 400, denied.content
        assert "reversible" in denied.json()["detail"]
        with django_runtime_role(), transaction.atomic():
            bind_local_rls_scope(
                DataScope.tenant(installation.tenant),
                organization_mode=OrganizationRLSMode.MSP_ONLY,
                actor_user_id=installation.owner.id,
                principal_mode=RLSPrincipalMode.USER,
            )
            authored_fragment = author_content(
                repository=repository,
                actor_id=installation.owner.id,
                request_id=None,
                operation="update",
                content_id=export.block_id,
                base_commit=fragment.accepted_commit,
                base_blob=fragment.source_blob,
                kind=None,
                path=None,
                title=None,
                markdown="Git-only repair steps retained on rollback.\n",
                metadata_patch={},
            )
        assert authored_fragment.accepted_commit != copied.object_id
        legacy_revision_before_rollback = document.placements.get(
            parent__isnull=True, position=0
        ).block.current_revision
        rollback_handoff = io.StringIO()
        call_command(
            "transition_document_authority",
            workspace=str(workspace.id),
            document=str(document.id),
            actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.LEGACY,
            apply=True,
            stdout=rollback_handoff,
        )
        rollback_result = json.loads(rollback_handoff.getvalue())
        assert rollback_result["status"] == "transitioned", rollback_result
        legacy_revision_after_rollback = BlockRevision.objects.get(
            block_id=export.block_id, revision_number=legacy_revision_before_rollback.revision_number + 1
        )
        assert legacy_revision_after_rollback.parent_id == legacy_revision_before_rollback.id
        assert legacy_revision_after_rollback.markdown == authored_fragment.markdown
        assert resolve_document(document).markdown == authored_fragment.markdown
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == (
            DocumentAuthorityMode.LEGACY
        )
        rolled_back_primary = prepare_repository_primary_publication(
            repository=repository,
            content_id=document.id,
            expected_current_entity_id=replacement_primary.entity_id,
        )
        assert [version.descriptor["owner"] for version in rolled_back_primary.versions] == [
            {"type": "legacy_document", "id": str(document.id)},
            {"type": "legacy_document", "id": str(document.id)},
        ]
        assert verify_repository_publication_evidence(evidence)["valid"]
        rolled_back_files = browser.get(reverse("msp-document-file-list"), {"kind": "primary"}).json()["results"]
        rolled_back_primary_file = next(
            item for item in rolled_back_files if item["id"] == str(replacement_primary.entity_id)
        )
        assert rolled_back_primary_file["source"] == "legacy"
        assert rolled_back_primary_file["download_url"] == reverse(
            "msp-document-attachment-download",
            kwargs={"document_entity_id": document.entity_id, "attachment_entity_id": replacement_primary.entity_id},
        )
        source = read_authored_content(repository=repository, content_id=document.id)
        assert source.accepted_commit == authored_fragment.accepted_commit

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
            authority = DocumentAuthority.objects.get(workspace=workspace, content_id=document.id)
            authority.authority = DocumentAuthorityMode.REPOSITORY
            authority.save(update_fields=("authority", "updated_at"))
            with pytest.raises(PlacementConflict, match="Git-authoritative"):
                update_document(
                    document=document,
                    actor_id=installation.owner.id,
                    title="Legacy write must fail",
                    markdown="Not canonical.\n",
                    base_revision_id=export.revision_id,
                )
            # Simulate an already-accepted pre-guard snapshot. Normal writes above
            # must refuse this; rollback must still fail closed for historical drift.
            with patch("apps.core.document_reversible_writes.guard_reversible_migration_write"):
                authored = author_content(
                    repository=repository,
                    actor_id=installation.owner.id,
                    request_id=None,
                    operation="update",
                    content_id=document.id,
                    base_commit=source.accepted_commit,
                    base_blob=source.source_blob,
                    kind=None,
                    path=None,
                    title=None,
                    markdown="Git-only repair steps.\n",
                    metadata_patch={"properties": {"collection": "Git collection", "tags": ["Git tag"]}},
                )

        structural_rollback = io.StringIO()
        call_command(
            "transition_document_authority",
            workspace=str(workspace.id),
            document=str(document.id),
            actor=str(installation.owner.id),
            authority=DocumentAuthorityMode.LEGACY,
            stdout=structural_rollback,
        )
        structural_result = json.loads(structural_rollback.getvalue())
        assert structural_result["status"] == "blocked"
        assert "rollback_root_metadata_changed" in structural_result["blockers"]

        assert authored.markdown == "Git-only repair steps.\n"
        assert authored.accepted_commit == authored.indexed_commit
        assert resolve_document(document).markdown == authored_fragment.markdown
        browser = Client()
        browser.force_login(installation.owner)
        canonical_hits = browser.get(reverse("msp-document-search"), {"q": "Git-only repair"}).json()
        assert canonical_hits["count"] == 1
        assert canonical_hits["results"][0]["content_authority"] == "repository"
        assert canonical_hits["results"][0]["collection"] == "Git collection"
        assert canonical_hits["results"][0]["tags"] == ["Git tag"]
        assert "Git-only repair steps" in canonical_hits["results"][0]["matching_excerpt"]
        metadata_filter = browser.get(reverse("msp-document-search"), {"collection": "Git collection"}).json()
        assert {item["id"] for item in metadata_filter["results"]} == {str(document.entity_id)}
        indexed_node = ContentNode.objects.get(repository=repository, content_id=document.id)
        assert indexed_node.markdown == "Git-only repair steps.\n"
        assert authored_fragment.markdown in indexed_node.composition_variants["msp_internal"]["markdown"]
        stale_hits = browser.get(reverse("msp-document-search"), {"q": "Git-only repair steps retained"}).json()
        assert str(document.entity_id) in {item["id"] for item in stale_hits["results"]}
        repository.refresh_from_db()
        indexed_commit_id = repository.indexed_commit_id
        repository.indexed_commit = None
        repository.save(update_fields=("indexed_commit", "updated_at"))
        pending = browser.get(reverse("msp-document-search"), {"q": "Git-only repair"})
        assert pending.status_code == 409
        repository.indexed_commit_id = indexed_commit_id
        repository.save(update_fields=("indexed_commit", "updated_at"))


def test_field_key_bindings_are_portable_preview_bound_and_reader_scoped(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Key migration MSP",
            owner_email=f"key-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Key Migration Owner",
            password="MigrationPassword-2026!",
        )
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Key client",
            legal_name="Key client",
            website="",
            classifications=["client"],
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        first = create_network_hardware_asset(installation=installation, organization=organization, name="First laptop")
        second = create_network_hardware_asset(
            installation=installation, organization=organization, name="Second laptop"
        )
        document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Laptop guide",
            markdown="Device <tekdocs://key/subject.name>.\n",
        )
        binding = DocumentKeyBinding.objects.create(
            tenant=installation.tenant,
            workspace=workspace,
            organization=organization,
            document=document,
            name="subject",
            target_entity=first.entity,
            created_by=installation.owner,
        )
        row = next(
            item
            for item in inventory_legacy_documents(workspace)["documents"]
            if item["document_id"] == str(document.id)
        )
        assert row["disposition"] == "simple_candidate"
        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
        )
        preview = json.loads(output.getvalue())
        assert preview["eligible"] is True, preview
        assert preview["key_binding_count"] == 1
        export = build_simple_document_export(document)
        root = parse_content(dict(export.files)[f"docs/{document.id}.md"])
        assert root.frontmatter["key_bindings"] == {"subject": str(first.entity_id)}
        assert "First laptop" not in b"".join(source for _path, source in export.files).decode()

        binding.target_entity = second.entity
        binding.save(update_fields=("target_entity", "updated_at"))
        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["blockers"] == ["preview_changed"]
        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
        )
        revised_preview = json.loads(output.getvalue())
        assert revised_preview["plan_sha256"] != preview["plan_sha256"]
        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=revised_preview["base_commit"],
            plan_sha256=revised_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        imported = json.loads(output.getvalue())
        assert imported["status"] == "imported", imported
        browser = Client()
        browser.force_login(installation.owner)
        detail_url = reverse(
            "organization-content-document-detail",
            kwargs={"organization_entity_id": organization.entity_id, "content_id": document.id},
        )
        detail = browser.get(detail_url)
        assert detail.status_code == 200, detail.content
        assert "Second laptop" in detail.json()["sanitized_html"]
        assert "First laptop" not in detail.json()["sanitized_html"]
        assert "tekdocs://key/" not in detail.json()["sanitized_html"]
        assert Client().get(detail_url).status_code in {401, 403}

        second.entity.display_name = "Renamed laptop"
        second.entity.save(update_fields=("display_name", "updated_at"))
        assert "Renamed laptop" in browser.get(detail_url).json()["sanitized_html"]
        status_url = reverse(
            "organization-document-migration-status",
            kwargs={"organization_entity_id": organization.entity_id, "document_entity_id": document.entity_id},
        )
        matched_status = browser.get(status_url).json()
        assert matched_status["read_projection_state"] == "matched"
        # Field-key values and permissions remain PostgreSQL-authoritative;
        # matching portable references and rendered output do not block handoff.
        assert "field_key_authority_not_transferred" not in matched_status["handoff_blockers"]
        binding.archived_at = timezone.now()
        binding.save(update_fields=("archived_at", "updated_at"))
        assert "Unresolved key" in browser.get(detail_url).json()["sanitized_html"]
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        binding.archived_at = None
        binding.save(update_fields=("archived_at", "updated_at"))

        output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["status"] == "rolled_back"
        assert DocumentKeyBinding.objects.get(pk=binding.id).target_entity_id == second.entity_id


def test_circular_content_keys_remain_blocked_from_document_copy(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Content key migration MSP",
            owner_email=f"content-key-{uuid.uuid4()}@example.invalid",
            owner_display_name="Content Key Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Content key guide",
            markdown="<tekdocs://key/procedure.content>\n",
        )
        block = document.placements.get().block
        DocumentKeyBinding.objects.create(
            tenant=installation.tenant,
            workspace=workspace,
            organization=None,
            document=document,
            name="procedure",
            target_entity=block.entity,
            created_by=installation.owner,
        )
        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
        )
        assert json.loads(output.getvalue())["blockers"] == ["content_key_cycle"]


def test_attachment_links_survive_copy_render_and_rollback(tmp_path, monkeypatch):
    with override_settings(
        TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"),
        MEDIA_ROOT=str(tmp_path / "media"),
    ):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Attachment migration MSP",
            owner_email=f"attachment-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Attachment Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Attachment guide",
            markdown="Initial notes.\n",
        )
        attachment = create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("steps.txt", b"setup steps\n", content_type="text/plain"),
        )
        block = document.placements.get().block
        update_document(
            document=document,
            actor_id=installation.owner.id,
            title="Attachment guide",
            markdown=f"[Setup steps](tekdocs://attachment/{attachment.entity_id})\n",
            base_revision_id=block.current_revision_id,
        )
        row = next(
            item
            for item in inventory_legacy_documents(workspace)["documents"]
            if item["document_id"] == str(document.id)
        )
        assert row["disposition"] == "simple_candidate"
        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
        )
        preview = json.loads(output.getvalue())
        assert preview["eligible"] is True, preview
        assert preview["attachment_count"] == 1
        assert b"setup steps" not in b"".join(source for _path, source in build_simple_document_export(document).files)

        create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("extra.txt", b"extra proof\n", content_type="text/plain"),
        )
        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["blockers"] == ["preview_changed"]
        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
        )
        revised_preview = json.loads(output.getvalue())
        assert revised_preview["attachment_count"] == 2
        assert revised_preview["plan_sha256"] != preview["plan_sha256"]

        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=revised_preview["base_commit"],
            plan_sha256=revised_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        imported = json.loads(output.getvalue())
        assert imported["status"] == "imported", imported
        browser = Client()
        browser.force_login(installation.owner)
        detail = browser.get(reverse("msp-content-document-detail", kwargs={"content_id": document.id}))
        assert detail.status_code == 200, detail.content
        html = detail.json()["sanitized_html"]
        assert "steps.txt · 12 bytes" in html
        assert "tekdocs://attachment/" not in html
        assert str(attachment.entity_id) in html
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        assert browser.get(status_url).json()["read_projection_state"] == "matched"
        with monkeypatch.context() as patch:
            patch.setattr(
                document_migration_coexistence,
                "read_accepted_repository_file",
                lambda **_kwargs: b"changed source",
            )
            source_status = browser.get(status_url).json()
        assert source_status["content_copy_state"] == "diverged"
        assert source_status["read_projection_state"] == "not_checked"
        assert "content_copy_not_in_sync" in source_status["handoff_blockers"]
        assert "changed source" not in json.dumps(source_status)

        def missing_source(**_kwargs):
            raise RepositoryServiceError("unavailable Git object")

        with monkeypatch.context() as patch:
            patch.setattr(document_migration_coexistence, "read_accepted_repository_file", missing_source)
            missing_source_status = browser.get(status_url).json()
        assert missing_source_status["content_copy_state"] == "diverged"
        assert missing_source_status["read_projection_state"] == "not_checked"
        assert "unavailable Git object" not in json.dumps(missing_source_status)
        assert browser.get(status_url).json()["read_projection_state"] == "matched"
        download = browser.get(
            reverse(
                "msp-document-attachment-download",
                kwargs={"document_entity_id": document.entity_id, "attachment_entity_id": attachment.entity_id},
            )
        )
        assert download.status_code == 200
        assert b"".join(download.streaming_content) == b"setup steps\n"

        retained_path = Path(attachment.file.path)
        retained_path.write_bytes(b"changed steps\n")
        damaged_status = browser.get(status_url).json()
        assert damaged_status["content_copy_state"] == "diverged"
        assert damaged_status["read_projection_state"] == "not_checked"
        assert "content_copy_not_in_sync" in damaged_status["handoff_blockers"]
        assert "changed steps" not in json.dumps(damaged_status)
        retained_path.write_bytes(b"setup steps\n")
        assert browser.get(status_url).json()["read_projection_state"] == "matched"
        retained_path.unlink()
        missing_status = browser.get(status_url).json()
        assert missing_status["content_copy_state"] == "diverged"
        assert missing_status["read_projection_state"] == "not_checked"
        retained_path.write_bytes(b"setup steps\n")
        assert browser.get(status_url).json()["read_projection_state"] == "matched"

        output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["status"] == "rolled_back"
        assert not ContentNode.objects.filter(repository=workspace.repository, content_id=document.id).exists()
        assert (
            browser.get(
                reverse(
                    "msp-document-attachment-download",
                    kwargs={"document_entity_id": document.entity_id, "attachment_entity_id": attachment.entity_id},
                )
            ).status_code
            == 200
        )


def test_attachment_preview_blocks_missing_links_storage_and_primary_files(tmp_path, monkeypatch):
    with override_settings(
        TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"),
        MEDIA_ROOT=str(tmp_path / "media"),
    ):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Attachment blockers MSP",
            owner_email=f"attachment-blockers-{uuid.uuid4()}@example.invalid",
            owner_display_name="Attachment Blockers Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        missing = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Missing file",
            markdown=f"[Missing](tekdocs://attachment/{uuid.uuid4()})\n",
        )
        output = io.StringIO()
        call_command("preview_document_migration", workspace=str(workspace.id), document=str(missing.id), stdout=output)
        assert json.loads(output.getvalue())["blockers"] == ["attachment_reference_unavailable"]

        other = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Other document",
            markdown="Other notes.\n",
        )
        other_attachment = create_document_attachment(
            document=other,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("other.txt", b"other proof\n", content_type="text/plain"),
        )
        missing_block = missing.placements.get().block
        update_document(
            document=missing,
            actor_id=installation.owner.id,
            title="Missing file",
            markdown=f"[Foreign file](tekdocs://attachment/{other_attachment.entity_id})\n",
            base_revision_id=missing_block.current_revision_id,
        )
        output = io.StringIO()
        call_command("preview_document_migration", workspace=str(workspace.id), document=str(missing.id), stdout=output)
        assert json.loads(output.getvalue())["blockers"] == ["attachment_reference_unavailable"]

        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Stored file",
            markdown="File is managed separately.\n",
        )
        create_document_attachment(
            document=document,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("proof.txt", b"proof\n", content_type="text/plain"),
        )

        def unavailable(_attachment):
            raise ValidationError("stored file unavailable")

        with monkeypatch.context() as patch:
            patch.setattr(
                "apps.core.document_migration_attachments.copy_attachment_content",
                unavailable,
            )
            output = io.StringIO()
            call_command(
                "preview_document_migration", workspace=str(workspace.id), document=str(document.id), stdout=output
            )
            assert json.loads(output.getvalue())["blockers"] == ["attachment_storage_unavailable"]

        primary = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Primary file",
            markdown="Primary file is separate.\n",
        )
        first_primary = create_document_attachment(
            document=primary,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("primary.txt", b"primary\n", content_type="text/plain"),
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
            version_number=1,
        )
        second_primary = replace_primary_document_file(
            document=primary,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("replacement.txt", b"replacement\n", content_type="text/plain"),
        )
        row = next(
            item
            for item in inventory_legacy_documents(workspace)["documents"]
            if item["document_id"] == str(primary.id)
        )
        assert row["disposition"] == "simple_candidate"
        output = io.StringIO()
        call_command("preview_document_migration", workspace=str(workspace.id), document=str(primary.id), stdout=output)
        preview = json.loads(output.getvalue())
        assert preview["eligible"] is True, preview
        assert preview["attachment_count"] == 2
        assert b"replacement\n" not in b"".join(source for _path, source in build_simple_document_export(primary).files)
        third_primary = replace_primary_document_file(
            document=primary,
            actor_id=installation.owner.id,
            upload=SimpleUploadedFile("third.txt", b"third retained version\n", content_type="text/plain"),
        )
        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(primary.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["blockers"] == ["preview_changed"]
        output = io.StringIO()
        call_command("preview_document_migration", workspace=str(workspace.id), document=str(primary.id), stdout=output)
        revised_preview = json.loads(output.getvalue())
        assert revised_preview["plan_sha256"] != preview["plan_sha256"]
        assert revised_preview["attachment_count"] == 3
        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(primary.id),
            base_commit=revised_preview["base_commit"],
            plan_sha256=revised_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["status"] == "imported"
        assert second_primary.replaces_id == first_primary.id
        assert third_primary.replaces_id == second_primary.id
        bundle = export_repository_editable_bundle(workspace.repository)
        bundle_manifest = verify_repository_editable_bundle(bundle.content)
        assert [(item["version_number"], item["owner"]) for item in bundle_manifest["primary_files"]] == [
            (number, {"type": "legacy_document", "id": str(primary.id)}) for number in (1, 2, 3)
        ]
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            assert archive.read(f"primary-files/{first_primary.entity_id}") == b"primary\n"
            assert archive.read(f"primary-files/{second_primary.entity_id}") == b"replacement\n"
            assert archive.read(f"primary-files/{third_primary.entity_id}") == b"third retained version\n"
        browser = Client()
        browser.force_login(installation.owner)
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": primary.entity_id})
        primary_status = browser.get(status_url).json()
        assert primary_status["content_copy_state"] == "in_sync"
        assert primary_status["primary_file_state"] == "retained_bytes_verified"
        assert "primary_file_parity_not_verified" not in primary_status["handoff_blockers"]
        with monkeypatch.context() as patch:
            from apps.core.document_attachments import copy_attachment_content

            def damaged_history(attachment):
                if attachment.id == first_primary.id:
                    raise ValidationError("Historical file is damaged")
                return copy_attachment_content(attachment)

            patch.setattr(document_migration_attachments, "copy_attachment_content", damaged_history)
            damaged_status = browser.get(status_url).json()
            damaged_retry_output = io.StringIO()
            call_command(
                "import_document_migration",
                workspace=str(workspace.id),
                document=str(primary.id),
                base_commit=revised_preview["base_commit"],
                plan_sha256=revised_preview["plan_sha256"],
                actor=str(installation.owner.id),
                apply=True,
                stdout=damaged_retry_output,
            )
            assert json.loads(damaged_retry_output.getvalue())["blockers"] == ["primary_file_storage_unavailable"]
        assert damaged_status["primary_file_state"] == "unavailable"
        assert "primary_file_parity_not_verified" not in damaged_status["handoff_blockers"]
        assert "primary_file_storage_unavailable" in damaged_status["handoff_blockers"]
        assert damaged_status["cutover_ready"] is False
        assert browser.get(status_url).json()["primary_file_state"] == "retained_bytes_verified"


def test_migration_status_identifies_retained_legacy_publication_history(tmp_path):
    with override_settings(
        TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"),
        MEDIA_ROOT=str(tmp_path / "media"),
    ):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Published migration MSP",
            owner_email=f"published-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Published Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Published notes",
            markdown="Retained published notes.\n",
        )
        publish_document(
            workspace=resolve_msp_workspace(installation.owner),
            document=document,
            actor_id=installation.owner.id,
            reason="Retain existing publication history",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        inventory_row = next(
            item
            for item in inventory_legacy_documents(workspace)["documents"]
            if item["document_id"] == str(document.id)
        )
        assert "publication_parity_required" not in inventory_row["reasons"]
        browser = Client()
        browser.force_login(installation.owner)
        status = browser.get(
            reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        )
        assert status.status_code == 200, status.content
        assert "legacy_publication_history_present" not in status.json()["handoff_blockers"]
        assert status.json()["publication_history"]["state"] == "verified"
        assert status.json()["authority_state"] == "legacy"
        assert status.json()["legacy_authoritative"] is True
        assert status.json()["cutover_ready"] is False


def test_structured_topic_migration_checks_composed_sections_and_preserves_type(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Topic migration MSP",
            owner_email=f"topic-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Topic Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        topic = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Setup guide",
            markdown="Initial setup steps.",
            topic_type=DocumentTopicType.GUIDE,
        )
        bad_topic = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Incomplete guide",
            markdown="Initial setup steps.",
            topic_type=DocumentTopicType.GUIDE,
        )
        bad_block = bad_topic.placements.get().block
        update_document(
            document=bad_topic,
            actor_id=installation.owner.id,
            title="Incomplete guide",
            markdown="## Overview\n\nOnly the overview.\n",
            base_revision_id=bad_block.current_revision_id,
            topic_type=DocumentTopicType.GUIDE,
        )
        inventory = inventory_legacy_documents(workspace)
        by_id = {row["document_id"]: row for row in inventory["documents"]}
        assert by_id[str(topic.id)]["disposition"] == "simple_candidate"
        assert by_id[str(bad_topic.id)]["disposition"] == "simple_candidate"

        output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(workspace.id), document=str(bad_topic.id), stdout=output
        )
        assert json.loads(output.getvalue())["blockers"] == ["structured_topic_sections_required"]
        output = io.StringIO()
        call_command("preview_document_migration", workspace=str(workspace.id), document=str(topic.id), stdout=output)
        preview = json.loads(output.getvalue())
        assert preview["eligible"] is True, preview
        exported = build_simple_document_export(topic)
        root = parse_content(dict(exported.files)[f"docs/{topic.id}.md"])
        assert root.topic_type == DocumentTopicType.GUIDE
        assert root.topic_schema_version == 1
        assert any(finding["code"] == "topic.section.missing" for finding in root.findings)

        output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(topic.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        imported = json.loads(output.getvalue())
        assert imported["status"] == "imported", imported
        node = ContentNode.objects.get(repository=workspace.repository, content_id=topic.id)
        assert node.topic_type == DocumentTopicType.GUIDE
        assert node.topic_schema_version == 1
        assert not any(
            finding["severity"] == "blocker"
            for finding in inspect_markdown(node.topic_type, node.composition_variants["all"]["markdown"])
        )
        assert not ContentFinding.objects.filter(node=node, code="topic.section.missing").exists()
        first_digest = index_repository_content(repository_id=workspace.repository.id).projection_digest
        assert index_repository_content(repository_id=workspace.repository.id).projection_digest == first_digest
        assert not ContentFinding.objects.filter(
            node__repository=workspace.repository, node__content_id=topic.id, severity="blocker"
        ).exists()

        output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(topic.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=output,
        )
        assert json.loads(output.getvalue())["status"] == "rolled_back"
        assert not ContentNode.objects.filter(repository=workspace.repository, content_id=topic.id).exists()

        topic.topic_schema_version = 2
        topic.save(update_fields=("topic_schema_version", "updated_at"))
        version_row = next(
            row for row in inventory_legacy_documents(workspace)["documents"] if row["document_id"] == str(topic.id)
        )
        assert "topic_version_mapping_required" in version_row["reasons"]


def test_inventory_is_repeatable_read_only_and_exact_workspace(tmp_path, monkeypatch):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Migration MSP",
            owner_email=f"migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Migration Owner",
            password="MigrationPassword-2026!",
        )
        msp = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(msp)
        simple = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Simple",
            markdown="Legacy body\n",
        )
        template = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Template",
            markdown="Template body\n",
            is_template=True,
        )
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Other Org",
            legal_name="Other Org",
            website="",
            classifications=[],
        )
        org_document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Private org document",
            markdown="Not in MSP report\n",
        )
        revision_count = BlockRevision.objects.count()
        repository_head = msp.repository.accepted_commit_id
        before = inventory_legacy_documents(msp)
        assert before == inventory_legacy_documents(msp)
        assert before["document_count"] == 2
        assert before["counts"] == {"simple_candidate": 2}
        assert before["documents"] == sorted(before["documents"], key=lambda row: row["document_id"])
        by_id = {row["document_id"]: row for row in before["documents"]}
        assert by_id[str(simple.id)]["reasons"] == []
        assert by_id[str(template.id)]["reasons"] == []
        assert "Legacy body" not in json.dumps(before)

        output = io.StringIO()
        call_command("inventory_document_migration", workspace=str(msp.id), stdout=output)
        assert json.loads(output.getvalue()) == before
        msp.repository.refresh_from_db()
        assert msp.repository.accepted_commit_id == repository_head
        assert BlockRevision.objects.count() == revision_count
        org_workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
        org_output = io.StringIO()
        call_command("inventory_document_migration", workspace=str(org_workspace.id), stdout=org_output)
        org_report = json.loads(org_output.getvalue())
        assert org_report["document_count"] == 1
        assert str(simple.id) not in json.dumps(org_report)

        index_repository_content(repository_id=msp.repository.id)
        browser = Client()
        browser.force_login(installation.owner)
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": simple.entity_id})
        org_status_url = reverse(
            "organization-document-migration-status",
            kwargs={"organization_entity_id": organization.entity_id, "document_entity_id": simple.entity_id},
        )
        initial_status = browser.get(status_url)
        assert initial_status.status_code == 200, initial_status.content
        assert initial_status.json()["content_copy_state"] == "legacy_only"
        assert initial_status.json()["legacy_authoritative"] is True
        assert initial_status.json()["cutover_ready"] is False
        assert initial_status.json()["read_projection_state"] == "not_checked"
        assert initial_status.json()["handoff_blockers"] == [
            "content_copy_not_in_sync",
        ]
        template_status_url = reverse(
            "msp-document-migration-status", kwargs={"document_entity_id": template.entity_id}
        )
        template_status = browser.get(template_status_url).json()
        assert template_status["content_copy_state"] == "legacy_only"
        assert "template_history_git_custody_unavailable" in template_status["handoff_blockers"]
        assert not template_status["cutover_ready"]
        assert browser.get(org_status_url).status_code == 404
        own_org_status_url = reverse(
            "organization-document-migration-status",
            kwargs={"organization_entity_id": organization.entity_id, "document_entity_id": org_document.entity_id},
        )
        org_status = browser.get(own_org_status_url)
        assert org_status.status_code == 200, org_status.content
        assert org_status.json()["document_id"] == str(org_document.id)
        assert (
            browser.get(
                reverse("msp-document-migration-status", kwargs={"document_entity_id": org_document.entity_id})
            ).status_code
            == 404
        )
        assert Client().get(status_url).status_code in {401, 403}
        first_export = build_simple_document_export(simple)
        assert first_export == build_simple_document_export(simple)
        assert len(first_export.files) == 2
        assert first_export.document_id == simple.id
        assert first_export.block_id == simple.placements.get().block_id
        source_by_path = dict(first_export.files)
        parsed_document = parse_content(source_by_path[f"docs/{simple.id}.md"])
        parsed_fragment = parse_content(source_by_path[f"fragments/{first_export.block_id}.md"])
        assert parsed_document.properties == {"category": "general", "collection": "", "tags": []}
        assert parsed_document.includes[0].target_content_id == first_export.block_id
        assert parsed_fragment.markdown == "Legacy body\n"
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(msp.id),
            document=str(simple.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        assert [item["path"] for item in preview["files"]] == [path for path, _source in first_export.files]
        assert preview["base_commit"] == msp.repository.accepted_commit.object_id
        assert "Legacy body" not in json.dumps(preview)
        msp.repository.refresh_from_db()
        assert msp.repository.accepted_commit.object_id == preview["base_commit"]

        blocked_output = io.StringIO()
        _preview_document_migration(
            workspace=str(msp.id),
            document=str(template.id),
            stdout=blocked_output,
        )
        assert json.loads(blocked_output.getvalue())["eligible"] is True

        import_args = {
            "workspace": str(msp.id),
            "document": str(simple.id),
            "base_commit": preview["base_commit"],
            "plan_sha256": preview["plan_sha256"],
            "actor": str(installation.owner.id),
        }
        with pytest.raises(CommandError, match="--apply"):
            call_command("import_document_migration", **import_args)
        stale_output = io.StringIO()
        call_command(
            "import_document_migration", **{**import_args, "plan_sha256": "0" * 64}, apply=True, stdout=stale_output
        )
        assert json.loads(stale_output.getvalue())["blockers"] == ["preview_changed"]
        msp.repository.refresh_from_db()
        assert msp.repository.accepted_commit.object_id == preview["base_commit"]
        foreign_actor_output = io.StringIO()
        call_command(
            "import_document_migration",
            **{**import_args, "actor": str(uuid.uuid4())},
            apply=True,
            stdout=foreign_actor_output,
        )
        assert json.loads(foreign_actor_output.getvalue())["blockers"] == ["repository_input_rejected"]
        msp.repository.refresh_from_db()
        assert msp.repository.accepted_commit.object_id == preview["base_commit"]

        imported_output = io.StringIO()

        def interrupt_index(**_kwargs):
            raise ContentIndexError("simulated interruption")

        with monkeypatch.context() as patch:
            patch.setattr(document_migration_import, "index_repository_content", interrupt_index)
            call_command("import_document_migration", **import_args, apply=True, stdout=imported_output)
        imported = json.loads(imported_output.getvalue())
        assert imported["status"] == "index_pending"
        assert imported["indexed"] is False
        assert imported["legacy_authoritative"] is True
        assert browser.get(status_url).json()["content_copy_state"] == "index_pending"
        repeated_output = io.StringIO()
        call_command("import_document_migration", **import_args, apply=True, stdout=repeated_output)
        assert json.loads(repeated_output.getvalue())["status"] == "already_present"
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        root_property = ContentProperty.objects.get(
            node__repository=msp.repository, node__content_id=simple.id, key="category"
        )
        root_property.value = "wrong-category"
        root_property.save(update_fields=("value",))
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        with monkeypatch.context() as patch:
            patch.setattr(document_migration_import, "index_repository_content", lambda **_kwargs: None)
            verification_output = io.StringIO()
            call_command("import_document_migration", **import_args, apply=True, stdout=verification_output)
        assert json.loads(verification_output.getvalue())["status"] == "verification_pending"
        index_repository_content(repository_id=msp.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        assert (
            ContentNode.objects.get(repository=msp.repository, content_id=simple.id).composition_variants["all"][
                "markdown"
            ]
            == "Legacy body\n"
        )
        assert ContentNode.objects.get(repository=msp.repository, content_id=first_export.block_id).markdown == (
            "Legacy body\n"
        )
        assert BlockRevision.objects.count() == revision_count
        msp.repository.refresh_from_db()
        assert msp.repository.accepted_commit.object_id == imported["commit"]

        foreign_output = io.StringIO()
        call_command(
            "import_document_migration",
            **{**import_args, "workspace": str(org_workspace.id)},
            apply=True,
            stdout=foreign_output,
        )
        assert json.loads(foreign_output.getvalue())["blockers"] == ["document_unavailable"]

        rollback_args = {
            "workspace": str(msp.id),
            "document": str(simple.id),
            "expected_commit": imported["commit"],
            "actor": str(installation.owner.id),
        }
        with pytest.raises(CommandError, match="--apply"):
            call_command("rollback_document_migration", **rollback_args)
        stale_rollback = io.StringIO()
        call_command(
            "rollback_document_migration",
            **{**rollback_args, "expected_commit": preview["base_commit"]},
            apply=True,
            stdout=stale_rollback,
        )
        assert json.loads(stale_rollback.getvalue())["blockers"] == ["repository_changed"]
        rollback_output = io.StringIO()
        call_command("rollback_document_migration", **rollback_args, apply=True, stdout=rollback_output)
        rollback = json.loads(rollback_output.getvalue())
        assert rollback["status"] == "rolled_back"
        assert rollback["commit"] not in (preview["base_commit"], imported["commit"])
        assert not ContentNode.objects.filter(repository=msp.repository, content_id=simple.id).exists()
        assert BlockRevision.objects.count() == revision_count
        assert browser.get(status_url).json()["content_copy_state"] == "legacy_only"

        new_preview_output = io.StringIO()
        call_command(
            "preview_document_migration", workspace=str(msp.id), document=str(simple.id), stdout=new_preview_output
        )
        new_preview = json.loads(new_preview_output.getvalue())
        assert new_preview["eligible"] is True
        assert new_preview["base_commit"] == rollback["commit"]
        assert new_preview["plan_sha256"] != preview["plan_sha256"]

        second_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            **{**import_args, "base_commit": new_preview["base_commit"], "plan_sha256": new_preview["plan_sha256"]},
            apply=True,
            stdout=second_import_output,
        )
        second_import = json.loads(second_import_output.getvalue())
        assert second_import["status"] == "imported"
        external = author_content(
            repository=msp.repository,
            actor_id=installation.owner.id,
            request_id=None,
            operation="create",
            content_id=uuid.uuid4(),
            base_commit=second_import["commit"],
            base_blob=None,
            kind="document",
            path=None,
            title="External reference",
            markdown=f"See [[{simple.id}]].\n",
            metadata_patch={},
        )
        referenced_rollback = io.StringIO()
        call_command(
            "rollback_document_migration",
            **{**rollback_args, "expected_commit": external.accepted_commit},
            apply=True,
            stdout=referenced_rollback,
        )
        assert json.loads(referenced_rollback.getvalue())["blockers"] == ["import_has_external_references"]
        update_document(
            document=simple,
            actor_id=installation.owner.id,
            title="Simple",
            markdown="New legacy text\n",
            base_revision_id=simple.placements.get().block.current_revision_id,
        )
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"


def test_wikilink_projection_parity_tracks_resolved_and_unresolved_backlinks(tmp_path, monkeypatch):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Wikilink Migration MSP",
            owner_email=f"wikilink-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Wikilink Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Linked guidance",
            markdown="Initial text\n",
        )
        unresolved_id = uuid.uuid4()
        update_document(
            document=document,
            actor_id=installation.owner.id,
            title="Linked guidance",
            markdown=f"See [[{document.id}#setup|Setup]] and [[{unresolved_id}|Missing]].\n",
            base_revision_id=document.placements.get().block.current_revision_id,
        )
        index_repository_content(repository_id=workspace.repository.id)
        assert inventory_legacy_documents(workspace)["documents"][0]["disposition"] == "simple_candidate"
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        import_args = {
            "workspace": str(workspace.id),
            "document": str(document.id),
            "base_commit": preview["base_commit"],
            "plan_sha256": preview["plan_sha256"],
            "actor": str(installation.owner.id),
        }
        imported_output = io.StringIO()
        call_command("import_document_migration", **import_args, apply=True, stdout=imported_output)
        assert json.loads(imported_output.getvalue())["status"] == "imported"
        block_id = document.placements.get().block_id
        links = list(ContentLink.objects.filter(source__repository=workspace.repository, source__content_id=block_id))
        assert [(link.target_content_id, link.fragment, link.label) for link in links] == [
            (document.id, "setup", "Setup"),
            (unresolved_id, "", "Missing"),
        ]
        assert links[0].target_id == ContentNode.objects.get(repository=workspace.repository, content_id=document.id).id
        assert links[1].target_id is None
        browser = Client()
        browser.force_login(installation.owner)
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        links[0].delete()
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        with monkeypatch.context() as patch:
            patch.setattr(document_migration_import, "index_repository_content", lambda **_kwargs: None)
            verification_output = io.StringIO()
            call_command("import_document_migration", **import_args, apply=True, stdout=verification_output)
        assert json.loads(verification_output.getvalue())["status"] == "verification_pending"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        resolved = ContentLink.objects.get(source__content_id=block_id, target_content_id=document.id)
        resolved.target = None
        resolved.save(update_fields=("target",))
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"


def test_owned_sections_preserve_flat_and_nested_order_and_roll_back_as_one_copy(tmp_path, monkeypatch):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Section Migration MSP",
            owner_email=f"section-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Section Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Ordered sections",
            markdown="First section\n",
        )
        second = create_document_block(
            document=document,
            actor_id=installation.owner.id,
            markdown="Second section\n",
            kind=BlockKind.RICH_TEXT,
            name="Second section",
            parent_id=None,
            position=1,
        )
        inventory = inventory_legacy_documents(workspace)
        assert inventory["documents"][0]["disposition"] == "simple_candidate"
        assert inventory["documents"][0]["placement_count"] == 2
        export = build_simple_document_export(document)
        assert len(export.blocks) == 2
        assert export.blocks[1][0] == second.block_id
        assert len(export.files) == 3
        parsed_root = parse_content(dict(export.files)[f"docs/{document.id}.md"])
        assert [item.target_content_id for item in parsed_root.includes] == [block_id for block_id, _ in export.blocks]

        index_repository_content(repository_id=workspace.repository.id)
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        assert len(preview["blocks"]) == 2
        assert len(preview["files"]) == 3
        args = {
            "workspace": str(workspace.id),
            "document": str(document.id),
            "base_commit": preview["base_commit"],
            "plan_sha256": preview["plan_sha256"],
            "actor": str(installation.owner.id),
        }
        import_output = io.StringIO()
        call_command("import_document_migration", **args, apply=True, stdout=import_output)
        imported = json.loads(import_output.getvalue())
        assert imported["status"] == "imported"
        assert (
            ContentNode.objects.get(repository=workspace.repository, content_id=document.id).composition_variants[
                "all"
            ]["markdown"]
            == "First section\n\nSecond section\n"
        )
        browser = Client()
        TOTP.activate(installation.owner, generate_totp_secret())
        browser.force_login(installation.owner)
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        status = browser.get(status_url).json()
        assert status["content_copy_state"] == "in_sync"
        assert status["read_projection_state"] == "matched"
        assert status["legacy_revision_ids"] == [str(revision_id) for _block_id, revision_id in export.blocks]
        assert status["legacy_authoritative"] is True
        assert status["cutover_ready"] is True
        assert status["handoff_blockers"] == []
        copied_source = read_authored_content(repository=workspace.repository, content_id=document.id)
        authoring_url = reverse("msp-content-authoring")
        for operation, changes in (
            ("create", {"kind": "document", "title": "Replacement", "markdown": "Replacement.\n"}),
            ("update", {"markdown": "Git-only edit.\n"}),
            ("move", {"path": "docs/legacy-moved.md"}),
        ):
            response = browser.post(
                authoring_url,
                data={
                    "operation": operation,
                    "content_id": str(document.id),
                    "base_commit": copied_source.accepted_commit,
                    "base_blob": copied_source.source_blob if operation != "create" else None,
                    **changes,
                },
                content_type="application/json",
            )
            assert response.status_code == 400, response.content
            assert "Legacy content remains authoritative" in response.json()["detail"]
            assert read_authored_content(repository=workspace.repository, content_id=document.id) == copied_source
        copied_fragment = read_authored_content(repository=workspace.repository, content_id=export.blocks[0][0])
        fragment_response = browser.post(
            authoring_url,
            data={
                "operation": "update",
                "content_id": str(copied_fragment.content_id),
                "base_commit": copied_fragment.accepted_commit,
                "base_blob": copied_fragment.source_blob,
                "markdown": "Git-only fragment edit.\n",
            },
            content_type="application/json",
        )
        assert fragment_response.status_code == 400, fragment_response.content
        assert "Legacy content remains authoritative" in fragment_response.json()["detail"]
        assert (
            read_authored_content(repository=workspace.repository, content_id=copied_fragment.content_id)
            == copied_fragment
        )
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        document.review_state = DocumentReviewState.APPROVED
        document.last_reviewed_at = timezone.now()
        document.review_content_sha256 = hashlib.sha256(b"First section\n\nSecond section\n").hexdigest()
        document.save(update_fields=("review_state", "last_reviewed_at", "review_content_sha256", "updated_at"))
        reviewed_status = browser.get(status_url).json()
        assert reviewed_status["content_copy_state"] == "in_sync"
        assert "review_workflow_parity_not_verified" not in reviewed_status["handoff_blockers"]
        assert reviewed_status["cutover_ready"] is True
        document.review_content_sha256 = "0" * 64
        document.save(update_fields=("review_content_sha256", "updated_at"))
        assert "review_workflow_parity_not_verified" in browser.get(status_url).json()["handoff_blockers"]
        document.review_state = DocumentReviewState.UNREVIEWED
        document.last_reviewed_at = None
        document.review_content_sha256 = None
        document.save(update_fields=("review_state", "last_reviewed_at", "review_content_sha256", "updated_at"))
        document.review_due_on = timezone.localdate()
        document.save(update_fields=("review_due_on", "updated_at"))
        scheduled_status = browser.get(status_url).json()
        assert "review_workflow_parity_not_verified" not in scheduled_status["handoff_blockers"]
        assert scheduled_status["cutover_ready"] is True
        document.review_due_on = None
        document.save(update_fields=("review_due_on", "updated_at"))
        ContentInclude.objects.get(
            source__repository=workspace.repository, source__content_id=document.id, ordinal=1
        ).delete()
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        with monkeypatch.context() as patch:
            patch.setattr(document_migration_import, "index_repository_content", lambda **_kwargs: None)
            verification_output = io.StringIO()
            call_command("import_document_migration", **args, apply=True, stdout=verification_output)
        assert json.loads(verification_output.getvalue())["status"] == "verification_pending"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        first_include = ContentInclude.objects.get(
            source__repository=workspace.repository, source__content_id=document.id, ordinal=0
        )
        first_include.resolved_content_digest = "0" * 64
        first_include.save(update_fields=("resolved_content_digest",))
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        ContentNode.objects.filter(repository=workspace.repository, content_id=document.id).update(title="Stale title")
        mismatched = browser.get(status_url).json()
        assert mismatched["content_copy_state"] == "diverged"
        assert mismatched["read_projection_state"] == "not_checked"
        assert "content_copy_not_in_sync" in mismatched["handoff_blockers"]
        ContentNode.objects.filter(repository=workspace.repository, content_id=document.id).update(
            title=document.entity.display_name
        )

        rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=rollback_output,
        )
        assert json.loads(rollback_output.getvalue())["status"] == "rolled_back"
        assert not ContentNode.objects.filter(
            repository=workspace.repository,
            content_id__in=[document.id, *(block_id for block_id, _revision_id in export.blocks)],
        ).exists()
        assert browser.get(status_url).json()["content_copy_state"] == "legacy_only"
        second.parent = document.placements.get(position=0)
        second.position = 0
        second.save(update_fields=("parent", "position", "updated_at"))
        grandchild = create_document_block(
            document=document,
            actor_id=installation.owner.id,
            markdown="Grandchild section\n",
            kind=BlockKind.RICH_TEXT,
            name="Grandchild section",
            parent_id=second.id,
            position=0,
        )
        third = create_document_block(
            document=document,
            actor_id=installation.owner.id,
            markdown="Third section\n",
            kind=BlockKind.RICH_TEXT,
            name="Third section",
            parent_id=None,
            position=1,
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["disposition"] == "simple_candidate"
        nested_export = build_simple_document_export(document)
        nested_files = dict(nested_export.files)
        nested_root = parse_content(nested_files[f"docs/{document.id}.md"])
        nested_first = parse_content(nested_files[f"fragments/{export.block_id}.md"])
        nested_second = parse_content(nested_files[f"fragments/{second.block_id}.md"])
        assert [block_id for block_id, _revision_id in nested_export.blocks] == [
            export.block_id,
            second.block_id,
            grandchild.block_id,
            third.block_id,
        ]
        assert [item.target_content_id for item in nested_root.includes] == [export.block_id, third.block_id]
        assert [item.target_content_id for item in nested_first.includes] == [second.block_id]
        assert [item.target_content_id for item in nested_second.includes] == [grandchild.block_id]

        nested_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=nested_preview_output,
        )
        nested_preview = json.loads(nested_preview_output.getvalue())
        assert nested_preview["eligible"] is True, nested_preview
        assert nested_preview["plan_sha256"] != preview["plan_sha256"]
        nested_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            **{**args, "base_commit": nested_preview["base_commit"], "plan_sha256": nested_preview["plan_sha256"]},
            apply=True,
            stdout=nested_import_output,
        )
        nested_import = json.loads(nested_import_output.getvalue())
        assert nested_import["status"] == "imported"
        assert (
            ContentNode.objects.get(repository=workspace.repository, content_id=document.id).composition_variants[
                "all"
            ]["markdown"]
            == "First section\n\nSecond section\n\nGrandchild section\n\nThird section\n"
        )
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        nested_rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=nested_import["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=nested_rollback_output,
        )
        assert json.loads(nested_rollback_output.getvalue())["status"] == "rolled_back"
        second.resolution_mode = PlacementResolutionMode.PINNED
        second.pinned_revision_id = second.block.current_revision_id
        second.save(update_fields=("resolution_mode", "pinned_revision", "updated_at"))
        assert "pinned_source_snapshot_required" in inventory_legacy_documents(workspace)["documents"][0]["reasons"]
        assert browser.get(status_url).json()["content_copy_state"] == "unsupported_legacy_shape"
        second.resolution_mode = PlacementResolutionMode.LIVE
        second.pinned_revision_id = None
        second.save(update_fields=("resolution_mode", "pinned_revision", "updated_at"))
        ancestor = grandchild
        for depth in range(10):
            ancestor = create_document_block(
                document=document,
                actor_id=installation.owner.id,
                markdown=f"Depth {depth}\n",
                kind=BlockKind.RICH_TEXT,
                name=f"Depth {depth}",
                parent_id=ancestor.id,
                position=0,
            )
        assert "composition_depth_exceeded" in inventory_legacy_documents(workspace)["documents"][0]["reasons"]
        with pytest.raises(DocumentMigrationExportError, match="composition_depth_exceeded"):
            build_simple_document_export(document)


def test_live_same_workspace_reuse_requires_indexed_source_and_never_deletes_it(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Reuse Migration MSP",
            owner_email=f"reuse-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Reuse Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        source = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Shared source",
            markdown="Source instructions\n",
        )
        target = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Using source",
            markdown="Target introduction\n",
        )
        add_document_placement(
            document=target,
            source_document=source,
            actor_id=installation.owner.id,
            resolution_mode=PlacementResolutionMode.LIVE,
            pinned_revision_id=None,
            parent_id=None,
            position=1,
        )
        index_repository_content(repository_id=workspace.repository.id)
        rows = {row["document_id"]: row for row in inventory_legacy_documents(workspace)["documents"]}
        assert rows[str(source.id)]["disposition"] == "simple_candidate"
        assert rows[str(target.id)]["reasons"] == ["cross_document_source_unavailable"]
        blocked_preview = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(target.id),
            stdout=blocked_preview,
        )
        assert json.loads(blocked_preview.getvalue())["blockers"] == ["cross_document_source_unavailable"]

        source_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(source.id),
            stdout=source_preview_output,
        )
        source_preview = json.loads(source_preview_output.getvalue())
        assert source_preview["eligible"] is True, source_preview
        source_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(source.id),
            base_commit=source_preview["base_commit"],
            plan_sha256=source_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=source_import_output,
        )
        assert json.loads(source_import_output.getvalue())["status"] == "imported"
        source_block_id = source.placements.get().block_id
        rows = {row["document_id"]: row for row in inventory_legacy_documents(workspace)["documents"]}
        assert rows[str(target.id)]["disposition"] == "simple_candidate"
        target_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(target.id),
            stdout=target_preview_output,
        )
        target_preview = json.loads(target_preview_output.getvalue())
        assert target_preview["eligible"] is True, target_preview
        assert len(target_preview["files"]) == 2
        assert target_preview["referenced_blocks"][0]["block_id"] == str(source_block_id)
        assert f"fragments/{source_block_id}.md" not in {item["path"] for item in target_preview["files"]}
        browser = Client()
        browser.force_login(installation.owner)
        target_status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": target.entity_id})
        assert browser.get(target_status_url).json()["content_copy_state"] == "legacy_only"

        target_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(target.id),
            base_commit=target_preview["base_commit"],
            plan_sha256=target_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=target_import_output,
        )
        target_import = json.loads(target_import_output.getvalue())
        assert target_import["status"] == "imported"
        assert browser.get(target_status_url).json()["content_copy_state"] == "in_sync"
        assert (
            ContentNode.objects.get(repository=workspace.repository, content_id=target.id).composition_variants["all"][
                "markdown"
            ]
            == "Target introduction\n\nSource instructions\n"
        )

        source_rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(source.id),
            expected_commit=target_import["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=source_rollback_output,
        )
        assert json.loads(source_rollback_output.getvalue())["blockers"] == ["import_has_external_references"]
        target_rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(target.id),
            expected_commit=target_import["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=target_rollback_output,
        )
        assert json.loads(target_rollback_output.getvalue())["status"] == "rolled_back"
        assert ContentNode.objects.filter(repository=workspace.repository, content_id=source_block_id).exists()
        assert not ContentNode.objects.filter(repository=workspace.repository, content_id=target.id).exists()
        assert browser.get(target_status_url).json()["content_copy_state"] == "legacy_only"
        update_document(
            document=source,
            actor_id=installation.owner.id,
            title="Shared source",
            markdown="Changed legacy instructions\n",
            base_revision_id=source.placements.get().block.current_revision_id,
        )
        drift_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(target.id),
            stdout=drift_preview_output,
        )
        assert json.loads(drift_preview_output.getvalue())["blockers"] == ["cross_document_source_drift"]
        assert browser.get(target_status_url).json()["content_copy_state"] == "diverged"


def test_pinned_same_workspace_leaf_retains_exact_snapshot_after_source_changes(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Pinned Migration MSP",
            owner_email=f"pinned-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Pinned Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        source = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Pinned source",
            markdown="Original source\n",
        )
        target = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Pinned target",
            markdown="Target body\n",
        )
        source_placement = source.placements.get()
        original_revision_id = source_placement.block.current_revision_id
        add_document_placement(
            document=target,
            source_document=source,
            actor_id=installation.owner.id,
            resolution_mode=PlacementResolutionMode.PINNED,
            pinned_revision_id=source_placement.block.current_revision_id,
            parent_id=None,
            position=1,
        )
        index_repository_content(repository_id=workspace.repository.id)
        source_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(source.id),
            stdout=source_preview_output,
        )
        source_preview = json.loads(source_preview_output.getvalue())
        source_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(source.id),
            base_commit=source_preview["base_commit"],
            plan_sha256=source_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=source_import_output,
        )
        source_commit = json.loads(source_import_output.getvalue())["commit"]
        target_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(target.id),
            stdout=target_preview_output,
        )
        target_preview = json.loads(target_preview_output.getvalue())
        assert target_preview["eligible"] is True, target_preview
        assert len(target_preview["files"]) == 2
        assert target_preview["referenced_blocks"][0]["pinned_commit"] == source_commit
        target_export = build_simple_document_export(target)
        target_root = parse_content(dict(target_export.files)[f"docs/{target.id}.md"])
        assert target_root.includes[1].mode == "pinned"
        assert target_root.includes[1].pinned_object_id == source_commit
        assert target_export.blocks[1][1] == source_placement.block.current_revision_id
        target_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(target.id),
            base_commit=target_preview["base_commit"],
            plan_sha256=target_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=target_import_output,
        )
        target_commit = json.loads(target_import_output.getvalue())["commit"]
        assert target_commit != source_commit
        browser = Client()
        browser.force_login(installation.owner)
        target_status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": target.entity_id})
        assert browser.get(target_status_url).json()["content_copy_state"] == "in_sync"
        source_authored = read_authored_content(repository=workspace.repository, content_id=source_placement.block_id)
        commit_repository_files(
            repository_id=workspace.repository.id,
            expected_base=source_authored.accepted_commit,
            changes={
                source_authored.path: source_authored.source.replace(
                    "Original source\n", "New repository source\n"
                ).encode()
            },
            message="Simulate operator edit to copied fragment",
            attribution=RepositoryAuditAttribution(
                actor_id=installation.owner.id, action="content.migration_test_operator_edit"
            ),
        )
        index_repository_content(repository_id=workspace.repository.id)
        update_document(
            document=source,
            actor_id=installation.owner.id,
            title="Pinned source",
            markdown="New legacy source\n",
            base_revision_id=source_placement.block.current_revision_id,
        )
        unmatched = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Unmatched pin",
            markdown="Separate target\n",
        )
        source_placement.block.refresh_from_db()
        add_document_placement(
            document=unmatched,
            source_document=source,
            actor_id=installation.owner.id,
            resolution_mode=PlacementResolutionMode.PINNED,
            pinned_revision_id=source_placement.block.current_revision_id,
            parent_id=None,
            position=1,
        )
        unmatched_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(unmatched.id),
            stdout=unmatched_output,
        )
        assert json.loads(unmatched_output.getvalue())["blockers"] == ["pinned_source_snapshot_required"]
        historical = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Historical pin",
            markdown="Historical target\n",
        )
        add_document_placement(
            document=historical,
            source_document=source,
            actor_id=installation.owner.id,
            resolution_mode=PlacementResolutionMode.PINNED,
            pinned_revision_id=original_revision_id,
            parent_id=None,
            position=1,
        )
        historical_preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(historical.id),
            stdout=historical_preview_output,
        )
        historical_preview = json.loads(historical_preview_output.getvalue())
        assert historical_preview["eligible"] is True, historical_preview
        assert historical_preview["referenced_blocks"][0]["pinned_commit"] == target_commit
        historical_import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(historical.id),
            base_commit=historical_preview["base_commit"],
            plan_sha256=historical_preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=historical_import_output,
        )
        historical_import = json.loads(historical_import_output.getvalue())
        assert historical_import["status"] == "imported"
        historical_status_url = reverse(
            "msp-document-migration-status", kwargs={"document_entity_id": historical.entity_id}
        )
        assert browser.get(historical_status_url).json()["content_copy_state"] == "in_sync"
        historical_rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(historical.id),
            expected_commit=historical_import["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=historical_rollback_output,
        )
        assert json.loads(historical_rollback_output.getvalue())["status"] == "rolled_back"
        assert build_simple_document_export(target).pinned_commits == ((source_placement.block_id, source_commit),)
        assert browser.get(target_status_url).json()["content_copy_state"] == "in_sync"
        assert (
            ContentNode.objects.get(repository=workspace.repository, content_id=target.id).composition_variants["all"][
                "markdown"
            ]
            == "Target body\n\nOriginal source\n"
        )
        rollback_output = io.StringIO()
        workspace.repository.refresh_from_db()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(target.id),
            expected_commit=workspace.repository.accepted_commit.object_id,
            actor=str(installation.owner.id),
            apply=True,
            stdout=rollback_output,
        )
        assert json.loads(rollback_output.getvalue())["status"] == "rolled_back"
        assert ContentNode.objects.filter(
            repository=workspace.repository, content_id=source_placement.block_id
        ).exists()


def test_current_taxonomy_keys_migrate_and_stale_selection_is_deferred(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Taxonomy Migration MSP",
            owner_email=f"taxonomy-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Taxonomy Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Taxonomy runbook",
            markdown="Taxonomy body\n",
        )
        taxonomy = create_taxonomy(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            key="technology",
            binding=TaxonomyBinding.DOCUMENT_TAGS,
            label="Technology",
            description="",
            allow_local_terms=False,
            terms=[{"stable_key": "endpoint", "label": "Endpoint"}],
        )
        term = taxonomy.current_version.terms.get(stable_key="endpoint")
        assign_document_terms(document=document, term_ids=[term.id], actor_id=installation.owner.id)
        assert inventory_legacy_documents(workspace)["documents"][0]["disposition"] == "simple_candidate"
        export = build_simple_document_export(document)
        root = parse_content(dict(export.files)[f"docs/{document.id}.md"])
        assert root.taxonomies == {"technology": ["endpoint"]}
        index_repository_content(repository_id=workspace.repository.id)
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=import_output,
        )
        imported = json.loads(import_output.getvalue())
        assert imported["status"] == "imported"
        assert ContentNode.objects.get(repository=workspace.repository, content_id=document.id).taxonomy_keys == {
            "technology": ["endpoint"]
        }
        browser = Client()
        browser.force_login(installation.owner)
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        node = ContentNode.objects.get(repository=workspace.repository, content_id=document.id)
        node.taxonomy_keys = {"technology": ["incorrect"]}
        node.save(update_fields=("taxonomy_keys", "updated_at"))
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["content_copy_state"] == "in_sync"
        rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=rollback_output,
        )
        assert json.loads(rollback_output.getvalue())["status"] == "rolled_back"
        revise_taxonomy(
            taxonomy=taxonomy,
            actor_id=installation.owner.id,
            label="Technology",
            description="",
            allow_local_terms=False,
            terms=[{"stable_key": "endpoint", "label": "Endpoint"}],
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == ["taxonomy_mapping_required"]
        stale_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=stale_output,
        )
        assert json.loads(stale_output.getvalue())["blockers"] == ["taxonomy_mapping_required"]


def test_client_local_taxonomy_key_stays_in_exact_workspace(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Local Taxonomy Migration MSP",
            owner_email=f"local-taxonomy-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Local Taxonomy Migration Owner",
            password="MigrationPassword-2026!",
        )
        organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Taxonomy Client",
            legal_name="Taxonomy Client",
            website="",
            classifications=[],
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, organization=organization)
        repository_storage.ensure_workspace_repository(workspace)
        document = create_document(
            tenant=installation.tenant,
            organization=organization,
            actor_id=installation.owner.id,
            title="Client runbook",
            markdown="Client body\n",
        )
        taxonomy = create_taxonomy(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            key="service-area",
            binding=TaxonomyBinding.DOCUMENT_TAGS,
            label="Service area",
            description="",
            allow_local_terms=True,
            terms=[{"stable_key": "general", "label": "General"}],
        )
        local = create_local_term(
            tenant=installation.tenant,
            organization=organization,
            taxonomy=taxonomy,
            actor_id=installation.owner.id,
            stable_key="onsite",
            label="Onsite",
            description="",
            aliases=[],
        )
        assign_document_terms(document=document, term_ids=[local.id], actor_id=installation.owner.id)
        assert inventory_legacy_documents(workspace)["documents"][0]["disposition"] == "simple_candidate"
        export = build_simple_document_export(document)
        root = parse_content(dict(export.files)[f"docs/{document.id}.md"])
        assert root.taxonomies == {"service-area": ["onsite"]}
        index_repository_content(repository_id=workspace.repository.id)
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=import_output,
        )
        assert json.loads(import_output.getvalue())["status"] == "imported"
        assert ContentNode.objects.get(repository=workspace.repository, content_id=document.id).taxonomy_keys == {
            "service-area": ["onsite"]
        }
        local.archived_at = timezone.now()
        local.save(update_fields=("archived_at", "updated_at"))
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == [
            "git_identity_collision",
            "taxonomy_mapping_required",
        ]


def test_exact_workspace_entity_references_map_to_neutral_mentions_only(tmp_path, monkeypatch):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Reference Migration MSP",
            owner_email=f"reference-migration-{uuid.uuid4()}@example.invalid",
            owner_display_name="Reference Migration Owner",
            password="MigrationPassword-2026!",
        )
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Asset guidance",
            markdown="Inspect the device.\n",
        )
        asset = Entity.objects.create_owned(
            tenant=installation.tenant,
            organization=None,
            entity_type="client_asset",
            display_name="Device",
        )
        person = Entity.objects.create_owned(
            tenant=installation.tenant,
            organization=None,
            entity_type="person",
            display_name="Technician",
        )
        network = Entity.objects.create_owned(
            tenant=installation.tenant,
            organization=None,
            entity_type="network_device",
            display_name="Switch",
        )
        link = EntityLink.objects.create(
            tenant=installation.tenant,
            source=document.entity,
            target=asset,
            link_type=EntityLinkType.REFERENCES,
        )
        for target in (person, network):
            EntityLink.objects.create(
                tenant=installation.tenant,
                source=document.entity,
                target=target,
                link_type=EntityLinkType.REFERENCES,
            )
        expected_references = [
            (target.id, "mention") for target in sorted((asset, person, network), key=lambda item: str(item.id))
        ]
        assert inventory_legacy_documents(workspace)["documents"][0]["disposition"] == "simple_candidate"
        export = build_simple_document_export(document)
        root = parse_content(dict(export.files)[f"docs/{document.id}.md"])
        assert [(item.target_entity_id, item.relationship) for item in root.entity_links] == expected_references
        assert export.resolved_entity_links == tuple(
            (str(entity_id), relationship, "typed") for entity_id, relationship in expected_references
        )
        index_repository_content(repository_id=workspace.repository.id)
        preview_output = io.StringIO()
        _preview_document_migration(
            workspace=str(workspace.id),
            document=str(document.id),
            stdout=preview_output,
        )
        preview = json.loads(preview_output.getvalue())
        assert preview["eligible"] is True, preview
        import_output = io.StringIO()
        call_command(
            "import_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            base_commit=preview["base_commit"],
            plan_sha256=preview["plan_sha256"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=import_output,
        )
        imported = json.loads(import_output.getvalue())
        assert imported["status"] == "imported"
        node = ContentNode.objects.get(repository=workspace.repository, content_id=document.id)
        assert sorted((item.target_entity_id, item.relationship) for item in node.entity_links.all()) == sorted(
            expected_references
        )
        browser = Client()
        browser.force_login(installation.owner)
        detail_url = reverse("msp-content-document-detail", kwargs={"content_id": document.id})
        detail = browser.get(detail_url)
        assert detail.status_code == 200, detail.content
        document_detail_url = reverse("msp-document-detail", kwargs={"document_entity_id": document.entity_id})
        document_detail = browser.get(document_detail_url)
        assert document_detail.status_code == 200, document_detail.content
        assert document_detail.json()["content_authority"] == "legacy"
        assert document_detail.json()["markdown"] == "Inspect the device.\n"
        assert {item["id"] for item in detail.json()["entity_context"]} == {
            str(asset.id),
            str(person.id),
            str(network.id),
        }
        person.display_name = "Renamed technician"
        person.save(update_fields=("display_name", "updated_at"))
        assert any(
            item["id"] == str(person.id) and item["display_name"] == "Renamed technician"
            for item in browser.get(detail_url).json()["entity_context"]
        )
        status_url = reverse("msp-document-migration-status", kwargs={"document_entity_id": document.entity_id})
        assert browser.get(status_url).json()["read_projection_state"] == "matched"
        # The API serializer must key authority by Document.id (the stable content UUID),
        # not by the distinct owning Entity.id.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
            authority = DocumentAuthority.objects.get(workspace=workspace, content_id=document.id)
            authority.authority = "repository"
            authority.save(update_fields=("authority", "updated_at"))
            repository_owned_detail = browser.get(document_detail_url).json()
            assert repository_owned_detail["content_authority"] == "repository"
            assert repository_owned_detail["markdown"] == ""
            assert repository_owned_detail["resolved_markdown"] == ""
            repository_owned_list = browser.get(reverse("msp-document-list-create")).json()
            listed_document = next(
                item for item in repository_owned_list["results"] if item["id"] == str(document.entity_id)
            )
            assert listed_document["content_authority"] == "repository"
            assert listed_document["markdown"] == ""
            authority.authority = "legacy"
            authority.save(update_fields=("authority", "updated_at"))
        indexed_person_link = ContentEntityLink.objects.get(source=node, target_entity_id=person.id)
        indexed_person_link.delete()
        shadow_status = browser.get(status_url).json()
        assert shadow_status["content_copy_state"] == "diverged"
        assert shadow_status["read_projection_state"] == "not_checked"
        with monkeypatch.context() as patch:
            patch.setattr(document_migration_import, "index_repository_content", lambda **_kwargs: None)
            verification_output = io.StringIO()
            call_command(
                "import_document_migration",
                workspace=str(workspace.id),
                document=str(document.id),
                base_commit=preview["base_commit"],
                plan_sha256=preview["plan_sha256"],
                actor=str(installation.owner.id),
                apply=True,
                stdout=verification_output,
            )
        assert json.loads(verification_output.getvalue())["status"] == "verification_pending"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        assert browser.get(status_url).json()["read_projection_state"] == "matched"
        node = ContentNode.objects.get(repository=workspace.repository, content_id=document.id)
        variants = deepcopy(node.composition_variants)
        variants["msp_internal"]["entity_links"] = []
        node.composition_variants = variants
        node.save(update_fields=("composition_variants", "updated_at"))
        ContentEntityLink.objects.filter(source=node).delete()
        assert browser.get(status_url).json()["content_copy_state"] == "diverged"
        index_repository_content(repository_id=workspace.repository.id, force=True)
        with monkeypatch.context() as patch:
            original_detail = document_migration_coexistence.document_detail
            patch.setattr(
                document_migration_coexistence,
                "document_detail",
                lambda **kwargs: {**original_detail(**kwargs), "entity_context": []},
            )
            shadow_status = browser.get(status_url).json()
        assert shadow_status["content_copy_state"] == "in_sync"
        assert shadow_status["read_projection_state"] == "different"
        assert "repository_read_projection_not_matched" in shadow_status["handoff_blockers"]
        with monkeypatch.context() as patch:
            original_detail = document_migration_coexistence.document_detail
            patch.setattr(
                document_migration_coexistence,
                "document_detail",
                lambda **kwargs: {**original_detail(**kwargs), "sanitized_html": "<p>Stale rendered view</p>"},
            )
            rendered_status = browser.get(status_url).json()
        assert rendered_status["content_copy_state"] == "in_sync"
        assert rendered_status["read_projection_state"] == "different"
        assert "repository_read_projection_not_matched" in rendered_status["handoff_blockers"]
        rollback_output = io.StringIO()
        call_command(
            "rollback_document_migration",
            workspace=str(workspace.id),
            document=str(document.id),
            expected_commit=imported["commit"],
            actor=str(installation.owner.id),
            apply=True,
            stdout=rollback_output,
        )
        assert json.loads(rollback_output.getvalue())["status"] == "rolled_back"
        assert browser.get(document_detail_url).json()["content_authority"] == "legacy"
        assert browser.get(document_detail_url).json()["markdown"] == "Inspect the device.\n"
        link.archived_at = timezone.now()
        link.save(update_fields=("archived_at", "updated_at"))
        unsupported = EntityLink.objects.create(
            tenant=installation.tenant,
            source=document.entity,
            target=asset,
            link_type=EntityLinkType.DEPENDS_ON,
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == ["relationship_mapping_required"]
        unsupported.archived_at = timezone.now()
        unsupported.save(update_fields=("archived_at", "updated_at"))
        incoming = EntityLink.objects.create(
            tenant=installation.tenant,
            source=asset,
            target=document.entity,
            link_type=EntityLinkType.REFERENCES,
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == ["relationship_mapping_required"]
        incoming.archived_at = timezone.now()
        incoming.save(update_fields=("archived_at", "updated_at"))
        unsupported_target = Entity.objects.create_owned(
            tenant=installation.tenant,
            organization=None,
            entity_type="document_block",
            display_name="Internal block",
        )
        unsupported = EntityLink.objects.create(
            tenant=installation.tenant,
            source=document.entity,
            target=unsupported_target,
            link_type=EntityLinkType.REFERENCES,
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == ["relationship_mapping_required"]
        unsupported.archived_at = timezone.now()
        unsupported.save(update_fields=("archived_at", "updated_at"))
        other_organization = create_organization(
            tenant=installation.tenant,
            actor_id=installation.owner.id,
            name="Different client",
            legal_name="Different client",
            website="",
            classifications=[],
        )
        foreign_asset = Entity.objects.create_owned(
            tenant=installation.tenant,
            organization=other_organization,
            entity_type="client_asset",
            display_name="Other device",
        )
        EntityLink.objects.create(
            tenant=installation.tenant,
            source=document.entity,
            target=foreign_asset,
            link_type=EntityLinkType.REFERENCES,
        )
        assert inventory_legacy_documents(workspace)["documents"][0]["reasons"] == ["relationship_mapping_required"]
        client_workspace = Workspace.objects.get(tenant=installation.tenant, organization=other_organization)
        repository_storage.ensure_workspace_repository(client_workspace)
        client_document = create_document(
            tenant=installation.tenant,
            organization=other_organization,
            actor_id=installation.owner.id,
            title="Client asset guidance",
            markdown="Check this client's device.\n",
        )
        EntityLink.objects.create(
            tenant=installation.tenant,
            source=client_document.entity,
            target=foreign_asset,
            link_type=EntityLinkType.REFERENCES,
        )
        assert inventory_legacy_documents(client_workspace)["documents"][0]["disposition"] == "simple_candidate"
        client_export = build_simple_document_export(client_document)
        client_root = parse_content(dict(client_export.files)[f"docs/{client_document.id}.md"])
        assert [(item.target_entity_id, item.relationship) for item in client_root.entity_links] == [
            (foreign_asset.id, "mention")
        ]
