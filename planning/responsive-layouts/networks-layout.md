# Networks collection and full record workspace

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Supported route boundary

This checkpoint replaces the visible simplified Networks page at `/networks` and
`/workspaces/organizations/:organizationId/networks`. It does not resurrect the old
NetBox-style object tabs. `NetworkAddressing`, `NetworkEndpoints`, `NetworkServices`,
`NetworkCircuits`, and related legacy components are not mounted by App.tsx today;
their APIs remain supported and their interface disposition remains Phase 3 work.
Do not mark every network object surface migrated based on this checkpoint.

The visible collection has curated name, location, VLAN and CIDR columns, personal
column preferences and 25/50/100-row pages. Identity cannot be hidden. All supported
columns sort on the server with entity-ID tie-breaking. Search applies before counts
and paging across names, CIDR, descriptions, locations/sites and DNS values. The
shared filter menu offers an exact VLAN number, including the legacy VLAN fallback.
There is no invented status field on simplified network records.

Names open the full shared drawer; Overview displays location, VLAN, CIDR, calculated
gateway/range, DNS, description and notes. Editing is section-local and retains
server validation/overlap/range rules. History loads real entity-filtered activity
only when selected. Outside clicks, Escape, mobile Back to networks and section
navigation use the shared dirty/busy guard. Failed requests preserve values without
automatic retry. The optional full-page link retains URL section state. The network
relationship map remains available explicitly on demand; it no longer loads below
every collection. Its canvas is a deliberate specialized scrolling surface.

## APIs and persistence

Existing bounded GET networks accepts additive `q`, `vlan`, `ordering`, `summary`
parameters. Summary=true omits notes and description from collection payloads;
legacy calls retain all fields and existing page-size defaults. No histories or
relationships are downloaded per row. Selected GET network detail is new and uses
the existing workspace scope and networks.view permission; PATCH retains
networks.edit. Missing/cross-workspace details return the existing unavailable
response. Permission inventory, OpenAPI and generated types include the new read.
Locations/choices load only when editing or creating. The existing choices endpoint
is unchanged; bounded location choice search remains a future improvement.

The existing personal-preferences model gains a networks registry entry only.
No schema, domain-data migration, RLS ownership or recovery-format change occurs.
Preferences remain installation/user/feature scoped and default safely on failure.
Queries/preview/record/section live in the URL; scroll/focus restoration is transient
router state. Saved edits refresh the collection and explain when the record no
longer appears on the current page/filter.

## Verification and next work

Sources: Networks component tests, network-layout.spec.ts, network addressing tests,
permission/IDOR and RLS gates, and the live workspace journey. The live journey
creates a network, verifies server-derived gateway/range and DNS in its drawer,
refreshes, closes, searches and checks independently retained PostgreSQL records.
Six-width browser checks cover long names, no overflow, dialog accessibility,
record/history links, focus restoration, off-page search, preference persistence,
failed edits, denied controls and unavailable records.

Reproduced test-harness failures: the first mock matched `/networks?…` document
navigation as well as API requests; it now targets the API prefix. The mutation
fixture lacked a CSRF cookie, so the real client correctly refused to send the
request before the intended conflict simulation; a random per-page test cookie now
allows the server-conflict assertion to exercise the intended path.

Remaining: explicit disposition/migration of device/rack/addressing/interface/
wireless/DNS/circuit/NetBox surfaces and child records; record relationships beyond
the optional existing map; technician/assistive-technology acceptance; complete
pre-1.0 release/recovery gates. The visible simplified page is not evidence that
these other surfaces are complete. Detailed gate results follow in progress.md.

## Child address follow-up

The [Addresses section](network-addresses.md) now brings the IP-address collection
and focused editing into the supported parent drawer/page. Other advanced network
objects remain pending; see that record for query compatibility and evidence.
