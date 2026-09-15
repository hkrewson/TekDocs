# Circuit register and service-detail drawers

Pre-1.0 Phase 3 (#80), under #60/#75. Version stays 0.8.46.
Status: verified implementation checkpoint. This is a bounded circuit
browsing/service-editing checkpoint, not completion of circuits or Phase 3.

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

Circuit kind/status workflows,
handoff creation/editing/placement/interface assignment, and handoff-specific
history remain open. They need bounded pickers with off-page retained selections,
existing provider/contract visibility enforcement and placement conflict checks.
The prior component was not mounted in the shell; removing it does not remove an
active creation workflow. Existing public mutation APIs continue to work. Creation and provider/contract editing are implemented in the subsequent checkpoint below.

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
Handoff editing, placement, kind/status transitions and Phase 3 acceptance remain open.
