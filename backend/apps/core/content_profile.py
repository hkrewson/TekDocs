"""Version 1 canonical Markdown/frontmatter profile and bounded wikilink parser."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import yaml
from markdown_it import MarkdownIt
from yaml.constructor import ConstructorError

from .content_index_models import ContentNodeKind
from .topic_schemas import SCHEMA_VERSION, SCHEMAS, inspect_markdown

CONTENT_SCHEMA = "tekdocs.content/v1"
MAX_FRONTMATTER_BYTES = 64 * 1024
MAX_FRONTMATTER_DEPTH = 8
MAX_FRONTMATTER_NODES = 512
MAX_LINKS = 256
MAX_PROPERTIES = 64
MAX_INCLUDES = 128
MAX_TEMPLATE_SOURCES = 128
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")
FRAGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,119}$")
GIT_OBJECT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
WIKILINK_PATTERN = re.compile(
    r"\[\[(?P<target>[0-9a-fA-F-]{36})(?:#(?P<fragment>[a-z][a-z0-9_-]{0,119}))?"
    r"(?:\|(?P<label>[^\]\r\n]{1,240}))?\]\]"
)
ALLOWED_FIELDS = frozenset(
    {
        "schema",
        "id",
        "kind",
        "title",
        "topic",
        "taxonomies",
        "properties",
        "includes",
        "derived_from",
        "template_sources",
    }
)
INCLUDE_MODES = frozenset({"live", "pinned"})
AUDIENCE_PROFILES = frozenset({"shared", "msp_internal", "client_visible"})


class ContentProfileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping", node.start_mark, "duplicate key", key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


@dataclass(frozen=True, slots=True)
class ParsedLink:
    target_content_id: uuid.UUID
    fragment: str
    label: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class ParsedInclude:
    target_content_id: uuid.UUID
    mode: str
    audience: str
    pinned_object_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class ParsedContentReference:
    content_id: uuid.UUID
    object_id: str


@dataclass(frozen=True, slots=True)
class ParsedTemplateSource:
    content_id: uuid.UUID
    object_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class ParsedContent:
    content_id: uuid.UUID
    kind: str
    title: str
    markdown: str
    frontmatter: dict[str, Any]
    properties: dict[str, Any]
    taxonomies: dict[str, list[str]]
    topic_type: str
    topic_schema_version: int | None
    links: tuple[ParsedLink, ...]
    includes: tuple[ParsedInclude, ...]
    derived_from: ParsedContentReference | None
    template_sources: tuple[ParsedTemplateSource, ...]
    findings: tuple[dict[str, Any], ...]
    content_digest: str


def _preflight_yaml(text: str) -> None:
    depth = 0
    nodes = 0
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent):
                raise ContentProfileError("frontmatter.alias", "Frontmatter aliases are not allowed")
            if isinstance(event, yaml.CollectionStartEvent):
                depth += 1
                nodes += 1
                if depth > MAX_FRONTMATTER_DEPTH:
                    raise ContentProfileError("frontmatter.depth", "Frontmatter nesting exceeds its limit")
            elif isinstance(event, yaml.CollectionEndEvent):
                depth -= 1
            elif isinstance(event, yaml.ScalarEvent):
                nodes += 1
            if nodes > MAX_FRONTMATTER_NODES:
                raise ContentProfileError("frontmatter.nodes", "Frontmatter structure exceeds its limit")
    except yaml.YAMLError as exc:
        raise ContentProfileError("frontmatter.yaml", "Frontmatter YAML is invalid") from exc


def _split_source(source: bytes) -> tuple[str, str]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContentProfileError("content.encoding", "Content must be UTF-8") from exc
    if not text.startswith("---\n"):
        raise ContentProfileError("frontmatter.missing", "Content must begin with versioned frontmatter")
    boundary = text.find("\n---\n", 4)
    if boundary < 0:
        raise ContentProfileError("frontmatter.unclosed", "Frontmatter closing delimiter is missing")
    frontmatter = text[4:boundary]
    if len(frontmatter.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise ContentProfileError("frontmatter.size", "Frontmatter exceeds its size limit")
    return frontmatter, text[boundary + 5 :]


def _portable_value(value: Any, *, key: str) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, list) and len(value) <= 64:
        if all(item is None or isinstance(item, bool | int | str) for item in value):
            return value
    raise ContentProfileError("property.value", f"Property {key} has an unsupported value")


def _mapping(value: Any, *, code: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) and KEY_PATTERN.fullmatch(key) for key in value):
        raise ContentProfileError(code, f"{label} must be a mapping with stable keys")
    return value


def _parse_frontmatter(text: str) -> dict[str, Any]:
    _preflight_yaml(text)
    try:
        value = yaml.load(text, Loader=_StrictLoader)  # noqa: S506  # nosec B506
    except yaml.YAMLError as exc:
        raise ContentProfileError("frontmatter.yaml", "Frontmatter YAML is invalid") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContentProfileError("frontmatter.shape", "Frontmatter must be a mapping")
    unknown = sorted(set(value) - ALLOWED_FIELDS)
    if unknown:
        raise ContentProfileError("frontmatter.field", f"Unsupported frontmatter field: {unknown[0]}")
    if value.get("schema") != CONTENT_SCHEMA:
        raise ContentProfileError("frontmatter.schema", "Frontmatter schema is unsupported")
    return value


def _parse_links(markdown: str) -> tuple[ParsedLink, ...]:
    parser = MarkdownIt("commonmark", {"html": False})
    links: list[ParsedLink] = []
    for token in parser.parse(markdown):
        if token.type != "inline" or token.children is None:
            continue
        for child in token.children:
            if child.type != "text":
                continue
            for match in WIKILINK_PATTERN.finditer(child.content):
                try:
                    target = uuid.UUID(match.group("target"))
                except ValueError as exc:
                    raise ContentProfileError("wikilink.target", "Wikilink target is invalid") from exc
                links.append(
                    ParsedLink(
                        target_content_id=target,
                        fragment=match.group("fragment") or "",
                        label=(match.group("label") or "").strip(),
                        ordinal=len(links),
                    )
                )
                if len(links) > MAX_LINKS:
                    raise ContentProfileError("wikilink.limit", "Content exceeds its wikilink limit")
            remainder = WIKILINK_PATTERN.sub("", child.content)
            if "[[" in remainder or "]]" in remainder:
                raise ContentProfileError("wikilink.syntax", "Wikilink syntax is invalid")
    return tuple(links)


def _uuid(value: Any, *, code: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ContentProfileError(code, message) from exc


def _object_id(value: Any, *, code: str, message: str) -> str:
    if not isinstance(value, str) or GIT_OBJECT_PATTERN.fullmatch(value) is None:
        raise ContentProfileError(code, message)
    return value


def _parse_includes(value: Any) -> tuple[ParsedInclude, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_INCLUDES:
        raise ContentProfileError("include.shape", "Includes must be a bounded ordered list")
    includes: list[ParsedInclude] = []
    for ordinal, item in enumerate(value):
        if not isinstance(item, dict):
            raise ContentProfileError("include.shape", "Each include must be a mapping")
        mode = item.get("mode")
        expected_fields = {"id", "mode", "audience", "commit"} if mode == "pinned" else {"id", "mode", "audience"}
        if set(item) != expected_fields or mode not in INCLUDE_MODES:
            raise ContentProfileError("include.shape", "Include fields or resolution mode are invalid")
        audience = item.get("audience")
        if audience not in AUDIENCE_PROFILES:
            raise ContentProfileError("include.audience", "Include audience is unsupported")
        includes.append(
            ParsedInclude(
                target_content_id=_uuid(item.get("id"), code="include.target", message="Include target must be a UUID"),
                mode=mode,
                audience=audience,
                pinned_object_id=(
                    _object_id(
                        item.get("commit"),
                        code="include.commit",
                        message="Pinned include commit is invalid",
                    )
                    if mode == "pinned"
                    else ""
                ),
                ordinal=ordinal,
            )
        )
    return tuple(includes)


def _parse_reference(value: Any, *, field: str) -> ParsedContentReference | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"id", "commit"}:
        raise ContentProfileError(f"{field}.shape", f"{field} must contain an id and exact commit")
    return ParsedContentReference(
        content_id=_uuid(value.get("id"), code=f"{field}.target", message=f"{field} target must be a UUID"),
        object_id=_object_id(value.get("commit"), code=f"{field}.commit", message=f"{field} commit is invalid"),
    )


def _parse_template_sources(value: Any) -> tuple[ParsedTemplateSource, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_TEMPLATE_SOURCES:
        raise ContentProfileError("template_source.shape", "Template sources must be a bounded ordered list")
    sources: list[ParsedTemplateSource] = []
    for ordinal, item in enumerate(value):
        reference = _parse_reference(item, field="template_source")
        if reference is None:  # pragma: no cover - list entries cannot be null
            raise ContentProfileError("template_source.shape", "Template source is invalid")
        sources.append(ParsedTemplateSource(reference.content_id, reference.object_id, ordinal))
    return tuple(sources)


def parse_content(source: bytes) -> ParsedContent:
    frontmatter_text, markdown = _split_source(source)
    frontmatter = _parse_frontmatter(frontmatter_text)
    try:
        raw_content_id = frontmatter["id"]
    except KeyError as exc:
        raise ContentProfileError("frontmatter.id", "Content id must be a UUID") from exc
    content_id = _uuid(raw_content_id, code="frontmatter.id", message="Content id must be a UUID")
    kind = frontmatter.get("kind")
    if kind not in ContentNodeKind.values:
        raise ContentProfileError("frontmatter.kind", "Content kind must be document or fragment")
    title = frontmatter.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 240 or title != title.strip():
        raise ContentProfileError("frontmatter.title", "Content title is invalid")

    properties_source = _mapping(frontmatter.get("properties", {}), code="property.shape", label="Properties")
    if len(properties_source) > MAX_PROPERTIES:
        raise ContentProfileError("property.limit", "Content exceeds its property limit")
    properties = {key: _portable_value(value, key=key) for key, value in sorted(properties_source.items())}

    taxonomy_source = _mapping(frontmatter.get("taxonomies", {}), code="taxonomy.shape", label="Taxonomies")
    taxonomies: dict[str, list[str]] = {}
    for taxonomy_key, stable_keys in sorted(taxonomy_source.items()):
        if (
            not isinstance(stable_keys, list)
            or len(stable_keys) > 64
            or not all(isinstance(item, str) and KEY_PATTERN.fullmatch(item) for item in stable_keys)
            or len(stable_keys) != len(set(stable_keys))
        ):
            raise ContentProfileError("taxonomy.terms", f"Taxonomy {taxonomy_key} has invalid stable keys")
        taxonomies[taxonomy_key] = sorted(stable_keys)

    topic_type = ""
    topic_version: int | None = None
    findings: list[dict[str, Any]] = []
    topic = frontmatter.get("topic")
    if topic is not None:
        if kind != ContentNodeKind.DOCUMENT or not isinstance(topic, dict) or set(topic) != {"type", "version"}:
            raise ContentProfileError("topic.shape", "Topic must be a document type and schema version")
        topic_type_value = topic.get("type")
        topic_version_value = topic.get("version")
        if (
            not isinstance(topic_type_value, str)
            or topic_type_value not in SCHEMAS
            or topic_version_value != SCHEMA_VERSION
        ):
            raise ContentProfileError("topic.schema", "Topic schema is unsupported")
        topic_type = topic_type_value
        topic_version = SCHEMA_VERSION
        findings.extend(inspect_markdown(topic_type, markdown))

    links = _parse_links(markdown)
    includes = _parse_includes(frontmatter.get("includes"))
    derived_from = _parse_reference(frontmatter.get("derived_from"), field="derived_from")
    template_sources = _parse_template_sources(frontmatter.get("template_sources"))
    if derived_from is not None and kind != ContentNodeKind.FRAGMENT:
        raise ContentProfileError("derived_from.kind", "Only fragments may record independent-copy provenance")
    if template_sources and kind != ContentNodeKind.DOCUMENT:
        raise ContentProfileError("template_source.kind", "Only documents may define template sources")
    canonical = {
        "frontmatter": frontmatter,
        "links": [
            {
                "fragment": link.fragment,
                "label": link.label,
                "ordinal": link.ordinal,
                "target": str(link.target_content_id),
            }
            for link in links
        ],
        "markdown": markdown,
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ParsedContent(
        content_id=content_id,
        kind=kind,
        title=title,
        markdown=markdown,
        frontmatter=frontmatter,
        properties=properties,
        taxonomies=taxonomies,
        topic_type=topic_type,
        topic_schema_version=topic_version,
        links=links,
        includes=includes,
        derived_from=derived_from,
        template_sources=template_sources,
        findings=tuple(findings),
        content_digest=digest,
    )
