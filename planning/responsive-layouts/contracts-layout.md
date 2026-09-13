# Contracts responsive collection and record workspace

Phase 3 (#80), required pre-1.0 under #60/#75. Version stays 0.8.46.
This checkpoint migrates Contracts in both MSP and organization workspaces.
Networks and the rest of Phase 3 remain open.

## User-visible boundary

The old automatically selected split detail and stacked contract/cost panels are
replaced by a bounded collection. Defaults are name, provider, kind, status,
renewal date and end date; the identity column cannot be hidden. Personal columns
and 25/50/100-row sizes use the existing preferences service, with defaults on
failure. Search covers the authorized collection, including reference and provider;
status/kind use the shared filter menu and removable summaries. Every supported
column has server ordering with an entity-ID tie-break.

A name opens the complete record in the shared overlay, following the user-approved
Assets revision. Overview contains operational facts, urgent expiry/renewal warning,
section editing and focused archive confirmation. Costs keeps individual amounts,
currencies, quantities and billing intervals separate. Related is an on-demand,
read-only list of existing links. History is actual entity-filtered audit activity,
with bounded pages; historical field values are not reconstructed.

Outside clicks and Escape close through the shared dirty/busy guard. On screens
below 768 CSS pixels, the drawer fills the screen and offers Back to contracts;
sections use the labeled mobile selector. There is no duplicate Close button.
Open in full page is optional and retains the selected section and history page.
Failed saves preserve entries and require explicit retry. Cancel, tab changes,
closing and navigation honor Keep editing / Discard changes. Consequential archive
and cost removal retain explicit confirmation. No new bulk action is introduced.

## URLs and data loading

Existing `/services` and `/workspaces/organizations/:organizationId/services`
remain valid. `q`, `kind`, `status`, `ordering`, `page`, `page_size` describe the
collection; `preview` opens a drawer; `record` opens the shared content in a full
page; `section` and `history_page` survive refresh and browser navigation.
`create=true` opens the focused creation form. Return navigation retains collection
query state and transient scroll/focus state; direct links return to the owning
collection. An unavailable record has an explicit error and a return path.

`GET .../contracts?summary=true` opts into summary serialization on the existing
bounded API. It never prefetches or serializes ContractCost rows, even for owners.
Legacy callers that omit summary retain their cost projection and page-size default.
The new UI explicitly requests 25 by default. Added search/filter/order/summary
parameters and relationship permission metadata are documented in OpenAPI and
regenerated TypeScript types. Cost ordering is deliberately unsupported.

Only the selected detail is requested. That existing detail endpoint returns its
permitted cost lines; switching sections does not request every contract or reload
the detail. Provider choices load only when editing/creating. Relationships and
history load only when their section is active. Reads abort on workspace/record
changes; response keys prevent stale data from displaying under another selection.

## Permissions, persistence, and compatibility

Existing `assets.view`, edit permissions and `costs.view` remain authoritative.
The server's existing commercial-contract relationship rule also requires cost
visibility; the new metadata/UI preserves it. Cost-denied users see an explanatory
Costs state and no financial actions or Related section. The summaries never offer
financial columns. Server mutations continue to revalidate workspace authorization.

Preferences adds only the `contracts` feature/column registry to the existing
installation/user-scoped model and API. No model, domain migration, RLS classification,
backup format or recovery procedure changes. Existing ownership/RLS and preference
isolation tests remain applicable; this feature has explicit save/reset coverage.

RecordActivity extracts the existing SoftwareHistory implementation so both features
share denied/error/loading, entity filtering, history pagination and focus behavior.
The asset wrapper retains its wording and action labels. QuickDrawer now receives a
feature-specific mobile return label; Assets still says Back to assets.

## Verification and follow-up

Executable coverage lives in `frontend/e2e/contract-layout.spec.ts`, Contracts/API
component tests, commercial API tests and the real-stack workspace journey.
The browser matrix covers all six required widths, touch and 200% CSS zoom, long identifiers, no page/drawer
overflow, heading/return focus, native dialog semantics, separate currencies,
refresh, Back/Forward, optional full page, off-page search, columns/reset, denied
costs, unavailable links and failed dirty edits. The live journey creates a contract
and cost, checks actual cost history after refresh, closes the drawer and continues
into recurring enrollment; retained database assertions remain authoritative.

An initial browser run reproduced test races: Escape ran before the asynchronous
drawer opened and refresh ran before preference persistence completed. Tests now
assert focused drawer heading and changed columns before proceeding. A provider
fixture also used the wrong endpoint; it now mocks the real `/contracts/providers`.
The live creation test now also waits for the New contract drawer and scopes its name field there; the old unscoped partial label matched the new ordering select before the drawer mounted. These changes add synchronization and preserve the original behavioral assertions.

Final gate results are recorded in progress.md. Technician validation (#39), the
broader touch/assistive-technology and 200% zoom acceptance inventory, production
rollout and full release/recovery obligations remain open. Networks is the next
visible migration, starting with record-specific lists and parent/child details.
