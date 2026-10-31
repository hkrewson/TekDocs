"""Retained enrollment evidence and scoped source/client authority transitions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from .document_template_models import DocumentTemplateEnrollment, DocumentTemplateRevision
from .models import BlockRevision, Document, DocumentPlacement, Workspace


class TemplateMigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TemplateEnrollmentEvidence:
    destination_document_id: UUID
    source_document_id: UUID
    applied_revision_id: UUID
    modes: tuple[str, ...]
    fingerprint: str
    library_placement_ids: tuple[UUID, ...]


def template_enrollment_fingerprint(document: Document) -> str | None:
    evidence = template_enrollment_evidence(document)
    if evidence is None:
        return None
    return evidence.fingerprint


def template_enrollment_evidence(document: Document) -> TemplateEnrollmentEvidence | None:
    enrollment = DocumentTemplateEnrollment.objects.filter(destination_document=document).first()
    if enrollment is None:
        return None
    mapping = enrollment.placement_map
    independent_copy = (
        isinstance(mapping, list)
        and bool(mapping)
        and all(isinstance(item, dict) and item.get("mode") == "copy" for item in mapping)
    )
    try:
        revision = enrollment.applied_revision
        source = None if independent_copy else enrollment.source_template
    except ObjectDoesNotExist as exc:
        raise TemplateMigrationError("template_source_unavailable") from exc
    if (
        enrollment.tenant_id != document.tenant_id
        or enrollment.organization_id != document.organization_id
        or document.organization_id is None
        or revision.tenant_id != document.tenant_id
        or revision.template_id != enrollment.source_template_id
        or (
            source is not None
            and (source.tenant_id != document.tenant_id or source.organization_id is not None or not source.is_template)
        )
    ):
        raise TemplateMigrationError("template_enrollment_scope_invalid")
    canonical = json.dumps(revision.manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    if hashlib.sha256(canonical).hexdigest() != revision.checksum:
        raise TemplateMigrationError("template_revision_invalid")
    if not isinstance(revision.manifest, dict):
        raise TemplateMigrationError("template_revision_invalid")
    blocks = revision.manifest.get("blocks")
    mapping = enrollment.placement_map
    if (
        (source is not None and revision.manifest.get("template_document_id") != str(source.entity_id))
        or not isinstance(blocks, list)
        or not 1 <= len(blocks) <= 500
        or not isinstance(mapping, list)
        or len(mapping) != len(blocks)
    ):
        raise TemplateMigrationError("template_enrollment_mapping_invalid")
    placements = {str(p.id): p for p in document.placements.select_related("block")}
    source_ids, destination_ids = set(), set()
    modes: list[str] = []
    copy_origins: list[tuple[str, str, str]] = []
    try:
        by_source = {item["source_block_id"]: item for item in blocks}
        if len(by_source) != len(blocks):
            raise ValueError
        for item in mapping:
            source_id = str(UUID(item["source_block_id"]))
            destination_id = str(UUID(item["destination_placement_id"]))
            if (
                source_id in source_ids
                or destination_id in destination_ids
                or item["mode"] not in {"copy", "live", "pinned"}
            ):
                raise ValueError
            source_ids.add(source_id)
            destination_ids.add(destination_id)
            mode = item["mode"]
            modes.append(mode)
            expected = by_source[source_id]
            placement = placements[destination_id]
            if (
                str(placement.block.entity_id) != item["destination_block_id"]
                or item["applied_revision_id"] != expected["source_revision_id"]
            ):
                raise ValueError
            if mode == "copy":
                if (
                    placement.block.source_document_id != document.id
                    or placement.resolution_mode != "live"
                    or placement.pinned_revision_id is not None
                ):
                    raise ValueError
            elif (
                source is None
                or not source.library_visible
                or not placement.block.library_visible
                or placement.block.source_document_id != source.id
                or placement.block.organization_id is not None
                or placement.resolution_mode != mode
                or str(placement.block.entity_id) != source_id
                or (mode == "live" and placement.pinned_revision_id is not None)
                or (mode == "pinned" and str(placement.pinned_revision_id) != expected["source_revision_id"])
            ):
                raise ValueError
            fork = item.get("forked_from")
            expected_checksum = expected["checksum"]
            if fork is not None:
                if (
                    mode != "copy"
                    or not isinstance(fork, dict)
                    or set(fork)
                    != {
                        "source_entity",
                        "content_id",
                        "workspace",
                        "revision",
                        "commit",
                        "checksum",
                        "mode",
                        "audit_event",
                    }
                    or not all(isinstance(value, str) for value in fork.values())
                    or fork["source_entity"] != source_id
                    or fork["mode"] not in {"live", "pinned"}
                    or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fork["commit"])
                    or not re.fullmatch(r"[0-9a-f]{64}", fork["checksum"])
                ):
                    raise ValueError
                for field in ("content_id", "workspace", "revision", "audit_event"):
                    UUID(fork[field])
                if source is not None:
                    original = BlockRevision.objects.get(
                        tenant_id=document.tenant_id,
                        pk=UUID(fork["revision"]),
                        block_id=UUID(fork["content_id"]),
                        block__entity_id=UUID(source_id),
                        block__source_document=source,
                    )
                    if original.checksum != fork["checksum"] or str(source.entity.workspace_id) != fork["workspace"]:
                        raise ValueError
                expected_checksum = fork["checksum"]
            owns_custody = independent_copy or fork is not None
            if owns_custody:
                # A copy owns its original bytes and complete local revision
                # chain. It has no live dependency on the MSP source's visibility.
                retained = BlockRevision.objects.get(
                    tenant_id=document.tenant_id,
                    block=placement.block,
                    revision_number=1,
                )
            else:
                retained = BlockRevision.objects.get(
                    tenant_id=document.tenant_id,
                    id=UUID(expected["source_revision_id"]),
                    block__entity_id=UUID(source_id),
                    block__source_document=source,
                )
            if hashlib.sha256(retained.markdown.encode()).hexdigest() != retained.checksum:
                raise ValueError
            if fork is not None:
                from .models import AuditEvent
                from .template_fork_evidence import template_fork_metadata

                if not AuditEvent.objects.filter(
                    tenant_id=document.tenant_id,
                    entity_id=document.entity_id,
                    action="document.template_section_forked",
                    pk=UUID(fork["audit_event"]),
                    metadata=template_fork_metadata(
                        enrollment_id=enrollment.id,
                        placement=placement,
                        revision=retained,
                        source={key: value for key, value in fork.items() if key != "audit_event"},
                    ),
                ).exists():
                    raise ValueError
            if owns_custody:
                # Instantiation rebinds source attachment URIs into client-owned
                # files. Those copied bytes intentionally have a different hash;
                # the retained definition records lineage, while the client's
                # immutable initial revision records its own content custody.
                if expected.get("attachment_ids") and fork is None:
                    from .models import DocumentAttachment
                    from .rendering import attachment_ids_in_markdown

                    copied_ids = attachment_ids_in_markdown(retained.markdown)
                    if (
                        len(copied_ids) != len(expected["attachment_ids"])
                        or set(
                            DocumentAttachment.objects.filter(
                                tenant_id=document.tenant_id,
                                document=document,
                                entity_id__in=copied_ids,
                            ).values_list("entity_id", flat=True)
                        )
                        != copied_ids
                    ):
                        raise ValueError
                elif retained.checksum != expected_checksum:
                    raise ValueError
                copy_origins.append((str(placement.block_id), str(retained.id), retained.checksum))
            elif retained.checksum != expected["checksum"]:
                raise ValueError
    except (KeyError, TypeError, ValueError, BlockRevision.DoesNotExist) as exc:
        raise TemplateMigrationError("template_enrollment_mapping_invalid") from exc
    payload = {
        "id": str(enrollment.id),
        "source": str(enrollment.source_template_id),
        "revision": str(revision.id),
        "checksum": revision.checksum,
        "map": mapping,
        "copy_origins": copy_origins,
        "actor": str(enrollment.last_applied_by_id),
        "applied_at": enrollment.last_applied_at.isoformat(),
        "updated_at": enrollment.updated_at.isoformat(),
        "archived_at": enrollment.archived_at.isoformat() if enrollment.archived_at else None,
    }
    return TemplateEnrollmentEvidence(
        destination_document_id=document.id,
        source_document_id=enrollment.source_template_id,
        applied_revision_id=revision.id,
        modes=tuple(modes),
        library_placement_ids=tuple(
            UUID(item["destination_placement_id"]) for item in mapping if item["mode"] in {"live", "pinned"}
        ),
        fingerprint=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class TemplateLibraryMigrationPlan:
    source_document_id: UUID
    destination_document_ids: tuple[UUID, ...]
    enrollments: tuple[TemplateEnrollmentEvidence, ...]
    plan_sha256: str


def prepare_template_library_migration(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
) -> TemplateLibraryMigrationPlan:
    """Review an explicit MSP source/client cohort; this never changes authority."""
    from .document_migration_publications import publication_migration_actor_allowed
    from .publications import canonical_json

    ids = tuple(sorted(set(destination_document_ids)))
    if not ids or len(ids) != len(destination_document_ids) or len(ids) > 63:
        raise TemplateMigrationError("invalid_template_migration_group")
    if source_workspace.organization_id is not None or not publication_migration_actor_allowed(
        workspace=source_workspace,
        actor_id=actor_id,
    ):
        raise TemplateMigrationError("template_migration_not_authorized")
    source = Document.objects.filter(
        id=source_document_id,
        tenant_id=source_workspace.tenant_id,
        organization__isnull=True,
        entity__workspace=source_workspace,
        is_template=True,
        archived_at__isnull=True,
    ).first()
    if source is None:
        raise TemplateMigrationError("template_source_unavailable")
    states, consumers = _scoped_template_destinations(source, ids, actor_id)
    consumers.update(
        DocumentPlacement.objects.filter(
            tenant_id=source.tenant_id,
            organization__isnull=True,
            document__entity__workspace=source_workspace,
            block__source_document=source,
            resolution_mode="live",
        )
        .exclude(document=source)
        .values_list("document_id", flat=True)
    )
    if not consumers.issubset(ids):
        raise TemplateMigrationError("template_live_dependency_group_incomplete")
    evidence = [item.enrollment for item in states]
    revisions = []
    for revision in DocumentTemplateRevision.objects.filter(template=source).order_by("revision_number"):
        if (
            not isinstance(revision.manifest, dict)
            or hashlib.sha256(canonical_json(revision.manifest)).hexdigest() != revision.checksum
        ):
            raise TemplateMigrationError("template_revision_invalid")
        blocks = revision.manifest.get("blocks")
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 500:
            raise TemplateMigrationError("template_revision_invalid")
        try:
            seen = set()
            for item in blocks:
                source_id = UUID(item["source_block_id"])
                if source_id in seen:
                    raise ValueError
                seen.add(source_id)
                retained = BlockRevision.objects.get(
                    tenant_id=source.tenant_id,
                    block__source_document=source,
                    block__entity_id=source_id,
                    id=UUID(item["source_revision_id"]),
                )
                if (
                    retained.checksum != item["checksum"]
                    or hashlib.sha256(retained.markdown.encode()).hexdigest() != retained.checksum
                ):
                    raise ValueError
        except (KeyError, TypeError, ValueError, BlockRevision.DoesNotExist) as exc:
            raise TemplateMigrationError("template_revision_invalid") from exc
        revisions.append((str(revision.id), revision.checksum))
    placements = list(source.placements.select_related("block").order_by("id"))
    if not placements or any(item.block.source_document_id != source.id for item in placements):
        raise TemplateMigrationError("template_source_shape_unsupported")
    payload = {
        "source": str(source.id),
        "actor": str(actor_id),
        "source_metadata": [
            source.entity.display_name,
            source.topic_type,
            source.library_visible,
            str(source.updated_at),
        ],
        "source_placements": [
            [
                str(item.id),
                str(item.block_id),
                str(item.block.current_revision_id),
                str(item.parent_id),
                item.position,
                item.audience_profile,
                item.block.library_visible,
            ]
            for item in placements
        ],
        "revisions": revisions,
        "enrollments": [item.fingerprint for item in evidence],
        "destinations": [item.fingerprint for item in states],
    }
    return TemplateLibraryMigrationPlan(
        source.id,
        ids,
        tuple(evidence),
        hashlib.sha256(canonical_json(payload)).hexdigest(),
    )


def template_source_fingerprint(document: Document) -> str | None:
    if not document.is_template and not DocumentTemplateRevision.objects.filter(template=document).exists():
        return None
    from .publications import canonical_json
    from .template_library_history import template_history_files

    _revisions, files = template_history_files(document)
    return hashlib.sha256(
        canonical_json(
            {
                "source": str(document.id),
                "library_visible": document.library_visible,
                "history": [(path, hashlib.sha256(value).hexdigest()) for path, value in files],
            }
        )
    ).hexdigest()


def template_history_custody_matches(document: Document, repository_id: UUID) -> bool:
    from .repository_service import RepositoryServiceError, read_accepted_repository_file
    from .template_library_history import template_history_files

    try:
        _revisions, files = template_history_files(document)
        return all(
            read_accepted_repository_file(repository_id=repository_id, path=path) == value for path, value in files
        )
    except (RepositoryServiceError, TemplateMigrationError):
        return False


@dataclass(frozen=True, slots=True)
class _ScopedTemplateDestination:
    document_id: UUID
    enrollment: TemplateEnrollmentEvidence
    fingerprint: dict[str, object]


def _scoped_template_destinations(
    source: Document,
    ids: tuple[UUID, ...],
    actor_id: UUID,
) -> tuple[list[_ScopedTemplateDestination], set[UUID]]:
    from apps.accounts.models import User
    from apps.accounts.policy import PermissionKey, accessible_organizations, require_installation_member

    from .template_library_scope import editable_template_workspace_scope

    actor = User.objects.get(pk=actor_id, is_active=True)
    member = require_installation_member(actor)
    organizations = accessible_organizations(member, PermissionKey.DOCUMENTS_EDIT)
    workspaces = (
        Workspace.objects.filter(
            tenant_id=source.tenant_id,
            organization_id__in=organizations.values("id"),
        )
        .select_related("organization", "tenant")
        .order_by("id")
    )
    states = []
    consumers: set[UUID] = set()
    for workspace in workspaces:
        if workspace.organization_id is None:
            continue
        with editable_template_workspace_scope(workspace, actor_id):
            consumers.update(
                DocumentPlacement.objects.filter(
                    tenant_id=source.tenant_id,
                    organization_id=workspace.organization_id,
                    document__entity__workspace_id=workspace.id,
                    block__source_document_id=source.id,
                    resolution_mode="live",
                ).values_list("document_id", flat=True)
            )
            documents = (
                Document.objects.filter(
                    id__in=ids,
                    tenant_id=source.tenant_id,
                    organization_id=workspace.organization_id,
                    entity__workspace=workspace,
                    archived_at__isnull=True,
                )
                .select_related("entity")
                .order_by("id")
            )
            for document in documents:
                evidence = template_enrollment_evidence(document)
                if evidence is None or evidence.source_document_id != source.id:
                    raise TemplateMigrationError("template_enrollment_scope_invalid")
                fingerprint: dict[str, object] = {
                    "id": str(document.id),
                    "workspace": str(workspace.id),
                    "title": document.entity.display_name,
                    "updated_at": str(document.updated_at),
                    "review": [document.review_state, document.review_content_sha256, str(document.last_reviewed_at)],
                    "placements": [
                        [
                            str(item.id),
                            str(item.block_id),
                            str(item.block.current_revision_id),
                            str(item.pinned_revision_id),
                            str(item.parent_id),
                            item.position,
                            item.audience_profile,
                            item.resolution_mode,
                        ]
                        for item in document.placements.select_related("block").order_by("id")
                    ],
                }
                states.append(_ScopedTemplateDestination(document.id, evidence, fingerprint))
    if len(states) != len(ids):
        raise TemplateMigrationError("template_destination_unavailable")
    return sorted(states, key=lambda item: item.document_id), consumers


@dataclass(frozen=True, slots=True)
class TemplateLibraryHandoffPlan:
    source_document_id: UUID
    destination_document_ids: tuple[UUID, ...]
    target: str
    plan_sha256: str


def _template_handoff_members(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
) -> list[tuple[Workspace, UUID]]:
    """Discover through editable scopes, then acquire every repository lease first."""
    from .models import WorkspaceRepository
    from .repository_service import _active_repository_transaction
    from .template_library_scope import editable_template_workspace_scope

    with editable_template_workspace_scope(source_workspace, actor_id):
        prepare_template_library_migration(
            source_workspace=source_workspace,
            source_document_id=source_document_id,
            destination_document_ids=destination_document_ids,
            actor_id=actor_id,
        )
        source = Document.objects.get(tenant_id=source_workspace.tenant_id, pk=source_document_id)
        states, _consumers = _scoped_template_destinations(source, destination_document_ids, actor_id)
    locations = {source_document_id: source_workspace.id}
    locations.update((state.document_id, UUID(str(state.fingerprint["workspace"]))) for state in states)
    workspaces = {
        w.id: w
        for w in Workspace.objects.select_related("organization", "tenant").filter(
            tenant_id=source_workspace.tenant_id,
            id__in=locations.values(),
        )
    }
    active = _active_repository_transaction()
    if active is None:
        raise TemplateMigrationError("template_handoff_transaction_required")
    repositories = list(
        WorkspaceRepository.objects.filter(
            tenant_id=source_workspace.tenant_id,
            workspace_id__in=workspaces,
        ).order_by("id")
    )
    if len(repositories) != len(workspaces):
        raise TemplateMigrationError("repository_missing")
    for repository in repositories:
        active.enlist(repository.id, write=False)
    members = [(workspaces[workspace_id], document_id) for document_id, workspace_id in locations.items()]
    return sorted(members, key=lambda item: (item[0].id, item[1]))


def _prepare_template_library_handoff(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
) -> tuple[TemplateLibraryHandoffPlan, list[tuple[Workspace, UUID]]]:
    from django.db import transaction

    from apps.accounts.models import User

    from .document_migration_coexistence import document_coexistence_status
    from .document_migration_export import build_simple_document_export
    from .models import Block, DocumentAuthority, WorkspaceRepository
    from .publications import canonical_json
    from .template_library_scope import editable_template_workspace_scope
    from .workspaces import resolve_msp_workspace, resolve_organization_workspace

    if target not in {"repository", "legacy"}:
        raise TemplateMigrationError("unsupported_template_authority_target")
    members = _template_handoff_members(
        source_workspace=source_workspace,
        source_document_id=source_document_id,
        destination_document_ids=destination_document_ids,
        actor_id=actor_id,
    )
    actor = User.objects.get(pk=actor_id, is_active=True)
    proofs = []
    with transaction.atomic():
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                document = (
                    Document.objects.select_for_update(of=("self",))
                    .select_related("entity")
                    .get(
                        tenant_id=workspace.tenant_id,
                        organization=workspace.organization,
                        entity__workspace=workspace,
                        pk=document_id,
                    )
                )
                list(
                    Block.objects.select_for_update()
                    .filter(
                        tenant_id=workspace.tenant_id,
                        source_document=document,
                    )
                    .order_by("id")
                )
                authority = DocumentAuthority.objects.select_for_update().get(
                    workspace=workspace,
                    tenant_id=workspace.tenant_id,
                    content_id=document.id,
                )
                repository = (
                    WorkspaceRepository.objects.select_for_update(of=("self",))
                    .select_related("accepted_commit")
                    .get(
                        tenant_id=workspace.tenant_id,
                        workspace=workspace,
                    )
                )
                if repository.accepted_commit is None or repository.accepted_commit_id != repository.indexed_commit_id:
                    raise TemplateMigrationError("repository_not_current")
                reader = (
                    resolve_organization_workspace(actor, entity_id=workspace.organization.entity_id)
                    if workspace.organization
                    else resolve_msp_workspace(actor)
                )
                status = document_coexistence_status(workspace=workspace, document=document, reader_workspace=reader)
                blockers = list(cast(list[str], status["handoff_blockers"]))
                rollback = target == "legacy" and authority.authority == "repository"
                if rollback:
                    from .document_authority_handoff import prepare_rollback_markdown_projection

                    prepare_rollback_markdown_projection(workspace=workspace, document=document)
                    blockers = [
                        code
                        for code in blockers
                        if code
                        not in {
                            "content_copy_not_in_sync",
                            "repository_read_projection_not_matched",
                            "managed_file_retention_limit",
                            "template_history_git_custody_unavailable",
                        }
                    ]
                if blockers:
                    raise TemplateMigrationError(", ".join(blockers))
                exported = build_simple_document_export(
                    document,
                    verify_attachments=True,
                    allow_repository_divergence=rollback,
                )
                proofs.append(
                    {
                        "document": str(document.id),
                        "workspace": str(workspace.id),
                        "authority": authority.authority,
                        "commit": repository.accepted_commit.object_id,
                        "files": [(path, hashlib.sha256(source).hexdigest()) for path, source in exported.files],
                        "enrollment": exported.template_enrollment_sha256,
                        "source": exported.template_source_sha256,
                        "history": status["publication_history"],
                        "review": [
                            document.review_state,
                            document.review_content_sha256,
                            str(document.last_reviewed_at),
                        ],
                    }
                )
    return TemplateLibraryHandoffPlan(
        source_document_id,
        tuple(sorted(destination_document_ids)),
        target,
        hashlib.sha256(canonical_json({"actor": str(actor_id), "target": target, "members": proofs})).hexdigest(),
    ), members


def prepare_template_library_handoff(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
) -> TemplateLibraryHandoffPlan:
    from .repository_service import coordinated_repository_transaction

    with coordinated_repository_transaction():
        plan, _members = _prepare_template_library_handoff(
            source_workspace=source_workspace,
            source_document_id=source_document_id,
            destination_document_ids=destination_document_ids,
            actor_id=actor_id,
            target=target,
        )
        return plan


def transition_template_library_authority(
    *,
    source_workspace: Workspace,
    source_document_id: UUID,
    destination_document_ids: tuple[UUID, ...],
    actor_id: UUID,
    target: str,
    plan_sha256: str,
) -> str:
    from django.db import connection

    from apps.accounts.models import User

    from .document_authority_handoff import _transition_document_authority_locked
    from .models import DocumentAuthority
    from .repository_service import coordinated_repository_transaction
    from .template_library_scope import editable_template_workspace_scope
    from .workspaces import resolve_msp_workspace, resolve_organization_workspace

    with coordinated_repository_transaction():
        plan, members = _prepare_template_library_handoff(
            source_workspace=source_workspace,
            source_document_id=source_document_id,
            destination_document_ids=destination_document_ids,
            actor_id=actor_id,
            target=target,
        )
        if plan.plan_sha256 != plan_sha256:
            raise TemplateMigrationError("preview_changed")
        actor = User.objects.get(pk=actor_id, is_active=True)
        changed = False
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                state = DocumentAuthority.objects.get(
                    tenant_id=workspace.tenant_id,
                    workspace=workspace,
                    content_id=document_id,
                )
                if state.authority != target:
                    changed = True
                    if target == "repository":
                        state.authority = target
                        state.save(update_fields=("authority", "updated_at"))
        if not changed:
            return "already_at_target"
        if target == "legacy":
            from .document_authority_handoff import prepare_rollback_markdown_projection
            from .documents import _append_block_revision
            from .models import Block

            # Every owned body is restored before verifying any dependent client.
            for workspace, document_id in members:
                with editable_template_workspace_scope(workspace, actor_id):
                    document = Document.objects.get(tenant_id=workspace.tenant_id, pk=document_id)
                    projection = prepare_rollback_markdown_projection(workspace=workspace, document=document)
                    for block in Block.objects.filter(
                        tenant_id=workspace.tenant_id,
                        source_document=document,
                        id__in=projection,
                    ).order_by("id"):
                        if block.current_revision_id is None:
                            raise TemplateMigrationError("rollback_legacy_block_unavailable")
                        _append_block_revision(
                            block=block,
                            actor_id=actor_id,
                            markdown=projection[block.id],
                            base_revision_id=block.current_revision_id,
                        )
        for workspace, document_id in members:
            with editable_template_workspace_scope(workspace, actor_id):
                reader = (
                    resolve_organization_workspace(actor, entity_id=workspace.organization.entity_id)
                    if workspace.organization
                    else resolve_msp_workspace(actor)
                )
                _transition_document_authority_locked(
                    workspace=workspace,
                    document_id=document_id,
                    actor_id=actor_id,
                    target=target,
                    reader_workspace=reader,
                    _group_staged=target == "repository",
                    _group_members=tuple(identity for _workspace, identity in members),
                )
        return "transitioned"
