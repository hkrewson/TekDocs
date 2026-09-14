# Interfaces within device records

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

The Devices record has Overview, Placement, Interfaces and History sections. Its
Interfaces section is a parent-scoped collection with search, kind/status filters,
curated name/kind/status columns, saved column choices/reset, and 25/50/100-row pages.
It loads on section entry. Selecting an interface replaces the child list within
the existing drawer; it never creates another overlay. Overview remains the default
when opening a device. The optional full page shares the same content.

The URL uses `devices_section=interfaces` and `interface=<id|new>`. Collection state
uses `interface_q`, `_page`, `_size`, `_order`, `_status` and `_association` (kind).
Back to interfaces restores the current page/search and focus to the selected row.
Refresh and browser navigation retain selected child context. Changing the selected
device clears the interface selection. A detail from another parent is rejected
with an unavailable message and return path, even when it is otherwise authorized.

Create fixes device identity to the current parent. Ordinary editing submits only
name, kind, status and description through the existing partial PATCH contract.
Save errors keep the draft; there is no uncertain-write retry. Section changes,
child return, closing and browser navigation use the existing dirty/busy guard.
Network-view/edit permissions and server business rules remain authoritative.

## API and shared components

Existing paginated interface endpoints accept additive `device_id`, `q`, `kind`,
`status`, `ordering` and `summary` parameters. Parent IDs must exist in the exact
workspace. Search covers name/description; sorting supports name/kind/status with
entity-ID tie-breaking. The existing default page size of 50 and full-description
responses remain for legacy consumers. The UI explicitly requests 25 by default
and summaries without descriptions, then selected detail on demand. No list fetches
IP/MAC records, relationships, or histories. Invalid filters/orderings are rejected.
OpenAPI and generated client types reflect the expanded contract.

`NetworkChildCollection` now accepts a generic parent ID and configured parent
field, while keeping its existing subnet callers compatible. It uses that same
field for query scope, selected-detail validation and post-save parent checks.
`network-interfaces` preferences reuse installation/user ownership, RLS and feature
permission filtering. No new model, migration, permission grant or dependency.

## Verification

Component cases cover scoped search, lazy detail, partial edits, new drafts, denied
saves without retry, mismatched parents, read-only views, and return focus. The API
case uses 31 interfaces plus another device and sibling workspace: page counts,
off-page description search, filters, stable ordering, summary versus legacy detail,
invalid queries, partial updates preserving parent identity, and preference reset.

Browser cases cover all six maintained widths, one drawer, axe checks, long content,
refresh, full-page and Back navigation, off-page search, new-record guards, ordinary
save/dismissal, failed touch editing, short height/200% zoom, denied access, parent
mismatch and columns/filter persistence. The live workflow creates an interface,
edits status, reloads it and returns to the child list. Independent PostgreSQL
assertions verify exact device/organization, description, kind/status and audit.
Executed results and any limitations are recorded in progress.md.

## Next boundary

Interface IP/MAC child collections and assignment remain open. Implement bounded
parent retrieval and explicit binding/unbinding through existing services; preserve
MAC uniqueness, IP rules and asset permissions. Do not consume `listIPAddresses` or
`listMACAddresses` as complete datasets or preload all endpoints into this section.
Moving an interface between devices is also a separate focused workflow; ordinary
edits deliberately omit the parent. Device relationships and hardware rebinding,
DNS/circuits, technician validation and full Phase 3/release acceptance remain open.

No production publication or version change is included. The local Wiki Roadmap
update is unpublished; its pre-existing missing-page limitation is unchanged.

Next-slice API caution: `IPAddressWriteSerializer` and `MACAddressWriteSerializer`
do not currently expose `interface_id`; their create views explicitly pass
`interface_entity_id=None`. The underlying `network_endpoints.py` services can
resolve interface bindings, while explicitly submitting a hardware asset binding
clears the current interface. Preserve that distinction when designing a public
assignment workflow. Do not merely add an input and resend both identities: review
permission checks, exact workspace/parent checks, mutually exclusive assignment,
partial-update semantics, OpenAPI and negative tests together. Existing read
responses can contain interface identity, but that is not an exposed write contract.
