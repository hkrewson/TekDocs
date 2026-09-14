# Devices register and complete record workspace

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

Devices is a Networks view in both MSP and organization workspaces. Its shared
register uses bounded server search, status/role filters, deterministic ordering,
25/50/100-row pages, and personal columns/reset. Defaults: name, role, status, site,
rack, starting unit. Mobile rows prioritize identity, role, status and rack; site
and unit details remain in the drawer. No page-spanning selection is introduced.

Record names open the complete Overview/Placement/History drawer. Overview shows
operational facts and the permitted hardware identity. Placement includes site,
location, rack and unit occupancy. History loads entity-filtered activity on demand.
The optional full-page link, direct record/section URLs, refresh and browser history
retain context. Drawers close through backdrop/Escape or mobile Back, with one
scrolling body and a labeled mobile Sections selector. Dirty/busy protection applies
to section changes, navigation and dismissal. Failed requests preserve drafts and
never automatically retry uncertain writes.

Ordinary detail edits PATCH exactly name/role/status. They do not resend a hidden
hardware asset ID or replace physical placement. Placement edits send only placement
fields. Outside a rack, site/location are optional and changing site clears location.
Inside a rack, site/location follow the server's selected rack. Capacity and overlap
rules remain authoritative. A failed move retains rack choice and unit values.
Existing hardware bindings are not editable in this checkpoint; binding replacement
needs its own focused workflow and asset authorization.

Creation chooses an authorized, unlinked hardware asset from a bounded search by
name. New records start unplaced; placement is set in the dedicated section after
save. The New device action requires both network-edit and asset-view permission.
Asset-denied network editors may still edit existing facts or placement without
receiving or overwriting the protected hardware identity.

A rack's selected-device view now links to the full device record, without opening
a nested drawer. Browser Back restores the rack's selected child and list context.

## API and persistence

Existing assignment-choice routes accept `kind=hardware_asset`: exact-workspace,
active hardware assets without a device binding, name search, name/entity-ID ordering,
default 25 and maximum 100 results. Asset-view permission is explicitly required.
Other kinds and legacy unpaginated choice behavior are retained. Device collection
responses add `can_create`, computed by the existing policy service. Existing write
services revalidate authorization, binding uniqueness and physical placement.

The `network-devices` preference definition reuses the installation/user ownership
and RLS model; no new model, migration, route or permission grant. No protected asset
column is offered. Existing device API search also respects asset-view permission.
OpenAPI and generated types include the additive choice and capability metadata.
Frontend device PATCH typing is partial to match the existing public API contract.

## Verification and next boundary

Focused tests cover 31 available choices, off-page lookup, sibling-workspace exclusion,
claimed-asset removal, permission-denied choices, ordinary edits with hidden bindings,
preferences/reset, dirty failed placement and creation. Browser coverage includes all
six widths, keyboard/focus, touch, short heights, 200% zoom, accessibility scans,
refresh/Back/Forward, unavailable records, saved columns, status/role filters and
immediate post-save dismissal. The isolated live journey creates a device, edits its
status, installs it in a rack, follows the rack-to-device link and independently
verifies hardware identity, derived location, occupancy and audit events in PostgreSQL.
Executed outcomes are recorded in progress.md.

This is the device register/core editing checkpoint, not full network acceptance.
Interfaces and their addresses/MAC records need bounded parent collections and focused
editing next. Device relationship editing and hardware-binding replacement remain
explicit follow-ups. DNS, circuits, other surfaces, technician validation and final
release/recovery obligations remain open. No production publication or version bump.

### Handoff for the next interface slice

The existing endpoint implementation is `backend/apps/core/network_endpoint_views.py`:
`InterfaceListCreateView` currently accepts only the common bounded page parameters;
`InterfaceDetailView` already supports selected GET and partial PATCH. The frontend
`listInterfaces` helper in `networks/api.ts` hardcodes page 1/100 and has no selected
detail helper. Do not use it to populate the device drawer or silently treat its
first page as the complete collection.

Add explicit authorized `device_id`, search, kind/status and deterministic ordering
to a bounded interface collection contract, with matching OpenAPI/types. Introduce
an Interfaces section under the selected device; load only that parent's requested
page. Create within that device and omit unchanged parent identity from ordinary
edits. Selected interface state must have a URL and revalidate parent membership;
reuse the current drawer for child content rather than opening another overlay.
Keep device Overview as the default. Decide and document the interface child return
and section URLs before editing so browser Back and dirty protection remain coherent.

Cover more than 25 interfaces, an off-page search hit, another device's interface,
sibling-workspace denial, failed partial saves, refresh and parent return. Interface
IP/MAC children need their own bounded retrieval and binding checks; do not preload
all addresses or expand the new section into the old stacked workspace. Existing
IP assignment, MAC uniqueness, permissions and audit services remain authoritative.
Rack placement and hardware-binding replacement stay separate from interface edits.

Interface collection/core editing is now implemented in [device-interfaces.md](device-interfaces.md). The handoff above records the prior starting point; IP/MAC children and reassignment remain open.
