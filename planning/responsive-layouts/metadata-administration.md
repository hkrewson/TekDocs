# Metadata administration workspace

Custom Fields and Taxonomies are the Phase 7 metadata-administration slice of the pre-1.0 responsive-layout program. The implementation replaces wide administration tables and permanently expanded editors with compact collections and focused editing surfaces while preserving the existing versioned data models, permissions and APIs.

## Collection contract

The MSP Custom Fields route, organization Custom Fields section and MSP Taxonomies route use the same collection behavior:

- Search, the primary type/use filter, page, page size and open editor are addressable in the URL.
- Pages offer 25, 50 or 100 records and default to 25. Search and filtering operate over the authorized collection returned by the existing endpoint.
- Active conditions remain visible as removable controls outside the filter menu.
- Compact list rows retain identity, stable key, applicability, version, usage and a short description. Version history stays available on demand for a custom field.
- Long labels, descriptions and identifiers wrap within the ordinary page. The pages do not use a wide data table or an isolated collection scroller.
- Empty, no-match, loading and retryable read-failure states remain explicit. A direct editor URL for a removed record reports that the record is unavailable and lets the user return to the collection.

The existing endpoints currently return the complete authorized definition collections. Client-side paging therefore preserves their compatibility and still searches beyond the first visible page. If installations grow beyond the present bounded metadata volume, a later additive paginated endpoint can replace the read without changing these URLs or interactions.

## Focused editing and migration

New custom fields, retained custom-field versions, new taxonomies and retained taxonomy versions open in focused modal workspaces. The background is locked while an editor is open. Cancel and route navigation use the shared dirty-form guard, and failed writes preserve every entered value for correction or retry. Only one metadata editor is open at a time.

Taxonomy legacy-tag matching is an on-demand workspace reached through `view=migration`. It is no longer permanently stacked below every definition. Preview results use compact rows and the existing exact-match-only mutation remains a separate explicit action. Archive confirmations and the domain rules for retained historical values remain unchanged.

## Authorization and compatibility

MSP and inherited organization fields retain their current ownership rules. Inherited fields remain read-only in the organization workspace. Taxonomy bindings, stable term keys, version creation, local-term policy, impact counts and migration semantics are unchanged. There is no schema migration, API contract change or version bump in this slice.

## Verification

Component coverage exercises collection rendering, create/version flows, archiving, on-demand migration, URL-restored filters and the shared dirty-form confirmation. `frontend/e2e/metadata-layout.spec.ts` covers MSP and organization Custom Fields plus Taxonomies at 320, 390, 768, 1024, 1280 and 1440 CSS pixels in Chromium, Firefox and WebKit. It verifies second-page records, off-page search, URL state, focused editors, background locking, long values, migration preview, accessibility and the absence of horizontal page overflow.

The live workspace journey creates and searches a real taxonomy, then creates, searches and uses an organization custom field through Django and PostgreSQL. The project gate covers lint, types, component tests, production compilation, contract drift and bundle budgets. Version remains 0.8.46; deployment, external push and Wiki publication remain separate.
