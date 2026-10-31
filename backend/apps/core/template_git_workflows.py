"""Reviewed template operations synchronized with the canonical client Git graph."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, cast
from uuid import UUID

from .document_migration_publications import publication_migration_actor_allowed
from .document_template_models import DocumentTemplateEnrollment
from .documents import PlacementConflict, apply_template_rollout, template_rollout_preview
from .models import (
    ContentNode,
    Document,
    DocumentAttachment,
    DocumentAuthority,
    DocumentPlacement,
    Workspace,
    WorkspaceRepository,
)
from .repository_service import (
    RepositoryAuditAttribution,
    _active_repository_transaction,
    commit_repository_files,
    coordinated_repository_transaction,
    pin_accepted_repository_for_publication,
    read_accepted_repository_markdown_files,
)
from .template_git_operation import TemplateGitOperation, template_git_operation
from .template_library_scope import editable_template_workspace_scope


@contextmanager
def _locked_template_client(
    document: Document,
    actor_id: UUID,
) -> Iterator[tuple[Document, DocumentTemplateEnrollment, WorkspaceRepository]]:
    workspace = document.entity.workspace
    if not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id):
        raise PlacementConflict("Template changes require permission to edit this Workspace.")
    current = Document.objects.filter(
        tenant_id=workspace.tenant_id,
        organization=workspace.organization,
        entity__workspace=workspace,
        pk=document.pk,
        archived_at__isnull=True,
    ).first()
    if current is None:
        raise PlacementConflict("The client document is unavailable.")
    enrollment = DocumentTemplateEnrollment.objects.filter(
        tenant_id=workspace.tenant_id,
        destination_document=current,
        archived_at__isnull=True,
    ).first()
    if enrollment is None:
        raise PlacementConflict("The template enrollment is unavailable.")
    try:
        source = enrollment.source_template
    except Document.DoesNotExist as exc:
        raise PlacementConflict("The template source is unavailable. Independent copies remain usable.") from exc
    if source.archived_at is not None or not source.is_template or not source.library_visible:
        raise PlacementConflict("The approved template source is unavailable.")
    if not DocumentAuthority.objects.filter(
        tenant_id=workspace.tenant_id,
        workspace_id=source.entity.workspace_id,
        content_id=source.id,
        authority="repository",
    ).exists():
        raise PlacementConflict("The source template must finish migration before these updates are available.")
    with _template_repositories(workspace, source) as repository:
        from .template_library_content import refresh_template_library_projection

        refresh_template_library_projection(repository)
        repository.refresh_from_db()
        if (
            repository.accepted_commit_id is None
            or repository.indexed_commit_id != repository.accepted_commit_id
            or not DocumentAuthority.objects.filter(
                tenant_id=workspace.tenant_id,
                workspace=workspace,
                content_id=document.id,
                authority="repository",
            ).exists()
        ):
            raise PlacementConflict("The Git-backed client document is not current.")
        current = (
            Document.objects.select_for_update(of=("self",))
            .select_related("entity")
            .get(
                tenant_id=workspace.tenant_id,
                organization=workspace.organization,
                pk=document.id,
            )
        )
        enrollment = DocumentTemplateEnrollment.objects.select_for_update().get(
            tenant_id=workspace.tenant_id,
            destination_document=current,
        )
        yield current, enrollment, repository


def preview_git_template_rollout(*, document: Document, actor_id: UUID) -> dict[str, Any]:
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(document.entity.workspace, actor_id),
        _locked_template_client(document, actor_id) as (current, enrollment, repo),
    ):
        _latest, preview = template_rollout_preview(enrollment=enrollment, actor_id=actor_id)
        node = ContentNode.objects.get(repository=repo, content_id=current.id)
        return _review_payload(current, enrollment, repo, node, preview)


def apply_git_template_rollout(
    *,
    document: Document,
    actor_id: UUID,
    expected_base: str,
    expected_composition: str,
    expected_applied_revision_id: UUID,
    expected_available_revision: int,
    placement_rules: dict[str, str] | None = None,
) -> dict[str, Any]:
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(document.entity.workspace, actor_id),
        _locked_template_client(document, actor_id) as (current, enrollment, repo),
    ):
        node = ContentNode.objects.get(repository=repo, content_id=current.id)
        if (
            _accepted_head(repo) != expected_base
            or node.composition_variants["msp_internal"]["digest"] != expected_composition
        ):
            raise PlacementConflict("The client content changed after this preview loaded. Review it again.")
        with template_git_operation(current, repo, enrollment.source_template_id) as operation:
            _project_client_bodies(current, repo, actor_id)
            result = apply_template_rollout(
                enrollment=enrollment,
                actor_id=actor_id,
                expected_applied_revision_id=expected_applied_revision_id,
                expected_available_revision=expected_available_revision,
                placement_rules=placement_rules,
            )
            _commit_template_graph(
                document=current,
                repository=repo,
                actor_id=actor_id,
                expected_base=expected_base,
                operation=operation,
                action="content.template_rollout",
                message="Apply reviewed template rollout",
            )
            enrollment.refresh_from_db()
            repo.refresh_from_db()
            node = ContentNode.objects.get(repository=repo, content_id=current.id)
            return _review_payload(current, enrollment, repo, node, result)


def _accepted_head(repository: WorkspaceRepository) -> str:
    if repository.accepted_commit is None:
        raise PlacementConflict("The Git-backed client document has no accepted content.")
    return repository.accepted_commit.object_id


def _project_client_bodies(document: Document, repository: WorkspaceRepository, actor_id: UUID) -> None:
    from .document_authority_handoff import prepare_rollback_markdown_projection
    from .documents import _append_block_revision
    from .models import Block

    # Preserve actual Git-authored local edits before exporting the new graph.
    projection = prepare_rollback_markdown_projection(workspace=repository.workspace, document=document)
    for block in Block.objects.filter(tenant_id=repository.tenant_id, source_document=document, id__in=projection):
        if block.current_revision_id is None:
            raise PlacementConflict("Retained client revision is unavailable.")
        _append_block_revision(
            block=block,
            actor_id=actor_id,
            markdown=projection[block.id],
            base_revision_id=block.current_revision_id,
        )


def _commit_template_graph(
    *,
    document: Document,
    repository: WorkspaceRepository,
    actor_id: UUID,
    expected_base: str,
    operation: TemplateGitOperation,
    action: str,
    message: str,
) -> str:
    from django.db import connection

    from .content_index import index_repository_content, validate_candidate_snapshot
    from .document_migration_export import build_simple_document_export

    document.refresh_from_db()
    exported = build_simple_document_export(document, verify_attachments=True)
    operation.changes = dict(exported.files)
    _accepted, existing_files = read_accepted_repository_markdown_files(repository_id=repository.id)
    candidate = dict(existing_files)
    candidate.update(operation.changes)
    validate_candidate_snapshot(repository=repository, files=tuple(sorted(candidate.items())))
    committed = commit_repository_files(
        repository_id=repository.id,
        expected_base=expected_base,
        changes=operation.changes,
        message=f"{message} {document.id}",
        attribution=RepositoryAuditAttribution(actor_id=actor_id, action=action),
    )
    index_repository_content(repository_id=repository.id)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL tekdocs.document_authority_transition = 'on'")
    root = DocumentAuthority.objects.get(
        tenant_id=repository.tenant_id,
        workspace=repository.workspace,
        content_id=document.id,
    )
    if root.authority == "legacy":
        root.authority = "repository"
        root.save(update_fields=("authority", "updated_at"))
    for state in DocumentAuthority.objects.filter(
        tenant_id=repository.tenant_id,
        workspace=repository.workspace,
        content_id__in=exported.copied_content_ids,
        authority="legacy",
    ):
        state.authority = "repository"
        state.save(update_fields=("authority", "updated_at"))
    return committed.object_id


def detach_git_template_section(
    *,
    document: Document,
    actor_id: UUID,
    placement_id: UUID,
    expected_base: str,
    expected_composition: str,
    expected_applied_revision_id: UUID,
) -> DocumentPlacement:
    from copy import deepcopy

    from .content_profile import ParsedInclude
    from .documents import detach_document_placement
    from .models import DocumentPlacement
    from .template_library_content import template_library_loader

    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(document.entity.workspace, actor_id),
        _locked_template_client(document, actor_id) as (current, enrollment, repository),
    ):
        node = ContentNode.objects.get(repository=repository, content_id=current.id)
        if (
            _accepted_head(repository) != expected_base
            or node.composition_variants["msp_internal"]["digest"] != expected_composition
            or enrollment.applied_revision_id != expected_applied_revision_id
        ):
            raise PlacementConflict("The client content or enrollment changed after this preview loaded.")
        placement = (
            DocumentPlacement.objects.select_for_update(of=("self",))
            .select_related(
                "block",
                "parent",
                "pinned_revision",
                "block__current_revision",
                "block__source_document__entity",
            )
            .filter(tenant_id=repository.tenant_id, document=current, pk=placement_id)
            .first()
        )
        mapped = next(
            (item for item in enrollment.placement_map if item["destination_placement_id"] == str(placement_id)), None
        )
        if placement is None or mapped is None or mapped["mode"] not in {"live", "pinned"}:
            raise PlacementConflict("Only an enrolled reused section can be detached here.")
        mode = placement.resolution_mode
        reference = next(
            (
                item
                for item in node.composition_variants["msp_internal"]["manifest"]
                if item["id"] == str(placement.block_id)
            ),
            None,
        )
        if reference is None:
            raise PlacementConflict("The selected template source is not in this composition.")
        source_document = placement.block.source_document
        if source_document is None:
            raise PlacementConflict("The enrolled source owner is unavailable.")
        include = ParsedInclude(
            target_content_id=placement.block_id,
            mode=mode,
            audience=placement.audience_profile,
            pinned_object_id=reference["commit"] if mode == "pinned" else "",
            ordinal=placement.position,
            library_workspace_id=source_document.entity.workspace_id,
            library_revision_id=enrollment.applied_revision_id,
        )
        parent_content_id = placement.parent.block_id if placement.parent is not None else current.id
        object_id, parsed = template_library_loader(repository)(parent_content_id, include)
        revision = placement.pinned_revision if mode == "pinned" else placement.block.current_revision
        if revision is None or revision.markdown != parsed.markdown:
            raise PlacementConflict("The retained template source differs from its actual selected Git bytes.")
        fork = {
            "source_entity": mapped["source_block_id"],
            "content_id": str(placement.block_id),
            "workspace": str(include.library_workspace_id),
            "revision": str(revision.id),
            "commit": object_id,
            "checksum": revision.checksum,
            "mode": mode,
        }
        with template_git_operation(current, repository, enrollment.source_template_id) as operation:
            _project_client_bodies(current, repository, actor_id)
            detached = detach_document_placement(placement=placement, actor_id=actor_id)
            from .models import AuditEvent
            from .template_fork_evidence import template_fork_metadata

            if detached.block.current_revision is None:
                raise PlacementConflict("The detached revision is unavailable.")
            proof = AuditEvent.objects.create(
                tenant_id=repository.tenant_id,
                actor_id=actor_id,
                entity_id=current.entity_id,
                action="document.template_section_forked",
                metadata=template_fork_metadata(
                    enrollment_id=enrollment.id,
                    placement=detached,
                    revision=detached.block.current_revision,
                    source=fork,
                ),
            )
            fork["audit_event"] = str(proof.id)
            mapping = deepcopy(enrollment.placement_map)
            target = next(item for item in mapping if item["destination_placement_id"] == str(placement_id))
            target.update({"destination_block_id": str(detached.block.entity_id), "mode": "copy", "forked_from": fork})
            enrollment.placement_map = mapping
            enrollment.save(update_fields=("placement_map", "updated_at"))
            _commit_template_graph(
                document=current,
                repository=repository,
                actor_id=actor_id,
                expected_base=expected_base,
                operation=operation,
                action="content.template_section_detached",
                message="Detach reviewed template section",
            )
            return detached


@contextmanager
def _template_repositories(workspace: Workspace, source: Document) -> Iterator[WorkspaceRepository]:
    repositories = list(
        WorkspaceRepository.objects.filter(
            tenant_id=workspace.tenant_id,
            workspace_id__in=(workspace.id, source.entity.workspace_id),
        ).order_by("id")
    )
    if len(repositories) != 2:
        raise PlacementConflict("The template repositories are unavailable.")
    with ExitStack() as pins:
        active = _active_repository_transaction()
        if active is None:
            raise PlacementConflict("Template synchronization requires the coordinated transaction.")
        for binding in repositories:
            active.enlist(binding.id, write=False)
        repository = None
        for binding in repositories:
            locked = WorkspaceRepository.objects.select_for_update().get(
                tenant_id=workspace.tenant_id,
                pk=binding.id,
            )
            if locked.workspace_id == workspace.id:
                repository = locked
            else:
                pins.enter_context(pin_accepted_repository_for_publication(binding.id))
        if repository is None:
            raise PlacementConflict("The client repository is unavailable.")
        yield repository


def template_definition_sha256(source: Document) -> str:
    return _template_definition_snapshot(source)[0]


def _template_definition_snapshot(source: Document) -> tuple[str, tuple[DocumentAttachment, ...]]:
    import hashlib

    from .content_profile import parse_content
    from .documents import _template_manifest
    from .publications import canonical_json
    from .repository_service import read_accepted_repository_file

    manifest = _template_manifest(source)
    repository = WorkspaceRepository.objects.get(tenant_id=source.tenant_id, workspace_id=source.entity.workspace_id)
    root = read_accepted_repository_file(repository_id=repository.id, path=f"docs/{source.id}.md")
    from django.db.models import Q

    from .documents import resolve_document
    from .rendering import attachment_ids_in_markdown

    linked = attachment_ids_in_markdown(resolve_document(source).markdown)
    files = list(
        source.attachments.filter(archived_at__isnull=True)
        .filter(
            Q(entity_id__in=linked) | Q(purpose="primary_file"),
        )
        .order_by("entity_id")
    )
    checksum = hashlib.sha256(
        canonical_json(
            {
                "definition": manifest,
                "root": parse_content(root).content_digest,
                "has_primary_file": any(item.purpose == "primary_file" for item in files),
                "files": [
                    (
                        str(item.entity_id),
                        item.checksum,
                        item.purpose,
                        item.version_number,
                        item.original_filename,
                        item.media_type,
                        item.size,
                    )
                    for item in files
                ],
            }
        )
    ).hexdigest()
    return checksum, tuple(files)


def instantiate_git_template(
    *,
    source: Document,
    workspace: Workspace,
    actor_id: UUID,
    title: str,
    category: str,
    placement_rules: dict[str, str] | None,
    expected_source_sha256: str,
) -> Document:
    from .document_template_models import DocumentTemplateRevision
    from .documents import instantiate_document_template
    from .models import AuditEvent

    organization = workspace.organization
    if organization is None or not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id):
        raise PlacementConflict("A permitted client Workspace is required.")
    with coordinated_repository_transaction(), editable_template_workspace_scope(workspace, actor_id):
        current = (
            Document.objects.select_related("entity")
            .filter(
                tenant_id=workspace.tenant_id,
                organization__isnull=True,
                pk=source.id,
                is_template=True,
                library_visible=True,
                archived_at__isnull=True,
            )
            .first()
        )
        if (
            current is None
            or not DocumentAuthority.objects.filter(
                tenant_id=workspace.tenant_id,
                workspace_id=current.entity.workspace_id,
                content_id=current.id,
                authority="repository",
            ).exists()
        ):
            raise PlacementConflict("The approved Git-backed template source is unavailable.")
        with _template_repositories(workspace, current) as repository:
            if (
                repository.accepted_commit_id is None
                or repository.indexed_commit_id != repository.accepted_commit_id
            ):
                raise PlacementConflict("The destination Workspace is not ready for template creation.")
            definition, source_files = _template_definition_snapshot(current)
            if definition != expected_source_sha256:
                raise PlacementConflict("The template changed after review. Review its current section choices.")
            from .documents import _template_manifest

            source_ids = {
                str(item["source_block_id"])
                for item in cast(list[dict[str, Any]], _template_manifest(current)["blocks"])
            }
            if not set(placement_rules or {}).issubset(source_ids):
                raise PlacementConflict("The section choices no longer match this template.")
            base = _accepted_head(repository)

            @contextmanager
            def enroll(
                destination: Document, version: DocumentTemplateRevision, mapping: list[dict[str, object]]
            ) -> Iterator[None]:
                enrollment = DocumentTemplateEnrollment.objects.create(
                    tenant_id=workspace.tenant_id,
                    organization=organization,
                    source_template=current,
                    destination_document=destination,
                    applied_revision=version,
                    placement_map=mapping,
                    created_by_id=actor_id,
                    last_applied_by_id=actor_id,
                )
                with template_git_operation(destination, repository, current.id) as operation:
                    yield
                    enrollment.placement_map = mapping
                    enrollment.save(update_fields=("placement_map", "updated_at"))
                    _commit_template_graph(
                        document=destination,
                        repository=repository,
                        actor_id=actor_id,
                        expected_base=base,
                        operation=operation,
                        action="content.template_enrolled",
                        message="Create reviewed template enrollment",
                    )
                    AuditEvent.objects.create(
                        tenant_id=workspace.tenant_id,
                        actor_id=actor_id,
                        entity_id=destination.entity_id,
                        action="document.git_template_instantiated",
                        metadata={
                            "enrollment": str(enrollment.id),
                            "source_document": str(current.id),
                            "source_definition_sha256": definition,
                            "applied_revision": str(version.id),
                            "source_files": [
                                (str(item.entity_id), item.checksum, item.purpose, item.version_number)
                                for item in source_files
                            ],
                        },
                    )

            active = _active_repository_transaction()
            if active is None:
                raise PlacementConflict("Template file creation requires a coordinated transaction.")
            def register_attachment(attachment: DocumentAttachment) -> None:
                identity, storage, name = attachment.id, attachment.file.storage, attachment.file.name

                def retained(identity: UUID = identity) -> bool:
                    with editable_template_workspace_scope(workspace, actor_id):
                        return DocumentAttachment.objects.filter(
                            tenant_id=workspace.tenant_id, organization=workspace.organization, pk=identity,
                        ).exists()

                from functools import partial

                active.register_created_artifact(retained, partial(storage.delete, name))

            created = instantiate_document_template(
                source=current,
                tenant=workspace.tenant,
                organization=organization,
                actor_id=actor_id,
                title=title,
                category=category,
                placement_rules=placement_rules,
                _git_enrollment=enroll,
                _source_attachments=source_files,
                _copied_attachment=register_attachment,
            )
            from django.db import connection
            from django.db.transaction import TransactionManagementError

            if connection.needs_rollback:
                raise TransactionManagementError("Template creation was rolled back before completion.")
    return created


def _review_payload(
    document: Document,
    enrollment: DocumentTemplateEnrollment,
    repository: WorkspaceRepository,
    node: ContentNode,
    preview: dict[str, Any],
) -> dict[str, Any]:
    mapping = {item["destination_placement_id"]: item for item in enrollment.placement_map}
    references = {item["id"]: item for item in node.composition_variants["msp_internal"]["manifest"]}
    sections = []
    for placement in document.placements.order_by("position", "id"):
        mapped = mapping.get(str(placement.id))
        reference = references.get(str(placement.block_id))
        if mapped and mapped["mode"] in {"live", "pinned"} and reference and reference.get("workspace"):
            sections.append({"placement_id": str(placement.id), "title": reference["title"], "mode": mapped["mode"]})
    return {
        **preview,
        "base_commit": _accepted_head(repository),
        "composition_digest": node.composition_variants["msp_internal"]["digest"],
        "applied_revision_id": str(enrollment.applied_revision_id),
        "reused_sections": sections,
    }
