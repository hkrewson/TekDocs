"""Key expressions for indirect addressing in document content (ADR 0089).

A key names a binding declared by a document and a field path within the record
that binding resolves to::

    Connect to the gateway at <tekdocs://key/subject.gateway> using the console.

Keys are stored unresolved. ``BlockRevision.markdown`` keeps the literal expression
and its checksum keeps covering authored source, so revision immutability is
unaffected: resolution is a function of one immutable revision and one binding
context, never a mutation of stored content.

Extraction runs through the Markdown parser rather than a regular expression over
raw text. CommonMark does not parse inline constructs inside fenced code, indented
code, or code spans, so a key written in a ``mermaid`` fence, a ``bash`` fence, or
inline code is literal text and is never resolved. That exclusion is a property of
the parser, not a rule this module has to enforce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt

KEY_TARGET_SCHEME = "tekdocs://key/"

# A binding name followed by one to three field segments. Segments are lowercase to
# keep one spelling per key: the stored form is permanent, so `Subject.Gateway` and
# `subject.gateway` must not both become valid names for the same value.
_SEGMENT = r"[a-z][a-z0-9_]{0,39}"
_KEY_EXPRESSION_PATTERN = re.compile(rf"^({_SEGMENT})((?:\.{_SEGMENT}){{1,3}})$")

#: The names a document may declare as bindings. This is the same grammar as one key
#: segment, and `DocumentKeyBinding` enforces it in the database with this pattern, so
#: a stored binding can always be named by a key expression.
BINDING_NAME_PATTERN = rf"^{_SEGMENT}$"

_KEY_SCAN_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})

#: Upper bound on distinct keys resolved for one document, so a hostile or generated
#: revision cannot turn a single render into an unbounded number of record reads.
MAXIMUM_KEYS_PER_DOCUMENT = 200


@dataclass(frozen=True, slots=True)
class DocumentKey:
    """One parsed key expression."""

    binding: str
    """The binding name declared by the document, such as ``subject``."""

    path: tuple[str, ...]
    """Field path within the bound record, such as ``("site", "gateway")``."""

    @property
    def expression(self) -> str:
        """The canonical text form, without the URL scheme."""
        return ".".join((self.binding, *self.path))

    @property
    def target(self) -> str:
        """The canonical stored form, including the URL scheme."""
        return f"{KEY_TARGET_SCHEME}{self.expression}"


def parse_key_expression(expression: str) -> DocumentKey | None:
    """Return the key named by ``expression``, or ``None`` when it is not a key.

    Returning ``None`` rather than raising keeps an unrecognised target renderable:
    the caller shows an explicit unresolvable marker instead of failing the document
    or silently dropping the text.
    """
    match = _KEY_EXPRESSION_PATTERN.fullmatch(expression)
    if match is None:
        return None
    binding, remainder = match.group(1), match.group(2)
    return DocumentKey(binding=binding, path=tuple(remainder.lstrip(".").split(".")))


def parse_key_target(target: str) -> DocumentKey | None:
    """Return the key named by a ``tekdocs://key/`` target, or ``None``."""
    if not target.startswith(KEY_TARGET_SCHEME):
        return None
    return parse_key_expression(target[len(KEY_TARGET_SCHEME) :])


def key_targets_in_markdown(markdown: str) -> list[str]:
    """Every ``tekdocs://key/`` target in ``markdown``, in document order.

    Targets are returned verbatim, including ones that are not valid keys, so the
    renderer can mark an unresolvable expression rather than ignoring it. Code
    regions are excluded by the parser.
    """
    targets: list[str] = []
    for token in _KEY_SCAN_MARKDOWN.parse(markdown):
        for child in token.children or ():
            if child.type != "link_open":
                continue
            target = child.attrGet("href")
            if isinstance(target, str) and target.startswith(KEY_TARGET_SCHEME):
                targets.append(target)
    return targets


def keys_in_markdown(markdown: str) -> tuple[list[DocumentKey], list[str]]:
    """Split the keys in ``markdown`` into resolvable keys and unresolvable targets.

    Keys are de-duplicated because one document commonly repeats a value; the
    resolver reads each distinct record field once.
    """
    keys: dict[str, DocumentKey] = {}
    unresolvable: list[str] = []
    for target in key_targets_in_markdown(markdown):
        key = parse_key_target(target)
        if key is None:
            if target not in unresolvable:
                unresolvable.append(target)
            continue
        keys.setdefault(key.expression, key)
    return list(keys.values()), unresolvable
