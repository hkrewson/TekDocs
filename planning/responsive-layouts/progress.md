# Progress and verification

Updated 2026-09-12. Version 0.8.46. Epic #77; existing delivery obligations remain open.

## Completed implementation slices

The Assets summary collection and typed browser API client are implemented under #86. This is a foundation slice, not completion of Phase 1 or the Assets redesign. The navigation slice adds the data router, capability-derived organization routes and registered Assets edit protection under #88; see [navigation-foundation.md](navigation-foundation.md). See [the API contract and integration notes](asset-collection.md). Personal collection preference persistence and its browser client are the next implemented foundation under #87; the chooser is now integrated in the Assets reference layout; see [assets-layout.md](assets-layout.md).

## Phase status

| Phase | Status | Outstanding completion boundary |
|---|---|---|
| 1 — Inventory/foundation | In progress | Expand nested states, extract reusable record header/sections through validation surfaces, and complete acceptance evidence; list/drawer/chooser and URL-backed Assets records implemented |
| 2 — Assets | In progress | Layout, preview actions, site filtering and software audit history implemented; expanded state/technician/release acceptance remains |
| 3 — Contracts/Networks | In progress: Contracts and simplified Networks collection/full record migrations | Remaining network object surfaces, wider validation and phase acceptance |
| 4 — Operational records | Pending | All planned migrations |
| 5 — Documentation/files | Pending | All planned migrations |
| 6 — Financial/compliance/integrations | Pending | All planned migrations |
| 7 — Shell/remaining surfaces | Pending | All planned migrations |
| 8 — Acceptance | Pending | Technician, browser, production-image and release evidence for every supported surface |

No route is marked fully accepted. Assets has an implemented replacement layout with remaining acceptance work. The shell route inventory uses actual App.tsx declarations; organization areas now derive from the existing capability registry. Additional auth/portal/shell states are recorded separately; nested record/workflow coverage remains an explicit task.

## Verified — Assets collection checkpoint

- `make check`: version, supply-chain, repository/security evidence tooling, Wiki/product/language contracts, Compose, workflow lint, backend lint/typecheck, migration drift, OpenAPI drift, generated types, frontend lint/typecheck/unit tests/build and bundle budgets pass (451 frontend tests across 97 files; backend typecheck covers 191 source files).
- Docker focused browser-client tests: five tests pass, including new collection URL encoding, false boolean filters, cancellation forwarding, detail errors without retries, and legacy calls.
- Docker/PostgreSQL focused collection tests pass, including the constrained runtime-role client-access test. Final combined collection/route-inventory check: six tests passed (three collection tests and three route-inventory/authentication/malformed-path checks).
- No schema migration or application version change. Existing API behavior remains covered by compatibility assertions.

## Not yet verified

Whole-page visual migration, the full responsive/browser matrix, preferences migration/upgrade/recovery, technician walkthrough and full release acceptance remain open. The edit-confirmation slice has focused browser evidence; see the checkpoint below. These remain required before the corresponding phase closes. There is no external blocker; this is remaining implementation work.

## Reproduction

Build local development test images (without replacing application containers), then run `make check`. Run focused backend checks with `docker compose run --rm migrate pytest apps/core/tests/test_asset_collections.py apps/core/tests/test_permission_idor_matrix.py -q -k 'asset_collection or asset-collection or test_route_permission_inventory'`. These operate on isolated test data. Frontend coverage includes `frontend/src/inventory/api.test.ts` in the ordinary frontend gate.

The sibling Wiki Roadmap has an uncommitted scoped update. Pre-existing Wiki edits remain untouched. No push, deployment or Wiki publication has been performed.

## Navigation checkpoint — 2026-09-12

- Implemented: data router, capability-derived organization route registration, registered Assets dirty/active/busy edit handling, Keep/Discard/native unload, and independent hardware history refresh with retry.
- Focused browser verification: 27 tests pass across Chromium, Firefox and WebKit. Six viewport widths, 600px height, keyboard focus/background locking, axe checks, Back/Forward, native refresh cancellation, and post-Keep-editing hardware request values are covered.
- Final `make check` passes: 459 frontend tests across 98 files, backend typechecking, contract/drift checks and production build. Original bundle limits remain unchanged: shell 130,940 / 131,072 compressed bytes; shell stylesheet 24,571 / 24,576 bytes. This leaves little shell budget headroom; future foundation components should remain feature-loaded.
- Final `make test-e2e-live` passes, including the real browser journey and independent PostgreSQL fixture verification. The first attempt exposed a delayed modal-dismissal race through its asset-tag database assertion; the fix passes the strengthened request assertions and five repeated Chromium reproductions. No database assertion was weakened.
- Evidence logs: `/tmp/tekdocs-layout-navigation-make-final.log`, `/tmp/tekdocs-layout-navigation-browser-final.log`, `/tmp/tekdocs-layout-navigation-race-repeat.log`, and `/tmp/tekdocs-layout-navigation-live-final.log`. These local logs are ephemeral; the reproducible checks and regression assertions are retained in source.
- Verified scope: the registered Assets editing workflows and shared guard. No external blocker. Wider record navigation, layout acceptance and release gates remain pending rather than inferred from these results.
- Remaining next implementation: personal collection preferences (#87), then the Assets list/drawer/tabbed record slice (#79) and URL/scroll-restoration work remaining in #88. No supported route is yet marked fully migrated.

## Personal preferences checkpoint — 2026-09-12

- Implemented foundation under #87: authenticated Assets preference API, installation/user ownership and forced RLS, migration 0149, generated types and browser client with safe read defaults and explicit write failures. See [personal-preferences.md](personal-preferences.md).
- Verified: 19 focused API/authorization/isolation/CSRF checks passed; the final preference suite separately passed all 12 cases, including malformed requests and upgrade/restore. Six browser-client tests passed. Final `make check` passes with 465 frontend tests across 99 files, backend typechecking over 192 files, migration/OpenAPI/generated-type checks and unchanged bundle limits. Final `make test-e2e-live` passes both the real browser journey and independent PostgreSQL fixture verification. The column chooser and Assets list integration remain pending; no route is marked migrated.
- Next: integrate the preference API into the shared column chooser and replace the Assets collection with the planned responsive list, preview and record navigation (#79).

- Evidence logs (ephemeral local artifacts): `/tmp/tekdocs-preferences-make-verified.log`, `/tmp/tekdocs-preferences-verified-api.log`, `/tmp/tekdocs-preferences-tests-complete.log`, `/tmp/tekdocs-preferences-client2.log`, and `/tmp/tekdocs-preferences-live-final.log`. Reproductions and assertions are retained in source.
- Known limits: last successful preference write wins between devices; there is no chooser UI yet. Full supported backup/recovery, responsive visual acceptance and release gates remain required. No external blocker. The sibling Wiki Roadmap has a scoped, uncommitted update; pre-existing Wiki work is preserved. No push, deployment or Wiki publication.

## Assets visible layout checkpoint — 2026-09-12

Implemented under #79: bounded summary table/mobile rows, persistent column chooser/reset and page size, shared modal preview with bounded status action, record/section URLs, focused tabs and on-demand hardware history, list context/focus restoration, page-only selection and registered relationship editing. The old split layout and lifecycle below the collection are removed. See [assets-layout.md](assets-layout.md) for implementation details, URL compatibility, reproduction notes and remaining scope.

**Verified:** `make check` passes, including 468 frontend tests across 99 files, lint/typecheck, API/schema/type drift and unchanged production bundle budgets. Final focused browser matrix passes 60 tests across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440px and short heights, plus touch and 200% CSS zoom stress. Final `make test-e2e-live` passes the isolated browser-to-Django-to-PostgreSQL journey and independent database fixture verification. Desktop list and 320px preview screenshots were visually inspected. Final browser-test lint and `git diff --check` pass.

Reproductions retained in source: preference reset previously opened an unintended navigation confirmation; a commit-boundary reset fixes it (five repeated checks). Viewport-unit drawer height exceeded the zoomed viewport; inset sizing fixes the bounds assertions in all engines. A save-button-disabled assertion could mean either pending or completed save, so closing tests now also await the status selector becoming enabled. A deterministic paused-request browser scenario verifies pending saves retain close protection; filtered departure passed five repeat checks before the full matrix.

Evidence logs (ephemeral): `/tmp/tekdocs-assets-layout-check3.log`, `/tmp/tekdocs-assets-layout-browser6.log`, `/tmp/tekdocs-assets-layout-live3.log`, `/tmp/tekdocs-assets-filter-repeat.log` and `/tmp/tekdocs-assets-layout-final-lint.log`. Durable assertions are linked from the implementation record.

**Remaining, not blocked:** preview assignment, site chooser, software history presentation, reusable record header/sections, expanded stale/conflict/permission-state acceptance, manual native zoom/screen-reader/mobile-keyboard and technician walkthroughs, followed by applicable production/recovery/release gates. CSS zoom does not substitute for native browser zoom acceptance. Other surfaces remain pending. No phase/epic closure is claimed. Version remains 0.8.46; no push, deployment or Wiki publication. The sibling Wiki has a scoped local checkpoint alongside preserved earlier edits.

## Preview assignment implementation — 2026-09-12

Implemented under #79: a focused Assign hardware action inside the existing preview, using the established assignment choices and write endpoint. Status and assignment editors are mutually exclusive. Choice loading can be retried; failed mutations retain selected person/site/location without automatic retry. Site changes clear incompatible locations, and selecting a location supplies its owning site. Server-returned lifecycle state is accepted after save, including automatic in-stock-to-in-service transitions.

Durable coverage: `Assets.test.tsx` adds denial/conflict/request-failure retention, canceled navigation/discard, failed choice-read retry, site/location consistency and server lifecycle reconciliation. `asset-layout.spec.ts` adds six responsive assignment scenarios per browser with accessibility scans and focus restoration. `live-workspace.spec.ts` now performs assignment in the preview and verifies the result in the full record; its independent database assertions are retained.

During verification, the new browser scenario reproduced exact-label lookup failures for implicit select labels containing options; selectors now have explicit accessible labels, while the named-dialog and exact-label assertions remain. An initial production build failed on unsupported Testing Library `exact` options in new tests; string role names already match exactly, and correcting the test options restores type checking. No production logic or permission assertion was removed to pass either check.

This remains required pre-1.0, at 0.8.46. Site picker, software history, reusable record header/sections, expanded stale/permission-state acceptance, technician/native zoom/screen-reader validation and later surface migrations remain open. No external blocker is known. No schema or API contract changes, migration, push, deployment or publication are part of this slice.

The live assignment rehearsal also reproduced an ambiguous broad Site lookup matching the collection sort selector behind the drawer. Its assignment fields now use exact labels scoped to the named preview; save/full-record/database verification remains unchanged.

The full component gate reproduced an existing MAC-editor timing assumption: its heading arrived before the separate collection permission metadata, so an immediate Add address lookup failed. The test now awaits that authorized control, preserving its mutation and rendered-address assertions. No authorization was bypassed.

Verified runtime and browser evidence: the final focused browser matrix passes 78 tests across Chromium, Firefox and WebKit; the final `make test-e2e-live` passes the isolated Django/PostgreSQL journey and independent database fixture verification. The final live-test lint passes. Logs: `/tmp/tekdocs-preview-assignment-browser2.log`, `/tmp/tekdocs-preview-assignment-live3.log`, `/tmp/tekdocs-preview-assignment-live-lint.log`. Earlier focused component checks passed 21 Assets tests. These logs are ephemeral; source assertions are the durable evidence.

Final project gate: `make check` passes, including 473 frontend tests across 99 files, lint/typecheck, API/schema/generated-type drift, production build and unchanged bundle budgets. Evidence: `/tmp/tekdocs-preview-assignment-check3.log`. Wiki/product contracts and diff checks pass. This checkpoint is implemented and verified within its stated scope; Phase 1/2 and the overall layout epic remain open.

## Assets Site picker checkpoint — 2026-09-12

Implemented under #79/#86: searchable, paginated Site choices in the shared filter menu; named removable URL conditions; refresh/list-return preservation; loading/retry/unavailable-selected handling; and an additive minimal site-choice API. The API returns only site identities already exposed by active authorized assets in the exact workspace, including software installations. It does not expose site addresses or location trees or change Sites-management access. OpenAPI, generated types and route permission inventory are aligned. See [asset-site-filter.md](asset-site-filter.md).

Reproduced and addressed: a narrow-screen filter menu could extend left of the viewport; the Assets toolbar now anchors it within the available width and bounds its scrolling height. Choice rows remain mounted during selected-site metadata refresh. Browser assertions await the checked state after the asynchronous URL transition instead of assuming a synchronous controlled-radio update; checked state, URL, results and selection clearing all remain asserted.

The build budget caught a startup payload overrun. Redundant selected-site copy was removed and standard pagination messages reused. That was insufficient, so the static Overview content was extracted into an on-demand route module as a small #40/#78 navigation-foundation follow-up. The heading, content, capability table and navigation stay unchanged; the route has an explicit loading state and its existing test awaits the loaded heading. No budget was increased. An attempted locale simplification was reverted and is not part of the final implementation.

No schema or model migration, version change, push, deployment or Wiki publication is included. Software history presentation, reusable record header/sections, expanded stale/conflict/permission-transition acceptance, technician/native zoom/screen-reader checks and subsequent surface migrations remain open. The Site picker is no longer an outstanding implementation item; whole-phase acceptance is still required.

The long-value browser scenario reproduced an active-filter chip causing horizontal page overflow at 320 pixels. Filter buttons now wrap long labels within their available width. The final focused matrix passes all 96 checks across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440 pixels, including off-page site search, refresh, removal and selection clearing (`/tmp/tekdocs-site-browser-final2.log`). The full project gate subsequently passed; the live gate result is recorded below.

The real-stack Site-filter rehearsal reproduced assigned hardware disappearing from collection results. A direct serializer reproduction showed that DRF treated an omitted optional Boolean query parameter as an unchecked HTML checkbox (`assigned=False`). The collection now uses an optional query Boolean field whose omitted value remains absent. Explicit true/false behavior remains intact. Regression coverage includes actual person-assigned hardware filtered by site under the restricted PostgreSQL role, absent/true/false query parsing, and the live response containing the assigned switch after refresh. The temporary live diagnostics were removed; the stronger result assertion remains.

With optional assignment filtering corrected, the live Assets selection/refresh/full-record sequence passed. The continued documentation journey reproduced a broad Markdown assertion matching both a search excerpt and the rendered paragraph. It now matches the exact paragraph text, retaining the imported heading, success state and canonical content checks. No document behavior changed.

Verified project evidence: `make check` passes (475 frontend tests across 100 files, lint/typecheck, schema/generated-type drift, production build and unchanged bundle budgets; `/tmp/tekdocs-site-check6.log`). The final live-assertion lint also passes (`/tmp/tekdocs-site-final-live-lint.log`). All eight collection API tests pass, plus the nine-test focused site/permission/query matrix (`/tmp/tekdocs-site-all-api.log`, `/tmp/tekdocs-site-fixed-api.log`). Wiki/product contracts and diff checks pass. No model migration or recovery-format change is needed. The startup shell/style budgets remain close to their limits; later migrations should continue loading feature content on demand rather than increasing the thresholds.

Verified live evidence: the final `make test-e2e-live` passes the isolated real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-site-live7.log`). This includes assigning hardware, selecting its site, refresh, full-record navigation, subsequent document import and client-portal/recurring-invoice coverage. Synthetic fixtures were isolated and existing user/demo data was preserved. This bounded Site-picker checkpoint is implemented and verified; no external blocker is known. Whole-phase technician/accessibility/release acceptance remains open. Source tests and this record are durable; `/tmp` logs are ephemeral.

## Shared record navigation checkpoint — 2026-09-12

Implemented under #78/#79 in preparation for #40 and Phase 3: Assets now uses shared RecordHeader and RecordSections components. Complete URLs, ordinary desktop links, the mobile Sections selector, list-return navigation state, record/section heading focus and the existing dirty-form guard are retained. Record content, permissions, urgent warnings and section fetches remain domain-owned. See [record-navigation.md](record-navigation.md) for the consumer contract and remaining validation through Contracts/Networks. No second Assets implementation or demonstration route remains.

Focused component verification passes the integrated Assets suite and shared navigation scenarios, including canceled/discarded mobile changes, retained drafts, URL history, transient state and focus. The browser suite adds section focus and Back/Forward assertions at all six widths. Final project/browser/live results follow after completion. No backend, API/schema/model/recovery-format, version or deployment change is required.

Verified: `make check` passes lint/typecheck, the full component suite, schema/generated-type drift, production build and unchanged bundle budgets (`/tmp/tekdocs-record-nav-check.log`). The final two shared-navigation behavior tests also pass independently after removing a redundant rendering-only assertion (`/tmp/tekdocs-record-nav-focused-final.log`); all 21 Assets integration tests passed in the focused run. All 96 maintained browser checks pass across Chromium/Firefox/WebKit and six widths (`/tmp/tekdocs-record-nav-browser.log`). The isolated `make test-e2e-live` journey and independent PostgreSQL fixture verification pass (`/tmp/tekdocs-record-nav-live.log`). Existing user/demo data was preserved. Wiki/product contracts and diff checks pass.

This extraction checkpoint is implemented and verified; no external blocker is known. Contracts/Networks reuse, software history and whole-phase accessibility/technician/production/recovery/release acceptance remain open. The executable test sources and component contract are durable; temporary logs are ephemeral. No push, deployment or Wiki publication is included.

## Software audit history checkpoint — 2026-09-12

Implemented under #79/#86: software History now reads actual creation/update audit events for the selected record, on demand, with 25-event pages and URL-addressed history page state. The existing Activity permission is preserved. Empty, denied, failed, loading and retry states are distinct; canceled/late reads cannot replace another page. This does not invent past installation values or expose metadata. See [software-history.md](software-history.md) for API and navigation contracts.

The additive activity entity filter is applied within the existing workspace/tenant scope before counts and action summaries. Legacy consumers retain their defaults. OpenAPI/generated types document the supported query interface. Focused API/runtime-role and component/client checks pass; final full project/browser/live results follow. No model/migration/RLS/recovery-format or version change is required. Contracts/Networks and broader phase acceptance remain open.

Verification reproduced a blank `entity_id=` being discarded by DRF as an omitted optional HTML form field, broadening the activity query. The new filter now preserves supplied values for UUID validation; blank/malformed identifiers are rejected, while genuine omission retains legacy workspace activity. A regression assertion covers the blank case. The initial live run completed software History but its renderer crashed later during publication withdrawal; the rerun uses the unchanged journey assertions after other heavy checks finish. Test-helper lint findings were corrected without removing its canceled/stale-response assertions.

Verified project evidence: `make check` passes with 480 frontend tests across 102 files, API/generated-type drift, lint/typecheck, production build and unchanged bundle budgets (`/tmp/tekdocs-software-history-check3.log`). Final backend lint/typecheck/schema drift checks also pass after the blank-filter fix (`/tmp/tekdocs-software-history-final-backend.log`). All four focused API scenarios pass, including restricted-role pagination and blank/malformed query denial (`/tmp/tekdocs-software-history-api2.log`). All 114 browser checks pass across three engines and six widths, including completed-page heading focus (`/tmp/tekdocs-software-history-browser2.log`). Wiki/product contracts and diff checks pass. The final live result follows below.

Verified live evidence: the final isolated `make test-e2e-live` passes the real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-software-history-live2.log`). Actual software creation/update events are visible after installation editing and refresh. The later publication withdrawal and portal/recurring workflows also pass with unchanged assertions; the earlier renderer crash was not reproduced. Existing user/demo data was preserved. No external blocker is known.

The final visible-focus check reproduced the History heading receiving focus outside the viewport on four Chromium desktop widths after paging. History page navigation now allows the browser to bring its focused heading into view; record/list return restoration is unchanged. The strengthened assertion requires both focus and viewport visibility across all maintained widths/engines.

Final focus correction verified: targeted lint/typecheck/production build and all 18 software-history browser scenarios pass with both heading focus and viewport visibility asserted (`/tmp/tekdocs-software-history-focus-fixed.log`). This is the focused follow-up to the passing 114-test matrix and full project gate. The bounded software-history checkpoint is implemented and verified. Contracts/Networks reuse and remaining phase accessibility/technician/production/recovery/release acceptance stay open. No push, deployment or Wiki publication is included. Executable tests and these notes are durable; temporary logs are ephemeral.

## Full asset record drawer checkpoint — 2026-09-13

User validation revised #79: the quick preview repeated the row and added an unnecessary full-record step. Asset names now open the complete record in a broad overlay/full-screen mobile drawer. Both presentations share AssetRecord sections and editing; the row-level Open record link is removed, with optional Open in full page inside the drawer preserving the selected section. The accepted contract, route/state inventory and implementation notes are updated; see [asset-record-drawer.md](asset-record-drawer.md). Version remains 0.8.46.

The drawer uses shared assignment, detail, network/installation, relationship and history content. The former quick-status component and duplicated assignment editor are replaced by shared Overview editing. Close exits the whole drawer after section navigation, with dirty/busy protection; URLs and browser navigation remain compatible. Screenshots exposed tiny inherited lifecycle text and redundant section spacing; record-scoped styling now restores readable fact/form sizes and a compact heading. Background locking and a single drawer scrolling body remain.

The first browser run reproduced a test race: its new reopen/Escape sequence sent Escape before the asynchronously opened drawer mounted, then attempted to click the now-inert background. The test now waits for the visible drawer and focused Close button before Escape. No application delay, forced click, reduced assertion, or weakened timeout was added. Final gate evidence follows below. No backend/API/model/recovery-format change is needed; user/demo data remains protected. Local refresh is authorized; production deployment and publication remain separate.

The next completed matrix exposed a second transition race in two narrow Chromium cases: the test matched the still-open drawer heading after clicking Open in full page, then changed its Sections selector before navigation completed. The browser test now requires the drawer to close, the record URL to appear, and the full-page h1 to be visible before section interaction. All heading-focus and Back/Forward assertions remain.

Verified: `make check` passes all 480 frontend tests across 102 files, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-full-drawer-check.log`). Final record-scoped readability styling and explicit browser-transition assertions are covered by the follow-up lint/build/browser run. The local Wiki Roadmap has the scoped contract update, but a full-checkout Wiki validation is blocked by pre-existing missing pages in this older local Wiki clone; the repository manifest/contextual-topic contract passes. No missing pages were fabricated or unrelated Wiki work overwritten.

Verified final browser evidence: all 117 checks pass across Chromium, Firefox and WebKit at 320/390/768/1024/1280/1440 pixels, including drawer section refresh/close, full-page transitions, dirty edits, assignment, focus, accessibility scans and touch/CSS zoom (`/tmp/tekdocs-full-drawer-browser-final.log`). The same final run passes frontend lint, typechecking, production build and unchanged bundle budgets after the readability adjustment. Desktop/mobile screenshots were visually inspected; executable tests and the contract notes are durable, while `/tmp/tekdocs-full-drawer-images` and logs are ephemeral. Live evidence follows below.

Verified live evidence: `make test-e2e-live` passes the isolated real browser-to-Django-to-PostgreSQL journey and independent database fixture assertions (`/tmp/tekdocs-full-drawer-live.log`). Hardware details, assignment and network addresses save inside the full drawer, with retained full-page verification. Subsequent documentation, portal and recurring workflows pass. Existing user/demo data was preserved. The bounded full-drawer implementation is verified; broader phase/technician/release acceptance and the pre-existing incomplete local Wiki checkout remain open.

## Assets refresh/public-port correction — 2026-09-13

Follow-up to #79 at 0.8.46: direct HTTP reproduction returned `301 Location: http://localhost:8080/assets/` for `/assets` at local port 3200. An HTTPS-proxy-header reproduction also returned `http://docs.example.invalid:8080/assets/`. The route collided with Nginx's physical bundle directory; client-side navigation avoided the document request, explaining intermittent refresh behavior. Both route spellings now serve the revalidated entry document directly, and Nginx-generated directory redirects are relative. Bundle caching, missing-chunk 404s and security headers remain intact.

Verified: the new real-production-image `make test-frontend-routing` gate passes all three scenarios, including local/proxy route subcases and static-file behavior (`/tmp/tekdocs-port-routing-final.log`). Its corrected root-directory probe independently failed against the old image with the exact internal-port Location before passing with the fix (`/tmp/tekdocs-port-routing-before2.log`). The gate is included in release acceptance. See [frontend-routing.md](frontend-routing.md) for cached-redirect recovery and rollout boundaries. No backend/API/schema/recovery-format or version change is involved. Final project/local-refresh evidence follows.

Verified final evidence: `make check` passes, including 480 frontend tests, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-port-routing-check.log`). The authorized local frontend rebuild completed; direct `/assets` with preview/section parameters and `/assets/` under HTTPS proxy headers now return 200 HTML with no Location header and revalidation/security headers. Local readiness reports healthy database/renderer and version 0.8.46. The local Wiki Roadmap is updated without publishing. Production deployment is not performed; the shared-image reproduction supports the cause there, but the remote instance has not been inspected or changed.

## Asset drawer backdrop dismissal — 2026-09-13

User-requested #79 follow-up: outside clicks dismiss the drawer and the Close button is removed. Escape remains; full-screen mobile provides a Back to assets link because there is no exposed backdrop. The dialog heading receives initial focus and Shift-Tab keeps focus inside. Dismissal requires a gesture starting and ending outside, so internal clicks and drag-out gestures remain safe. All paths use the existing dirty/busy guard and list-return callback. The accepted contract, drawer/navigation notes and state inventory are updated. Version stays 0.8.46; no API, model, migration or recovery-format changes are needed. Component checks pass; final browser/project/live evidence follows.

Verified project/browser evidence: `make check` passes all 480 frontend tests, lint/type/schema checks, production build and unchanged bundle budgets (`/tmp/tekdocs-backdrop-check.log`). All 120 focused browser checks pass across Chromium/Firefox/WebKit and six widths (`/tmp/tekdocs-backdrop-browser.log`), including native backdrop gestures, blocked underlying navigation, internal clicks, drag-out protection, mobile return, failed/pending saves, focus restoration, accessibility and touch/CSS zoom. The repository Wiki contract and diff checks pass. Final isolated live and local-refresh evidence follows.

Verified live evidence: `make test-e2e-live` passes the isolated browser-to-Django-to-PostgreSQL journey and independent fixture assertions (`/tmp/tekdocs-backdrop-live.log`). Outside clicks now exercise both dirty Keep editing and clean dismissal after hardware/network saves. Later document, portal and recurring workflows pass unchanged. Existing user/demo data was preserved. The bounded dismissal follow-up is verified; broader layout rollout and technician/release acceptance remain open. Local refresh is authorized; production and Wiki publication remain separate.

## 2026-09-13 — Contracts visible migration (#80)

Contracts in MSP/client workspaces now replaces the old split panels with a bounded
collection and shared full record drawer/page. Overview, Costs, permitted Related
and actual History are URL-addressable. Costs keep currencies/intervals separate;
summary requests never read cost rows and legacy consumers retain their projection.
Personal preferences reuse the existing model; no migration or version change.
See [contracts-layout.md](contracts-layout.md) for the complete implementation and
handoff boundary. Networks remains the next visible migration, not a completed one.

Browser verification: 120 Assets/Contracts checks passed across Chromium, Firefox
and WebKit, plus three contract touch/200% CSS zoom checks. Contract coverage includes
six widths, native-dialog accessibility, focus, outside dismissal, failed-edit guards,
column persistence/reset, off-page search, denied costs and unavailable direct links.
Synthetic mobile/desktop screenshots were reviewed locally. Component-focused checks
passed for Contracts, SoftwareHistory and Assets (28 tests); API-client coverage was
expanded for the explicit summary and detail requests.

Reproduced harness issues: the first new browser tests sent Escape before drawer
focus and refreshed before the preference write completed; synchronization now waits
for those outcomes without removing assertions. The live journey's existing Assets
site check captured an outstanding pre-refresh response whose body was invalidated by
navigation. It now consumes the applied filter response before testing refresh. The
first broad frontend pass had one unrelated SearchResults test exceed its timeout
under concurrent Docker work (480 others passed); that unchanged test passes isolated
(4/4). The full gate is being rerun with fewer concurrent jobs; final results follow.

Final broad verification: `make check` passes (102 component files, 481 tests,
OpenAPI/types, Python lint/type/migration checks and production bundle budgets).
The unchanged SearchResults test passes in the full rerun. The isolated live
browser-to-Django-to-PostgreSQL journey passes, including contract creation, cost
creation, history refresh, subsequent recurring enrollment/stop and retained
record/audit assertions. Browser checks remain 120 combined plus 3 touch/zoom.
No domain-data migration or version change was introduced. Final API/local runtime
completion is recorded below.

API/runtime completion: `make test-commercial` exited successfully, covering
commercial records, recycle bin, permission/IDOR, runtime RLS and migration
stabilization (the suite retains its existing skipped case). `make up` completed
with existing data volumes retained. Local `/api/v1/health/ready` reports status ok,
database/renderer ready and version 0.8.46; `/services` returns 200. Backend/frontend
health checks pass. This is the authorized local refresh only; no production
publication, push or tag occurred. The Wiki Roadmap checkpoint is updated locally.

Verified: this bounded Contracts implementation and the gates above. Inferred:
the transient unrelated search timeout was resource contention; no test or search
code was changed to make it pass. Blocked: none for this checkpoint. Still open:
Networks, later surface migrations, technician/assistive-technology acceptance and
full pre-1.0 release/recovery obligations. Temporary logs/screenshots are local;
executable test sources and these notes are the durable evidence.


## 2026-09-13 — Simplified Networks visible migration (#80)

The supported Networks page now uses bounded responsive rows and full record
drawers/pages. Curated personal columns, global search/VLAN filter/order, on-demand
detail/history, protected inline editing and an optional relationship map replace
the original wide scrolling table and always-loaded topology. Calculated gateways,
range/overlap validation and existing network permissions remain authoritative.
Existing APIs remain compatible; selected GET details and summary query options are
additive. No model/migration/recovery-format/version change. See
[networks-layout.md](networks-layout.md) for the exact scope and follow-up inventory.

Focused component tests pass. All 24 six-width browser checks pass across Chromium,
Firefox and WebKit. Initial mocked-browser failures were reproduced: an overly broad
API mock intercepted page refresh URLs; after narrowing it, the conflict test lacked
the random CSRF cookie required by the real client. The tests retain the assertions
and now exercise their intended request boundaries. Touch/zoom and full gates follow.

Do not mark Phase 3 complete: legacy device/rack/addressing/interface/wireless/DNS/
circuit/NetBox interfaces are not mounted by the current shell and still require
explicit disposition, parent/child layout work and acceptance. Technician walkthroughs
and the existing pre-1.0 security/recovery/release obligations remain open.

The full project gate passes: 102 component files / 481 tests, backend lint/type
and migration checks, OpenAPI/generated types, and production bundle budgets.
All 24 network browser scenarios pass, plus 3 touch/200% CSS zoom scenarios.
Mobile editor screenshots were reviewed locally. The touch test initially used a
DOM-test-only required-field matcher; the browser test now asserts the same native
required property with Playwright's supported matcher. No application assertion was
removed. The final summary/detail TypeScript boundary also passes focused lint and
type checks; summaries cannot be treated as loaded descriptions/notes.

The isolated live browser-to-Django-to-PostgreSQL journey passes, including network
creation, calculated range/gateway and DNS in the drawer, refresh, collection search,
and independently retained database records. The authorized local rebuild completed
with existing volumes retained. Local readiness reports database/renderer ready,
status ok and version 0.8.46; `/networks` returns 200. No production push/publication
or version change. The broader network-validation gate remains in progress; final
completion is recorded below.

Final network validation passed: `make test-network-validation` exited successfully,
covering network inventory/addressing/endpoints/services/circuits, reconciliation,
transfer, relationships, permission/IDOR, runtime RLS, migration stabilization,
network stabilization and a second complete 481-test frontend pass. The existing
suite skip remains unchanged. Final focused type/lint checks pass after tightening
the summary type. Wiki manifest and whitespace checks pass.

Verified: this bounded simplified Networks migration, all checks above, the isolated
live journey and healthy local 0.8.46 runtime. No blocker remains for this checkpoint.
No broader advanced-network or whole-phase acceptance is inferred from those results.
The tracked implementation notes and executable tests are durable; temporary logs and
synthetic screenshots remain local. Production deployment, publication and all
remaining pre-1.0 delivery obligations are separate and remain open.
