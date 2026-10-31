"""Synthetic addressed-document fixture, including a legacy-compatible seed adapter.

Hosted upgrade passes this source to the old image's management shell in seed
mode. Imports needed only after migration stay inside the candidate operations.
The same fixture drives the real browser and encrypted-recovery checks.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass

from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.document_attachments import (
    copy_attachment_content,
    create_document_attachment,
    replace_primary_document_file,
)
from apps.core.documents import create_document, resolve_document, update_document
from apps.core.models import (
    Document,
    DocumentKeyBinding,
    DocumentPublication,
    InstallationState,
    Site,
    workspace_for_owner,
)
from apps.core.organizations import create_organization
from apps.core.publications import publish_document, read_publication_artifact
from apps.core.rendering import render_pdf
from apps.core.sites import create_site, update_site
from apps.core.workspaces import resolve_organization_workspace

TITLE = "Addressed migration acceptance guide"
ORIGINAL_NAME = "Original addressed site"
CURRENT_NAME = "Current addressed site"


@dataclass
class AddressedFixture:
    document: Document
    site: Site
    binding: DocumentKeyBinding
    original: DocumentPublication
    original_manifest: dict
    original_signature: str
    original_pdf: bytes

    @property
    def browser(self) -> dict[str, object]:
        document = self.document
        linked = document.attachments.get(purpose="attachment")
        return {
            "organization_id": str(document.organization.entity_id),
            "document_id": str(document.entity_id),
            "content_id": str(document.id),
            "fragment_id": str(document.placements.get().block_id),
            "original_id": str(self.original.entity_id),
            "original_pdf_sha256": hashlib.sha256(self.original_pdf).hexdigest(),
            "edited_markdown": (
                "# Current addressed instructions\n\n"
                "Visit <tekdocs://key/subject.name> with code <tekdocs://key/subject.code>.\n\n"
                f"[Site](tekdocs://entity/{self.site.entity_id})\n\n"
                f"[Checklist](tekdocs://attachment/{linked.entity_id})\n"
            ),
            "files": [
                {"filename": record.original_filename, "sha256": record.checksum}
                for record in document.attachments.order_by("entity_id")
            ],
        }


def seed_addressed_fixture(owner) -> AddressedFixture:
    """Use only APIs present at the supported 0.8.46 source boundary."""
    from apps.accounts.policy import require_installation_member

    member = require_installation_member(owner)
    assert not Document.objects.filter(tenant=member.tenant, entity__display_name=TITLE).exists()
    if not Authenticator.objects.filter(user=owner, type=Authenticator.Type.TOTP).exists():
        TOTP.activate(owner, generate_totp_secret())
    organization = create_organization(
        tenant=member.tenant,
        actor_id=owner.id,
        name="Addressed acceptance client",
        legal_name="",
        website="",
        classifications=["client"],
    )
    workspace = workspace_for_owner(tenant=member.tenant, organization=organization)
    site = create_site(
        tenant=member.tenant,
        organization=organization,
        actor_id=owner.id,
        name=ORIGINAL_NAME,
        code="OPS",
        address_line_1="",
        address_line_2="",
        city="",
        region="",
        postal_code="",
        country_code="",
        timezone="UTC",
        phone="",
    )
    document = create_document(
        tenant=member.tenant,
        organization=organization,
        actor_id=owner.id,
        title=TITLE,
        markdown="Initial addressed instructions.\n",
    )
    binding = DocumentKeyBinding.objects.create(
        tenant=member.tenant,
        organization=organization,
        workspace=workspace,
        document=document,
        name="subject",
        target_entity=site.entity,
        created_by=owner,
    )
    create_document_attachment(
        document=document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("addressed-primary-v1.pdf", render_pdf("Addressed primary original.")),
        purpose="primary_file",
        version_number=1,
    )
    replace_primary_document_file(
        document=document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("addressed-primary-v2.pdf", render_pdf("Addressed primary revised.")),
    )
    linked = create_document_attachment(
        document=document,
        actor_id=owner.id,
        upload=SimpleUploadedFile("addressed-checklist.txt", b"Addressed fixture checklist.\n"),
    )
    update_document(
        document=document,
        actor_id=owner.id,
        title=TITLE,
        markdown=(
            "Visit <tekdocs://key/subject.name>.\n\n"
            f"[Site](tekdocs://entity/{site.entity_id})\n\n"
            f"[Checklist](tekdocs://attachment/{linked.entity_id})\n"
        ),
        base_revision_id=document.placements.get().block.current_revision_id,
    )
    original = publish_document(
        workspace=resolve_organization_workspace(owner, entity_id=organization.entity_id),
        document=document,
        actor_id=owner.id,
        reason="Retain original addressed instructions",
        audience="msp_internal",
        retention="permanent",
        retention_review_on=None,
    )
    return AddressedFixture(
        document,
        site,
        binding,
        original,
        deepcopy(original.manifest),
        original.signature,
        read_publication_artifact(original.artifacts.get(kind="pdf")),
    )


def load_addressed_fixture(owner) -> AddressedFixture:
    from apps.accounts.policy import require_installation_member

    document = Document.objects.get(
        tenant=require_installation_member(owner).tenant,
        entity__display_name=TITLE,
    )
    binding = document.key_bindings.get(name="subject", archived_at__isnull=True)
    original = document.publications.order_by("published_at", "id").first()
    assert original is not None
    return AddressedFixture(
        document,
        binding.target_entity.site_record,
        binding,
        original,
        deepcopy(original.manifest),
        original.signature,
        read_publication_artifact(original.artifacts.get(kind="pdf")),
    )


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def legacy_addressed_fingerprint(fixture: AddressedFixture) -> str:
    """Bind unchanged legacy identities and bytes across the image upgrade."""
    document = fixture.document
    fixture.binding.refresh_from_db()
    fixture.original.refresh_from_db()
    return _digest(
        {
            "document": str(document.id),
            "source": resolve_document(document).markdown,
            "binding": [str(fixture.binding.id), fixture.binding.name, str(fixture.binding.target_entity_id)],
            "publication": [
                str(fixture.original.id),
                fixture.original.manifest,
                fixture.original.signature,
                hashlib.sha256(read_publication_artifact(fixture.original.artifacts.get(kind="pdf"))).hexdigest(),
            ],
            "files": [
                (
                    str(record.entity_id),
                    record.version_number,
                    str(record.replaces_id),
                    record.checksum,
                    hashlib.sha256(copy_attachment_content(record)).hexdigest(),
                )
                for record in document.attachments.order_by("entity_id")
            ],
        }
    )


def promote_addressed_fixture(fixture: AddressedFixture, owner) -> None:
    from apps.core.content_index import index_repository_content
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_migration_import import apply_document_import, prepare_document_import
    from apps.core.repository_storage import ensure_workspace_repository

    document = fixture.document
    workspace = document.entity.workspace
    ensure_workspace_repository(workspace)
    index_repository_content(repository_id=workspace.repository.id)
    plan = prepare_document_import(workspace=workspace, document_id=document.id)
    assert apply_document_import(
        workspace=workspace,
        document_id=document.id,
        expected_base=plan.base_commit,
        plan_sha256=plan.plan_sha256,
        actor_id=owner.id,
    ).indexed
    assert (
        transition_document_authority(
            workspace=workspace,
            document_id=document.id,
            actor_id=owner.id,
            target="repository",
            reader_workspace=resolve_organization_workspace(owner, entity_id=document.organization.entity_id),
        )
        == "transitioned"
    )
    update_site(site=fixture.site, actor_id=owner.id, name=CURRENT_NAME)


def addressed_recovery_fingerprint(fixture: AddressedFixture, owner) -> str:
    from apps.core.content_read import document_detail
    from apps.core.document_migration_export import build_simple_document_export
    from apps.core.models import DocumentAuthority
    from apps.core.publications import verify_publication, verify_retained_publication_custody
    from apps.core.repository_service import read_accepted_repository_file

    document = fixture.document
    assert (
        DocumentAuthority.objects.get(workspace=document.entity.workspace, content_id=document.id).authority
        == "repository"
    )
    current = document_detail(
        workspace=resolve_organization_workspace(owner, entity_id=document.organization.entity_id),
        content_id=document.id,
        audience="msp_internal",
    )
    assert CURRENT_NAME in current["sanitized_html"]
    publications = []
    for publication in document.publications.order_by("id"):
        assert verify_publication(publication)["valid"] and verify_retained_publication_custody(publication)
        publications.append(
            [
                str(publication.entity_id),
                publication.manifest,
                publication.signature,
                [
                    (str(item.entity_id), item.checksum, hashlib.sha256(read_publication_artifact(item)).hexdigest())
                    for item in publication.artifacts.order_by("entity_id")
                ],
            ]
        )
    assert len(publications) == 2
    git_files = []
    for path, expected in build_simple_document_export(document).files:
        actual = read_accepted_repository_file(repository_id=document.entity.workspace.repository.id, path=path)
        assert actual == expected
        git_files.append((path, hashlib.sha256(actual).hexdigest()))
    fixture.site.refresh_from_db()
    fixture.site.entity.refresh_from_db()
    return _digest(
        {
            "legacy": legacy_addressed_fingerprint(fixture),
            "git_files": git_files,
            "target": [str(fixture.site.entity_id), fixture.site.entity.display_name, fixture.site.code],
            "publications": publications,
            "html": hashlib.sha256(current["sanitized_html"].encode()).hexdigest(),
        }
    )


def verify_addressed_browser_fixture(fixture: AddressedFixture, owner) -> None:
    from apps.core.content_read import document_detail
    from apps.core.document_authority_handoff import transition_document_authority
    from apps.core.document_git_publications import verify_internal_git_publication
    from apps.core.publications import verify_retained_publication_custody

    document = fixture.document
    reader = resolve_organization_workspace(owner, entity_id=document.organization.entity_id)
    original = fixture.original
    original.refresh_from_db()
    assert (original.manifest, original.signature) == (fixture.original_manifest, fixture.original_signature)
    assert read_publication_artifact(original.artifacts.get(kind="pdf")) == fixture.original_pdf
    newer = document.publications.exclude(pk=original.pk).get()
    assert newer.manifest["format"] == "tekdocs-static-publication/v9"
    assert {item["expression"]: item["value"] for item in newer.manifest["key_resolutions"]} == {
        "subject.name": CURRENT_NAME,
        "subject.code": "OPS",
    }
    assert verify_internal_git_publication(newer)
    body = document_detail(workspace=reader, content_id=document.id, audience="msp_internal")["markdown"]
    assert "subject.code" in body
    for target in ("legacy", "repository"):
        assert (
            transition_document_authority(
                workspace=document.entity.workspace,
                document_id=document.id,
                actor_id=owner.id,
                target=target,
                reader_workspace=reader,
            )
            == "transitioned"
        )
        if target == "legacy":
            assert resolve_document(document).markdown == body
    versions = list(document.attachments.filter(purpose="primary_file").order_by("version_number"))
    assert [record.version_number for record in versions] == [1, 2]
    assert versions[1].replaces_id == versions[0].id
    assert verify_retained_publication_custody(newer) and verify_retained_publication_custody(original)


def run_fixture_mode(mode: str) -> None:
    owner = InstallationState.objects.select_related("owner").get().owner
    assert owner is not None
    if mode in {"seed", "recovery_create"}:
        fixture = seed_addressed_fixture(owner)
    else:
        fixture = load_addressed_fixture(owner)
    if mode == "seed":
        print("ADDRESSED_LEGACY_SHA256=" + legacy_addressed_fingerprint(fixture))
        return
    if mode == "promote":
        assert legacy_addressed_fingerprint(fixture) == os.environ["TEKDOCS_ADDRESSED_LEGACY_SHA256"]
    if mode in {"promote", "recovery_create"}:
        from apps.core.document_git_publications import publish_internal_git_document

        promote_addressed_fixture(fixture, owner)
        publication = publish_internal_git_document(
            workspace=resolve_organization_workspace(owner, entity_id=fixture.document.organization.entity_id),
            document=fixture.document,
            actor=owner,
            reason="Retain addressed fixture after promotion",
        )
        assert publication.manifest["format"] == "tekdocs-static-publication/v9"
        fingerprint = addressed_recovery_fingerprint(fixture, owner)
        if mode == "recovery_create":
            print("ADDRESSED_RECOVERY_SHA256=" + fingerprint)
        print("Addressed Git, bindings, file versions, signatures and PDFs verified")
    elif mode == "recovery_verify":
        assert addressed_recovery_fingerprint(fixture, owner) == os.environ["TEKDOCS_ADDRESSED_RECOVERY_SHA256"]
        print("Addressed Git, bindings, file versions, signatures and PDFs recovered exactly")
    else:
        raise ValueError("Unknown addressed fixture mode")


if os.environ.get("TEKDOCS_KEY_ENTITY_FIXTURE_MODE"):
    run_fixture_mode(os.environ["TEKDOCS_KEY_ENTITY_FIXTURE_MODE"])
