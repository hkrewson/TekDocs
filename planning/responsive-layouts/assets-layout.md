# Assets reference layout checkpoint — 0.8.46

Scope: #79, with shared foundation work under #78/#87/#88. Required pre-1.0 under #77/#60; existing #75 delivery, security, recovery and recurring-invoice obligations remain open. This checkpoint replaces the visible Assets split layout. It does not close Phase 1, Phase 2 or whole-application acceptance.

## Implemented behavior

The collection is a balanced table with curated name, model/type, status, assignment, site and warranty columns. Below 768 CSS pixels, rows become labeled compact records. Identity remains visible; a column chooser saves personal choices through the existing preferences API. Reset restores curated columns and default page size. Search/filter/order/paging use the existing additive summary API across the authorized collection, with 25/50/100 rows. Bulk selection clears when collection context changes and remains limited to the loaded page; existing server validation remains authoritative.

Names open a native modal preview, a right overlay on larger screens and full screen below 768px. The background is locked; only the drawer body scrolls. The preview shows identity, serial/tag, status, assignment, location and warranty, and allows ordinary hardware status changes or a focused assignment action. Disposal is excluded from this action. Long names have a short heading and explicit Full name disclosure. Separate full-record links support new tabs and bookmarks.

The full record owns lifecycle information; no record panel remains below the collection. Overview retains urgent warranty/disposal warnings. Specifications retains the existing Markdown reader and published product documents. Network owns hardware addresses; Installation owns the software editor. Related is permission-filtered and opens the optional graph on demand. Hardware history is fetched only when History opens. Existing lifecycle, assignment, installation, address, relationship, CSV and bulk business workflows remain in use. Related editing now registers with shared dirty/busy navigation protection.

## URLs and loading

Existing collection paths remain unchanged. Query parameters encode `search`, `kind`, `status`, `assigned`, `warranty`, `site`, `ordering`, `page` and `page_size`. A preview adds `preview=<asset-id>`; a record adds `record=<asset-id>` and optional `section=specifications|network|installation|related|history`. Omitted section means Overview. Record and preview are mutually exclusive in generated links. Invalid/unavailable sections display Overview; unavailable record requests show an explicit error rather than selecting a different row.

List rendering requests bounded summaries and permission metadata. Selected record details use the existing detail API. That response still includes the selected record's specifications, document references and addresses; this slice does not introduce new tab endpoints. Histories and relationship graph reads are deferred. Legacy public list behavior is unchanged. No domain schema, API contract, generated types or migration changes are needed for this presentation slice.

Collection URLs carry durable context. Browser navigation state carries transient list scroll position and focused row identity. Closing a preview restores focus; an updated row that has left the current page/filter restores focus to the collection heading and shows a notice. A direct record link returns to its owning collection. Create success supplies an explicit Open created asset link after the form completes.

## Failure handling and reproduced defects

Failed writes preserve drafts and expose errors. Closing/changing records or sections uses shared Keep editing/Discard protection; uncertain mutations are not automatically retried. Preference load failure falls back to defaults; a failed chooser write retains the choices for retry or cancel.

The reset browser scenario reproduced a stale React Router busy predicate: after successful reset, clearing page-size URL state opened a Ready to leave confirmation. The URL reset now waits for the clean guard state and the parent effect commit through a cancellable animation frame. Five repeated Chromium regressions passed before the full browser matrix.

A 200% root CSS zoom stress case reproduced an oversized drawer in all maintained engines. Fixed top/bottom positioning now determines its height instead of an explicit viewport-unit height. Tests retain both viewport bounds and document overflow assertions. This is CSS zoom stress evidence, not a claim of manual native-browser zoom acceptance.

## Verification sources

- `frontend/e2e/asset-layout.spec.ts`: 131 synthetic records, six widths at short heights, keyboard/focus, accessibility scan, drawer/full-record URLs, refresh, column save/reset, off-page identifier search, page-only selection, dirty preview actions, filtered-row departure and touch/CSS zoom.
- `frontend/e2e/asset-edit-navigation.spec.ts`: registered dirty forms, Keep/Discard, browser Back/Forward, native unload and failed-save continuation across Chromium, Firefox and WebKit.
- `frontend/src/inventory/Assets.test.tsx`: summary/detail separation, preference denial, missing direct record, failed preview saves, lifecycle/history failure and existing mutation regressions. Relationship and application tests cover the integrated routing/permission changes.
- `frontend/e2e/live-workspace.spec.ts`: isolated browser-to-Django-to-PostgreSQL workflow, including created hardware/software, retained specifications, installation and addresses, with independent database verification. Existing user/demo data is untouched.

Final gate results are recorded in [progress.md](progress.md). Screenshots and logs under `/tmp/tekdocs-assets-layout-*` are ephemeral; executable assertions above are the durable reproduction.

## Remaining before Assets / foundation closure

- Shared record header/section navigation is extracted and used by Assets; see [record-navigation.md](record-navigation.md). Validate reuse through Contracts/Networks, including cost permissions, child records and richer connected-data layouts before wider rollout.
- Site filtering now has a searchable picker; see [asset-site-filter.md](asset-site-filter.md) for its authorized-use boundary and verification. Preview assignment is implemented; see the checkpoint below.
- Software History currently explains that no history is available; do not invent history from installation fields. Establish the required software audit presentation against supported history data.
- Expand tracked nested route/state coverage, stale/conflict and permission-transition scenarios, native browser zoom/screen-reader/mobile-keyboard walkthroughs and technician validation (#39).
- Full production-image, supported recovery/upgrade and applicable release acceptance remain open. Specialized document tables, code, graph/canvas and artifact viewers retain necessary isolated scrolling and need their own inventory/acceptance in later phases.

No version bump, deployment, push or Wiki publication is part of this checkpoint.


## Preview assignment checkpoint — 0.8.46

The drawer now offers Assign hardware for manageable, non-disposed hardware. It replaces the status form while open, using the same authorized assignment choices and mutation endpoint as the full record. Switching from a dirty status action requires Keep editing or Discard changes. No nested drawer or extra record tabs are introduced.

The assignment form explicitly explains that saving replaces the existing person, site and location. At least one target is required. Selecting a location selects its owning site; changing sites clears an incompatible location. Empty selections become null values in the existing API payload. The server still validates workspace ownership, target availability and disposal state. Choices load only when the action opens, with a retry for failed reads. Late reads from closed forms are ignored. This slice reuses the existing choice response; it does not add bounded choice-search endpoints.

Failed writes retain all choices, including permission denial, conflict and failed-request cases, without automatically retrying. Cancel, drawer close and full-record navigation use the shared guard. Only one preview action is editable at a time. The returned hardware profile becomes authoritative, including the server's in-stock-to-in-service transition after assignment, so a completed assignment does not leave a spurious dirty status form.

Verification is recorded in progress.md. Component coverage includes three failed-write outcomes, canceled navigation, explicit discard, failed choice-read retry, site/location consistency and server lifecycle reconciliation. Browser coverage exercises assignment at all six maintained widths across three engines, accessibility scans, canceled close and focus restoration. The live journey now assigns hardware through the preview and verifies the resulting person/site/location in the full record and PostgreSQL. No schema, API contract, version or production deployment changes are required.
