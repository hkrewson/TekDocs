"""Authorization-scoped adapter from enrolled library references to Git custody."""

from __future__ import annotations

import hashlib
from uuid import UUID

from django.db import transaction
from django.db.models import F

from .content_composition import ContentCompositionError, LibraryFragmentLoader
from .content_profile import ContentProfileError, ParsedContent, ParsedInclude, parse_content
from .models import Document, DocumentPlacement, WorkspaceRepository
from .repository_service import RepositoryServiceError, read_library_fragment


def template_library_loader(repository: WorkspaceRepository) -> LibraryFragmentLoader:
    cache: dict[tuple[UUID, ParsedInclude], tuple[str, ParsedContent]] = {}

    def load(document_id: UUID, include: ParsedInclude) -> tuple[str, ParsedContent]:
        key = (document_id, include)
        if key in cache:
            return cache[key]
        if (
            repository.workspace.organization_id is None
            or include.library_workspace_id is None
            or include.library_workspace_id == repository.workspace_id
        ):
            raise ContentCompositionError("include.library.scope", "Enrolled template library source is unavailable")
        from .native_templates import NativeTemplateConflict, NativeTemplateUnavailable, read_native_template_fragment
        try:
            native = read_native_template_fragment(repository=repository, content_id=document_id, include=include)
        except NativeTemplateUnavailable as exc:
            raise ContentCompositionError('include.native.unavailable', str(exc)) from exc
        except NativeTemplateConflict as exc:
            raise ContentCompositionError('include.library.scope', str(exc)) from exc
        if native is not None:
            selected, _revision = native
            cache[key] = (selected.object_id, parse_content(selected.source))
            return cache[key]
        destination_id = document_id
        pin = ({"pinned_revision_id": include.library_revision_id}
               if include.library_source_id is not None and include.mode == "pinned" else {})
        is_document = Document.objects.filter(
            pk=destination_id, tenant_id=repository.tenant_id,
            organization=repository.workspace.organization, entity__workspace_id=repository.workspace_id,
        ).exists()
        if is_document and not DocumentPlacement.objects.filter(
            tenant_id=repository.tenant_id, document_id=destination_id,
            block_id=include.target_content_id, parent__isnull=True,
            position=include.ordinal,
            resolution_mode=include.mode, audience_profile=include.audience,
            **pin,
        ).exists():
            raise ContentCompositionError("include.library.scope", "Enrolled template parent does not match")
        if not is_document:
            # Indexing also resolves each owned fragment independently. Permit a
            # foreign child only through its actual retained parent placement.
            destinations = tuple(DocumentPlacement.objects.filter(
                tenant_id=repository.tenant_id, organization=repository.workspace.organization,
                document__entity__workspace_id=repository.workspace_id,
                parent__block_id=document_id, parent__block__source_document_id=F("document_id"),
                block_id=include.target_content_id,
                position=include.ordinal,
                resolution_mode=include.mode, audience_profile=include.audience,
                **pin,
            ).values_list("document_id", flat=True).distinct()[:2])
            if len(destinations) != 1:
                raise ContentCompositionError("include.library.scope", "Enrolled template parent is unavailable")
            destination_id = destinations[0]
        try:
            with transaction.atomic():
                selected = read_library_fragment(
                    tenant_id=repository.tenant_id,
                    destination_document_id=destination_id,
                    library_workspace_id=include.library_workspace_id,
                    source_block_id=include.target_content_id,
                    mode=include.mode,
                    pinned_object_id=include.pinned_object_id,
                    library_revision_id=include.library_revision_id,
                    library_source_id=include.library_source_id,
                    audience=include.audience,
                )
            parsed = parse_content(selected.source)
            if hashlib.sha256(parsed.markdown.encode()).hexdigest() != selected.expected_body_sha256:
                raise ContentProfileError("include.library.parity", "Template library source proof differs")
        except (RepositoryServiceError, ContentProfileError) as exc:
            raise ContentCompositionError(
                "include.library.unavailable", "Enrolled template library Git content is unavailable or changed"
            ) from exc
        cache[key] = (selected.object_id, parsed)
        return cache[key]

    return load


def refresh_template_library_projection(repository: WorkspaceRepository) -> None:
    """Refresh exact grants, clearing unavailable native bytes without blocking other documents."""
    from .content_index import index_repository_content
    from .content_profile import _parse_includes
    from .models import ContentInclude, ContentNode, RepositoryTemplateEnrollment

    with transaction.atomic():
        native_ids = set(RepositoryTemplateEnrollment.objects.filter(
            repository=repository, tenant_id=repository.tenant_id, workspace_id=repository.workspace_id,
            organization=repository.workspace.organization,
        ).values_list('content_id', flat=True))
        references = list(ContentInclude.objects.filter(
            source__repository=repository, library_workspace_id__isnull=False,
        ).select_related('source').order_by('source__content_id', 'ordinal'))
        prior = {(row.source.content_id, row.ordinal): row for row in references}
        loader = template_library_loader(repository)
        changed = False
        for node in ContentNode.objects.filter(repository=repository, content_id__in=native_ids):
            available = True
            for include in _parse_includes(node.frontmatter.get('includes')):
                if include.library_workspace_id is None:
                    continue
                try:
                    object_id, parsed = loader(node.content_id, include)
                except ContentCompositionError as exc:
                    if exc.code != 'include.native.unavailable':
                        raise
                    available = False
                    continue
                previous = prior.get((node.content_id, include.ordinal))
                changed |= previous is None or (
                    previous.resolved_object_id, previous.resolved_content_digest
                ) != (object_id, parsed.content_digest)
            was_unavailable = bool(node.composition_variants.get('all', {}).get('unavailable'))
            changed |= was_unavailable == available
        for reference in references:
            if reference.source.content_id in native_ids:
                continue
            object_id, parsed = loader(reference.source.content_id, ParsedInclude(
                target_content_id=reference.target_content_id, mode=reference.resolution_mode,
                audience=reference.audience_profile, pinned_object_id=reference.pinned_object_id,
                ordinal=reference.ordinal, library_workspace_id=reference.library_workspace_id,
                library_revision_id=reference.library_revision_id, library_source_id=reference.library_source_id,
            ))
            changed |= (reference.resolved_object_id, reference.resolved_content_digest) != (
                object_id, parsed.content_digest,
            )
        if changed:
            index_repository_content(repository_id=repository.id, force=True)
