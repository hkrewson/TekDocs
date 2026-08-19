"""The fields a key expression may resolve (ADR 0089).

A key such as ``<tekdocs://key/subject.serial_number>`` names a binding and a field
path. This module decides which field paths exist. It is an allowlist by
construction: a path that is not registered here does not resolve, so a key can
never walk arbitrary model attributes. That matters for two reasons. Traversing
attributes by name would expose every field of every related record, including ones
no API returns, and it would let one authored line pull an unbounded chain of
queries into a render.

Registration is data, not code. Adding a field is one ``ResolvableField`` entry and
adding a record type is one ``ResolvableRecord`` entry; neither requires a change to
the resolver. That is deliberate — the initial scope covers assets and networks, and
the registry is expected to grow as more of the model becomes worth quoting in
documentation.

Each entry states four things:

``accessor``
    The attribute chain to read, starting at the domain record rather than the
    ``Entity``. Every hop is named here, so the query cost of a field is visible at
    registration time and can be pre-joined.
``kind``
    How the value becomes text. Documentation quotes a value; it does not quote a
    database representation, so a choice field renders its human label and a date
    renders in ISO form rather than the local format of whoever rendered it.
``sensitivity``
    The ``SensitiveField`` classification, when the field carries one. The resolver
    applies the same permission the direct read applies; a reader without it gets a
    withheld marker, not the value.
``label``
    What the field is called, used by the withheld and unresolvable markers so a
    reader can tell what is missing without being told what it said.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from apps.accounts.policy import SensitiveField


class FieldKind(StrEnum):
    """How a stored value becomes the text a reader sees."""

    TEXT = "text"
    """Rendered as-is after stripping surrounding whitespace."""

    CHOICE = "choice"
    """Rendered as the human label of the choice, not the stored value."""

    DATE = "date"
    """Rendered in ISO 8601 form, which is unambiguous across locales."""

    NUMBER = "number"
    """Rendered as a decimal integer."""


@dataclass(frozen=True, slots=True)
class ResolvableField:
    """One addressable field on one record type."""

    label: str
    accessor: tuple[str, ...]
    kind: FieldKind = FieldKind.TEXT
    sensitivity: SensitiveField | None = None


@dataclass(frozen=True, slots=True)
class ResolvableRecord:
    """One addressable record type, reached from its ``Entity``."""

    record_accessor: str
    """The reverse one-to-one accessor from ``Entity`` to the domain record."""

    label: str
    """What this record type is called in a marker."""

    select_related: tuple[str, ...]
    """Relations to pre-join, so resolving a document costs one query per record."""

    fields: Mapping[str, ResolvableField]
    """Field paths, keyed by the dotted text that follows the binding name."""


_HARDWARE_FIELDS = {
    "serial_number": ResolvableField("Serial number", ("hardware", "serial_number")),
    "asset_tag": ResolvableField("Asset tag", ("hardware", "asset_tag")),
    "lifecycle_state": ResolvableField("Lifecycle state", ("hardware", "lifecycle_state"), FieldKind.CHOICE),
    "warranty_provider": ResolvableField("Warranty provider", ("hardware", "warranty_provider")),
    "warranty_ends_on": ResolvableField("Warranty end date", ("hardware", "warranty_ends_on"), FieldKind.DATE),
    "acquired_on": ResolvableField("Acquisition date", ("hardware", "acquired_on"), FieldKind.DATE),
}

_SITE_FIELDS = {
    "site.name": ResolvableField("Site", ("site", "entity", "display_name")),
    "site.code": ResolvableField("Site code", ("site", "code")),
    "site.city": ResolvableField("Site city", ("site", "city")),
    "site.region": ResolvableField("Site region", ("site", "region")),
    "site.timezone": ResolvableField("Site time zone", ("site", "timezone")),
}


#: Every addressable record type, keyed by ``Entity.entity_type``.
#:
#: The initial scope is assets and networks: the records a homelab or a small MSP
#: quotes constantly in procedures. Person, credential, contract, domain, and
#: certificate records are deliberately absent — they carry PII and cost fields whose
#: sensitivity classifications are not yet modelled, and shipping them before that is
#: modelled would mean resolving fields the sensitive-field gate cannot see.
RESOLVABLE_RECORDS: Mapping[str, ResolvableRecord] = {
    "network_device": ResolvableRecord(
        record_accessor="network_device",
        label="Network device",
        select_related=("entity", "site__entity", "rack__entity", "hardware_asset__hardware"),
        fields={
            "name": ResolvableField("Name", ("entity", "display_name")),
            "role": ResolvableField("Role", ("role",), FieldKind.CHOICE),
            "status": ResolvableField("Status", ("status",), FieldKind.CHOICE),
            "rack.name": ResolvableField("Rack", ("rack", "entity", "display_name")),
            "rack_unit": ResolvableField("Rack unit", ("rack_unit",), FieldKind.NUMBER),
            **_SITE_FIELDS,
            **{
                path: ResolvableField(
                    field.label,
                    ("hardware_asset", *field.accessor),
                    field.kind,
                    field.sensitivity,
                )
                for path, field in _HARDWARE_FIELDS.items()
            },
        },
    ),
    "client_asset": ResolvableRecord(
        record_accessor="client_asset",
        label="Asset",
        select_related=("entity", "hardware", "model__entity", "product__entity", "supplier__entity"),
        fields={
            "name": ResolvableField("Name", ("entity", "display_name")),
            "model.name": ResolvableField("Model", ("model", "entity", "display_name")),
            "product.name": ResolvableField("Product", ("product", "entity", "display_name")),
            "supplier.name": ResolvableField("Supplier", ("supplier", "entity", "display_name")),
            **_HARDWARE_FIELDS,
        },
    ),
    "network_ip_address": ResolvableRecord(
        record_accessor="network_ip_address",
        label="IP address",
        select_related=("entity", "subnet__entity", "subnet__vlan", "subnet__vrf"),
        fields={
            "address": ResolvableField("Address", ("address",)),
            "dns_name": ResolvableField("DNS name", ("dns_name",)),
            "status": ResolvableField("Status", ("status",), FieldKind.CHOICE),
            "description": ResolvableField("Description", ("description",)),
            "subnet.name": ResolvableField("Subnet", ("subnet", "entity", "display_name")),
            "subnet.cidr": ResolvableField("Subnet", ("subnet", "cidr")),
            "subnet.primary_dns": ResolvableField("Primary DNS", ("subnet", "primary_dns")),
            "subnet.secondary_dns": ResolvableField("Secondary DNS", ("subnet", "secondary_dns")),
            "subnet.vlan_number": ResolvableField("VLAN number", ("subnet", "vlan_number"), FieldKind.NUMBER),
        },
    ),
    "network_subnet": ResolvableRecord(
        record_accessor="network_subnet",
        label="Subnet",
        select_related=("entity", "vlan", "vrf"),
        fields={
            "name": ResolvableField("Name", ("entity", "display_name")),
            "cidr": ResolvableField("CIDR", ("cidr",)),
            "primary_dns": ResolvableField("Primary DNS", ("primary_dns",)),
            "secondary_dns": ResolvableField("Secondary DNS", ("secondary_dns",)),
            "vlan_number": ResolvableField("VLAN number", ("vlan_number",), FieldKind.NUMBER),
            "assignable_start": ResolvableField("First assignable address", ("assignable_start",)),
            "assignable_end": ResolvableField("Last assignable address", ("assignable_end",)),
        },
    ),
    "site": ResolvableRecord(
        record_accessor="site_record",
        label="Site",
        select_related=("entity",),
        fields={
            "name": ResolvableField("Name", ("entity", "display_name")),
            "code": ResolvableField("Site code", ("code",)),
            "city": ResolvableField("City", ("city",)),
            "region": ResolvableField("Region", ("region",)),
            "postal_code": ResolvableField("Postal code", ("postal_code",)),
            "country_code": ResolvableField("Country", ("country_code",)),
            "timezone": ResolvableField("Time zone", ("timezone",)),
            "phone": ResolvableField("Phone", ("phone",)),
        },
    ),
    "organization": ResolvableRecord(
        record_accessor="organization_record",
        label="Organization",
        select_related=("entity",),
        fields={"name": ResolvableField("Name", ("entity", "display_name"))},
    ),
}


def resolvable_field(entity_type: str, path: tuple[str, ...]) -> tuple[ResolvableRecord, ResolvableField] | None:
    """Return the record and field a key path names, or ``None`` when unregistered."""
    record = RESOLVABLE_RECORDS.get(entity_type)
    if record is None:
        return None
    field = record.fields.get(".".join(path))
    if field is None:
        return None
    return record, field
