# Rack register and full drawer

Pre-1.0 Phase 3 (#80), extending #60 and delivery #75. Version stays 0.8.46.

## Implemented boundary

The Networks navigation exposes Racks, using the shared responsive collection and
complete-record drawer. Default columns are name, site, location, status, capacity
in rack units, and installed-device count. Personal columns and page size persist
through the existing `network-racks` preference feature. Identity is mandatory;
reset restores the curated defaults. Mobile rows prioritize name, site, status and
installed-device count; location and capacity remain available in the drawer. Search/status filters/order/page/page size and
record/section selection use URL parameters, with pages of 25, 50 or 100.

Record names open a full drawer with Overview, Devices and History. Below 768 CSS
pixels this fills the screen and uses the labeled Sections selector. Desktop uses
an overlay without squeezing the list. Outside click or Escape closes the drawer;
dirty changes prompt Keep editing/Discard changes. The full-page link remains
optional. Back/Forward, refresh, and direct record URLs retain the selected section.

Overview includes physical placement, capacity, status and device count. Occupied
racks retain the server's placement/capacity warning. A single editor handles rack
name, capacity, ordinary status, required site and optional location. Site/location
lookup pages contain at most 25 choices, with independent search by name/code.
Selecting a different site clears the old location; searching/paging alone never
changes the selected value. Save errors retain fields and never retry automatically.
Existing authorization, occupied-unit and placement rules remain authoritative.

Devices load only when that section opens, using the exact `rack_id`. A compact
paginated list supports search and sorting, then selected-device facts appear in
the same drawer. No nested drawer or bulk download of device detail is used.
Child selection is addressable, revalidates rack membership, and returns to its list
context. Asset facts retain API redaction. Device editing, the independent Devices
register and interface migration are later checkpoints, not claimed here.
History uses the existing lazy, permission-aware record activity component.

## API and persistence

The existing assignment-choice endpoint additionally accepts `kind=location` with
required `site_id`. Other kinds reject `site_id`; invalid or unavailable parents
fail before querying choices. Name/code search is scoped to active locations in
the exact workspace/site, ordered by name then entity ID. Site choices no longer
prefetch every site's location tree. Existing site/VLAN response shapes are unchanged.
OpenAPI and generated types are updated. No new route, domain migration or permission
grant was added. `network-racks` reuses existing personal preference ownership/RLS.

## Verification and open work

Component checks cover lazy devices, failed edits, preserved assignments, successful
save/dismissal, required site and denied actions. Browser scenarios exercise 31 racks
and devices, six widths, long strings, accessibility, drawer/full-page navigation,
mobile/touch, zoom, preferences/reset and filter behavior. A live isolated workflow
creates and edits a rack, refreshes it and verifies placement/audit state in PostgreSQL.
Executed results and any fixes are recorded in progress.md.

Devices, interfaces, DNS, circuits, remaining network surfaces, technician walkthroughs
and final pre-1.0 acceptance remain open. No production publication or version bump.

## Device-register follow-up

The standalone Devices register now supports Overview/Placement/History, asset-backed
creation and guarded detail/placement edits; see device-register.md. Rack child details
link to that full record with browser return context. Interfaces and other follow-ups
remain open rather than inferred from the device register checkpoint.
