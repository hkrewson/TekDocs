"""Read-only library summaries for Git documents without legacy Document records."""

import re
from typing import Any

from .content_read import RepositoryContentNotIndexed
from .models import ContentNode, Document, WorkspaceRepository, workspace_for_owner
from .repository_service import RepositoryServiceError, read_accepted_repository_file_dates
from .workspaces import ResolvedWorkspace


def native_document_summaries(workspace: ResolvedWorkspace, values: dict[str, Any]) -> list[dict[str, Any]]:
    # Repository readers are staff-only. Listing is not client publication.
    if workspace.member.surface == "client_portal":
        return []
    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    repository = WorkspaceRepository.objects.select_related("accepted_commit").filter(workspace=owner).first()
    if repository is None:
        return []
    if repository.accepted_commit_id != repository.indexed_commit_id:
        raise RepositoryContentNotIndexed()
    # Include archived rows here: a retained shadow copy must not resurrect them.
    legacy_ids = Document.objects.filter(tenant=workspace.member.tenant, entity__workspace=owner).values("id")
    nodes = list(ContentNode.objects.filter(repository=repository, workspace=owner, kind="document").exclude(
        content_id__in=legacy_ids
    ))
    result = []
    accepted = repository.accepted_commit
    if not nodes:
        return []
    if accepted is None or any(node.indexed_commit_id != accepted.id for node in nodes):
        raise RepositoryContentNotIndexed()
    try:
        file_dates = read_accepted_repository_file_dates(
            repository_id=repository.id, expected_commit=accepted.object_id, paths=[node.source_path for node in nodes],
        )
    except RepositoryServiceError as exc:
        raise RepositoryContentNotIndexed() from exc
    for node in nodes:
        if accepted is None or node.indexed_commit_id != accepted.id:
            raise RepositoryContentNotIndexed()
        properties = node.frontmatter.get("properties", {})
        properties = properties if isinstance(properties, dict) else {}
        category = str(properties.get("category", "general"))
        collection = str(properties.get("collection", ""))
        tags = properties.get("tags", [])
        tags = [str(tag) for tag in tags] if isinstance(tags, list) else []
        taxonomy_tags = [str(tag) for group in node.taxonomy_keys.values() if isinstance(group, list) for tag in group]
        composition = node.composition_variants.get("msp_internal", {})
        markdown = composition.get("markdown", node.markdown) if isinstance(composition, dict) else node.markdown
        is_template = properties.get("is_template") is True
        if (
            (values["category"] and values["category"] != category)
            or (values["collection"] and values["collection"].casefold() != collection.casefold())
            or (values["tag"] and values["tag"].strip().casefold()
                not in {tag.casefold() for tag in tags + taxonomy_tags})
            or (values["template"] == "templates" and not is_template)
            or (values["template"] == "documents" and is_template)
            or values["owner_id"]
            or values["review_state"] not in ("", "unreviewed")
            or values["health"] not in ("", "attention", "unowned")
            or str(values.get("exclude_document", "")) == str(node.content_id)
        ):
            continue
        query = values["q"].casefold()
        if query and not all(term in (node.title + " " + markdown).casefold()
                             for term in (re.findall(r"\w+", query)[:12] or [query])):
            continue
        organization = workspace.organization
        # These are discovery summaries, not fabricated legacy lifecycle records.
        # repository_native routes selection to the existing repository editor.
        record: dict[str, Any] = {
            "id": str(node.content_id), "content_id": str(node.content_id), "title": node.title,
            "repository_native": True, "content_authority": "repository",
            "owner_kind": "organization" if organization else "msp",
            "owner_organization_id": str(organization.entity_id) if organization else None,
            "owner_organization_name": organization.entity.display_name if organization else None,
            "is_reference": False, "category": category, "collection": collection, "tags": tags,
            "taxonomy_terms": [], "topic_type": node.topic_type or "unstructured",
            "topic_schema_version": node.topic_schema_version or 1,
            "is_template": is_template, "library_visible": properties.get("library_visible") is True,
            "health_status": "unowned", "review_state": "unreviewed", "review_note": "",
            "attachments": [], "attachment_count": 0, "primary_file": None, "primary_file_versions": [],
            "publications": [], "publication_count": 0, "placements": [], "placement_count": 0,
            "markdown": "", "resolved_markdown": "", "checksum": "",
            "created_at": file_dates[node.source_path][0].isoformat(),
            "updated_at": file_dates[node.source_path][1].isoformat(),
            "_search_markdown": markdown, "_facet_tags": tags + taxonomy_tags,
        }
        for field in (
            "owner_id", "owner_name", "review_due_on", "review_requested_by_id", "review_requested_by_name",
            "review_requested_at", "reviewer_id", "reviewer_name", "review_decided_at", "last_reviewed_by_id",
            "last_reviewed_by_name", "last_reviewed_at", "template_enrollment_id", "template_applied_revision_id",
            "template_source_id", "block_id", "current_revision_id", "revision_number",
        ):
            record[field] = None
        result.append(record)
    return result
