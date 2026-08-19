"""Resolving document keys as the audience that will read the output (ADR 0089).

Resolution is an authorization boundary. A key that quietly returned a field the
reader could not otherwise read would be an IDOR vector wearing documentation
syntax, so this module does not implement its own access rules. It composes the two
gates the direct read paths already use:

``entity_visible_to_audience``
    Decides whether the reader may see the bound record at all, evaluated as the
    audience the output is for rather than as the author. The client-portal branch
    applies the same tenant, organization, and ``CLIENT_VISIBLE`` conditions the
    portal applies when it decides whether a publication may be served.
``context_has_field_access``
    Decides whether the reader may see a field carrying a ``SensitiveField``
    classification, using the same permission a direct read requires.

Three outcomes exist and they are kept distinct on purpose:

``RESOLVED``
    The reader may see the value; it is rendered with its provenance.
``WITHHELD``
    The reader may not see the record or the field. The result carries the field
    label and nothing else — no value, no record identity, and no distinction
    between "the record is not yours" and "the field is classified", because
    telling those apart would disclose more than a direct denial does.
``UNRESOLVABLE``
    Nothing is being hidden: the binding is missing, the field is not addressable,
    the record is archived, or the value is empty. These carry a reason, which is
    safe because they are conditions on records the reader may already see.

An unresolvable key never renders blank and never falls back to a stale value.

Resolution is batched: bindings load once per document, entities once, domain
records once per record type with their relations pre-joined, and integration
provenance once. Nothing is cached across scopes — a cache keyed by anything other
than the reader would be the disclosure this module exists to prevent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model

from apps.accounts.policy import (
    DataAudience,
    InstallationMemberContext,
    context_has_field_access,
    entity_visible_to_audience,
)

from .document_key_fields import (
    RESOLVABLE_RECORDS,
    FieldKind,
    ResolvableField,
    resolvable_field,
)
from .document_keys import KEY_TARGET_SCHEME, MAXIMUM_KEYS_PER_DOCUMENT, DocumentKey, keys_in_markdown
from .models import Document, DocumentKeyBinding, Entity, NetBoxReference, Organization


class ResolutionState(StrEnum):
    RESOLVED = "resolved"
    WITHHELD = "withheld"
    UNRESOLVABLE = "unresolvable"


class ValueProvenance(StrEnum):
    """Where a resolved value came from.

    This is a record-level statement, not a field-level one: an entity reconciled
    against an integration provider is ``OBSERVED``. Claiming that one particular
    field arrived from the provider would require per-field reconciliation records
    that do not exist yet, and a provenance claim that cannot be computed is worse
    than one that is honest about its granularity.
    """

    LOCAL = "local"
    OBSERVED = "observed"


class UnresolvableReason(StrEnum):
    NO_BINDING = "no_binding"
    NOT_ADDRESSABLE = "not_addressable"
    ARCHIVED = "archived"
    EMPTY = "empty"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass(frozen=True, slots=True)
class ResolvedKey:
    """The outcome of resolving one key for one reader."""

    expression: str
    state: ResolutionState
    label: str
    value: str = ""
    provenance: ValueProvenance | None = None
    source_entity_id: UUID | None = None
    reason: UnresolvableReason | None = None


def _withheld(key: DocumentKey, label: str) -> ResolvedKey:
    return ResolvedKey(expression=key.expression, state=ResolutionState.WITHHELD, label=label)


def _unresolvable(key: DocumentKey, label: str, reason: UnresolvableReason) -> ResolvedKey:
    return ResolvedKey(
        expression=key.expression,
        state=ResolutionState.UNRESOLVABLE,
        label=label,
        reason=reason,
    )


def _read(record: object, field: ResolvableField) -> str:
    """Read and format one field, returning ``""`` when the value is absent."""
    *hops, attribute = field.accessor
    owner: object | None = record
    for hop in hops:
        if owner is None:
            return ""
        try:
            owner = getattr(owner, hop)
        except ObjectDoesNotExist:
            # An optional one-to-one that was never created, such as an asset with
            # no hardware record. Absent, not hidden.
            return ""
    if owner is None:
        return ""
    if field.kind == FieldKind.CHOICE:
        display = getattr(owner, f"get_{attribute}_display", None)
        if callable(display):
            return str(display()).strip()
    value = getattr(owner, attribute, None)
    if value is None:
        return ""
    if field.kind == FieldKind.DATE and isinstance(value, date):
        return value.isoformat()
    if field.kind == FieldKind.NUMBER:
        return str(value)
    return str(value).strip()


def _bindings(document: Document, names: set[str]) -> dict[str, DocumentKeyBinding]:
    return {
        binding.name: binding
        for binding in DocumentKeyBinding.objects.filter(document=document, name__in=names).select_related(
            "target_entity"
        )
    }


def _records_by_entity(entities: Sequence[Entity]) -> dict[UUID, object]:
    """Load each bound record once, grouped by record type so relations pre-join.

    One query per distinct record type, not one per key: a document that quotes
    twelve fields of one firewall reads that firewall once.
    """
    by_type: dict[str, list[Entity]] = {}
    for entity in entities:
        if entity.entity_type in RESOLVABLE_RECORDS:
            by_type.setdefault(entity.entity_type, []).append(entity)

    records: dict[UUID, object] = {}
    for entity_type, group in by_type.items():
        specification = RESOLVABLE_RECORDS[entity_type]
        related_model = Entity._meta.get_field(specification.record_accessor).related_model
        if not (isinstance(related_model, type) and issubclass(related_model, Model)):
            continue  # pragma: no cover - the registry names a real relation
        queryset = related_model._default_manager.filter(entity__in=group)
        if specification.select_related:
            queryset = queryset.select_related(*specification.select_related)
        for record in queryset:
            # Every addressable record is entity-anchored; the base Model type is not.
            records[record.entity_id] = record  # type: ignore[attr-defined]
    return records


def _observed_entity_ids(entity_ids: set[UUID]) -> set[UUID]:
    if not entity_ids:
        return set()
    return set(
        NetBoxReference.objects.filter(entity_id__in=entity_ids, archived_at__isnull=True).values_list(
            "entity_id", flat=True
        )
    )


def resolve_keys(
    keys: Iterable[DocumentKey],
    *,
    context: InstallationMemberContext,
    document: Document,
    audience: DataAudience,
    organization: Organization | None,
) -> dict[str, ResolvedKey]:
    """Resolve ``keys`` for one reader, keyed by the ``tekdocs://key/`` target.

    Keying by target rather than by expression lets the renderer look a key up by the
    href it already has, and lets a malformed target carry a result of its own.
    """
    requested = list(dict.fromkeys(keys))
    resolutions: dict[str, ResolvedKey] = {}

    if len(requested) > MAXIMUM_KEYS_PER_DOCUMENT:
        # Bounded so one generated revision cannot turn a render into an unbounded
        # number of record reads. The excess is reported, never silently dropped.
        for key in requested[MAXIMUM_KEYS_PER_DOCUMENT:]:
            resolutions[key.target] = _unresolvable(key, key.expression, UnresolvableReason.LIMIT_EXCEEDED)
        requested = requested[:MAXIMUM_KEYS_PER_DOCUMENT]

    bindings = _bindings(document, {key.binding for key in requested})
    entities = list({binding.target_entity_id: binding.target_entity for binding in bindings.values()}.values())
    visible = {
        entity.id
        for entity in entities
        if entity_visible_to_audience(context, entity, audience=audience, organization=organization)
    }
    records = _records_by_entity([entity for entity in entities if entity.id in visible])
    observed = _observed_entity_ids(visible)

    for key in requested:
        resolutions[key.target] = _resolve_one(
            key,
            context=context,
            binding=bindings.get(key.binding),
            records=records,
            visible=visible,
            observed=observed,
            organization=organization,
        )
    return resolutions


def _resolve_one(
    key: DocumentKey,
    *,
    context: InstallationMemberContext,
    binding: DocumentKeyBinding | None,
    records: Mapping[UUID, object],
    visible: set[UUID],
    observed: set[UUID],
    organization: Organization | None,
) -> ResolvedKey:
    if binding is None:
        return _unresolvable(key, key.expression, UnresolvableReason.NO_BINDING)

    entity = binding.target_entity
    if entity.id not in visible:
        # Withheld before the record type is consulted, so the marker carries only
        # the key the author wrote. Deriving the field label here would disclose
        # what kind of record the binding points at, which a direct denial does not.
        return _withheld(key, key.expression)

    registered = resolvable_field(entity.entity_type, key.path)
    if registered is None:
        return _unresolvable(key, key.expression, UnresolvableReason.NOT_ADDRESSABLE)

    _, field = registered
    label = field.label
    if field.sensitivity is not None and not context_has_field_access(
        context, field.sensitivity, organization=organization
    ):
        return _withheld(key, label)

    record = records.get(entity.id)
    if record is None:
        return _unresolvable(key, label, UnresolvableReason.NOT_ADDRESSABLE)
    if getattr(record, "archived_at", None) is not None or getattr(entity, "archived_at", None) is not None:
        return _unresolvable(key, label, UnresolvableReason.ARCHIVED)

    value = _read(record, field)
    if not value:
        return _unresolvable(key, label, UnresolvableReason.EMPTY)

    return ResolvedKey(
        expression=key.expression,
        state=ResolutionState.RESOLVED,
        label=label,
        value=value,
        provenance=ValueProvenance.OBSERVED if entity.id in observed else ValueProvenance.LOCAL,
        source_entity_id=entity.id,
    )


def resolve_markdown_keys(
    markdown: str,
    *,
    context: InstallationMemberContext,
    document: Document,
    audience: DataAudience,
    organization: Organization | None,
) -> dict[str, ResolvedKey]:
    """Resolve every key in ``markdown``, including ones that are not valid keys.

    Malformed targets are reported as unresolvable rather than dropped, so the
    renderer marks them instead of emitting the raw expression.
    """
    keys, unresolvable = keys_in_markdown(markdown)
    resolutions = resolve_keys(
        keys,
        context=context,
        document=document,
        audience=audience,
        organization=organization,
    )
    for target in unresolvable:
        # The scheme is stripped from the label: the marker names the expression the
        # author wrote, and the renderer puts the label in an accessible name where
        # a URL would read as a link that is not one.
        expression = target.removeprefix(KEY_TARGET_SCHEME)
        resolutions[target] = ResolvedKey(
            expression=expression,
            state=ResolutionState.UNRESOLVABLE,
            label=expression,
            reason=UnresolvableReason.NOT_ADDRESSABLE,
        )
    return resolutions
