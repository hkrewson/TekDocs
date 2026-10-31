"""Authorization-scoped adapter from enrolled library references to Git custody."""

from __future__ import annotations

import hashlib
from uuid import UUID

from django.db import transaction
from django.db.models import F

from .content_composition import ContentCompositionError, LibraryFragmentLoader
from .content_profile import ContentProfileError, ParsedContent, ParsedInclude, parse_content
from .models import Document, DocumentPlacement, WorkspaceRepository
from .repository_service import RepositoryServiceError, read_template_library_fragment


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
        destination_id = document_id
        is_document = Document.objects.filter(
            pk=destination_id, tenant_id=repository.tenant_id,
            organization=repository.workspace.organization, entity__workspace_id=repository.workspace_id,
        ).exists()
        if is_document and not DocumentPlacement.objects.filter(
            tenant_id=repository.tenant_id, document_id=destination_id,
            block_id=include.target_content_id, parent__isnull=True,
            resolution_mode=include.mode, audience_profile=include.audience,
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
                resolution_mode=include.mode, audience_profile=include.audience,
            ).values_list("document_id", flat=True).distinct()[:2])
            if len(destinations) != 1:
                raise ContentCompositionError("include.library.scope", "Enrolled template parent is unavailable")
            destination_id = destinations[0]
        try:
            with transaction.atomic():
                selected = read_template_library_fragment(
                    destination_document_id=destination_id,
                    library_workspace_id=include.library_workspace_id,
                    source_block_id=include.target_content_id,
                    mode=include.mode,
                    pinned_object_id=include.pinned_object_id,
                    template_revision_id=include.library_revision_id,
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
    """Recheck Git custody on reads; a client commit alone cannot freeze LIVE sources."""
    from django.db import transaction

    from .content_index import index_repository_content
    from .models import ContentInclude

    with transaction.atomic():
        references = list(
            ContentInclude.objects.filter(
                source__repository=repository,
                library_workspace_id__isnull=False,
            )
            .select_related("source")
            .order_by("source__content_id", "ordinal")
        )
        if not references:
            return
        loader = template_library_loader(repository)
        changed = False
        for reference in references:
            object_id, parsed = loader(
                reference.source.content_id,
                ParsedInclude(
                    target_content_id=reference.target_content_id,
                    mode=reference.resolution_mode,
                    audience=reference.audience_profile,
                    pinned_object_id=reference.pinned_object_id,
                    ordinal=reference.ordinal,
                    library_workspace_id=reference.library_workspace_id,
                    library_revision_id=reference.library_revision_id,
                ),
            )
            changed |= (reference.resolved_object_id, reference.resolved_content_digest) != (
                object_id,
                parsed.content_digest,
            )
        if changed:
            index_repository_content(repository_id=repository.id, force=True)
