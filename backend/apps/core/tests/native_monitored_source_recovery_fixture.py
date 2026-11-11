"""Git-native monitored-source upgrade and independent-recovery fixture."""

import hashlib
import json
import os
import uuid

from apps.accounts.models import User
from apps.accounts.policy import require_installation_member
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.document_source_git import apply_git_observation, preview_remote_observation
from apps.core.document_source_models import DocumentRemoteObservation, DocumentRemoteSource
from apps.core.models import Document, InstallationState, Workspace, WorkspaceKind
from apps.core.repository_service import coordinated_repository_transaction
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope

CONTENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.acceptance.native-monitored-source")


def _bind(owner: User) -> None:
    tenant = require_installation_member(owner).tenant
    bind_local_rls_scope(
        DataScope.owner(tenant, None),
        organization_mode=OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )


def native_monitored_source_fingerprint(owner: User) -> str:
    with coordinated_repository_transaction():
        _bind(owner)
        tenant = require_installation_member(owner).tenant
        workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        repository = ensure_workspace_repository(workspace).repository
        authored = read_authored_content(repository=repository, content_id=CONTENT_ID)
        source = DocumentRemoteSource.objects.get(repository=repository, content_id=CONTENT_ID)
        observations = list(source.observations.order_by("fetched_at", "id"))
        assert not Document.objects.filter(pk=CONTENT_ID).exists()
        assert len(observations) == 2
        assert source.last_applied_observation_id == observations[-1].id
        assert authored.markdown == observations[-1].canonical_markdown
        payload = {
            "content": {"id": str(CONTENT_ID), "path": authored.path, "title": authored.title,
                        "commit": authored.accepted_commit, "blob": authored.source_blob,
                        "sha256": hashlib.sha256(authored.markdown.encode()).hexdigest()},
            "source": {"id": str(source.id), "tenant": str(source.tenant_id),
                       "organization": str(source.organization_id or ""),
                       "repository": str(source.repository_id), "content_id": str(source.content_id),
                       "url": source.url, "kind": source.source_kind, "enabled": source.enabled,
                       "interval": source.check_interval_minutes, "created_by": str(source.created_by_id),
                       "next_check_at": source.next_check_at.isoformat(),
                       "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else "",
                       "last_applied": str(source.last_applied_observation_id),
                       "archived_at": source.archived_at.isoformat() if source.archived_at else "",
                       "created_at": source.created_at.isoformat(), "updated_at": source.updated_at.isoformat()},
            "observations": [{"id": str(item.id), "tenant": str(item.tenant_id),
                              "organization": str(item.organization_id or ""), "source": str(item.source_id),
                              "state": item.state, "status_code": item.status_code,
                              "content_type": item.content_type, "etag_digest": item.etag_digest,
                              "last_modified_digest": item.last_modified_digest,
                              "digest": item.content_digest, "error_code": item.error_code,
                              "markdown": item.canonical_markdown, "fetched_at": item.fetched_at.isoformat(),
                              "application_id": str(item.application.id),
                              "application_tenant": str(item.application.tenant_id),
                              "application_organization": str(item.application.organization_id or ""),
                              "application_source": str(item.application.source_id),
                              "applied_at": item.application.applied_at.isoformat(),
                              "actor": str(item.application.actor_id)}
                             for item in observations],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def create_native_monitored_source_fixture(owner: User) -> str:
    with coordinated_repository_transaction():
        _bind(owner)
        tenant = require_installation_member(owner).tenant
        workspace = Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP)
        repository = ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        authored = author_content(
            repository=repository, actor_id=owner.id, request_id=None, operation="create",
            content_id=CONTENT_ID,
            base_commit=repository.accepted_commit.object_id if repository.accepted_commit else None,
            base_blob=None, kind="document", path="docs/native-monitored-acceptance.md",
            title="Native monitored acceptance", markdown="Native monitored baseline.\n", metadata_patch={},
        )
        source = DocumentRemoteSource.objects.create(
            tenant=tenant, organization=None, repository=repository, content_id=CONTENT_ID,
            url="https://example.invalid/native-monitored-acceptance.md", source_kind="markdown",
            enabled=False, check_interval_minutes=180, created_by=owner,
        )
        for markdown in (authored.markdown, "Native monitored recovered update.\n"):
            observation = DocumentRemoteObservation.objects.create(
                tenant=tenant, organization=None, source=source, state="changed", status_code=200,
                content_type="text/markdown", content_digest=hashlib.sha256(markdown.encode()).hexdigest(),
                canonical_markdown=markdown,
            )
            review = preview_remote_observation(observation=observation)
            assert review and not review["blocker"]
            with coordinated_repository_transaction():
                _bind(owner)
                apply_git_observation(
                    source=source, document=None, repository=repository, observation=observation,
                    actor_id=owner.id, review_fingerprint=review["fingerprint"],
                )
            source.refresh_from_db()
            repository.refresh_from_db()
    return native_monitored_source_fingerprint(owner)


mode = os.environ.get("TEKDOCS_NATIVE_MONITORED_SOURCE_FIXTURE_MODE")
if mode:
    owner = InstallationState.objects.select_related("owner").get(pk=InstallationState.SINGLETON_ID).owner
    if mode == "create":
        print("NATIVE_MONITORED_SOURCE_SHA256=" + create_native_monitored_source_fixture(owner))
    elif mode == "verify":
        expected = os.environ["TEKDOCS_NATIVE_MONITORED_SOURCE_SHA256"]
        actual = native_monitored_source_fingerprint(owner)
        assert actual == expected, (actual, expected)
        print("Git-native monitored settings, observations and managed Git recovered independently.")
    else:
        raise ValueError("Unsupported native monitored-source fixture mode")
