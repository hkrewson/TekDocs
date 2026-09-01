from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.accounts.models import User

from .diagram_exports import DiagramExportArtifact
from .document_exports import export_docx, export_html, export_pdf, resolve_export_snapshot
from .documents import resolve_document
from .models import (
    AuditEvent,
    BlockRevision,
    Document,
    DocumentationMap,
    DocumentationMapAudience,
    DocumentationMapBaseline,
    DocumentationMapEntry,
    DocumentationMapEntryKind,
    DocumentationMapRevision,
    DocumentationMapType,
    DocumentPublication,
    DocumentPublicationArtifact,
    DocumentPublicationControlEvent,
    DocumentReviewState,
    Entity,
    PublicationAudience,
    PublicationControlAction,
)
from .preflight import run_map_preflight
from .publications import read_publication_artifact
from .rendering import attachment_ids_in_markdown
from .topic_schemas import inspect_markdown
from .workspaces import ResolvedWorkspace

MAP_FORMAT = "tekdocs-documentation-map/v1"
BASELINE_FORMAT = "tekdocs-documentation-map-baseline/v1"
MAX_MAP_ENTRIES = 250
MAX_BASELINE_ENTRIES = 500
MAX_BASELINE_BYTES = 100 * 1024 * 1024
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class MapRevisionConflict(APIException):
    status_code = 409
    default_detail = "The documentation map changed after this editor loaded."
    default_code = "revision_conflict"


@dataclass(frozen=True, slots=True)
class MapFinding:
    code: str
    severity: str
    entry_id: UUID | None
    detail: str


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _entries(revision: DocumentationMapRevision) -> QuerySet[DocumentationMapEntry]:
    return revision.entries.select_related(
        "parent",
        "document__entity",
        "document_revision__block__source_document__entity",
        "publication__entity",
        "publication__document__entity",
        "subordinate_map__entity",
        "subordinate_map__current_revision",
    ).order_by("parent_id", "position", "id")


def ordered_map_entries(revision: DocumentationMapRevision) -> list[DocumentationMapEntry]:
    """Return the immutable entry tree in stable, accessible reading order."""

    records = list(_entries(revision))
    children: dict[UUID | None, list[DocumentationMapEntry]] = {}
    for entry in records:
        children.setdefault(entry.parent_id, []).append(entry)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.position, str(item.id)))
    ordered: list[DocumentationMapEntry] = []

    def append(parent_id: UUID | None) -> None:
        for entry in children.get(parent_id, []):
            ordered.append(entry)
            append(entry.id)

    append(None)
    return ordered


def maps_for_workspace(workspace: ResolvedWorkspace, *, include_archived: bool = False) -> QuerySet[DocumentationMap]:
    records = DocumentationMap.objects.filter(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
    )
    if not include_archived:
        records = records.filter(archived_at__isnull=True)
    revisions = DocumentationMapRevision.objects.select_related("created_by").prefetch_related(
        Prefetch("entries", queryset=DocumentationMapEntry.objects.order_by("parent_id", "position", "id"))
    )
    return records.select_related(
        "entity", "owner", "current_revision", "current_revision__created_by"
    ).prefetch_related(Prefetch("revisions", queryset=revisions), "baselines__created_by")


def map_for_workspace(workspace: ResolvedWorkspace, entity_id: UUID) -> DocumentationMap:
    try:
        return maps_for_workspace(workspace).get(entity_id=entity_id)
    except DocumentationMap.DoesNotExist as exc:
        raise NotFound("The selected documentation map is unavailable in this Workspace.") from exc


def _safe_external_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValidationError({"entries": "External map resources must use a plain public HTTPS URL."})
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValidationError({"entries": "External map resources cannot target private or local addresses."})
    if parsed.port not in (None, 443):
        raise ValidationError({"entries": "External map resources must use the standard HTTPS port."})
    return value.strip()


def _approved_current(publication: DocumentPublication) -> bool:
    approved = DocumentPublicationControlEvent.objects.filter(
        publication=publication, action=PublicationControlAction.APPROVED
    ).exists()
    withdrawn = DocumentPublicationControlEvent.objects.filter(
        publication=publication, action=PublicationControlAction.WITHDRAWN
    ).exists()
    superseded = DocumentPublicationControlEvent.objects.filter(
        publication__supersedes=publication, action=PublicationControlAction.APPROVED
    ).exists()
    return approved and not withdrawn and not superseded


def _target_payload(entry: dict[str, Any]) -> dict[str, str | None]:
    return {
        "document_id": str(entry.get("document_id")) if entry.get("document_id") else None,
        "document_revision_id": str(entry.get("document_revision_id")) if entry.get("document_revision_id") else None,
        "publication_id": str(entry.get("publication_id")) if entry.get("publication_id") else None,
        "map_id": str(entry.get("map_id")) if entry.get("map_id") else None,
        "external_url": str(entry.get("external_url") or ""),
    }


def _revision_contract(
    *, title: str, purpose: str, map_type: str, audience: str, entries: list[dict[str, Any]]
) -> dict[str, object]:
    normalized = []
    for index, entry in enumerate(entries):
        normalized.append(
            {
                "index": index,
                "parent_index": entry.get("parent_index"),
                "position": int(entry.get("position", index)),
                "kind": str(entry["kind"]),
                "label": str(entry.get("label") or "").strip(),
                **_target_payload(entry),
            }
        )
    return {
        "format": MAP_FORMAT,
        "title": title.strip(),
        "purpose": purpose.strip(),
        "map_type": map_type,
        "audience": audience,
        "entries": normalized,
    }


def _resolve_targets(
    *, workspace: ResolvedWorkspace, audience: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(entries) > MAX_MAP_ENTRIES:
        raise ValidationError({"entries": f"A map may contain at most {MAX_MAP_ENTRIES} entries."})
    resolved: list[dict[str, Any]] = []
    seen_positions: set[tuple[int | None, int]] = set()
    seen_targets: set[tuple[int | None, str, str]] = set()
    for index, raw in enumerate(entries):
        entry = dict(raw)
        parent_index = entry.get("parent_index")
        if parent_index is not None and (
            not isinstance(parent_index, int) or parent_index < 0 or parent_index >= index
        ):
            raise ValidationError({"entries": "Every parent must precede its child in the submitted order."})
        position = int(entry.get("position", index))
        position_key = (parent_index, position)
        if position_key in seen_positions:
            raise ValidationError({"entries": "Sibling entry positions must be unique."})
        seen_positions.add(position_key)
        kind = str(entry.get("kind") or "")
        targets = _target_payload(entry)
        target_values = [value for value in targets.values() if value]
        expected_target_count = 2 if kind == DocumentationMapEntryKind.DOCUMENT_REVISION else 1
        if len(target_values) != expected_target_count or kind not in DocumentationMapEntryKind.values:
            raise ValidationError({"entries": "Each entry must name exactly one supported target."})
        target_identity = "|".join(target_values)
        duplicate_key = (parent_index, kind, target_identity)
        if duplicate_key in seen_targets:
            raise ValidationError({"entries": "The same target cannot appear twice under one map heading."})
        seen_targets.add(duplicate_key)

        if kind in {DocumentationMapEntryKind.DOCUMENT, DocumentationMapEntryKind.DOCUMENT_REVISION}:
            try:
                document = Document.objects.select_related("entity").get(
                    tenant=workspace.member.tenant,
                    organization=workspace.organization,
                    entity__workspace_id=workspace.data_scope.workspace_id,
                    entity_id=cast(UUID, entry.get("document_id")),
                    archived_at__isnull=True,
                )
            except Document.DoesNotExist as exc:
                raise ValidationError({"entries": "A selected document is unavailable in this Workspace."}) from exc
            entry["document"] = document
            if kind == DocumentationMapEntryKind.DOCUMENT_REVISION:
                try:
                    revision = BlockRevision.objects.select_related("block__source_document").get(
                        id=cast(UUID, entry.get("document_revision_id")),
                        tenant=workspace.member.tenant,
                        organization=workspace.organization,
                        block__source_document=document,
                    )
                except BlockRevision.DoesNotExist as exc:
                    raise ValidationError({"entries": "A selected document revision is unavailable."}) from exc
                entry["document_revision"] = revision
        elif kind == DocumentationMapEntryKind.PUBLICATION:
            try:
                publication = DocumentPublication.objects.select_related("entity", "document__entity").get(
                    tenant=workspace.member.tenant,
                    organization=workspace.organization,
                    document__entity__workspace_id=workspace.data_scope.workspace_id,
                    entity_id=cast(UUID, entry.get("publication_id")),
                )
            except DocumentPublication.DoesNotExist as exc:
                raise ValidationError({"entries": "A selected publication is unavailable in this Workspace."}) from exc
            entry["publication"] = publication
        elif kind == DocumentationMapEntryKind.MAP:
            try:
                subordinate = DocumentationMap.objects.select_related("entity", "current_revision").get(
                    tenant=workspace.member.tenant,
                    organization=workspace.organization,
                    workspace_id=workspace.data_scope.workspace_id,
                    entity_id=cast(UUID, entry.get("map_id")),
                    archived_at__isnull=True,
                )
            except DocumentationMap.DoesNotExist as exc:
                raise ValidationError({"entries": "A selected subordinate map is unavailable."}) from exc
            entry["subordinate_map"] = subordinate
        else:
            entry["external_url"] = _safe_external_url(str(entry.get("external_url") or ""))

        if audience == DocumentationMapAudience.CLIENT_VISIBLE:
            selected_publication = cast(DocumentPublication | None, entry.get("publication"))
            selected_subordinate = cast(DocumentationMap | None, entry.get("subordinate_map"))
            if selected_publication is not None:
                if selected_publication.audience != PublicationAudience.CLIENT_VISIBLE or not _approved_current(
                    selected_publication
                ):
                    raise ValidationError(
                        {"entries": "Client-visible maps require approved current client publications."}
                    )
            elif selected_subordinate is not None:
                if (
                    selected_subordinate.current_revision is None
                    or selected_subordinate.current_revision.audience != DocumentationMapAudience.CLIENT_VISIBLE
                ):
                    raise ValidationError(
                        {"entries": "Client-visible maps may include only client-visible subordinate maps."}
                    )
            else:
                raise ValidationError(
                    {"entries": "Client-visible maps may contain only approved publications or client maps."}
                )
        resolved.append(entry)
    return resolved


def _assert_no_map_cycle(documentation_map: DocumentationMap | None, entries: list[dict[str, Any]]) -> None:
    root_id = documentation_map.id if documentation_map is not None else None
    child_ids = {entry["subordinate_map"].id for entry in entries if entry.get("subordinate_map") is not None}
    if root_id is not None and root_id in child_ids:
        raise ValidationError({"entries": "A documentation map cannot include itself."})

    def descendants(map_id: UUID, path: set[UUID]) -> None:
        if root_id is not None and map_id == root_id:
            raise ValidationError({"entries": "The subordinate map selection would create a cycle."})
        if map_id in path:
            raise ValidationError({"entries": "The subordinate map selection contains a cycle."})
        record = DocumentationMap.objects.select_related("current_revision").get(pk=map_id)
        if record.current_revision_id is None:
            return
        nested = DocumentationMapEntry.objects.filter(
            revision_id=record.current_revision_id,
            kind=DocumentationMapEntryKind.MAP,
            subordinate_map__isnull=False,
        ).values_list("subordinate_map_id", flat=True)
        for nested_id in nested:
            descendants(nested_id, path | {map_id})

    for child_id in child_ids:
        descendants(child_id, set())


def _create_revision(
    *,
    workspace: ResolvedWorkspace,
    actor: User,
    documentation_map: DocumentationMap,
    title: str,
    purpose: str,
    map_type: str,
    audience: str,
    entries: list[dict[str, Any]],
    parent: DocumentationMapRevision | None,
) -> DocumentationMapRevision:
    if map_type not in DocumentationMapType.values or audience not in DocumentationMapAudience.values:
        raise ValidationError("The selected map type or audience is unsupported.")
    if audience == DocumentationMapAudience.CLIENT_VISIBLE and workspace.organization is None:
        raise ValidationError({"audience": "An MSP-wide map cannot be client visible."})
    resolved = _resolve_targets(workspace=workspace, audience=audience, entries=entries)
    _assert_no_map_cycle(documentation_map, resolved)
    contract = _revision_contract(title=title, purpose=purpose, map_type=map_type, audience=audience, entries=entries)
    revision = DocumentationMapRevision.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        documentation_map=documentation_map,
        parent=parent,
        revision_number=1 if parent is None else parent.revision_number + 1,
        title=title.strip(),
        purpose=purpose.strip(),
        map_type=map_type,
        audience=audience,
        content_digest=_digest(contract),
        created_by=actor,
    )
    created: list[DocumentationMapEntry] = []
    for index, entry in enumerate(resolved):
        parent_index = entry.get("parent_index")
        created.append(
            DocumentationMapEntry.objects.create(
                tenant=workspace.member.tenant,
                workspace_id=workspace.data_scope.workspace_id,
                organization=workspace.organization,
                revision=revision,
                parent=created[parent_index] if parent_index is not None else None,
                position=int(entry.get("position", index)),
                kind=entry["kind"],
                label=str(entry.get("label") or "").strip(),
                document=entry.get("document"),
                document_revision=entry.get("document_revision"),
                publication=entry.get("publication"),
                subordinate_map=entry.get("subordinate_map"),
                external_url=entry.get("external_url", ""),
            )
        )
    return revision


@transaction.atomic
def create_map(
    *,
    workspace: ResolvedWorkspace,
    actor: User,
    title: str,
    purpose: str,
    map_type: str,
    audience: str,
    owner_id: UUID | None,
    entries: list[dict[str, Any]],
) -> DocumentationMap:
    membership = (
        workspace.member.tenant.memberships.filter(user_id=owner_id).select_related("user").first()
        if owner_id
        else None
    )
    if owner_id and membership is None:
        raise ValidationError({"owner_id": "The selected owner is unavailable."})
    owner = membership.user if membership else None
    entity = Entity.objects.create_owned(  # type: ignore[no-untyped-call]
        tenant=workspace.member.tenant,
        organization=workspace.organization,
        entity_type="documentation_map",
        display_name=title.strip(),
    )
    record = DocumentationMap.objects.create(
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        entity=entity,
        owner=owner,
    )
    revision = _create_revision(
        workspace=workspace,
        actor=actor,
        documentation_map=record,
        title=title,
        purpose=purpose,
        map_type=map_type,
        audience=audience,
        entries=entries,
        parent=None,
    )
    record.current_revision = revision
    record.save(update_fields=("current_revision", "updated_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="documentation_map.created",
        entity_id=entity.id,
        metadata={"revision_id": str(revision.id), "entry_count": len(entries)},
    )
    return map_for_workspace(workspace, entity.id)


@transaction.atomic
def update_map(
    *,
    workspace: ResolvedWorkspace,
    actor: User,
    documentation_map: DocumentationMap,
    expected_revision_id: UUID,
    title: str,
    purpose: str,
    map_type: str,
    audience: str,
    owner_id: UUID | None,
    entries: list[dict[str, Any]],
) -> DocumentationMap:
    locked = (
        DocumentationMap.objects.select_for_update(of=("self",))
        .select_related("entity", "current_revision")
        .get(pk=documentation_map.pk)
    )
    if locked.current_revision_id != expected_revision_id:
        raise MapRevisionConflict()
    membership = (
        workspace.member.tenant.memberships.filter(user_id=owner_id).select_related("user").first()
        if owner_id
        else None
    )
    if owner_id and membership is None:
        raise ValidationError({"owner_id": "The selected owner is unavailable."})
    owner = membership.user if membership else None
    revision = _create_revision(
        workspace=workspace,
        actor=actor,
        documentation_map=locked,
        title=title,
        purpose=purpose,
        map_type=map_type,
        audience=audience,
        entries=entries,
        parent=locked.current_revision,
    )
    locked.current_revision = revision
    locked.owner = owner
    locked.review_state = DocumentReviewState.UNREVIEWED
    locked.entity.display_name = title.strip()
    locked.entity.save(update_fields=("display_name", "updated_at"))
    locked.save(update_fields=("current_revision", "owner", "review_state", "updated_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="documentation_map.revised",
        entity_id=locked.entity_id,
        metadata={"revision_id": str(revision.id), "entry_count": len(entries)},
    )
    return map_for_workspace(workspace, locked.entity_id)


@transaction.atomic
def review_map(
    *, workspace: ResolvedWorkspace, actor: User, documentation_map: DocumentationMap, state: str
) -> DocumentationMap:
    if state not in {DocumentReviewState.APPROVED, DocumentReviewState.CHANGES_REQUESTED}:
        raise ValidationError({"state": "Choose approved or changes requested."})
    locked = DocumentationMap.objects.select_for_update().get(pk=documentation_map.pk)
    locked.review_state = state
    locked.save(update_fields=("review_state", "updated_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action=f"documentation_map.{state}",
        entity_id=locked.entity_id,
        metadata={"revision_id": str(locked.current_revision_id)},
    )
    return map_for_workspace(workspace, locked.entity_id)


@transaction.atomic
def archive_map(*, workspace: ResolvedWorkspace, actor: User, documentation_map: DocumentationMap) -> None:
    locked = DocumentationMap.objects.select_for_update().get(pk=documentation_map.pk)
    if (
        DocumentationMapEntry.objects.filter(
            subordinate_map=locked, revision__documentation_map__archived_at__isnull=True
        )
        .exclude(revision__documentation_map=locked)
        .exists()
    ):
        raise ValidationError("A map included by another active map cannot be archived.")
    locked.archived_at = timezone.now()
    locked.entity.archived_at = locked.archived_at
    locked.entity.save(update_fields=("archived_at", "updated_at"))
    locked.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="documentation_map.archived",
        entity_id=locked.entity_id,
        metadata={},
    )


def _finding(code: str, severity: str, entry: DocumentationMapEntry | None, detail: str) -> MapFinding:
    return MapFinding(code=code, severity=severity, entry_id=entry.id if entry else None, detail=detail)


def inspect_map(documentation_map: DocumentationMap) -> list[MapFinding]:
    revision = documentation_map.current_revision
    if revision is None:
        return [_finding("missing_revision", "blocker", None, "The map has no current revision.")]
    findings: list[MapFinding] = []
    for entry in ordered_map_entries(revision):
        if entry.kind == DocumentationMapEntryKind.DOCUMENT and entry.document is not None:
            if entry.document.archived_at is not None:
                findings.append(_finding("archived_document", "blocker", entry, "The document is archived."))
            if entry.document.owner_id is None:
                findings.append(_finding("unowned_document", "warning", entry, "The document has no owner."))
            if entry.document.review_state != DocumentReviewState.APPROVED:
                findings.append(_finding("unreviewed_document", "warning", entry, "The document is not approved."))
            resolved_markdown = resolve_document(entry.document).markdown
            for topic_finding in inspect_markdown(entry.document.topic_type, resolved_markdown):
                severity = str(topic_finding["severity"])
                section_id = topic_finding.get("section_id")
                findings.append(
                    _finding(
                        str(topic_finding["code"]),
                        severity,
                        entry,
                        f"The structured document has an incomplete {section_id or 'section'} contract.",
                    )
                )
        elif entry.kind == DocumentationMapEntryKind.PUBLICATION and entry.publication is not None:
            if not _approved_current(entry.publication):
                findings.append(
                    _finding(
                        "unavailable_publication",
                        "blocker",
                        entry,
                        "The publication is withdrawn, superseded, or unapproved.",
                    )
                )
        elif entry.kind == DocumentationMapEntryKind.MAP and entry.subordinate_map is not None:
            if entry.subordinate_map.archived_at is not None or entry.subordinate_map.current_revision_id is None:
                findings.append(
                    _finding("unavailable_subordinate_map", "blocker", entry, "The subordinate map is unavailable.")
                )
    return sorted(findings, key=lambda item: (item.severity != "blocker", item.code, str(item.entry_id or "")))


def _zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            info.create_system = 3
            archive.writestr(info, files[path])
    return output.getvalue()


def _entry_title(entry: DocumentationMapEntry) -> str:
    if entry.label:
        return entry.label
    if entry.document is not None:
        return entry.document.entity.display_name
    if entry.publication is not None:
        return entry.publication.title
    if entry.subordinate_map is not None:
        return entry.subordinate_map.entity.display_name
    return entry.external_url


def _file(files: dict[str, bytes], path: str, content: bytes, media_type: str) -> dict[str, object]:
    files[path] = content
    return {
        "path": path,
        "media_type": media_type,
        "size": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
    }


def _publication_files(
    *, entry: DocumentationMapEntry, prefix: str, files: dict[str, bytes], formats: set[str]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    publication = entry.publication
    if publication is None:
        raise ValidationError("The publication entry is unavailable.")
    descriptors = [
        _file(files, f"{prefix}/document.md", publication.canonical_markdown.encode(), "text/markdown; charset=utf-8"),
        _file(files, f"{prefix}/document.html", publication.sanitized_html.encode(), "text/html; charset=utf-8"),
    ]
    for artifact in DocumentPublicationArtifact.objects.filter(publication=publication).order_by("kind", "id"):
        if artifact.kind == "pdf" and "pdf" not in formats:
            continue
        content = read_publication_artifact(artifact)
        safe_name = PurePosixPath(artifact.original_filename).name
        descriptors.append(
            _file(files, f"{prefix}/artifacts/{artifact.kind}-{artifact.id}-{safe_name}", content, artifact.media_type)
        )
    if "docx" in formats:
        descriptors.append(
            _file(
                files,
                f"{prefix}/document.docx",
                export_docx(title=_entry_title(entry), markdown=publication.canonical_markdown),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        )
    return descriptors, {
        "kind": entry.kind,
        "source_id": str(publication.entity_id),
        "source_digest": publication.content_digest,
        "title": _entry_title(entry),
        "audience": publication.audience,
    }


def _document_files(
    *,
    workspace: ResolvedWorkspace,
    entry: DocumentationMapEntry,
    prefix: str,
    files: dict[str, bytes],
    formats: set[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    document = entry.document
    if document is None:
        raise ValidationError("The document entry is unavailable.")
    if entry.kind == DocumentationMapEntryKind.DOCUMENT_REVISION:
        revision = entry.document_revision
        if revision is None:
            raise ValidationError("The selected document revision is unavailable.")
        markdown = revision.markdown
        html = export_html(title=_entry_title(entry), markdown=markdown)
        diagrams: tuple[DiagramExportArtifact, ...] = ()
        source_digest = revision.checksum
        snapshot_manifest: dict[str, object] = {
            "document_id": str(document.entity_id),
            "revision_id": str(revision.id),
            "revision_number": revision.revision_number,
        }
    else:
        referenced = tuple(sorted(attachment_ids_in_markdown(resolve_document(document).markdown)))
        snapshot = resolve_export_snapshot(workspace=workspace, document=document, attachment_ids=referenced)
        markdown = snapshot.markdown
        html = export_html(title=snapshot.title, markdown=markdown, retained_html=snapshot.sanitized_html)
        diagrams = snapshot.diagrams
        source_digest = snapshot.digest
        snapshot_manifest = snapshot.manifest
    descriptors = [
        _file(files, f"{prefix}/document.md", markdown.encode(), "text/markdown; charset=utf-8"),
        _file(files, f"{prefix}/document.html", html, "text/html; charset=utf-8"),
    ]
    if "pdf" in formats:
        descriptors.append(
            _file(
                files,
                f"{prefix}/document.pdf",
                export_pdf(title=_entry_title(entry), markdown=markdown, diagrams=diagrams),
                "application/pdf",
            )
        )
    if "docx" in formats:
        descriptors.append(
            _file(
                files,
                f"{prefix}/document.docx",
                export_docx(title=_entry_title(entry), markdown=markdown, diagrams=diagrams),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        )
    return descriptors, {
        "kind": entry.kind,
        "source_id": str(document.entity_id),
        "source_digest": source_digest,
        "title": _entry_title(entry),
        "snapshot": snapshot_manifest,
    }


def _collect_baseline(
    *,
    workspace: ResolvedWorkspace,
    documentation_map: DocumentationMap,
    revision: DocumentationMapRevision,
    files: dict[str, bytes],
    formats: set[str],
    visited: set[UUID],
    base_path: str = "entries",
) -> list[dict[str, object]]:
    if documentation_map.id in visited:
        raise ValidationError("The documentation map contains a cycle.")
    visited = visited | {documentation_map.id}
    records = ordered_map_entries(revision)
    if len(records) > MAX_BASELINE_ENTRIES:
        raise ValidationError(f"A baseline may resolve at most {MAX_BASELINE_ENTRIES} entries.")
    indexes = {entry.id: index for index, entry in enumerate(records)}
    results: list[dict[str, object]] = []
    for index, entry in enumerate(records):
        prefix = f"{base_path}/{index:03d}-{entry.id}"
        descriptor: dict[str, object] = {
            "entry_id": str(entry.id),
            "parent_index": indexes.get(entry.parent_id) if entry.parent_id is not None else None,
            "position": entry.position,
            "title": _entry_title(entry),
            "kind": entry.kind,
        }
        if entry.kind in {DocumentationMapEntryKind.DOCUMENT, DocumentationMapEntryKind.DOCUMENT_REVISION}:
            item_files, source = _document_files(
                workspace=workspace, entry=entry, prefix=prefix, files=files, formats=formats
            )
            descriptor.update(source)
            descriptor["files"] = item_files
        elif entry.kind == DocumentationMapEntryKind.PUBLICATION:
            item_files, source = _publication_files(entry=entry, prefix=prefix, files=files, formats=formats)
            descriptor.update(source)
            descriptor["files"] = item_files
        elif entry.kind == DocumentationMapEntryKind.MAP:
            subordinate = entry.subordinate_map
            if subordinate is None or subordinate.current_revision is None:
                raise ValidationError("The subordinate map is unavailable.")
            descriptor["source_id"] = str(subordinate.entity_id)
            descriptor["source_revision_id"] = str(subordinate.current_revision_id)
            descriptor["source_digest"] = subordinate.current_revision.content_digest
            descriptor["entries"] = _collect_baseline(
                workspace=workspace,
                documentation_map=subordinate,
                revision=subordinate.current_revision,
                files=files,
                formats=formats,
                visited=visited,
                base_path=f"{prefix}/entries",
            )
        else:
            descriptor["url"] = entry.external_url
        results.append(descriptor)
    return results


@transaction.atomic
def create_baseline(
    *,
    workspace: ResolvedWorkspace,
    actor: User,
    documentation_map: DocumentationMap,
    expected_revision_id: UUID,
    formats: set[str],
) -> DocumentationMapBaseline:
    if not formats.issubset({"pdf", "docx"}):
        raise ValidationError({"formats": "Only PDF and DOCX supplemental output is supported."})
    locked = (
        DocumentationMap.objects.select_for_update(of=("self",))
        .select_related("entity", "current_revision")
        .get(pk=documentation_map.pk)
    )
    if locked.current_revision_id != expected_revision_id or locked.current_revision is None:
        raise MapRevisionConflict("The map changed before the baseline lock was acquired.")
    preflight = run_map_preflight(documentation_map=locked, findings=inspect_map(locked))
    blockers = [finding for finding in preflight["findings"] if finding.severity == "blocker"]
    if blockers:
        raise ValidationError({"map": blockers[0].detail})
    if (
        locked.current_revision.audience == DocumentationMapAudience.CLIENT_VISIBLE
        and locked.review_state != DocumentReviewState.APPROVED
    ):
        raise ValidationError({"map": "A client-visible map must be approved before baselining."})

    captured_at = timezone.now()
    files: dict[str, bytes] = {}
    entries = _collect_baseline(
        workspace=workspace,
        documentation_map=locked,
        revision=locked.current_revision,
        files=files,
        formats=formats,
        visited=set(),
    )
    toc_lines = [f"# {locked.current_revision.title}", "", locked.current_revision.purpose, "", "## Contents", ""]
    toc_html = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>',
        escape(locked.current_revision.title),
        "</title></head><body><main><h1>",
        escape(locked.current_revision.title),
        '</h1><nav aria-label="Documentation map contents"><ol>',
    ]

    def toc_items(items: list[dict[str, object]], base_depth: int = 0):  # type: ignore[no-untyped-def]
        for item in items:
            depth = base_depth
            parent_index = item.get("parent_index")
            while isinstance(parent_index, int):
                depth += 1
                parent_index = items[parent_index].get("parent_index")
            yield item, depth
            nested = item.get("entries")
            if isinstance(nested, list):
                yield from toc_items(nested, depth + 1)

    for item, depth in toc_items(entries):
        toc_lines.append(f"{'  ' * depth}- {item['title']}")
        href = ""
        item_files = item.get("files")
        if isinstance(item_files, list):
            for descriptor in item_files:
                if isinstance(descriptor, dict) and str(descriptor.get("path", "")).endswith("document.html"):
                    href = str(descriptor["path"])
                    break
        if not href and item.get("kind") == DocumentationMapEntryKind.EXTERNAL:
            href = str(item.get("url", ""))
        label = escape(str(item["title"]))
        toc_html.extend(
            [
                f'<li style="margin-left:{depth * 1.25}rem">',
                f'<a href="{escape(href, quote=True)}">{label}</a>' if href else label,
                "</li>",
            ]
        )
    toc_html.append("</ol></nav></main></body></html>")
    _file(files, "index.md", ("\n".join(toc_lines).rstrip() + "\n").encode(), "text/markdown; charset=utf-8")
    _file(files, "index.html", "".join(toc_html).encode(), "text/html; charset=utf-8")
    manifest: dict[str, object] = {
        "format": BASELINE_FORMAT,
        "map_id": str(locked.entity_id),
        "map_revision_id": str(locked.current_revision_id),
        "map_revision_number": locked.current_revision.revision_number,
        "map_digest": locked.current_revision.content_digest,
        "title": locked.current_revision.title,
        "purpose": locked.current_revision.purpose,
        "map_type": locked.current_revision.map_type,
        "audience": locked.current_revision.audience,
        "workspace": {
            "kind": workspace.kind,
            "id": str(workspace.organization.entity_id) if workspace.organization else None,
        },
        "created_by": str(actor.id),
        "created_at": captured_at.isoformat(),
        "formats": sorted(formats),
        "entries": entries,
        "files": [
            {"path": path, "size": len(content), "checksum": hashlib.sha256(content).hexdigest()}
            for path, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = _canonical_json(manifest) + b"\n"
    content = _zip(files)
    if len(content) > MAX_BASELINE_BYTES:
        raise ValidationError("The retained map baseline exceeds 100 MiB.")
    baseline = DocumentationMapBaseline(
        id=uuid4(),
        tenant=workspace.member.tenant,
        workspace_id=workspace.data_scope.workspace_id,
        organization=workspace.organization,
        documentation_map=locked,
        revision=locked.current_revision,
        manifest=manifest,
        content_digest=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        created_by=actor,
    )
    baseline.artifact.save("bundle.zip", ContentFile(content), save=False)
    baseline.save()  # type: ignore[no-untyped-call]
    AuditEvent.objects.create(
        tenant=workspace.member.tenant,
        actor=actor,
        action="documentation_map.baseline_created",
        entity_id=locked.entity_id,
        metadata={"baseline_id": str(baseline.id), "revision_id": str(locked.current_revision_id)},
    )
    return baseline


def read_baseline(baseline: DocumentationMapBaseline) -> bytes:
    with baseline.artifact.open("rb") as source:
        content = source.read(MAX_BASELINE_BYTES + 1)
    if len(content) > MAX_BASELINE_BYTES or hashlib.sha256(content).hexdigest() != baseline.content_digest:
        raise ValidationError("The retained map baseline failed its integrity check.")
    return bytes(content)


def portal_maps_for_organization(organization_id: UUID) -> QuerySet[DocumentationMapBaseline]:
    return DocumentationMapBaseline.objects.filter(
        organization_id=organization_id,
        revision__audience=DocumentationMapAudience.CLIENT_VISIBLE,
        documentation_map__review_state=DocumentReviewState.APPROVED,
        documentation_map__archived_at__isnull=True,
    ).select_related("documentation_map__entity", "revision", "created_by")


def portal_baseline_is_current(baseline: DocumentationMapBaseline) -> bool:
    """Re-check every published dependency before exposing a retained map in the portal."""

    visited: set[UUID] = set()

    def current(documentation_map: DocumentationMap, revision: DocumentationMapRevision) -> bool:
        if documentation_map.id in visited:
            return False
        visited.add(documentation_map.id)
        for entry in ordered_map_entries(revision):
            if entry.kind == DocumentationMapEntryKind.PUBLICATION:
                if entry.publication is None or not _approved_current(entry.publication):
                    return False
            elif entry.kind == DocumentationMapEntryKind.MAP:
                subordinate = entry.subordinate_map
                if (
                    subordinate is None
                    or subordinate.archived_at is not None
                    or subordinate.review_state != DocumentReviewState.APPROVED
                    or subordinate.current_revision is None
                    or subordinate.current_revision.audience != DocumentationMapAudience.CLIENT_VISIBLE
                    or not current(subordinate, subordinate.current_revision)
                ):
                    return False
            else:
                return False
        return True

    documentation_map = baseline.documentation_map
    return (
        documentation_map.archived_at is None
        and documentation_map.review_state == DocumentReviewState.APPROVED
        and documentation_map.current_revision_id == baseline.revision_id
        and current(documentation_map, baseline.revision)
    )
