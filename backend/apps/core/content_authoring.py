"""Compare-and-swap authoring of portable Markdown in one managed repository."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

import yaml

from .content_index import (
    ContentIndexError,
    index_repository_content,
    validate_candidate_snapshot,
)
from .content_profile import ALLOWED_FIELDS, CONTENT_SCHEMA, parse_content
from .models import RepositoryObjectFormat, WorkspaceRepository
from .repository_service import (
    RepositoryAuditAttribution,
    RepositoryConflictError,
    RepositoryFileNotFoundError,
    RepositoryInputError,
    _load_repository,
    _validate_path,
    commit_repository_files,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)

MAX_AUTHORING_SOURCE = 1024 * 1024
EDITABLE_FIELDS = ALLOWED_FIELDS - {"schema", "id", "kind", "aliases"}
TOP_LEVEL_FIELD = re.compile(r"^([a-z][a-z0-9_]*):")
logger = logging.getLogger(__name__)


class ContentAuthoringError(ValueError):
    pass


class ContentAuthoringConflict(ContentAuthoringError):
    def __init__(
        self,
        *,
        reason: str,
        base: str | None,
        current: str | None,
        proposed: str | None,
        base_commit: str | None,
        current_commit: str | None,
        current_blob: str | None,
    ) -> None:
        super().__init__(reason)
        self.payload = {
            "reason": reason,
            "base": base,
            "current": current,
            "proposed": proposed,
            "base_commit": base_commit,
            "current_commit": current_commit,
            "current_blob": current_blob,
        }


@dataclass(frozen=True, slots=True)
class AuthoredContent:
    content_id: uuid.UUID
    path: str
    kind: str
    title: str
    markdown: str
    source: str
    source_blob: str
    accepted_commit: str | None
    indexed_commit: str | None


def _blob(source: bytes, object_format: str) -> str:
    digest = (
        hashlib.sha1(usedforsecurity=False)  # noqa: S324  # nosec B324 -- Git object identity, not authentication
        if object_format == RepositoryObjectFormat.SHA1
        else hashlib.sha256()
    )
    digest.update(f"blob {len(source)}\0".encode())
    digest.update(source)
    return digest.hexdigest()


def _snapshot(repository: WorkspaceRepository) -> tuple[str | None, dict[str, bytes]]:
    repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    if repository.accepted_commit_id is None:
        return None, {}
    commit, files = read_accepted_repository_markdown_files(repository_id=repository.id)
    return commit.object_id, dict(files)


def _source_for_id(files: dict[str, bytes], content_id: uuid.UUID) -> tuple[str, bytes] | None:
    matches = [(path, source) for path, source in files.items() if parse_content(source).content_id == content_id]
    if len(matches) > 1:
        raise ContentAuthoringError("Content identity is ambiguous")
    return matches[0] if matches else None


def _decode(source: bytes | None) -> str | None:
    return source.decode("utf-8") if source is not None else None


def _inline_yaml_comment(line: str) -> str:
    """Find a YAML comment without treating a quoted # as one."""

    quoted: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        character = line[index]
        if quoted == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = None
        elif quoted == "'":
            if character == "'":
                if index + 1 < len(line) and line[index + 1] == "'":
                    index += 1
                else:
                    quoted = None
        elif character in {'"', "'"}:
            quoted = character
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[index:].rstrip("\n")
        index += 1
    return ""


def _replace_fields(source: bytes, replacements: dict[str, Any], markdown: str | None) -> bytes:
    text = source.decode("utf-8")
    boundary = text.find("\n---\n", 4)
    if not text.startswith("---\n") or boundary < 0:
        raise ContentAuthoringError("Content frontmatter is invalid")
    lines = text[4:boundary].splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    for field, value in replacements.items():
        positions = [
            (index, match.group(1)) for index, line in enumerate(lines) if (match := TOP_LEVEL_FIELD.match(line))
        ]
        start = next((index for index, key in positions if key == field), None)
        end = next((index for index, _key in positions if start is not None and index > start), len(lines))
        if value is None:
            replacement: list[str] = []
        elif field == "title":
            replacement = [f"title: {json.dumps(value, ensure_ascii=False)}\n"]
        else:
            replacement = yaml.safe_dump({field: value}, allow_unicode=True, sort_keys=False).splitlines(keepends=True)
        if start is None:
            lines.extend(replacement)
        else:
            # A top-level key owns its YAML value, not the comments and spacing
            # before the next key. Keep standalone comments from the replaced
            # value too, placing them immediately above the new value.
            owned = lines[start:end]
            if field == "title" and replacement:
                if comment := _inline_yaml_comment(owned[0]):
                    replacement[0] = replacement[0].rstrip("\n") + " " + comment + "\n"
            trailing: list[str] = []
            while owned[1:] and (not owned[-1].strip() or owned[-1].startswith("#")):
                trailing.insert(0, owned.pop())
            comments = [line.lstrip() for line in owned[1:] if line.lstrip().startswith("#")]
            lines[start:end] = comments + replacement + trailing
    body = text[boundary + 5 :] if markdown is None else markdown
    encoded = ("---\n" + "".join(lines) + "---\n" + body).encode("utf-8")
    if len(encoded) > MAX_AUTHORING_SOURCE:
        raise ContentAuthoringError("Content exceeds its size limit")
    return encoded


def _validate_patch(patch: dict[str, Any]) -> None:
    if not set(patch) <= EDITABLE_FIELDS or len(patch) > 12:
        raise ContentAuthoringError("Metadata patch contains unsupported fields")
    try:
        json.dumps(patch, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContentAuthoringError("Metadata patch is invalid") from exc


def read_authored_content(*, repository: WorkspaceRepository, content_id: uuid.UUID) -> AuthoredContent:
    accepted, files = _snapshot(repository)
    located = _source_for_id(files, content_id)
    if located is None:
        raise RepositoryFileNotFoundError("Content does not exist")
    path, source = located
    parsed = parse_content(source)
    _repository, _root, _path, object_format = _load_repository(repository.id)
    return AuthoredContent(
        content_id,
        path,
        parsed.kind,
        parsed.title,
        parsed.markdown,
        source.decode("utf-8"),
        _blob(source, object_format),
        accepted,
        repository.indexed_commit.object_id if repository.indexed_commit is not None else None,
    )


def resolve_authored_path(*, repository: WorkspaceRepository, path: str) -> AuthoredContent:
    """Resolve a current path or retained same-repository alias to stable content identity."""

    selected = _validate_path(path)
    _accepted, files = _snapshot(repository)
    matches: list[uuid.UUID] = []
    for current_path, source in files.items():
        parsed = parse_content(source)
        if current_path == selected or selected in parsed.frontmatter.get("aliases", []):
            matches.append(parsed.content_id)
    if len(matches) != 1:
        raise RepositoryFileNotFoundError("Content path is unavailable")
    return read_authored_content(repository=repository, content_id=matches[0])


def author_content(
    *,
    repository: WorkspaceRepository,
    actor_id: uuid.UUID,
    request_id: uuid.UUID | None,
    operation: str,
    content_id: uuid.UUID,
    base_commit: str | None,
    base_blob: str | None,
    kind: str | None,
    path: str | None,
    title: str | None,
    markdown: str | None,
    metadata_patch: dict[str, Any],
) -> AuthoredContent:
    if operation not in {"create", "update", "move"}:
        raise ContentAuthoringError("Authoring operation is unsupported")
    _validate_patch(metadata_patch)
    if title is not None and "title" in metadata_patch:
        raise ContentAuthoringError("Title may be supplied only once")
    current_commit, files = _snapshot(repository)
    if repository.indexed_commit_id != repository.accepted_commit_id and current_commit is not None:
        try:
            index_repository_content(repository_id=repository.id)
        except ContentIndexError as exc:
            raise ContentAuthoringError("Repository indexing must finish before authoring") from exc
        repository.refresh_from_db(fields=("accepted_commit", "indexed_commit"))
    _repository, _root, _path, object_format = _load_repository(repository.id)
    current = _source_for_id(files, content_id)
    if operation == "create":
        if base_commit != current_commit:
            raise ContentAuthoringConflict(
                reason="repository_changed",
                base=None,
                current=None,
                proposed=None,
                base_commit=base_commit,
                current_commit=current_commit,
                current_blob=None,
            )
        if current is not None:
            raise ContentAuthoringError("Content identity already exists")
        if kind not in {"document", "fragment"} or title is None or markdown is None:
            raise ContentAuthoringError("New content needs kind, title and Markdown")
        destination = path or f"{'fragments' if kind == 'fragment' else 'docs'}/{content_id}.md"
        _validate_path(destination)
        if not destination.endswith(".md") or destination in files:
            raise ContentAuthoringError("Content path is unavailable")
        initial = (
            "---\n"
            + f"schema: {CONTENT_SCHEMA}\n"
            + f"id: {content_id}\n"
            + f"kind: {kind}\n"
            + f"title: {json.dumps(title, ensure_ascii=False)}\n"
            + "---\n"
            + markdown
        ).encode()
        proposed = _replace_fields(initial, metadata_patch, None)
        changes: dict[str, bytes | None] = {destination: proposed}
        base_source = None
        current_source = None
    else:
        if base_commit is None or base_blob is None:
            raise ContentAuthoringError("An exact base commit and blob are required")
        if current is None:
            raise ContentAuthoringConflict(
                reason="deleted",
                base=None,
                current=None,
                proposed=None,
                base_commit=base_commit,
                current_commit=current_commit,
                current_blob=None,
            )
        source_path, current_source = current
        try:
            _commit, base_files = read_repository_markdown_files_at_commit(
                repository_id=repository.id, object_id=base_commit
            )
        except (RepositoryFileNotFoundError, RepositoryInputError) as exc:
            raise ContentAuthoringError("Base commit is unavailable") from exc
        base = _source_for_id(dict(base_files), content_id)
        base_source = base[1] if base is not None else None
        if base is None or base_source is None or _blob(base_source, object_format) != base_blob:
            raise ContentAuthoringError("Base blob does not match the selected commit")
        proposed = _replace_fields(
            base_source, {**metadata_patch, **({"title": title} if title is not None else {})}, markdown
        )
        if source_path != base[0] or current_source != base_source:
            raise ContentAuthoringConflict(
                reason="changed",
                base=_decode(base_source),
                current=_decode(current_source),
                proposed=_decode(proposed),
                base_commit=base_commit,
                current_commit=current_commit,
                current_blob=_blob(current_source, object_format),
            )
        destination = source_path
        if operation == "move":
            if path is None:
                raise ContentAuthoringError("Move needs a destination path")
            destination = _validate_path(path)
            if not destination.endswith(".md") or (destination != source_path and destination in files):
                raise ContentAuthoringError("Content path is unavailable")
            aliases = list(parse_content(base_source).frontmatter.get("aliases", []))
            aliases = [alias for alias in aliases if alias != destination]
            if destination != source_path and source_path not in aliases:
                aliases.append(source_path)
            proposed = _replace_fields(proposed, {"aliases": aliases or None}, None)
        changes = {destination: proposed}
        if destination != source_path:
            changes[source_path] = None
    candidate = dict(files)
    for changed_path, changed_source in changes.items():
        if changed_source is None:
            candidate.pop(changed_path, None)
        else:
            candidate[changed_path] = changed_source
    validate_candidate_snapshot(repository=repository, files=tuple(sorted(candidate.items())))
    try:
        result = commit_repository_files(
            repository_id=repository.id,
            expected_base=current_commit,
            changes=changes,
            message=f"{operation.capitalize()} {content_id}",
            attribution=RepositoryAuditAttribution(
                actor_id=actor_id, action=f"content.{operation}", request_id=request_id
            ),
        )
    except RepositoryConflictError as exc:
        latest_commit, latest_files = _snapshot(repository)
        latest = _source_for_id(latest_files, content_id)
        latest_source = latest[1] if latest else None
        raise ContentAuthoringConflict(
            reason="repository_changed",
            base=_decode(base_source),
            current=_decode(latest_source),
            proposed=_decode(proposed),
            base_commit=base_commit,
            current_commit=latest_commit,
            current_blob=_blob(latest_source, object_format) if latest_source is not None else None,
        ) from exc
    if result.created:
        try:
            index_repository_content(repository_id=repository.id)
        except ContentIndexError:
            logger.exception("managed_content_index_pending repository=%s", repository.id)
    return read_authored_content(repository=repository, content_id=content_id)
