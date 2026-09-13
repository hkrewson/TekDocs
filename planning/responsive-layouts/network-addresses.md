# Addresses within network records

Required pre-1.0 Phase 3 (#80), extending #60 and #75. Version stays 0.8.46.

## Delivered boundary

Networks now has Overview, Addresses and History. Addresses is a child collection
inside the same full record drawer or optional full page, replacing the collection
with the selected address's facts or focused edit form. It never opens a nested
drawer. New addresses use the owning network; existing addresses show assignment
and interface information permitted by the server. Ordinary edits change address,
status, DNS name and description only, preserving existing asset/interface links.
Assignment management is not introduced in this checkpoint.

The child collection has identity, status and DNS columns, curated personal column
preferences, reset, 25/50/100 paging, full-parent search and a shared status filter.
Explicit address ordering uses PostgreSQL inet ordering, with entity ID tie-breaking.
Search examines address, DNS name and description before counting/paging. No address
detail is downloaded until selection, and no address collection until its tab opens.

## Navigation and failure behavior

`section=addresses` selects the parent section. `address=<entity-id>` selects an
address and `address=new` opens creation. `address_q`, `address_status`,
`address_order`, `address_page` and `address_size` preserve collection context.
These work with both parent `preview` and `record` URLs. Changing the parent clears
child parameters; changing sections retains them. Returning to the child collection
restores row focus when present, otherwise its heading. A child detail with a parent
ID different from the current network is treated as unavailable, even if otherwise
authorized. Server scoping remains authoritative.

The existing shared dirty/busy guard covers drawer dismissal, section changes and
child navigation. Failed saves retain entries and are not automatically retried.
A saved record outside the current collection page/search produces the shared
updated-outside-view notice. Mobile uses the parent's labeled Sections selector and
single overlay body; address editing introduces no specialized scrolling surface.

## Compatibility and permissions

The existing bounded IP-address GET accepts additive `subnet_id`, `q`, `status`,
`ordering` and `summary`. `summary=true` omits description. Calls omitting ordering
keep legacy lexical address ordering; explicit `ordering=name` uses numeric IP
ordering. Legacy response fields/page defaults remain intact. Unknown query fields
and invalid values are rejected. A requested parent outside the workspace is denied.

Personal feature `network-addresses` uses the existing installation/user-owned
preferences model and networks.view permission. No migration or RLS ownership change
is needed. Asset columns are not offered; detail assignment projection remains under
existing permissions. OpenAPI and generated types describe the additive queries and
optional summary description. POST/PATCH business validation is unchanged.
The live journey also exposed and fixed an existing PostgreSQL PATCH lock failure:
address updates now lock the address and entity explicitly, avoiding the nullable
VRF outer join while retaining namespace serialization.

## Evidence and next work

See progress.md for executed checks and results. Regression coverage includes a
31-address parent, numeric ordering, off-page search, summary/legacy compatibility,
foreign-parent denial, personal preference persistence/reset, direct child refresh,
focus return, failed edits and preserved assignment keys. Browser coverage exercises
all maintained desktop engines and six widths, accessibility, touch and zoom. The
isolated live journey creates and updates an address, then reloads persisted values.

Phase 3 remains open for devices, racks, VLANs/VRFs, interfaces, wireless, DNS,
circuits and their parent/child navigation, plus broader technician acceptance.
This checkpoint does not make the unmounted legacy network components supported UI
or imply that all network inventory surfaces have migrated. Production publication,
release gates and existing security/recovery/invoice obligations remain separate.
