"""Synthetic staff publication lineage carried through independent recovery."""

import hashlib
import json
import os
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.policy import require_installation_member
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.content_index import index_repository_content
from apps.core.content_read import document_detail
from apps.core.document_attachments import append_repository_primary_document_file, copy_attachment_content
from apps.core.models import (
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    Entity,
    RepositoryPublicationEvidence,
    Site,
    Tenant,
    Workspace,
)
from apps.core.repository_internal_publications import internal_publication_state, record_internal_publication
from apps.core.repository_key_context import canonical_key_bindings
from apps.core.repository_publication_evidence import (
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
from apps.core.sites import create_site
from apps.core.workspaces import resolve_msp_workspace

CONTENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.native.internal.publication")
FRAGMENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.native.key.fragment")
ORIGINAL_LOCATION = "Native recovery original location"
LATER_LOCATION = "Native recovery replacement location"


def _site(owner: User, tenant: Tenant, name: str) -> Site:
    return create_site(
        tenant=tenant, organization=None, actor_id=owner.id, name=name,
        code="NKR1" if name == ORIGINAL_LOCATION else "NKR2",
        address_line_1="", address_line_2="", city="", region="", postal_code="",
        country_code="", timezone="UTC", phone="",
    )


PRIMARY_CONTENT = (
    b"Native recovery primary file, original.\n",
    b"Native recovery primary file, replacement.\n",
    b"Native recovery primary file, after publication.\n",
)


def native_internal_publication_fingerprint(owner: User) -> str:
    tenant = require_installation_member(owner).tenant
    snapshots = list(
        RepositoryPublicationEvidence.objects.filter(
            tenant=tenant,
            content_id=CONTENT_ID,
            audience="msp_internal",
        ).order_by("signed_at")
    )
    assert len(snapshots) == 2 and not Document.objects.filter(tenant=tenant, pk=CONTENT_ID).exists()
    assert [internal_publication_state(item) for item in snapshots] == ["superseded", "withdrawn"]
    versions = list(DocumentAttachment.objects.filter(
        tenant=tenant, owner_content_id=CONTENT_ID, document__isnull=True,
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
            "id": str(version.entity_id), "owner": str(version.owner_content_id),
            "workspace": str(version.owner_workspace_id), "version": version.version_number,
            "replaces": str(version.replaces_id), "file": version.file.name,
            "checksum": version.checksum, "bytes_sha256": hashlib.sha256(content).hexdigest(),
        })
    records = []
    for index, snapshot in enumerate(snapshots):
        assert verify_repository_publication_evidence(snapshot)["valid"]
        assert snapshot.manifest['format'] == 'tekdocs-repository-publication-evidence/v3'
        assert ORIGINAL_LOCATION in snapshot.manifest['key_snapshot']['markdown']
        assert LATER_LOCATION not in snapshot.manifest['key_snapshot']['markdown']
        assert {record['kind'] for record in snapshot.manifest['key_snapshot']['records']} == {'field', 'content'}
        assert snapshot.manifest["primary_file"]["selected_source_id"] == str(versions[index].entity_id)
        assert [row["source_id"] for row in snapshot.manifest["primary_file"]["versions"]] == [
            str(version.entity_id) for version in versions[:index + 1]
        ]
        with snapshot.pdf_file.open("rb") as stream:
            pdf = stream.read()
        records.append(
            {
                "id": str(snapshot.id),
                "manifest": snapshot.manifest,
                "signature": snapshot.signature,
                "digest": snapshot.content_digest,
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "events": [
                    {
                        "id": str(event.id),
                        "action": event.action,
                        "reason": event.reason,
                        "actor": str(event.actor_id),
                        "supersedes": str(event.supersedes_id),
                        "at": event.occurred_at.isoformat(),
                    }
                    for event in snapshot.internal_events.all()
                ],
            }
        )
    repository = snapshots[0].repository
    root = read_authored_content(repository=repository, content_id=CONTENT_ID)
    fragment = read_authored_content(repository=repository, content_id=FRAGMENT_ID)
    from apps.core.content_profile import parse_content

    bindings = canonical_key_bindings(parse_content(root.source.encode()).frontmatter['key_bindings'])
    assert bindings['procedure'] == str(FRAGMENT_ID)
    assert not Document.objects.filter(pk=CONTENT_ID).exists()
    html = document_detail(
        workspace=resolve_msp_workspace(owner), content_id=CONTENT_ID, audience='all',
    )['sanitized_html']
    assert LATER_LOCATION in html and 'Native recovery later procedure.' in html
    live = {
        'bindings': bindings,
        'sources': [{'id': str(item.content_id), 'path': item.path, 'blob': item.source_blob,
                     'sha256': hashlib.sha256(item.source.encode()).hexdigest()} for item in (root, fragment)],
        'html_sha256': hashlib.sha256(html.encode()).hexdigest(),
    }
    payload = json.dumps(
        {"publications": records, "primary_files": files, "native_keys": live}, sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def create_native_internal_publication_fixture(owner: User) -> str:
    tenant = require_installation_member(owner).tenant
    workspace = Workspace.objects.get(tenant=tenant, organization__isnull=True)
    repository = ensure_workspace_repository(workspace).repository
    if repository.accepted_commit_id is not None:
        index_repository_content(repository_id=repository.id)
    location = _site(owner, tenant, ORIGINAL_LOCATION)
    repository.refresh_from_db()
    accepted = repository.accepted_commit
    fragment = author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation='create', content_id=FRAGMENT_ID,
        base_commit=accepted.object_id if accepted else None, base_blob=None,
        kind='fragment', path='fragments/native-recovery-keys.md', title='Native recovery key source',
        markdown=f'Native recovery original procedure.\n\n<tekdocs://key/location.name>\n\n<tekdocs://entity/{location.entity_id}>\n',
        metadata_patch={},
    )
    source = None
    previous = None
    primary = None
    for index, body in enumerate(("Staff recovery original.\n", "Staff recovery corrected.\n")):
        repository.refresh_from_db()
        accepted = repository.accepted_commit
        source = author_content(
            repository=repository,
            actor_id=owner.id,
            request_id=None,
            operation="update" if source else "create",
            content_id=CONTENT_ID,
            base_commit=source.accepted_commit if source else accepted.object_id if accepted else None,
            base_blob=source.source_blob if source else None,
            kind="document" if source is None else None,
            path="docs/native-staff-publication-recovery.md" if source is None else None,
            title="Native staff publication recovery" if source is None else None,
            markdown=body + '\n<tekdocs://key/procedure.content>\n',
            metadata_patch={'key_bindings': {'location': str(location.entity_id), 'procedure': str(FRAGMENT_ID)}}
            if source is None else {},
        )
        primary = append_repository_primary_document_file(
            repository=repository, content_id=CONTENT_ID, actor_id=owner.id,
            upload=SimpleUploadedFile(f"native-recovery-v{index + 1}.txt", PRIMARY_CONTENT[index]),
            expected_current_entity_id=primary.entity_id if primary else None,
        )
        evidence = retain_repository_publication_evidence(
            repository_id=repository.id,
            content_id=CONTENT_ID,
            audience="msp_internal",
            actor=owner,
            expected_commit=source.accepted_commit,
        )
        record_internal_publication(
            evidence=evidence,
            actor=owner,
            action="released",
            reason="Retain staff recovery edition",
            supersedes_id=previous.id if previous else None,
        )
        previous = evidence
    assert previous is not None
    record_internal_publication(
        evidence=previous, actor=owner, action="withdrawn", reason="Retain withdrawn staff history"
    )
    later = _site(owner, tenant, LATER_LOCATION)
    Entity.objects.filter(pk=location.entity_id).update(display_name='Native recovery original record changed')
    author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation='update', content_id=FRAGMENT_ID,
        base_commit=fragment.accepted_commit, base_blob=fragment.source_blob, kind=None, path=None, title=None,
        markdown='Native recovery later procedure.\n\n<tekdocs://key/location.name>\n', metadata_patch={},
    )
    assert source is not None
    author_content(
        repository=repository, actor_id=owner.id, request_id=None, operation='update', content_id=CONTENT_ID,
        base_commit=source.accepted_commit, base_blob=source.source_blob, kind=None, path=None, title=None,
        markdown=None,
        metadata_patch={'key_bindings': {'location': str(later.entity_id), 'procedure': str(FRAGMENT_ID)}},
    )
    assert primary is not None
    append_repository_primary_document_file(
        repository=repository, content_id=CONTENT_ID, actor_id=owner.id,
        upload=SimpleUploadedFile("native-recovery-v3.txt", PRIMARY_CONTENT[2]),
        expected_current_entity_id=primary.entity_id,
    )
    return native_internal_publication_fingerprint(owner)


if os.environ.get("TEKDOCS_NATIVE_INTERNAL_FIXTURE_MODE"):
    owner = User.objects.get(email="validation-recovery@example.invalid")
    tenant = require_installation_member(owner).tenant
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.tenant(tenant),
            organization_mode=OrganizationRLSMode.MSP_ONLY,
            actor_user_id=owner.id,
            principal_mode=RLSPrincipalMode.USER,
        )
        print("INTERNAL_PUBLICATION_SHA256=" + create_native_internal_publication_fixture(owner))
