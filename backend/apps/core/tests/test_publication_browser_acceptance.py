"""Real HTTP/browser acceptance, opt-in through the existing-project harness.

Private IPC carries generated test sessions only and is never retained as evidence.
Normal backend shards skip this test; the required live-browser job runs it.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import uuid
from copy import deepcopy
from pathlib import Path

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.conf import settings
from django.db import connection
from django.db.backends.signals import connection_created
from django.test import Client, override_settings

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core import document_migration_import, repository_storage
from apps.core.content_index import index_repository_content
from apps.core.document_authority_handoff import transition_document_authority
from apps.core.document_migration_publications import assess_retained_publications
from apps.core.documents import create_document, resolve_document, update_document
from apps.core.models import DocumentAuthority, DocumentPublication, InstallationState, Workspace, WorkspaceKind
from apps.core.publications import publish_document, read_publication_artifact, verify_publication
from apps.core.rls_contract import RUNTIME_ROLE
from apps.core.workspaces import resolve_msp_workspace

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not os.environ.get("TEKDOCS_PUBLICATION_ACCEPTANCE_DIRECTORY"), reason="Requires live browser harness"
    ),
]


def _write_state(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream)
    temporary.replace(path)


def _wait(path: Path) -> dict[str, str]:
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text())  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("The browser did not complete its acceptance phase")


def test_migrated_publication_browser_journey(request, tmp_path, django_runtime_role):
    state = Path(os.environ["TEKDOCS_PUBLICATION_ACCEPTANCE_DIRECTORY"])
    with override_settings(
        TEKDOCS_REPOSITORY_ROOT=str(tmp_path / "repositories"),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["localhost", "127.0.0.1", "migrate", "testserver"],
        CSRF_TRUSTED_ORIGINS=["http://localhost:8080"],
    ):
        InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
        installation = bootstrap_owner(
            tenant_name="Publication browser fixture",
            owner_email=f"publisher-{uuid.uuid4()}@example.invalid",
            owner_display_name="Browser fixture owner",
            password=f"{secrets.token_urlsafe(24)}Aa7!",
        )
        TOTP.activate(installation.owner, generate_totp_secret())
        workspace = Workspace.objects.get(tenant=installation.tenant, kind=WorkspaceKind.MSP)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        reader = resolve_msp_workspace(installation.owner)
        document = create_document(
            tenant=installation.tenant,
            organization=None,
            actor_id=installation.owner.id,
            title="Migrated publication acceptance guide",
            markdown="Original signed browser instructions.\n",
        )
        original = publish_document(
            workspace=reader,
            document=document,
            actor_id=installation.owner.id,
            reason="Retain original instructions",
            audience="msp_internal",
            retention="permanent",
            retention_review_on=None,
        )
        retained = (deepcopy(original.manifest), original.signature, original.content_digest)
        original_pdf = read_publication_artifact(original.artifacts.get())
        update_document(
            document=document,
            actor_id=installation.owner.id,
            title=document.entity.display_name,
            markdown="Current migrated browser instructions.\n",
            base_revision_id=document.placements.get().block.current_revision_id,
        )
        plan = document_migration_import.prepare_document_import(workspace=workspace, document_id=document.id)
        assert (
            document_migration_import.apply_document_import(
                workspace=workspace,
                document_id=document.id,
                expected_base=plan.base_commit,
                plan_sha256=plan.plan_sha256,
                actor_id=installation.owner.id,
            ).status
            == "imported"
        )
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=document.id,
                actor_id=installation.owner.id,
                target="repository",
                reader_workspace=reader,
            )
            == "transitioned"
        )
        viewer = User.objects.create_user(email=f"viewer-{uuid.uuid4()}@example.invalid", display_name="Browser reader")
        TenantMembership.objects.create(tenant=installation.tenant, user=viewer, role=BuiltInRole.READ_ONLY)
        sessions = {}
        for name, user in (("owner", installation.owner), ("viewer", viewer)):
            browser = Client()
            browser.force_login(user)
            sessions[name] = browser.cookies[settings.SESSION_COOKIE_NAME].value

        prepared_state = {
            "document_id": str(document.entity_id),
            "content_id": str(document.id),
            "fragment_id": str(document.placements.get().block_id),
            "original_id": str(original.entity_id),
            "original_pdf_sha256": hashlib.sha256(original_pdf).hexdigest(),
            "session_name": settings.SESSION_COOKIE_NAME,
            "sessions": sessions,
        }
        # The live server opens its own connections through the constrained role.
        # Fixture metadata is collected beforehand, outside the request RLS scope.
        served_roles = set()

        def record_http_connection(sender, connection, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                served_roles.add(cursor.fetchone()[0])

        with django_runtime_role():
            assert connection.settings_dict["USER"] == RUNTIME_ROLE
            server = request.getfixturevalue("live_server")
            assert server.url.endswith(":8081")
            connection_created.connect(record_http_connection, weak=False)
            try:
                _write_state(state / "ready.json", prepared_state)
                result = _wait(state / "browser-finished.json")
                assert result.get("status") == "passed", "Browser acceptance failed"
            finally:
                server.stop()
                connection_created.disconnect(record_http_connection)
        assert served_roles == {RUNTIME_ROLE}

        original.refresh_from_db()
        assert (original.manifest, original.signature, original.content_digest) == retained
        assert read_publication_artifact(original.artifacts.get()) == original_pdf
        assert original.lifecycle_state == "superseded"
        snapshots = list(DocumentPublication.objects.filter(document=document).order_by("published_at"))
        assert len(snapshots) == 4
        assert [item.lifecycle_state for item in snapshots] == ["superseded", "superseded", "published", "withdrawn"]
        assert all(verify_publication(item)["valid"] for item in snapshots)
        assessment = assess_retained_publications(workspace=workspace, document=document)
        assert assessment["state"] == "verified"
        for target in ("legacy", "repository"):
            assert (
                transition_document_authority(
                    workspace=workspace,
                    document_id=document.id,
                    actor_id=installation.owner.id,
                    target=target,
                    reader_workspace=reader,
                )
                == "transitioned"
            )
            assert assess_retained_publications(workspace=workspace, document=document) == assessment
            if target == "legacy":
                assert "Browser-corrected Git instructions." in resolve_document(document).markdown
        assert DocumentAuthority.objects.get(workspace=workspace, content_id=document.id).authority == "repository"
