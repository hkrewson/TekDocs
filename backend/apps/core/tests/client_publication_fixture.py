"""Synthetic client custody for browser, 0.8.46 upgrade and encrypted recovery."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.serializers.json import DjangoJSONEncoder
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_control import assign_organization_staff
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.accounts.policy import require_installation_member
from apps.core.document_attachments import (
    copy_attachment_content,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.documents import create_document, create_document_block, resolve_document
from apps.core.models import Document, DocumentKeyBinding, InstallationState
from apps.core.organizations import create_organization
from apps.core.publications import approve_publication, publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.sites import create_site
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Client publication migration acceptance guide"
COMPANION = "Client publication recovery companion"
SHARED = "Retained shared client instructions."
CURRENT = "Current shared client instructions."
PRIVATE = "MSP-only migration instructions."
PUBLIC = "Client-only migration instructions."


class _RetainedJSONEncoder(DjangoJSONEncoder):
    # The standalone seed also runs on 0.8.46. Keep every stored microsecond;
    # Django's ordinary JSON encoder truncates datetime output to milliseconds.
    def default(self, value):
        return value.isoformat() if isinstance(value, datetime) else super().default(value)


def _digest(value):
    return hashlib.sha256(json.dumps(value, cls=_RetainedJSONEncoder, sort_keys=True).encode()).hexdigest()


def _cohort(owner):
    tenant = require_installation_member(owner).tenant
    document = Document.objects.select_related("entity__workspace", "organization__entity").get(
        tenant=tenant,
        entity__display_name=TITLE,
    )
    companion = Document.objects.select_related("entity__workspace").get(
        tenant=tenant,
        organization=document.organization,
        entity__display_name=COMPANION,
    )
    original = document.publications.get(reason="Retained original client release")
    approver = original.control_events.get(action="approved").actor
    client = (
        TenantMembership.objects.select_related("user")
        .get(
            tenant=tenant,
            organization=document.organization,
            role=BuiltInRole.CLIENT_USER,
        )
        .user
    )
    return document, companion, original, approver, client


def seed_client_publication_fixture(owner):
    tenant = require_installation_member(owner).tenant
    assert not Document.objects.filter(tenant=tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=tenant,
        actor_id=owner.id,
        name="Client publication migration fixture",
        legal_name="",
        website="",
        classifications=["client"],
    )
    approver = User.objects.create_user(
        email=f"publication-approver-{uuid.uuid4()}@example.invalid",
        display_name="Client publication fixture approver",
    )
    TenantMembership.objects.create(tenant=tenant, user=approver, role=BuiltInRole.ADMINISTRATOR)
    TOTP.activate(approver, generate_totp_secret())
    assign_organization_staff(actor=owner, organization_entity_id=organization.entity_id, member_user_id=approver.id)
    client = User.objects.create_user(
        email=f"publication-client-{uuid.uuid4()}@example.invalid",
        display_name="Client publication fixture reader",
    )
    TenantMembership.objects.create(
        tenant=tenant,
        organization=organization,
        user=client,
        role=BuiltInRole.CLIENT_USER,
    )
    document = create_document(
        tenant=tenant,
        organization=organization,
        actor_id=owner.id,
        title=TITLE,
        markdown=SHARED + "\n",
    )
    companion = create_document(
        tenant=tenant,
        organization=organization,
        actor_id=owner.id,
        title=COMPANION,
        markdown="Companion client access survives migration and recovery.\n",
    )
    first = create_document_attachment(
        document=document,
        actor_id=owner.id,
        purpose="primary_file",
        version_number=1,
        upload=SimpleUploadedFile("client-primary-v1.pdf", render_pdf("Retained client primary version one.")),
    )
    second = replace_primary_document_file(
        document=document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("client-primary-v2.pdf", render_pdf("Retained client primary version two.")),
    )
    assert first.id != second.id
    for name, audience, text in (("staff", "msp_internal", PRIVATE), ("client", "client_visible", PUBLIC)):
        site = create_site(
            tenant=tenant,
            organization=organization,
            actor_id=owner.id,
            name=f"{name.title()} publication fixture site",
            code=name.upper(),
            address_line_1="",
            address_line_2="",
            city="",
            region="",
            postal_code="",
            country_code="",
            timezone="UTC",
            phone="",
        )
        if name == "client":
            site.entity.visibility = "client_visible"
            site.entity.save(update_fields=("visibility",))
        DocumentKeyBinding.objects.create(
            tenant=tenant,
            organization=organization,
            workspace=document.entity.workspace,
            document=document,
            name=name,
            target_entity=site.entity,
            created_by=owner,
        )
        attachment = create_document_attachment(
            document=document,
            actor_id=owner.id,
            upload=SimpleUploadedFile(f"{name}-checklist.txt", f"{name.title()} retained checklist bytes.\n".encode()),
        )
        create_document_block(
            document=document,
            actor_id=owner.id,
            kind="rich_text",
            name=f"{name.title()} scoped instructions",
            markdown=f"{text}\n\nVisit <tekdocs://key/{name}.name>.\n\n"
            f"[Checklist](tekdocs://attachment/{attachment.entity_id})\n",
            parent_id=None,
            position=None,
            audience_profile=audience,
        )
    reader = resolve_organization_workspace(owner, entity_id=organization.entity_id)
    for target, reason in ((document, "Retained original client release"), (companion, "Retained companion release")):
        publication = publish_document(
            workspace=reader,
            document=target,
            actor_id=owner.id,
            reason=reason,
            audience="client_visible",
            retention="review_on",
            retention_review_on=timezone.localdate() + timedelta(days=30),
        )
        approve_publication(publication=publication, actor_id=approver.id, reason="Independent fixture approval")
    for reason, withdraw in (("Retained pending client release", False), ("Retained withdrawn client release", True)):
        publication = publish_document(
            workspace=reader,
            document=document,
            actor_id=owner.id,
            reason=reason,
            audience="client_visible",
            retention="permanent",
            retention_review_on=None,
        )
        if withdraw:
            from apps.core.publications import withdraw_publication

            approve_publication(publication=publication, actor_id=approver.id, reason="Independent fixture approval")
            withdraw_publication(publication=publication, actor_id=approver.id, reason="Retain original withdrawal")
    publish_document(
        workspace=reader,
        document=document,
        actor_id=owner.id,
        reason="Retained staff edition",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    _client_notifications(owner)


def _client_notifications(owner):
    from apps.core.outbox import dispatch_due_outbox_events

    document, _companion, _original, _approver, client_user = _cohort(owner)
    while dispatch_due_outbox_events(tenant=document.tenant):
        pass
    client = Client()
    client.force_login(client_user)
    with override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False):
        response = client.get(reverse("client-portal-notification-list"))
        assert response.status_code == 200
        records = response.json()["results"]
        for record in records:
            assert PRIVATE not in str(record)
            target = record["target"]
            if target is not None:
                assert target["kind"] == "portal_document"
                assert (
                    client.get(reverse("client-portal-document-detail", args=[target["publication_id"]])).status_code
                    == 200
                )
    return sorted(records, key=lambda item: item["id"])


def client_publication_retained_state(owner):
    from apps.core.models import BlockRevision, InboxNotification
    from apps.core.publications import verify_publication

    document, companion, _original, approver, client = _cohort(owner)
    snapshots, files, revisions = {}, {}, {}
    identities = []
    for selected in (document, companion):
        identities.append(
            [
                str(selected.id),
                str(selected.entity_id),
                str(selected.entity.workspace_id),
                str(selected.organization_id),
                list(
                    selected.placements.order_by("id").values_list(
                        "id",
                        "block_id",
                        "parent_id",
                        "position",
                        "audience_profile",
                        "resolution_mode",
                        "pinned_revision_id",
                    )
                ),
            ]
        )
        for publication in selected.publications.order_by("id"):
            # This shared fingerprint also runs on the actual 0.8.46 seed. Its
            # public signature verifier and strict artifact reads predate Git custody.
            assert verify_publication(publication)["valid"]
            snapshots[str(publication.id)] = {
                "entity": str(publication.entity_id),
                "manifest": publication.manifest,
                "signature": publication.signature,
                "digest": publication.content_digest,
                "markdown": hashlib.sha256(publication.canonical_markdown.encode()).hexdigest(),
                "html": hashlib.sha256(publication.sanitized_html.encode()).hexdigest(),
                "controls": list(
                    publication.control_events.order_by("id").values_list(
                        "id",
                        "action",
                        "reason",
                        "actor_id",
                        "occurred_at",
                    )
                ),
                "artifacts": [
                    (
                        str(item.entity_id),
                        item.kind,
                        item.checksum,
                        hashlib.sha256(read_publication_artifact(item)).hexdigest(),
                    )
                    for item in publication.artifacts.order_by("entity_id")
                ],
            }
        for attachment in selected.attachments.order_by("entity_id"):
            files[str(attachment.entity_id)] = [
                attachment.purpose,
                attachment.version_number,
                str(attachment.replaces_id),
                attachment.original_filename,
                attachment.media_type,
                attachment.size,
                attachment.checksum,
                hashlib.sha256(copy_attachment_content(attachment)).hexdigest(),
            ]
        for revision in BlockRevision.objects.filter(block__source_document=selected).order_by("id"):
            revisions[str(revision.id)] = [
                str(revision.block_id),
                revision.revision_number,
                revision.checksum,
                hashlib.sha256(revision.markdown.encode()).hexdigest(),
            ]
    members = list(
        TenantMembership.objects.filter(
            tenant_id=document.tenant_id,
            user__in=(owner, approver, client),
        )
        .order_by("id")
        .values_list(
            "id",
            "tenant_id",
            "organization_id",
            "role",
            "user_id",
            "user__is_active",
            "user__password",
        )
    )
    assignments = list(
        OrganizationAccessAssignment.objects.filter(
            tenant_id=document.tenant_id,
            organization_id=document.organization_id,
        )
        .order_by("id")
        .values_list("id", "membership_id", "organization_id", "created_by_id")
    )
    notifications = {
        str(row.id): [
            str(row.event_id),
            row.event.topic,
            str(row.event.subject_id),
            str(row.recipient_id),
            row.surface,
            row.read_at,
            row.created_at,
        ]
        for row in InboxNotification.objects.filter(
            tenant_id=document.tenant_id,
            organization_id=document.organization_id,
        )
        .select_related("event")
        .order_by("id")
    }
    return {
        "publications": snapshots,
        "files": files,
        "revisions": revisions,
        "identities": identities,
        "members": members,
        "assignments": assignments,
        "notifications": notifications,
    }


def _assert_retained(before, after):
    for kind in ("publications", "revisions", "notifications"):
        assert all(after[kind].get(identity) == value for identity, value in before[kind].items())
    for kind in ("files", "identities", "members", "assignments"):
        assert after[kind] == before[kind]


def prepare_client_publication_fixture(owner):
    from apps.core import repository_storage
    from apps.core.content_authoring import author_content, read_authored_content
    from apps.core.content_index import index_repository_content
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import

    notifications = _client_notifications(owner)
    before = client_publication_retained_state(owner)
    document, companion, _original, _approver, _client = _cohort(owner)
    for selected in (document, companion):
        workspace = selected.entity.workspace
        reader = resolve_organization_workspace(owner, entity_id=selected.organization.entity_id)
        repository_storage.ensure_workspace_repository(workspace)
        index_repository_content(repository_id=workspace.repository.id)
        plan = prepare_document_import(workspace=workspace, document_id=selected.id)
        apply_document_import(
            workspace=workspace,
            document_id=selected.id,
            expected_base=plan.base_commit,
            plan_sha256=plan.plan_sha256,
            actor_id=owner.id,
        )
        assert (
            transition_document_authority(
                workspace=workspace,
                document_id=selected.id,
                actor_id=owner.id,
                target="repository",
                reader_workspace=reader,
            )
            == "transitioned"
        )
    fragment = read_authored_content(
        repository=document.entity.workspace.repository,
        content_id=document.placements.get(parent__isnull=True, position=0).block_id,
    )
    author_content(
        repository=document.entity.workspace.repository,
        actor_id=owner.id,
        request_id=None,
        operation="update",
        content_id=fragment.content_id,
        base_commit=fragment.accepted_commit,
        base_blob=fragment.source_blob,
        kind=None,
        path=None,
        title=None,
        markdown=CURRENT + "\n",
        metadata_patch={},
    )
    _assert_retained(before, client_publication_retained_state(owner))
    assert _client_notifications(owner) == notifications
    return before


def _portal_state(owner):
    document, companion, original, _approver, client_user = _cohort(owner)
    client = Client()
    client.force_login(client_user)
    with override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False):
        response = client.get(reverse("client-portal-document-list"))
        assert response.status_code == 200
        records = response.json()["results"]
        for record in records:
            record["artifacts"].sort(key=lambda item: item["id"])
            detail = client.get(reverse("client-portal-document-detail", args=[record["id"]]))
            assert detail.status_code == 200
            assert PRIVATE not in detail.json()["sanitized_html"]
            for artifact in record["artifacts"]:
                downloaded = client.get(
                    reverse(
                        "client-portal-document-artifact-download",
                        args=[record["id"], artifact["id"]],
                    )
                )
                assert downloaded.status_code == 200
                assert hashlib.sha256(downloaded.content).hexdigest() == artifact["checksum"]
        assert any(record["title"] == COMPANION for record in records)
        main = client.get(reverse("client-portal-document-detail", args=[original.entity_id]))
        assert main.status_code == (404 if original.lifecycle_state == "superseded" else 200)
    return sorted(records, key=lambda item: item["id"])


def client_publication_recovery_fingerprint(owner):
    from apps.core.content_publication_sources import pinned_git_document_dependencies
    from apps.core.models import DocumentAuthority

    state = client_publication_retained_state(owner)
    document, companion, _original, _approver, _client = _cohort(owner)
    git = []
    for selected in (document, companion):
        repository = selected.entity.workspace.repository
        for audience in ("msp_internal", "client_visible"):
            with pinned_git_document_dependencies(
                repository_id=repository.id,
                content_id=selected.id,
                audience=audience,
            ) as source:
                git.append(source)
    ids = [selected.id for selected in (document, companion)]
    ids.extend(document.placements.values_list("block_id", flat=True))
    ids.extend(companion.placements.values_list("block_id", flat=True))
    authority = list(
        DocumentAuthority.objects.filter(
            tenant_id=document.tenant_id,
            workspace=document.entity.workspace,
            content_id__in=ids,
        )
        .order_by("content_id")
        .values_list(
            "content_id",
            "authority",
        )
    )
    return _digest(
        {
            "retained": state,
            "git": git,
            "authority": authority,
            "portal": _portal_state(owner),
            "notifications": _client_notifications(owner),
        }
    )


def verify_client_publication_fixture(owner, before):
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.publications import verify_retained_publication_custody

    document, companion, original, _approver, _client = _cohort(owner)
    client_snapshots = list(
        document.publications.filter(
            audience="client_visible",
            manifest__has_key="git_source",
        )
    )
    assert len(client_snapshots) == 1
    snapshot = client_snapshots[0]
    assert snapshot.lifecycle_state == "withdrawn" and snapshot.supersedes_id == original.id
    assert PRIVATE not in snapshot.canonical_markdown
    assert PUBLIC in snapshot.canonical_markdown and CURRENT in snapshot.canonical_markdown
    assert set(snapshot.manifest["key_bindings"]) == {"client"}
    assert {item.original_filename for item in snapshot.artifacts.filter(kind="attachment")} == {
        "client-primary-v1.pdf",
        "client-primary-v2.pdf",
        "client-checklist.txt",
    }
    assert verify_retained_publication_custody(snapshot)
    for selected in (document, companion):
        assert all(verify_retained_publication_custody(item) for item in selected.publications.all())
    notifications = _client_notifications(owner)
    _assert_retained(before, client_publication_retained_state(owner))
    for target in ("legacy", "repository"):
        for selected in (document, companion):
            assert (
                transition_document_authority(
                    workspace=selected.entity.workspace,
                    document_id=selected.id,
                    actor_id=owner.id,
                    target=target,
                    reader_workspace=resolve_organization_workspace(owner, entity_id=selected.organization.entity_id),
                )
                == "transitioned"
            )
        assert CURRENT in resolve_document(document).markdown
        _portal_state(owner)
        assert _client_notifications(owner) == notifications
    _assert_retained(before, client_publication_retained_state(owner))
    return client_publication_recovery_fingerprint(owner)


def exercise_client_publication_fixture(owner):
    from apps.core.publications import withdraw_publication

    before = prepare_client_publication_fixture(owner)
    document, _companion, original, approver, _client = _cohort(owner)
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    correction = publish_document(
        workspace=reader,
        document=document,
        actor_id=owner.id,
        reason="Client recovery correction",
        audience="client_visible",
        retention="review_on",
        retention_review_on=timezone.localdate() + timedelta(days=30),
        supersedes_entity_id=original.entity_id,
    )
    assert correction.lifecycle_state == "pending_approval"
    targets = [item["target"] for item in _client_notifications(owner) if item["target"]]
    assert any(item["publication_id"] == str(original.entity_id) for item in targets)
    assert all(item["publication_id"] != str(correction.entity_id) for item in targets)
    approve_publication(publication=correction, actor_id=approver.id, reason="Independent recovery correction approval")
    targets = [item["target"] for item in _client_notifications(owner) if item["target"]]
    assert any(item["publication_id"] == str(correction.entity_id) for item in targets)
    assert all(item["publication_id"] != str(original.entity_id) for item in targets)
    withdraw_publication(publication=correction, actor_id=approver.id, reason="Retain corrected client withdrawal")
    notifications = _client_notifications(owner)
    assert any(item["target"] is None for item in notifications)
    assert all(
        item["target"] is None
        or item["target"]["publication_id"]
        not in {
            str(original.entity_id),
            str(correction.entity_id),
        }
        for item in notifications
    )
    return verify_client_publication_fixture(owner, before)


def run_client_publication_fixture_mode(mode):
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        seed_client_publication_fixture(owner)
    if mode == "seed":
        print("CLIENT_PUBLICATION_LEGACY_SHA256=" + _digest(client_publication_retained_state(owner)))
    elif mode in {"promote", "recovery_create"}:
        if mode == "promote":
            assert (
                _digest(client_publication_retained_state(owner))
                == os.environ["TEKDOCS_CLIENT_PUBLICATION_LEGACY_SHA256"]
            )
        digest = exercise_client_publication_fixture(owner)
        print("Client publications, portal access, audience isolation, files, PDFs and rollback verified.")
        print("CLIENT_PUBLICATION_RECOVERY_SHA256=" + digest)
    elif mode == "recovery_verify":
        assert (
            client_publication_recovery_fingerprint(owner) == os.environ["TEKDOCS_CLIENT_PUBLICATION_RECOVERY_SHA256"]
        )
        print("Client publications, portal access, audience isolation, files and PDFs recovered exactly.")
    else:
        raise ValueError("Unknown client-publication fixture mode")


def client_publication_browser_state(owner):
    from django.conf import settings

    document, companion, original, approver, client = _cohort(owner)
    sessions = {}
    for name, user in (("approver", approver), ("client", client)):
        browser = Client()
        browser.force_login(user)
        sessions[name] = browser.cookies[settings.SESSION_COOKIE_NAME].value
    return {
        "organization_id": str(document.organization.entity_id),
        "document_id": str(document.entity_id),
        "content_id": str(document.id),
        "original_id": str(original.entity_id),
        "original_pdf_filename": original.artifacts.get(kind="pdf").original_filename,
        "original_pdf_sha256": hashlib.sha256(
            read_publication_artifact(original.artifacts.get(kind="pdf"))
        ).hexdigest(),
        "review_on": original.retention_review_on.isoformat(),
        "companion_publication_id": str(companion.publications.get().entity_id),
        "sessions": sessions,
        "files": [
            {"filename": item.original_filename, "sha256": item.checksum}
            for item in document.attachments.exclude(original_filename="staff-checklist.txt").order_by("id")
        ],
    }


if os.environ.get("TEKDOCS_CLIENT_PUBLICATION_FIXTURE_MODE"):
    run_client_publication_fixture_mode(os.environ["TEKDOCS_CLIENT_PUBLICATION_FIXTURE_MODE"])
