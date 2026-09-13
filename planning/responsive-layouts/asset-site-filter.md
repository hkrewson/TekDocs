# Assets site filtering — pre-1.0, version 0.8.46

Scope: #79/#86 under responsive layout epic #77. This implements the outstanding Assets Site picker. It does not close the Assets phase, foundation, or release acceptance.

## User behavior

The existing Filters menu now has a Site submenu with search, paginated choices and All. Choices are sites used by active hardware assignments or software installations in the current workspace. Unused sites are deliberately omitted; the submenu explains this boundary. Search and paging cover the full authorized choice collection, independently of the currently loaded asset page.

Selecting a site uses the existing `site=<site entity UUID>` collection query. It resets the asset page and clears page-only bulk selection through the existing list-context behavior. Searching or paging the picker itself does not change the asset filter. The selected site appears in the submenu summary and removable active-filter condition. Refresh, direct links, full-record navigation and list return retain the URL condition.

Failed choice reads offer an explicit retry; they do not silently clear the filter. A selected site that is archived or no longer used by active assets has an unavailable explanation and remains removable. If its label lookup fails, the condition retains a generic Selected site label. No workspace filter selections are written to personal collection preferences.

## Additive API contract

GET `/api/v1/workspaces/msp/assets/site-choices` and GET `/api/v1/workspaces/organizations/{organization_entity_id}/assets/site-choices` require `assets.view` through the existing policy/workspace service.

Parameters: `search` (optional, maximum 240 characters), `page` (default 1), `page_size` (25/50/100, default 25), and `selected` (optional site entity UUID). Unknown or invalid query parameters are rejected. Response: `results` containing only `{id, name}`, canonical `page`, `page_size`, `count`, `has_more`, and `selected` containing the authorized selected identity or null. Selected lookup is independent of search/page but obeys the same workspace/active-use boundary.

Site identities are already disclosed by authorized asset summaries; this endpoint does not grant access to site addresses, contact fields, location trees or the Sites management surface. Both the candidate Sites query and its asset subqueries use the exact workspace/tenant data scope. Archived assets/entities and sites/entities are excluded. Hardware and software use the same site entity IDs already accepted by the asset collection filter. Results sort by display name with entity UUID tie-breaking.

This is a new explicitly paginated interface. Existing Assets and Sites APIs retain their behavior. OpenAPI, generated TypeScript and permission-route inventory are updated. No model, schema migration, ownership/RLS model classification or recovery format changes are required.

## Implementation and regressions

`AssetSiteFilter.tsx` is a custom group inside the shared FilterMenu; `useAssetSiteLabel.ts` resolves the active condition's name. Requests are cancelable and scoped by query/workspace. Choice rows remain mounted during selected-value metadata refresh, avoiding unnecessary focus loss. Search/page changes replace results with a loading state; failed results cannot appear as a successful new query.

Browser checks reproduced a narrow-screen popover extending outside the viewport. The Assets collection toolbar now anchors the menu within its width on mobile and bounds the menu's scrolling height. This is deliberate isolated scrolling for a transient filter menu. Ordinary pages retain their primary scrolling area. A second browser regression uses an unbroken 300-character site suffix: active-filter buttons now wrap within the available width, preserving access to the complete label and removal action at 320 pixels.

Site selection changes URL state through an asynchronous router transition. Browser tests click the choice, await its checked state, and then verify URL/result changes; they do not assume a synchronous controlled-radio update. The checked-state assertion remains explicit. A duplicate selected-site caption was removed because the summary and active condition already identify the choice; pagination reuses the shared labels. Startup-size budgets remain authoritative.

## Durable verification and remaining scope

- `backend/apps/core/tests/test_asset_collections.py`: 31 used sites, off-page search, paging, minimal response fields, selected-site lookup, archive handling, software sites, unused-site exclusion, query rejection and runtime-role workspace denial.
- `backend/apps/core/tests/test_permission_idor_matrix.py`: new route inventory, anonymous/non-member denial and malformed identifiers through the maintained matrix.
- `frontend/src/inventory/AssetSiteFilter.test.tsx`: search/page request behavior, failed reads, unavailable selected values, explicit retry and clearing.
- `frontend/e2e/asset-layout.spec.ts`: six widths, off-page picker search, selection clearing, named active condition, refresh and removal across maintained browsers.
- `frontend/e2e/live-workspace.spec.ts`: actual assigned site selected from the filter menu, retained through refresh, followed by full-record navigation and the established independent PostgreSQL assertions.

Final gate results belong in progress.md. Software history presentation, reusable record navigation, expanded stale/conflict/permission-transition acceptance, technician/native zoom/screen-reader walkthroughs, later surface migrations and release/recovery gates remain open. No deployment or publication is implied.

The final startup-budget fix extracts the static Overview page into `frontend/src/workspaces/Overview.tsx`, loaded through the existing route's Suspense pattern. This is a small #40/#78 navigation-foundation follow-up; it preserves the Overview content and labels. Existing Overview coverage now awaits its loaded heading. No locale behavior or bundle-budget threshold is changed.

The real-stack Site-filter rehearsal reproduced assigned hardware disappearing from collection results. A direct serializer reproduction showed that DRF treated an omitted optional Boolean query parameter as an unchecked HTML checkbox (`assigned=False`). The collection now uses an optional query Boolean field whose omitted value remains absent. Explicit true/false behavior remains intact. Regression coverage includes actual person-assigned hardware filtered by site under the restricted PostgreSQL role, absent/true/false query parsing, and the live response containing the assigned switch after refresh. The temporary live diagnostics were removed; the stronger result assertion remains.
