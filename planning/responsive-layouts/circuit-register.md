# Circuit register and service-detail drawers

Pre-1.0 Phase 3 (#80), under #60/#75. Version stays 0.8.46.
Status: circuit browsing, creation, assignment, handoff editing and selected history checkpoints.
Circuit kind/status workflows and broader Phase 3 acceptance remain open.

## Scope and decisions

Networks → Circuits replaces the orphaned, unmounted NetworkCircuits split-panel
component. Curated columns are name, provider, service identifier, kind, status,
and download Mbps. Search covers circuit name, provider name and service identifier
across the full authorized collection. Kind/status use the shared filter menu;
ordering uses an entity-ID tie-breaker; pages are 25/50/100. Personal column/page
preferences reuse the existing installation/user/feature model.

Circuit names open the full overlay workspace, with Overview, Handoffs and History.
Overview retains service identity, provider, status, bandwidth, dates, notes,
permission-filtered contract identity and lifecycle warnings. Edit service details
changes only name, service identifier, bandwidth, dates and description. It does
not submit provider, contract, kind, status or handoff placement fields. Failed
writes retain values and never auto-retry; tabs, browser navigation and dismissal
use the existing dirty-form guard. Dates document service plans; editing a date
does not disconnect a service or change circuit status.

Handoffs load only when their section is opened. Their paginated collection shows
name, side, media and site, with search and a side filter. Selecting a handoff
replaces the child list inside the circuit drawer, without opening another drawer.
Details expose full connector/reference, site/location/device/interface facts and
notes; missing placement remains visible. Parent identity is checked on the server
and again by the shared collection. Returning restores the selected child button's
focus; the selected handoff has a refreshable URL.

Small screens use the full-screen drawer and Sections selector. The optional full
page shares record content. Background/body scroll rules, keyboard dismissal,
backdrop dismissal and full-name access come from the shared drawer; no new CSS or
special scrolling surface was added.

## API and compatibility

- Circuit collection adds q, status, kind, ordering and summary parameters. Explicit
  summary responses omit descriptions, contract projections, dates, lifecycle
  projections and handoffs; queries disable the handoff prefetch. Legacy full
  collection responses retain their shape and default paging.
- Circuit detail adds include_handoffs=false. The new drawer uses this form and
  loads child collections separately; legacy detail and mutation responses retain
  their existing handoff payloads.
- The handoff collection retains its legacy array response unless paginated=true
  is explicitly requested. The paginated shape includes the shared count/page/
  page_size/has_more/can_manage fields and supports q, side and ordering. OpenAPI
  documents both response shapes. Existing list operation IDs remain stable.
- Handoff detail adds GET under NETWORKS_VIEW, scoped by exact workspace and parent.
  Existing PATCH/business rules remain unchanged. Both new GET route variants are
  included in the central permission inventory. Handoff payloads add circuit_id.
- network-circuits and circuit-handoffs preference features use existing permissions
  and persistence. No model, domain-data migration, new permission or dependency.

## Deliberate next slices

Circuit kind/status workflows remain open.
Creation, provider/contract assignment, handoff details/placement and history have subsequent
implementation checkpoints below. Existing public mutation APIs continue to work.
Do not silently expand this work to service disconnection or cross-workspace moves.

Do not describe this checkpoint as complete circuit lifecycle management or Phase 3
acceptance. DNS transfers, endpoint creation/transfers, device relationships and
hardware rebinding, other surfaces, technician walkthroughs and release gates stay
open. Production deployment/publication are separate from the authorized local
rebuild.

## Verification

See progress.md for executed evidence. Coverage includes off-page identifiers,
31 circuits and 31 handoffs, legacy compatibility, bounded query behavior, stable
sorts, parent/sibling isolation, read-only/unavailable states, dirty failed saves,
partial-edit preservation, direct links, full-page/Back navigation, return focus,
320/390/768/1024/1280/1440 widths, short-height touch edits, 200% zoom and axe checks.

The isolated live rehearsal seeds a circuit and handoff through the existing API,
edits service notes through the browser, reloads, opens/returns from the handoff
and reads circuit history. Independent PostgreSQL assertions verify exact ownership,
provider, retained identifier/status, absent contract/interface linkage and a single
update audit event. These fixtures do not modify existing user or demo data.


Final verification: `make check` passes with 553 frontend tests; all 33 circuit
browser cases and six focused component cases pass. The complete serial
`make test-network-validation` passes, including migration/isolation restoration,
the new legacy detail query-count regression and stabilization. The initial
circuit/preferences API set passes 18 cases. `make test-e2e-live` passes, including
the independent database assertions. Final backend Ruff/mypy, OpenAPI/generated
types, frontend lint/type checks and the original build budgets pass. No existing
API operation ID changed. Earlier discarded harness runs are documented in
progress.md and are not counted as successful evidence.

## Provider/contract choice API prerequisite

The creation/assignment prerequisite adds an opt-in interface on the existing
`circuits/choices` route: `choice=providers|contracts`, `q`, `page`, `page_size`
(default 25, maximum 100), optional `selected_id`, and `provider_id` for contracts.
It returns `results`, `selected`, count/page/page_size/has_more, and
`can_view_contracts`. Search covers choice names across the full authorized
collection, with name/entity-ID ordering. `selected` is resolved independently
of search/paging but within the same workspace, permission and provider filter;
unavailable selections return null. It is never inserted into the result page.
Contract requests require the existing assets-view permission. No costs, histories,
or placement choices are fetched. A request without parameters retains the legacy
six-array response and limits. Query typos or filters without a choice are rejected.
OpenAPI describes both shapes; the frontend has a separate `circuitChoicePage`
adapter, preserving its legacy helper. No new route, permission or migration.

This API prerequisite supports the subsequent creation UI checkpoint. The UI must
use these bounded choices, retain chosen labels across searches, clear/reconfirm
incompatible contracts when providers change, and preserve drafts on failed saves.
Hidden contract/provider changes must still follow existing mutation permissions.

## Circuit creation and provider/contract editing

The register now offers New circuit to network editors. A focused form in the same
full-screen/right overlay creates a named service with service identifier, kind,
provider, optional contract and notes. New records explicitly start Ordered; dates,
bandwidth and operational status remain separate service/lifecycle workflows.
Successful creation opens the saved Overview without losing collection context or
leaving a dirty guard. Contract/provider updates use a separate focused section;
only changed provider and visible contract linkage are submitted, preserving all
service fields. A restricted contract projection hides assignment editing. Selecting
a different provider clears the draft contract and remounts its provider-filtered
picker. Removing a selection is a draft action until Save.

Pickers request 25 choices with name search and paging. Selected labels remain
visible outside the current page/search, and retained-selection availability is
checked within the API's permission/provider boundary. Failed reads offer Retry;
failed writes preserve input and never retry automatically. The existing server
validates provider/contract compatibility and permissions at mutation time. Dirty
forms use Keep editing/Discard for cancellation, drawer dismissal and navigation.
No additional drawer, CSS, domain model, migration or public API change is needed.
Handoff-specific history, kind/status transitions and Phase 3 acceptance remain open.

## Handoff creation, details and placement checkpoint

Handoffs offers New handoff for network editors. Creation takes name, side, media,
connector, provider reference and notes; optional placement is explicitly unassigned.
It opens selected child detail within the same circuit drawer and URL. Detail and
placement edits are separate forms, one at a time. Detail PATCH submits only its
fields, preserving placement. Placement PATCH submits site/location/device/interface
IDs, preserving identity and service facts. Cancel, dismissal and navigation guard
dirty forms; errors retain drafts and never trigger uncertain automatic retries.
Successful save returns to the focused handoff heading; Back to handoffs restores
row focus. Read-only viewers retain details and have no create/edit actions.

Placement reuses existing bounded APIs: site and site-scoped location choices,
device register summaries and device-scoped interface summaries, all pages of 25
with name search. Selected labels stay visible outside result pages. Location and
interface pickers load only after their parent is chosen. Changing site clears all
placement dependencies; changing device clears interface. Clear buttons alter drafts
until Save. Device choices include unplaced devices, which existing handoff rules
permit; the server rejects site contradictions, wrong parent links, workspace/tenant
mismatches and interface reuse by another handoff. Failed writes retain selections.

The previous read-only handoff view is replaced by HandoffView. Existing
mutation endpoints already support partial PATCH and emit circuit-owned handoff
audit events; frontend mutation types now reflect partial values and the already
returned circuit_id. No new endpoint, schema, migration, permission, dependency or
CSS. Handoff-specific history presentation and circuit kind/status workflows remain
open, as do wider Phase 3 and pre-1.0 acceptance.


## Selected handoff history checkpoint

Phase 3 (#80, under #60/#75): selected handoffs now offer View handoff history
inside the existing circuit drawer. This is a focused reader with a return link,
not another drawer or child tab bar. `handoff_section=history` and
`handoff_history_page` make the reader and its 25-event pages refreshable and
bookmarkable. History loads only when requested; returning restores the handoff
heading. Changing handoffs or leaving the circuit clears child history parameters,
including through mobile return links. Existing dirty edit guards remain authoritative.

The existing authenticated activity API adds optional `handoff_id`, requiring
`entity_id` to identify its parent circuit. Both activity-view and network-view
permissions apply in the exact workspace. A mismatched/unavailable parent-child
pair is denied before audit selection. Filtering uses the existing parent-owned
handoff audit metadata and only handoff-created/updated actions; counts, actions
and deterministic ordering are calculated after filtering. Event metadata is not
returned. Legacy queries retain their behavior. OpenAPI and generated types are
updated; no persistence, domain-data or audit migration is required.

Empty, denied and failed history retain the return path; failed requests retry only
on user action. Wider Phase 3 acceptance and circuit kind/status workflows remain
open. Earlier statements that handoff history is open describe prior checkpoints.


### Build-on notes and remaining circuit slice

History displays the event action, actor and time. Existing handoff audit metadata
contains only the handoff identifier, so this change cannot reconstruct old field
values or placement diffs. A future richer audit model must preserve append-only
history and distinguish newly captured data from historical events with no diff.

The next circuit slice can reuse the existing partial PATCH serializer for kind
and status. Current server enums are Internet/WAN/MPLS/Dark fiber/Broadband/Cellular/
Voice/Other and Ordered/Provisioning/Active/Suspended/Disconnected. The present
backend validates and records documentation changes; it does not invoke a carrier
or provisioning integration. Use a separate focused form for kind and a deliberate
status workflow, with confirmation for consequential suspension/disconnection.
Submit only the selected fields, retain failed drafts, use the existing navigation
guard, and keep lifecycle warnings on Overview. Cover permissions, unrelated-field
preservation, failure/confirmation states, updated list filters, full-page/drawer
parity and the live PostgreSQL journey before calling that slice complete.


Verification: `make check` and the full `make test-network-validation` gate passed;
focused components/API client 27 cases, PostgreSQL circuit/document activity 15
cases, circuit browser 90 cases across maintained browser projects and six widths,
and the isolated live browser→Django→PostgreSQL journey passed. Current local
backend/frontend images are healthy at localhost:3200, version 0.8.46. Detailed
logs and test corrections are recorded in progress.md. Production deployment,
Wiki publication and broader Phase 3 acceptance are separate.
