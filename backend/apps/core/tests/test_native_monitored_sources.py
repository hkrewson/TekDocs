from __future__ import annotations

import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, transaction
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core import repository_storage
from apps.core.content_authoring import author_content, read_authored_content
from apps.core.models import (
    Document,
    DocumentRemoteObservation,
    DocumentRemoteSource,
    InstallationState,
    Workspace,
    WorkspaceKind,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def authoring_context(tmp_path):
    with override_settings(TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories")):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Native monitored MSP",
            owner_email=f"native-monitored-{uuid.uuid4()}@example.invalid",
            owner_display_name="Native Monitored Owner",
            password="NativeMonitoredPassword-2026!",
        )
        TOTP.activate(installation.owner, generate_totp_secret())
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository = repository_storage.ensure_workspace_repository(workspace).repository
        repository.refresh_from_db()
        yield installation, repository


def _native_document(authoring_context):
    installation, repository = authoring_context
    result = author_content(
        repository=repository,
        actor_id=installation.owner.id,
        request_id=None,
        operation="create",
        content_id=uuid.uuid4(),
        base_commit=repository.accepted_commit.object_id if repository.accepted_commit else None,
        base_blob=None,
        kind="document",
        path=None,
        title="Native monitored procedure",
        markdown="Original local instructions.\n",
        metadata_patch={},
    )
    assert not Document.objects.filter(pk=result.content_id).exists()
    return installation, repository, result


def test_native_monitored_source_configuration_has_no_legacy_owner_requirement(authoring_context):
    installation, repository, authored = _native_document(authoring_context)
    browser = Client()
    browser.force_login(installation.owner)
    url = reverse("msp-content-authoring-remote-source", args=[authored.content_id])
    assert Client().get(url).status_code in {401, 403}
    response = browser.get(url)
    assert response.status_code == 204, response.content
    saved = browser.put(url, {
        "url": "https://example.invalid/native-guide.md",
        "source_kind": "markdown",
        "enabled": False,
        "check_interval_minutes": 180,
    }, content_type="application/json")
    assert saved.status_code == 201, saved.content
    source = DocumentRemoteSource.objects.get(pk=saved.json()["id"])
    assert source.document_id is None
    assert source.repository_id == repository.id
    assert source.content_id == authored.content_id
    assert browser.get(url).json()["url"] == "https://example.invalid/native-guide.md"
    with pytest.raises(DatabaseError, match="remote source owner is immutable"), transaction.atomic():
        DocumentRemoteSource.objects.filter(pk=source.pk).update(content_id=uuid.uuid4())
    source.refresh_from_db()
    assert source.content_id == authored.content_id


def test_native_monitored_observations_apply_and_protect_local_edits(authoring_context, tmp_path):
    installation, repository, authored = _native_document(authoring_context)
    browser = Client()
    browser.force_login(installation.owner)
    source_url = reverse("msp-content-authoring-remote-source", args=[authored.content_id])
    saved = browser.put(source_url, {
        "url": "https://example.invalid/native-guide.md",
        "source_kind": "markdown", "enabled": False, "check_interval_minutes": 180,
    }, content_type="application/json")
    source = DocumentRemoteSource.objects.get(pk=saved.json()["id"])
    baseline = DocumentRemoteObservation.objects.create(
        tenant=source.tenant, organization=source.organization, source=source,
        state="changed", status_code=200, content_type="text/markdown",
        content_digest="a" * 64, canonical_markdown="Original local instructions.\n",
    )
    observations_url = reverse("msp-content-authoring-remote-observations", args=[authored.content_id])
    review = browser.get(observations_url)
    assert review.status_code == 200, review.content
    fingerprint = review.json()["results"][0]["apply_review"]["fingerprint"]
    applied = browser.post(
        reverse("msp-content-authoring-remote-observation-apply", args=[authored.content_id, baseline.id]),
        {"review_fingerprint": fingerprint}, content_type="application/json",
    )
    assert applied.status_code == 200, applied.content
    source.refresh_from_db()
    assert source.last_applied_observation_id == baseline.id

    current = read_authored_content(repository=repository, content_id=authored.content_id)
    local = author_content(
        repository=repository, actor_id=installation.owner.id, request_id=None,
        operation="update", content_id=authored.content_id,
        base_commit=current.accepted_commit, base_blob=current.source_blob,
        kind=None, path=None, title=None, markdown="Important local edit.\n", metadata_patch={},
    )
    changed = DocumentRemoteObservation.objects.create(
        tenant=source.tenant, organization=source.organization, source=source,
        state="changed", status_code=200, content_type="text/markdown",
        content_digest="b" * 64, canonical_markdown="New remote instructions.\n",
    )
    blocked_review = browser.get(observations_url).json()["results"][0]["apply_review"]
    assert blocked_review["blocker"] == "local_edits_require_integration"
    from apps.core.repository_publication_evidence import (
        RepositoryPublicationEvidenceError,
        retain_repository_publication_evidence,
    )

    with override_settings(MEDIA_ROOT=str(tmp_path / "native-monitored-publication")):
        with pytest.raises(RepositoryPublicationEvidenceError, match="remote.observation.unapplied"):
            retain_repository_publication_evidence(
                repository_id=repository.id, content_id=authored.content_id,
                audience="msp_internal", actor=installation.owner,
            )
    blocked = browser.post(
        reverse("msp-content-authoring-remote-observation-apply", args=[authored.content_id, changed.id]),
        {"review_fingerprint": blocked_review["fingerprint"]}, content_type="application/json",
    )
    assert blocked.status_code == 409
    assert read_authored_content(repository=repository, content_id=authored.content_id) == local
    source.refresh_from_db()
    assert source.last_applied_observation_id == baseline.id
