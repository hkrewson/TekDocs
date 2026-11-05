"""Synthetic native enrollment and independent signed custody for encrypted recovery."""

import hashlib
import json
import os
import uuid
from contextlib import contextmanager

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.accounts.policy import require_installation_member
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_index import index_repository_content
from apps.core.content_read import document_detail
from apps.core.document_attachments import append_repository_primary_document_file, copy_attachment_content
from apps.core.models import (
    Block,
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    Organization,
    RepositoryPublicationEvidence,
    RepositoryTemplate,
    RepositoryTemplateEnrollment,
    Workspace,
)
from apps.core.native_templates import (
    apply_native_template,
    configure_native_template,
    detach_native_template,
    enroll_native_template,
    native_template_state,
)
from apps.core.organizations import create_organization
from apps.core.repository_internal_publications import internal_publication_state, record_internal_publication
from apps.core.repository_publication_evidence import (
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from apps.core.repository_service import coordinated_repository_transaction
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.workspaces import resolve_organization_workspace

SOURCE_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.native.template")
SECTION_IDS = {
    mode: uuid.uuid5(uuid.NAMESPACE_DNS, f"tekdocs.recovery.fixture.native.template.{mode}")
    for mode in ("copy", "live", "pinned")
}
CLIENT_NAME = "Native template recovery client"
LOCAL_INTRO = "Native recovery client-owned introduction.\n"
PRIMARY_CONTENT = tuple(f"Native template recovery primary {number}.\n".encode() for number in (1, 2, 3))


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _bind(owner, tenant, organization=None):
    bind_local_rls_scope(
        DataScope.owner(tenant, organization),
        organization_mode=OrganizationRLSMode.ORGANIZATION if organization else OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id, principal_mode=RLSPrincipalMode.USER,
    )


@contextmanager
def _fixture_scope(owner):
    """Fixture orchestration spans the owner's explicitly authorized Workspaces."""
    tenant = require_installation_member(owner).tenant
    with coordinated_repository_transaction():
        bind_local_rls_scope(
            DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.ALL_AUTHORIZED,
            actor_user_id=owner.id, principal_mode=RLSPrincipalMode.USER,
        )
        yield tenant


def _edit(repository, owner, content_id, *, body=None):
    current = read_authored_content(repository=repository, content_id=content_id)
    return author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation="update",
        content_id=content_id, base_commit=current.accepted_commit, base_blob=current.source_blob,
        kind=None, path=None, title=None, markdown=body, metadata_patch={},
    )


def _html(owner, organization, content_id):
    return document_detail(
        workspace=resolve_organization_workspace(owner, entity_id=organization.entity_id),
        content_id=content_id, audience="all",
    )["sanitized_html"]


def _body(mode, edition):
    return f"Native recovery {mode} edition {edition}.\n"


def _source_record(source):
    return {"id": str(source.content_id), "path": source.path, "blob": source.source_blob,
            "sha256": _sha(source.source.encode())}


def native_template_recovery_fingerprint(owner: User) -> str:
    """Check live enrollment and retained bytes separately, then hash their exact state."""
    with _fixture_scope(owner) as tenant:
        organization = Organization.objects.get(tenant=tenant, entity__display_name=CLIENT_NAME)
        _bind(owner, tenant)
        template = RepositoryTemplate.objects.select_related("repository", "latest_revision").get(
            tenant=tenant, content_id=SOURCE_ID, workspace__organization__isnull=True,
        )
        source_ids = [SOURCE_ID, *SECTION_IDS.values()]
        assert not Document.objects.filter(tenant=tenant, pk__in=source_ids).exists()
        assert not Block.objects.filter(tenant=tenant, pk__in=source_ids).exists()
        source_files = [_source_record(read_authored_content(repository=template.repository, content_id=item))
                        for item in source_ids]
        source_revisions = [{"id": str(row.id), "manifest": row.manifest, "checksum": row.checksum,
                             "commit": row.commit.object_id}
                            for row in template.revisions.select_related("commit").order_by("created_at", "id")]
        _bind(owner, tenant, organization)
        enrollment = RepositoryTemplateEnrollment.objects.select_related("repository").get(
            tenant=tenant, organization=organization, source_template=template,
        )
        repository = enrollment.repository
        root = read_authored_content(repository=repository, content_id=enrollment.content_id)
        ids = [SOURCE_ID, *SECTION_IDS.values(), enrollment.content_id]
        ids.extend(uuid.UUID(item["local_id"]) for item in enrollment.placement_map if item.get("local_id"))
        assert not Document.objects.filter(tenant=tenant, pk__in=ids).exists()
        assert not Block.objects.filter(tenant=tenant, pk__in=ids).exists()
        html = _html(owner, organization, enrollment.content_id)
        assert LOCAL_INTRO.strip() in html
        for mode, edition in (("copy", 1), ("live", 2), ("pinned", 2)):
            assert _body(mode, edition).strip() in html
            assert _body(mode, 3).strip() not in html
        versions = list(DocumentAttachment.objects.filter(
            tenant=tenant, organization=organization, owner_workspace_id=repository.workspace_id,
            owner_content_id=enrollment.content_id, document__isnull=True,
            purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
        ).order_by("version_number"))
        assert len(versions) == len(PRIMARY_CONTENT)
        files = []
        for index, version in enumerate(versions):
            content = copy_attachment_content(version)
            assert content == PRIMARY_CONTENT[index]
            assert version.version_number == index + 1
            assert version.replaces_id == (versions[index - 1].id if index else None)
            files.append({
                "id": str(version.entity_id), "workspace": str(version.owner_workspace_id),
                "owner": str(version.owner_content_id), "version": version.version_number,
                "replaces": str(version.replaces_id), "file": version.file.name,
                "filename": version.original_filename, "media_type": version.media_type, "size": version.size,
                "checksum": version.checksum, "sha256": _sha(content),
            })
        snapshots = list(RepositoryPublicationEvidence.objects.filter(
            tenant=tenant, organization=organization, repository=repository,
            content_id=enrollment.content_id, audience="msp_internal",
        ).order_by("signed_at"))
        assert len(snapshots) == 2
        assert [internal_publication_state(item) for item in snapshots] == ["superseded", "released"]
        publications = []
        for index, snapshot in enumerate(snapshots):
            # The verifier consumes retained source proofs/files, never today's source definition.
            assert verify_repository_publication_evidence(snapshot)["valid"]
            assert snapshot.manifest["format"] == "tekdocs-repository-publication-evidence/v4"
            frozen = snapshot.canonical_markdown
            assert LOCAL_INTRO.strip() in frozen and _body("copy", 1).strip() in frozen
            for mode in ("live", "pinned"):
                assert _body(mode, index + 1).strip() in frozen
                assert _body(mode, 3).strip() not in frozen
            primary = snapshot.manifest["primary_file"]
            assert primary["selected_source_id"] == str(versions[index].entity_id)
            assert [row["source_id"] for row in primary["versions"]] == [
                str(version.entity_id) for version in versions[:index + 1]
            ]
            retained = []
            artifacts = list(snapshot.attachments.select_related("source_attachment").order_by("id"))
            assert len(artifacts) == index + 1
            for artifact in artifacts:
                position = next(i for i, item in enumerate(versions) if item.id == artifact.source_attachment_id)
                with artifact.file.open("rb") as stream:
                    content = stream.read()
                assert content == PRIMARY_CONTENT[position]
                assert artifact.file.name != artifact.source_attachment.file.name
                retained.append({"id": str(artifact.id), "source": str(artifact.source_attachment_id),
                                 "file": artifact.file.name, "checksum": artifact.checksum, "sha256": _sha(content),
                                 "media_type": artifact.media_type, "size": artifact.size})
            with snapshot.pdf_file.open("rb") as stream:
                pdf = stream.read()
            publications.append({
                "id": str(snapshot.id), "manifest": snapshot.manifest, "signature": snapshot.signature,
                "digest": snapshot.content_digest, "pdf": snapshot.pdf_file.name,
                "pdf_sha256": _sha(pdf), "files": retained,
                "events": [{"id": str(event.id), "action": event.action, "reason": event.reason,
                            "actor": str(event.actor_id), "supersedes": str(event.supersedes_id),
                            "at": event.occurred_at.isoformat()}
                           for event in snapshot.internal_events.order_by("occurred_at", "id")],
            })
        local_ids = [uuid.UUID(item["local_id"]) for item in enrollment.placement_map if item.get("local_id")]
        live_sources = [_source_record(root)] + [
            _source_record(read_authored_content(repository=repository, content_id=item)) for item in local_ids
        ]
        payload = {
            "source": {"id": str(template.id), "repository": str(template.repository_id),
                       "workspace": str(template.workspace_id), "enabled": template.enabled,
                       "library_visible": template.library_visible, "latest": str(template.latest_revision_id),
                       "files": source_files,
                       "revisions": source_revisions,
                       },
            "client": {"id": str(enrollment.id), "organization": str(organization.id),
                       "workspace": str(enrollment.workspace_id), "repository": str(repository.id),
                       "content_id": str(enrollment.content_id), "applied": str(enrollment.applied_revision_id),
                       "placements": enrollment.placement_map, "sources": live_sources,
                       "html_sha256": _sha(html.encode())},
            "publications": publications, "primary_files": files,
        }
        return _sha(json.dumps(payload, sort_keys=True).encode())


def create_native_template_recovery_fixture(owner: User) -> str:
    with _fixture_scope(owner) as tenant:
        organization = create_organization(
            tenant=tenant, actor_id=owner.id, name=CLIENT_NAME, legal_name="", website="", classifications=["client"],
        )
        _bind(owner, tenant)
        source_workspace = Workspace.objects.get(tenant=tenant, organization__isnull=True)
        source_repository = ensure_workspace_repository(source_workspace).repository
        if source_repository.accepted_commit_id is not None:
            index_repository_content(repository_id=source_repository.id)
        for mode, content_id in SECTION_IDS.items():
            source_repository.refresh_from_db()
            accepted = source_repository.accepted_commit
            author_content(
                repository=source_repository, actor_id=owner.id, request_id=None, operation="create",
                content_id=content_id, base_commit=accepted.object_id if accepted else None, base_blob=None,
                kind="fragment", path=f"fragments/native-template-recovery-{mode}.md",
                title=f"Recovery {mode} section", markdown=_body(mode, 1), metadata_patch={},
            )
        source_repository.refresh_from_db()
        source = author_content(
            repository=source_repository, actor_id=owner.id, request_id=None, operation="create",
            content_id=SOURCE_ID, base_commit=source_repository.accepted_commit.object_id, base_blob=None,
            kind="document", path="docs/native-template-recovery.md", title="Native recovery template",
            markdown="Native recovery template introduction.\n", metadata_patch={},
        )
        configure_native_template(
            repository=source_repository, actor_id=owner.id, request_id=None, content_id=SOURCE_ID,
            base_commit=source.accepted_commit, base_blob=source.source_blob, enabled=True,
            library_visible=True, fragment_ids=list(SECTION_IDS.values()),
        )
        template = RepositoryTemplate.objects.select_related("latest_revision").get(
            tenant=tenant, repository=source_repository, content_id=SOURCE_ID,
        )
        _bind(owner, tenant, organization)
        workspace = Workspace.objects.get(tenant=tenant, organization=organization)
        repository = ensure_workspace_repository(workspace).repository
        root = enroll_native_template(
            repository=repository, actor_id=owner.id, request_id=None, source_content_id=SOURCE_ID,
            definition_sha256=template.latest_revision.checksum, title="Native enrolled recovery document",
            rules={str(item): mode for mode, item in SECTION_IDS.items()},
        )
        root = _edit(repository, owner, root.content_id, body=LOCAL_INTRO)
        primary = None
        previous = None
        for edition in (1, 2):
            if edition == 2:
                _bind(owner, tenant)
                for mode, content_id in SECTION_IDS.items():
                    _edit(source_repository, owner, content_id, body=_body(mode, 2))
                _bind(owner, tenant, organization)
                before = _html(owner, organization, root.content_id)
                assert _body("copy", 1).strip() in before and _body("live", 2).strip() in before
                assert _body("pinned", 1).strip() in before
                state = native_template_state(repository=repository, content_id=root.content_id)["enrollment"]
                root = apply_native_template(
                    repository=repository, actor_id=owner.id, request_id=None, content_id=root.content_id,
                    base_commit=state["expected_base"], base_blob=state["expected_blob"],
                    expected_applied_revision_id=state["applied_revision_id"],
                    expected_available_revision_id=state["available_revision_id"],
                    rules={str(item): "keep" if mode == "copy" else mode for mode, item in SECTION_IDS.items()},
                )
                state = native_template_state(repository=repository, content_id=root.content_id)["enrollment"]
                root = detach_native_template(
                    repository=repository, actor_id=owner.id, request_id=None, content_id=root.content_id,
                    base_commit=state["expected_base"], base_blob=state["expected_blob"],
                    expected_applied_revision_id=state["applied_revision_id"],
                    expected_available_revision_id=state["available_revision_id"], section_id=str(SECTION_IDS["live"]),
                )
            primary = append_repository_primary_document_file(
                repository=repository, content_id=root.content_id, actor_id=owner.id,
                upload=SimpleUploadedFile(f"native-template-recovery-{edition}.txt", PRIMARY_CONTENT[edition - 1]),
                expected_current_entity_id=primary.entity_id if primary else None,
            )
            root = read_authored_content(repository=repository, content_id=root.content_id)
            evidence = retain_repository_publication_evidence(
                repository_id=repository.id, content_id=root.content_id, audience="msp_internal",
                actor=owner, expected_commit=root.accepted_commit,
            )
            record_internal_publication(
                evidence=evidence, actor=owner, action="released", reason="Native template recovery edition",
                supersedes_id=previous.id if previous else None,
            )
            previous = evidence
        _bind(owner, tenant)
        for mode, content_id in SECTION_IDS.items():
            _edit(source_repository, owner, content_id, body=_body(mode, 3))
        _bind(owner, tenant, organization)
        append_repository_primary_document_file(
            repository=repository, content_id=root.content_id, actor_id=owner.id,
            upload=SimpleUploadedFile("native-template-recovery-3.txt", PRIMARY_CONTENT[2]),
            expected_current_entity_id=primary.entity_id,
        )
    return native_template_recovery_fingerprint(owner)


if os.environ.get("TEKDOCS_NATIVE_TEMPLATE_FIXTURE_MODE") == "create":
    owner = User.objects.get(email="validation-recovery@example.invalid")
    print("NATIVE_TEMPLATE_SHA256=" + create_native_template_recovery_fixture(owner))
