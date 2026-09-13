# Wireless records within network drawers

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Delivered boundary and navigation

The supported Networks record drawer/full page now has Overview, Addresses,
Wireless and History. Wireless shows SSIDs associated with that parent subnet;
selecting one replaces the child collection within the same drawer, with readable
facts and section-local editing. It does not open another drawer or mount the old
expansive NetworkServices interface. The optional full-page link retains the child
selection and collection state.

`section=wireless` opens this section. `wireless=<entity-id>` selects a record;
`wireless=new` opens creation. `wireless_q`, `wireless_status`, `wireless_order`,
`wireless_page` and `wireless_size` preserve collection context. Switching parent
network clears both address and wireless state; switching sections retains it.
A selected record returned with another subnet ID is treated as unavailable.

The list defaults to SSID, status, purpose and security, with personal columns/reset
and 25/50/100 paging. Search and status filtering operate over all authorized records
in that parent before counting/paging. Sorting uses a supported field plus entity
ID tie-breaking. Detail reads happen only on selection. Mobile uses the parent's
Sections menu and one overlay scrolling body. No new specialized scrolling surface.

## Shared collection foundation

`NetworkChildCollection` now owns the list/query/preference/detail/return behavior
previously embedded in NetworkAddresses. Static typed configuration supplies each
feature's columns, localized labels, queries, row values and record component.
Addresses and Wireless share this behavior while retaining their distinct editors.
Record components are passed as components rather than called as render functions,
so editor state and React hook/ref rules remain predictable. Existing Address
component and browser checks are required regression coverage for this extraction.

Save results wait for dirty/busy guards to clear before updating the URL. Return
navigation and new-form cancellation use the router guard directly, preserving the
single-confirmation fix from the address checkpoint. Existing-edit cancellation uses
the local guard. Failed requests keep field values and are not retried automatically.
A save outside the current page/filter produces the shared outside-view notice.

## Editing, permissions and compatibility

The editor records SSID, status, purpose, security mode, hidden flag, client isolation
and description. It records documentation; it does not apply configuration to access
points. No credential/password input is introduced. Existing updates omit site,
VLAN and subnet identifiers so those associations remain intact, including legacy
values. Creation sets the current parent, leaving optional site/VLAN associations
unset. Workspace-wide discovery is covered by [the Wireless register](wireless-register.md).
[Parent reassignment](wireless-parent-assignment.md) now uses a focused section; existing data is not silently reassigned.

The existing bounded wireless API accepts additive subnet_id, q, status, ordering
and summary parameters. Summary=true omits description. Legacy calls retain fields,
page defaults and ordering when explicit ordering is absent. Unknown/invalid query
fields fail closed. Parent scope is checked before filtering. The response now has a
typed OpenAPI collection schema; generated TypeScript is synchronized.

Personal feature network-wireless uses the existing installation/user preferences
model and networks.view permission. No new permissions, models, RLS classification
or migration are required. Existing networks.edit authorization remains decisive.
The regression suite checks parent/sibling denial and retained associations.

A pre-existing PostgreSQL update error was reproduced before fixing it: unrestricted
FOR UPDATE attempted to lock nullable site/VLAN/subnet outer joins. Wireless updates
now lock self and entity explicitly while retaining the existing workspace wireless
serialization lock. The API regression verifies a status update preserves all three
associated IDs. Runtime proof must include a live update and refresh.

## Acceptance and remaining work

See progress.md for executed checks and their final results. Maintained browser
coverage includes six widths, bounded off-page lookup, selected/full-page URLs,
refresh/Back, focus return, columns, status filtering, failed edits, dirty navigation,
accessibility, touch, short screens and 200% CSS zoom. Synthetic fixtures stay isolated.
The live journey creates a guest SSID, changes its status and reloads the persisted
security mode and status through Django/PostgreSQL.

Phase 3 remains open for wireless site/VLAN editing, devices,
racks, VLANs/VRFs, interfaces, DNS, circuits and related parent/child workflows.
Technician acceptance, release gates and existing security/recovery/invoice work
remain open. Local rebuild is separate from production publication; no version bump.
