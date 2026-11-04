"""Reviewed template enrollment for Git-owned documents and independent leaves."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import UUID, uuid4

from django.db.models import F

from .content_authoring import (
    AuthoredContent,
    ContentAuthoringError,
    _replace_fields,
    _snapshot,
    _source_for_id,
    author_content,
    read_authored_content,
)
from .content_profile import ParsedContent, ParsedInclude, parse_content
from .models import (
    Document,
    Organization,
    RepositoryCommit,
    RepositoryTemplate,
    RepositoryTemplateEnrollment,
    RepositoryTemplateRevision,
    WorkspaceRepository,
)
from .repository_key_context import native_fragment_nodes
from .repository_service import (
    LibraryFragmentRead,
    RepositoryAuditAttribution,
    RepositoryCommitResult,
    RepositoryServiceError,
    commit_repository_files,
    coordinated_repository_transaction,
    pin_accepted_repository_for_publication,
    read_repository_markdown_files_at_commit,
)
from .template_library_scope import editable_template_workspace_scope

_native_operation = ContextVar("native_template_operation", default=False)


class NativeTemplateConflict(ContentAuthoringError):
    pass


class NativeTemplateUnavailable(NativeTemplateConflict):
    """A previously granted source is withdrawn or no longer offers its section."""


def _latest(template: RepositoryTemplate) -> RepositoryTemplateRevision:
    revision = template.latest_revision
    if revision is None:
        raise NativeTemplateConflict("Template revision is unavailable")
    return revision


def _accepted(repository: WorkspaceRepository) -> RepositoryCommit:
    if repository.accepted_commit is None:
        raise NativeTemplateConflict("Template accepted commit is unavailable")
    return repository.accepted_commit


def _client(repository: WorkspaceRepository) -> Organization:
    if repository.workspace.organization is None:
        raise NativeTemplateConflict("Select a client Workspace for template enrollment")
    return repository.workspace.organization


@contextmanager
def native_template_operation() -> Iterator[None]:
    token = _native_operation.set(True)
    try:
        yield
    finally:
        _native_operation.reset(token)


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _native_document(repository: WorkspaceRepository, content_id: UUID) -> AuthoredContent:
    source = read_authored_content(repository=repository, content_id=content_id)
    if (
        source.kind != "document"
        or Document.objects.filter(
            pk=content_id,
            tenant_id=repository.tenant_id,
            organization=repository.workspace.organization,
        ).exists()
    ):
        raise NativeTemplateConflict("Only new Git-backed documents can be native templates")
    return source


def _independent_body(parsed: ParsedContent) -> None:
    from .document_keys import key_targets_in_markdown
    from .rendering import attachment_ids_in_markdown, entity_ids_in_markdown

    if (
        parsed.links
        or parsed.entity_links
        or parsed.findings
        or parsed.frontmatter.get("key_bindings")
        or key_targets_in_markdown(parsed.markdown)
        or attachment_ids_in_markdown(parsed.markdown)
        or entity_ids_in_markdown(parsed.markdown)
    ):
        raise NativeTemplateConflict("Template text cannot contain unresolved keys, entities or file references")


def _leaf(parsed: ParsedContent) -> None:
    if parsed.includes or parsed.template_sources or parsed.derived_from:
        raise NativeTemplateConflict("Template sections must be independent text fragments")
    _independent_body(parsed)


def _record(path: str, source: bytes) -> dict[str, Any]:
    parsed = parse_content(source)
    return {
        "id": str(parsed.content_id),
        "title": parsed.title,
        "path": path,
        "source": source.decode(),
        "content_digest": parsed.content_digest,
        "body_sha256": _digest(parsed.markdown.encode()),
    }


def project_native_templates(
    *, repository: WorkspaceRepository, commit: RepositoryCommit, parsed_by_path: dict[str, ParsedContent]
) -> None:
    """Project registered declarations atomically with accepted source indexing."""
    if repository.workspace.organization_id is not None:
        return
    templates = list(RepositoryTemplate.objects.filter(repository=repository, tenant_id=repository.tenant_id))
    if not templates:
        return
    _, files = _snapshot(repository)
    native_ids = set(native_fragment_nodes(repository).values_list("content_id", flat=True))
    for template in templates:
        root = _source_for_id(files, template.content_id)
        if root is None:
            template.enabled = False
            template.save(update_fields=["enabled", "updated_at"])
            continue
        parsed = parse_content(root[1])
        properties = parsed.frontmatter.get("properties", {})
        template.enabled = properties.get("template") is True and properties.get("lifecycle") != "archived"
        template.library_visible = properties.get("library_visible") is True
        if not template.enabled:
            template.save(update_fields=["enabled", "library_visible", "updated_at"])
            continue
        _independent_body(parsed)
        if any(
            selected is not None and parse_content(selected[1]).properties.get("lifecycle") == "archived"
            for include in parsed.includes
            for selected in [_source_for_id(files, include.target_content_id)]
        ):
            template.enabled = False
            template.save(update_fields=["enabled", "library_visible", "updated_at"])
            continue
        sections = []
        for include in parsed.includes:
            if (
                include.target_content_id not in native_ids
                or include.library_workspace_id is not None
                or include.mode != "live"
                or include.audience != "shared"
            ):
                raise NativeTemplateConflict("Template source includes must select native same-Workspace fragments")
            selected = _source_for_id(files, include.target_content_id)
            if selected is None:
                raise NativeTemplateConflict("Template source section is unavailable")
            _leaf(parse_content(selected[1]))
            sections.append(_record(*selected))
        if len({row["id"] for row in sections}) != len(sections):
            raise NativeTemplateConflict("Template source sections must be unique")
        manifest = {
            "format": "tekdocs.native-template/v1",
            "content_id": str(template.content_id),
            "workspace_id": str(repository.workspace_id),
            "repository_id": str(repository.id),
            "commit": commit.object_id,
            "title": parsed.title,
            "root": _record(*root),
            "sections": sections,
        }
        prior = _latest(template).manifest if template.latest_revision_id else None
        if prior and {k: v for k, v in prior.items() if k != "commit"} == {
            k: v for k, v in manifest.items() if k != "commit"
        }:
            template.save(update_fields=["enabled", "library_visible", "updated_at"])
            continue
        revision, _ = RepositoryTemplateRevision.objects.get_or_create(
            template=template,
            checksum=_digest(canonical_bytes(manifest)),
            defaults={"tenant_id": repository.tenant_id, "commit": commit, "manifest": manifest},
        )
        template.latest_revision = revision
        template.save(update_fields=["latest_revision", "enabled", "library_visible", "updated_at"])


def configure_native_template(
    *,
    repository: WorkspaceRepository,
    actor_id: UUID,
    request_id: UUID | None,
    content_id: UUID,
    base_commit: str,
    base_blob: str,
    enabled: bool,
    library_visible: bool,
    fragment_ids: list[UUID],
) -> AuthoredContent:
    if repository.workspace.organization_id is not None:
        raise NativeTemplateConflict("Templates must belong to the MSP Workspace")
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(repository.workspace, actor_id),
        native_template_operation(),
    ):
        source = _native_document(repository, content_id)
        allowed = set(native_fragment_nodes(repository).values_list("content_id", flat=True))
        selected = [UUID(str(value)) for value in fragment_ids]
        if len(selected) != len(set(selected)) or any(value not in allowed for value in selected):
            raise NativeTemplateConflict("Template fragments are unavailable in this Workspace")
        RepositoryTemplate.objects.get_or_create(
            tenant_id=repository.tenant_id, repository=repository, workspace=repository.workspace, content_id=content_id
        )
        properties = dict(parse_content(source.source.encode()).frontmatter.get("properties", {}))
        properties.update(template=enabled, library_visible=library_visible)
        result = author_content(
            repository=repository,
            actor_id=actor_id,
            request_id=request_id,
            operation="update",
            content_id=content_id,
            base_commit=base_commit,
            base_blob=base_blob,
            kind=None,
            path=None,
            title=None,
            markdown=None,
            metadata_patch={
                "properties": properties,
                "includes": [{"id": str(value), "mode": "live", "audience": "shared"} for value in selected],
            },
        )
        # Unlike ordinary edits, this operation cannot succeed with a pending projection.
        repository.refresh_from_db()
        if repository.accepted_commit_id != repository.indexed_commit_id:
            raise NativeTemplateConflict("Template source indexing did not complete")
        return result


def _template(
    repository: WorkspaceRepository, source_content_id: UUID | None = None, *, template_id: UUID | None = None
) -> RepositoryTemplate:
    source = (
        RepositoryTemplate.objects.select_related("latest_revision", "repository__accepted_commit")
        .filter(
            tenant_id=repository.tenant_id,
            **({"content_id": source_content_id} if template_id is None else {"id": template_id}),
            enabled=True,
            library_visible=True,
            workspace__organization__isnull=True,
            repository__lifecycle_state="active",
        )
        .first()
    )
    if source is None or source.latest_revision_id is None:
        raise NativeTemplateUnavailable("Approved native template is unavailable")
    if source.repository.accepted_commit_id != source.repository.indexed_commit_id:
        raise NativeTemplateUnavailable("Template source index is unavailable")
    return source


def native_template_library(repository: WorkspaceRepository) -> list[dict[str, Any]]:
    if repository.workspace.organization_id is None:
        raise NativeTemplateConflict("Select a client Workspace for template enrollment")
    return [
        dict(
            id=str(row.content_id),
            title=_latest(row).manifest["title"],
            definition_sha256=_latest(row).checksum,
            sections=[
                {"id": item["id"], "title": item["title"], "markdown": parse_content(item["source"].encode()).markdown}
                for item in _latest(row).manifest["sections"]
            ],
        )
        for row in RepositoryTemplate.objects.select_related("latest_revision").filter(
            tenant_id=repository.tenant_id,
            enabled=True,
            library_visible=True,
            workspace__organization__isnull=True,
            latest_revision__isnull=False,
            repository__lifecycle_state="active",
            repository__accepted_commit_id=F("repository__indexed_commit_id"),
        )
    ]


def _new_source(content_id: UUID | str, kind: str, title: str, markdown: str) -> bytes:
    return (
        "---\nschema: tekdocs.content/v1\nid: "
        + str(content_id)
        + "\nkind: "
        + kind
        + "\ntitle: "
        + json.dumps(title)
        + "\n---\n"
        + markdown
    ).encode()


def _include(item: dict[str, Any], source_workspace_id: UUID) -> dict[str, Any]:
    if item["mode"] == "copy":
        return {"id": item["local_id"], "mode": "live", "audience": "shared"}
    result = {
        "id": item["id"],
        "mode": item["mode"],
        "audience": "shared",
        "library_workspace": str(source_workspace_id),
        "library_revision": item["revision_id"],
    }
    if item["mode"] == "pinned":
        result["commit"] = item["commit"]
    return result


def _write(
    repository: WorkspaceRepository,
    actor_id: UUID,
    request_id: UUID | None,
    expected_base: str | None,
    changes: dict[str, bytes | None],
) -> RepositoryCommitResult:
    from .content_index import index_repository_content

    result = commit_repository_files(
        repository_id=repository.id,
        expected_base=expected_base,
        changes=changes,
        message="Update native template enrollment",
        attribution=RepositoryAuditAttribution(actor_id=actor_id, action="content.template", request_id=request_id),
    )
    index_repository_content(repository_id=repository.id)
    return result


def _mapped(
    section: dict[str, Any], mode: str, revision: RepositoryTemplateRevision, changes: dict[str, bytes | None]
) -> dict[str, Any]:
    if mode not in {"copy", "live", "pinned"}:
        raise NativeTemplateConflict("Choose copy, live or pinned for every template section")
    item = {
        "id": section["id"],
        "title": section["title"],
        "mode": mode,
        "revision_id": str(revision.id),
        "commit": revision.commit.object_id,
        "body_sha256": section["body_sha256"],
        "workspace_id": revision.manifest["workspace_id"],
    }
    if mode == "copy":
        item["local_id"] = str(uuid4())
        changes[f"fragments/{item['local_id']}.md"] = _new_source(
            item["local_id"], "fragment", section["title"], parse_content(section["source"].encode()).markdown
        )
    return item


def enroll_native_template(
    *,
    repository: WorkspaceRepository,
    actor_id: UUID,
    request_id: UUID | None,
    source_content_id: UUID,
    definition_sha256: str,
    title: str,
    rules: dict[str, str],
) -> AuthoredContent:
    if repository.workspace.organization_id is None:
        raise NativeTemplateConflict("Select a client Workspace for template enrollment")
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(repository.workspace, actor_id),
        native_template_operation(),
        ExitStack() as pins,
    ):
        source = _template(repository, source_content_id)
        pins.enter_context(pin_accepted_repository_for_publication(source.repository_id))
        source = _template(repository, source_content_id)
        revision = _latest(source)
        if revision.checksum != definition_sha256:
            raise NativeTemplateConflict("Template definition changed; review it again")
        sections = revision.manifest["sections"]
        if set(rules) != {row["id"] for row in sections}:
            raise NativeTemplateConflict("Review every template section")
        base, _ = _snapshot(repository)
        changes: dict[str, bytes | None] = {}
        mapped = [_mapped(section, rules[section["id"]], revision, changes) for section in sections]
        content_id = uuid4()
        root = _new_source(
            content_id,
            "document",
            title or revision.manifest["title"],
            parse_content(revision.manifest["root"]["source"].encode()).markdown,
        )
        changes[f"docs/{content_id}.md"] = _replace_fields(
            root, {"includes": [_include(item, source.workspace_id) for item in mapped]}, None
        )
        RepositoryTemplateEnrollment.objects.create(
            tenant_id=repository.tenant_id,
            organization=_client(repository),
            workspace=repository.workspace,
            repository=repository,
            content_id=content_id,
            source_template=source,
            applied_revision=revision,
            placement_map=mapped,
        )
        _write(repository, actor_id, request_id, base, changes)
        return read_authored_content(repository=repository, content_id=content_id)


def native_enrollment(repository: WorkspaceRepository, content_id: UUID) -> RepositoryTemplateEnrollment | None:
    return RepositoryTemplateEnrollment.objects.filter(
        tenant_id=repository.tenant_id,
        repository=repository,
        workspace_id=repository.workspace_id,
        organization=repository.workspace.organization,
        content_id=content_id,
    ).first()


def read_native_template_fragment(
    *, repository: WorkspaceRepository, content_id: UUID, include: ParsedInclude, allow_removed: bool = False
) -> tuple[LibraryFragmentRead, RepositoryTemplateRevision] | None:
    """Authorize the exact occurrence before accessing any MSP Git source bytes."""
    enrollment = native_enrollment(repository, content_id)
    if enrollment is None:
        return None
    mapping = enrollment.placement_map
    if include.ordinal >= len(mapping):
        raise NativeTemplateConflict("Template occurrence is unavailable")
    item = mapping[include.ordinal]
    if (
        item["id"] != str(include.target_content_id)
        or item["mode"] != include.mode
        or item["mode"] == "copy"
        or include.audience != "shared"
        or str(include.library_workspace_id) != item["workspace_id"]
        or str(include.library_revision_id) != item["revision_id"]
        or include.library_source_id is not None
        or (include.mode == "pinned" and include.pinned_object_id != item["commit"])
    ):
        raise NativeTemplateConflict("Template occurrence does not match its enrollment")
    source = _template(repository, template_id=enrollment.source_template_id)
    revision = (
        _latest(source)
        if include.mode == "live"
        else RepositoryTemplateRevision.objects.select_related("commit").get(
            pk=item["revision_id"], template=source, tenant_id=repository.tenant_id
        )
    )
    section = next((row for row in revision.manifest["sections"] if row["id"] == item["id"]), None)
    if section is None and allow_removed:
        for retained in source.revisions.select_related("commit").order_by("-created_at"):
            section = next((row for row in retained.manifest["sections"] if row["id"] == item["id"]), None)
            if section:
                revision = retained
                break
    if section is None:
        raise NativeTemplateUnavailable("Template section was removed; review its update")
    try:
        commit, files = read_repository_markdown_files_at_commit(
            repository_id=source.repository_id,
            object_id=(
                _accepted(source.repository).object_id
                if include.mode == "live" and not allow_removed
                else revision.commit.object_id
            ),
        )
        raw = dict(files).get(section["path"])
        if raw is None or raw.decode() != section["source"]:
            raise NativeTemplateUnavailable("Template source proof is unavailable")
    except (RepositoryServiceError, UnicodeError) as exc:
        raise NativeTemplateUnavailable("Template source Git content is unavailable") from exc
    parsed = parse_content(raw)
    _leaf(parsed)
    from .repository_service import LibraryFragmentRead

    return LibraryFragmentRead(commit.object_id, raw, section["body_sha256"], section["path"], revision.id), revision


def native_template_state(
    *, repository: WorkspaceRepository, content_id: UUID, read_only: bool = False
) -> dict[str, Any]:
    source = _native_document(repository, content_id)
    if repository.workspace.organization_id is None:
        template = RepositoryTemplate.objects.filter(
            tenant_id=repository.tenant_id, repository=repository, content_id=content_id
        ).first()
        fragments = []
        for node in native_fragment_nodes(repository).order_by("title", "content_id"):
            try:
                item = read_authored_content(repository=repository, content_id=node.content_id)
                _leaf(parse_content(item.source.encode()))
            except ContentAuthoringError:
                continue
            fragments.append({"id": str(node.content_id), "title": node.title, "markdown": item.markdown})
        return {
            "role": "source",
            "read_only": read_only,
            "source": {
                "enabled": bool(template and template.enabled),
                "library_visible": bool(template and template.library_visible),
                "fragments": fragments,
                "selected_fragment_ids": [
                    str(row.target_content_id) for row in parse_content(source.source.encode()).includes
                ],
            },
        }
    enrollment = native_enrollment(repository, content_id)
    if enrollment is None:
        return {"role": "none", "read_only": read_only}
    template = _template(repository, template_id=enrollment.source_template_id)
    latest = _latest(template)
    sections = {item["id"]: item for item in latest.manifest["sections"]}
    changes = []
    for item in enrollment.placement_map:
        section = sections.pop(item["id"], None)
        markdown = parse_content(section["source"].encode()).markdown if section else ""
        state = (
            "removed"
            if section is None
            else ("updated" if item["body_sha256"] != section["body_sha256"] else "unchanged")
        )
        if item["mode"] == "copy":
            local = read_authored_content(repository=repository, content_id=UUID(item["local_id"]))
            if state != "unchanged" or _digest(local.markdown.encode()) != item["body_sha256"]:
                state = "conflict"
        changes.append(
            {
                "id": item["id"],
                "title": item["title"],
                "mode": item["mode"],
                "state": state,
                "markdown": markdown,
                "current_markdown": local.markdown if item["mode"] == "copy" else markdown,
            }
        )
    changes.extend(
        {
            "id": item["id"],
            "title": item["title"],
            "mode": "copy",
            "state": "added",
            "markdown": parse_content(item["source"].encode()).markdown,
        }
        for item in sections.values()
    )
    return {
        "role": "enrolled",
        "read_only": read_only,
        "enrollment": {
            "source_title": latest.manifest["title"],
            "applied_revision_id": str(enrollment.applied_revision_id),
            "available_revision_id": str(latest.id),
            "expected_base": source.accepted_commit,
            "expected_blob": source.source_blob,
            "changes": changes,
            "can_apply": not read_only,
        },
    }


def _review(
    repository: WorkspaceRepository,
    content_id: UUID,
    base_commit: str,
    base_blob: str,
    expected_applied_revision_id: UUID,
    expected_available_revision_id: UUID,
) -> tuple[AuthoredContent, RepositoryTemplateEnrollment, RepositoryTemplate]:
    source = _native_document(repository, content_id)
    enrollment = native_enrollment(repository, content_id)
    if enrollment is None:
        raise NativeTemplateConflict("Native enrollment is unavailable")
    template = _template(repository, template_id=enrollment.source_template_id)
    if (
        source.accepted_commit != base_commit
        or source.source_blob != base_blob
        or str(enrollment.applied_revision_id) != str(expected_applied_revision_id)
        or str(template.latest_revision_id) != str(expected_available_revision_id)
    ):
        raise NativeTemplateConflict("Template or client document changed; review it again")
    return source, enrollment, template


def apply_native_template(
    *,
    repository: WorkspaceRepository,
    actor_id: UUID,
    request_id: UUID | None,
    content_id: UUID,
    base_commit: str,
    base_blob: str,
    expected_applied_revision_id: UUID,
    expected_available_revision_id: UUID,
    rules: dict[str, str],
) -> AuthoredContent:
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(repository.workspace, actor_id),
        native_template_operation(),
        ExitStack() as pins,
    ):
        source, enrollment, template = _review(
            repository, content_id, base_commit, base_blob, expected_applied_revision_id, expected_available_revision_id
        )
        pins.enter_context(pin_accepted_repository_for_publication(template.repository_id))
        source, enrollment, template = _review(
            repository, content_id, base_commit, base_blob, expected_applied_revision_id, expected_available_revision_id
        )
        sections = {row["id"]: row for row in _latest(template).manifest["sections"]}
        old = {row["id"]: row for row in enrollment.placement_map}
        if set(rules) != set(sections) | set(old):
            raise NativeTemplateConflict("Review every changed or retained section")
        changes: dict[str, bytes | None] = {}
        mapped: list[dict[str, Any]] = []
        for section_id in [*old, *[value for value in sections if value not in old]]:
            rule, previous, section = rules[section_id], old.get(section_id), sections.get(section_id)
            if rule == "keep":
                if previous is None:
                    raise NativeTemplateConflict("New sections need a resolution mode")
                if section is None and previous["mode"] != "copy":
                    ordinal = next(
                        index for index, row in enumerate(enrollment.placement_map) if row["id"] == section_id
                    )
                    selection = read_native_template_fragment(
                        repository=repository,
                        content_id=content_id,
                        include=parse_content(source.source.encode()).includes[ordinal],
                        allow_removed=True,
                    )
                    if selection is None:
                        raise NativeTemplateConflict("Native enrollment is unavailable")
                    selected, retained_revision = selection
                    mapped.append(
                        _mapped(_record(selected.source_path, selected.source), "copy", retained_revision, changes)
                    )
                else:
                    mapped.append(previous)
            elif section is None:
                raise NativeTemplateConflict("Removed sections must be explicitly retained")
            else:
                mapped.append(_mapped(section, rule, _latest(template), changes))
        enrollment.applied_revision = _latest(template)
        enrollment.placement_map = mapped
        enrollment.save(update_fields=["applied_revision", "placement_map", "updated_at"])
        changes[source.path] = _replace_fields(
            source.source.encode(), {"includes": [_include(item, template.workspace_id) for item in mapped]}, None
        )
        _write(repository, actor_id, request_id, base_commit, changes)
        return read_authored_content(repository=repository, content_id=content_id)


def detach_native_template(
    *,
    repository: WorkspaceRepository,
    actor_id: UUID,
    request_id: UUID | None,
    content_id: UUID,
    base_commit: str,
    base_blob: str,
    expected_applied_revision_id: UUID,
    expected_available_revision_id: UUID,
    section_id: UUID,
) -> AuthoredContent:
    with (
        coordinated_repository_transaction(),
        editable_template_workspace_scope(repository.workspace, actor_id),
        native_template_operation(),
        ExitStack() as pins,
    ):
        source, enrollment, template = _review(
            repository, content_id, base_commit, base_blob, expected_applied_revision_id, expected_available_revision_id
        )
        pins.enter_context(pin_accepted_repository_for_publication(template.repository_id))
        source, enrollment, template = _review(
            repository, content_id, base_commit, base_blob, expected_applied_revision_id, expected_available_revision_id
        )
        includes = parse_content(source.source.encode()).includes
        changes: dict[str, bytes | None] = {}
        for ordinal, item in enumerate(enrollment.placement_map):
            if item["id"] != str(section_id):
                continue
            if item["mode"] == "copy":
                raise NativeTemplateConflict("Section is already an independent copy")
            selection = read_native_template_fragment(
                repository=repository, content_id=content_id, include=includes[ordinal], allow_removed=True
            )
            if selection is None:
                raise NativeTemplateConflict("Native enrollment is unavailable")
            selected, revision = selection
            section = _record(selected.source_path, selected.source)
            enrollment.placement_map[ordinal] = _mapped(section, "copy", revision, changes)
            break
        else:
            raise NativeTemplateConflict("Template section is unavailable")
        enrollment.save(update_fields=["placement_map", "updated_at"])
        changes[source.path] = _replace_fields(
            source.source.encode(),
            {"includes": [_include(item, template.workspace_id) for item in enrollment.placement_map]},
            None,
        )
        _write(repository, actor_id, request_id, base_commit, changes)
        return read_authored_content(repository=repository, content_id=content_id)


def validate_native_template_snapshot(repository: WorkspaceRepository, files: dict[str, bytes]) -> None:
    """Reject unsafe declared source changes before advancing an accepted Git head."""
    from .models import Block

    if repository.workspace.organization_id is not None:
        return
    for content_id in RepositoryTemplate.objects.filter(
        repository=repository, tenant_id=repository.tenant_id
    ).values_list("content_id", flat=True):
        root = _source_for_id(files, content_id)
        if root is None:
            continue
        parsed = parse_content(root[1])
        if parsed.frontmatter.get("properties", {}).get("template") is not True:
            continue
        _independent_body(parsed)
        seen = set()
        for include in parsed.includes:
            selected = _source_for_id(files, include.target_content_id)
            if (
                selected is None
                or include.target_content_id in seen
                or include.mode != "live"
                or include.audience != "shared"
                or include.library_workspace_id is not None
            ):
                raise NativeTemplateConflict("Template sections must be unique native live shared fragments")
            seen.add(include.target_content_id)
            leaf = parse_content(selected[1])
            if (
                leaf.kind != "fragment"
                or Block.objects.filter(
                    id=leaf.content_id, tenant_id=repository.tenant_id, organization=repository.workspace.organization
                ).exists()
            ):
                raise NativeTemplateConflict("Legacy fragments cannot be native template sources")
            _leaf(leaf)


def validate_native_enrollment_shape(repository: WorkspaceRepository, parsed: ParsedContent) -> None:
    """A withdrawn grant never turns malformed or forged includes into valid content."""
    enrollment = native_enrollment(repository, parsed.content_id)
    if enrollment is None:
        return
    expected = [_include(item, UUID(item["workspace_id"])) for item in enrollment.placement_map]
    if parsed.frontmatter.get("includes", []) != expected or parsed.template_sources or parsed.derived_from:
        raise NativeTemplateConflict("Template occurrence does not match its enrollment")
