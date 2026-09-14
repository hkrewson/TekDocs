# Devices and racks: collection prerequisite

Pre-1.0 Phase 3, #80; extends #60 and delivery #75. Version remains 0.8.46.

## Bounded completion contract

Prepare existing devices/racks APIs and browser clients for responsive registers:
full-collection search, strict filters, deterministic ordering, bounded pages,
independent detail reads, and retained public compatibility. This checkpoint does
not migrate a visible surface or close Phase 3. No domain migration, new API route,
permission grant, external publication, or production deployment is included.

## API contract

Existing MSP and organization `/networks/racks` and `/networks/devices` routes
retain their response shapes, detail/write endpoints, and default page size 50.
Responsive clients must explicitly request 25, 50, or 100; the public API retains
its existing 1–100 range. Existing frontend `listRacks`/`listDevices` helpers remain
compatible. New `rackCollection`/`deviceCollection` helpers accept an explicit query;
`rackDetail`/`deviceDetail` fetch only the selected record and support cancellation.

Both collections accept `q`, `status`, `site_id`, `ordering`, `page`, and `page_size`.
Devices additionally accept `role` and `rack_id`. Parent identifiers are validated
against the exact authorized workspace before filtering, including empty matches.
Malformed/unknown filters and unsupported ordering fields produce validation errors.

Search covers record name, site name/code, and location name. Devices also search
rack name; linked asset name participates only with asset-view permission. Hidden
asset names cannot influence result counts. Neither collection permits asset-name
ordering. Existing response redaction and policy services remain authoritative.

Rack order fields: name, site, location, status, unit_count, device_count.
Device order fields: name, site, location, status, role, rack, rack_unit.
Prefix a field with `-` to reverse its ordering. Equal values always use ascending
entity ID as a deterministic tie-breaker. PostgreSQL's existing null ordering is
retained. Racks compute device counts in SQL instead of prefetching all installed
devices. Lists contain operational facts, not histories, documents or relationships.

## Verification

Synthetic 31-rack/31-device fixtures exercise two pages, off-page search, empty
results, reverse and tied sorting, site-code lookup, parent boundaries, status/role
filters, legacy defaults and invalid parameters. Additional tests cover asset-name
search/redaction under denied asset permission and escaped browser-client routes.
Full network validation supplies existing tenant/RLS, permission, migration and
high-volume checks. Executed outcomes are recorded in progress.md.

## Next implementation boundary

Build the rack register through the shared collection and complete-record drawer.
Use Overview, Devices and History; load Devices only when requested with `rack_id`.
Do not recreate the old list/detail split or fetch every device to count occupants.
Add user preferences and default columns: name, site, location, status, capacity,
installed-device count. Create/edit must handle required site and optional location
with bounded choices, preserving failed drafts and guarding dismissal. Then extend
the device register with permission-aware asset presentation and parent-scoped
interfaces. These UI, preferences, assignment and browser/live acceptance steps
remain open; this API prerequisite is not evidence that those surfaces are treated.

## Follow-up: rack surface

The rack register and complete drawer are implemented in rack-register.md, with
Overview, lazy Devices/History, bounded placement editing and personal preferences.
See progress.md for executed verification. The next implementation boundary is
the standalone Devices register and its interface/placement workflows; this note
supersedes the earlier rack prerequisite handoff without closing Phase 3.
