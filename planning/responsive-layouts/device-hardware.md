# Device hardware replacement

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

Authorized device records include a Hardware section beside Overview, Placement,
Interfaces, Relationships and History. It uses `devices_section=hardware` in the
existing drawer and optional full-page record. The section appears only when the user
can both edit networks and view assets. A denied direct URL falls back to Overview;
the unavailable section is omitted from desktop tabs and the mobile Sections menu.

The section shows the current hardware identity, then offers bounded, paginated search
over active, unlinked hardware assets in the exact workspace. An explicit selection is
required before replacement. Searches, selections and failed writes participate in the
shared navigation guard, remain visible after a failure and are never retried
automatically. A successful replacement retains the device record, placement,
interfaces, IP/MAC assignments and typed relationships.

## API and persistence

The existing device PATCH accepts hardware replacement only as a separate two-field
request containing `hardware_asset_id` and `expected_hardware_asset_id`. It cannot be
combined with ordinary device facts or placement. The service locks the device,
compares the expected binding, resolves the replacement within the exact workspace and
rejects stale, same-asset or already-linked choices. Asset-view and network-edit
permissions are both rechecked by the server. The device collection exposes the
combined capability so the client can omit the unavailable workflow.

No model, migration, route, permission grant, dependency or CSS changed. OpenAPI and
generated client types include the additive expected-binding field and capability.

## Verification

Focused API coverage exercises successful replacement, stale and same-asset conflicts,
occupied and sibling-workspace assets, mixed-edit rejection, audit history and asset
permission denial. Component coverage verifies the dedicated section, exact request,
permission-controlled visibility and guarded selection. Browser coverage visits the
section at all six maintained widths and completes a touch replacement with reload and
accessibility checks across Chromium, Firefox and WebKit.

The isolated live workspace journey replaces a real device's asset after creating its
placement, relationship, interfaces and endpoint records. Independent PostgreSQL
assertions verify the replacement, released original asset, retained connected records
and append-only device audit history. Executed gate results are recorded in
[progress.md](progress.md).

Remaining network surfaces, technician walkthroughs and full Phase 3 and release
acceptance remain open. No production publication or version change is included.
