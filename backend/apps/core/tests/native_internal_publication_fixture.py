"""Synthetic staff publication lineage carried through independent recovery."""

import hashlib
import json
import os
import uuid

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.policy import require_installation_member
from apps.core.content_authoring import author_content
from apps.core.content_index import index_repository_content
from apps.core.models import Document, RepositoryPublicationEvidence, Workspace
from apps.core.repository_internal_publications import internal_publication_state, record_internal_publication
from apps.core.repository_publication_evidence import (
    retain_repository_publication_evidence,
    verify_repository_publication_evidence,
)
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope

CONTENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "tekdocs.recovery.fixture.native.internal.publication")


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
    records = []
    for snapshot in snapshots:
        assert verify_repository_publication_evidence(snapshot)["valid"]
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
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def create_native_internal_publication_fixture(owner: User) -> str:
    tenant = require_installation_member(owner).tenant
    workspace = Workspace.objects.get(tenant=tenant, organization__isnull=True)
    repository = ensure_workspace_repository(workspace).repository
    index_repository_content(repository_id=repository.id)
    source = None
    previous = None
    for body in ("Staff recovery original.\n", "Staff recovery corrected.\n"):
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
            markdown=body,
            metadata_patch={},
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
