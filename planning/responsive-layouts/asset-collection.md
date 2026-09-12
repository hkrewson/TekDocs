# Assets collection foundation (#86)

This is an additive API implementation within Phases 1–2 of #77. It does not mark the Assets UI migration or any later phase complete. Application version: 0.8.46.

## Implemented interfaces

- `GET /api/v1/workspaces/msp/assets/collection`
- `GET /api/v1/workspaces/organizations/{organization_entity_id}/assets/collection`

Both require existing workspace access and `assets.view`. Vendor-only workspaces remain ineligible. Mutation and relationship capability flags are evaluated by the existing policy service. There is no new permission or domain-data migration.

The collection projects identity, model/type, operational status, assignment, site and warranty end. It does not load full specifications, retained publications, MAC collections, or lifecycle histories. A SQL count and a bounded, field-limited row query supply pagination. Related display fields use joins, not per-row detail requests. Selected previews/records use the existing asset detail endpoint through `browserAssetCollectionClient.detail`.

| Query | Contract |
|---|---|
| `page` | Positive bounded integer, default 1 |
| `page_size` | 25, 50 or 100; default 25 |
| `search` | Name, model name/number, serial number or asset tag; max 240 characters |
| `kind` | hardware or software |
| `status` | Existing hardware lifecycle or software installation status |
| `site` | Site entity UUID; matches hardware assignment or software installation |
| `assigned` | Whether a person is assigned; false includes records with no person assignment |
| `warranty` | expired, current or missing; hardware only; evaluated on the server's current local date |
| `ordering` | name, model, kind, status, assignment, site or warranty; prefix `-` for descending |

Every ordering uses entity UUID ascending as a deterministic tie-breaker, and nullable fields sort last in either direction. Unknown parameters and unsupported values fail validation rather than silently broadening a query. Out-of-range pages return an empty result with the actual count. Offset pagination is deterministic for an unchanged collection; concurrent insertion/deletion may change page membership and the UI must clear page selection/refetch as specified in #77.

Legacy `/assets` behavior, default page size of 50, full response, creation and operation IDs remain unchanged. OpenAPI and generated TypeScript include only intentional additions. The browser client forwards cancellation, encodes identifiers/conditions, retains false boolean filters, and does not retry failed detail requests.

## Verification record

Focused Docker API checks cover multiple pages, off-page serial searches, warranty filtering, reverse and tied sorting, hardware/software records, malformed query rejection, legacy response compatibility, workspace separation and permission flags. The API route inventory includes both routes for anonymous/nonmember/malformed-identifier checks. Runtime-role testing uses an isolated PostgreSQL test database, including a read-only user with one explicitly assigned client workspace.

Record final gate results in `progress.md`. No layout/viewport or live-browser acceptance is claimed for this API-only slice. Running application containers and existing user/demo records are unchanged.

## Next implementation dependencies

1. Under #88, extend `frontend/src/product/capabilities.ts` and `workspaces/navigation.ts`, which already drive navigation, rather than create a competing capability registry. Reconcile the organization route map in App.tsx with those definitions; preserve underscore organization routes and hyphen MSP paths for custom fields/recycle bin.
2. Decide the shared data-router integration before dirty-form guards. App currently uses BrowserRouter/MemoryRouter plus descendant Routes; React Router `useBlocker` needs the data router. Do not implement a partial guard that misses browser Back or programmatic navigation.
3. Introduce query-addressed Assets list state and the summary client; clear selection on every effective collection condition change. Account for delayed/cancelled responses, count changes, lost authorization and mutations that remove a record from the current filter.
4. Add the personal preferences model/API and migration under #87; no local-storage-only substitute for the accepted cross-device contract.
5. Replace the old Assets split list/detail and below-list lifecycle in one complete UI slice. Preserve CSV, bulk confirmation, retained documents, relationship access and lifecycle rules. Existing HardwareLifecycle mixes editing and history; separate history fetching from mutation success, so a successful write followed by failed history refresh is not presented as a failed write.
6. Asset detail currently includes retained document summaries and current specifications. New tab-specific endpoints may be needed before claiming all tabs load only on demand; do not mistake a lightweight list for completion of the detail-loading contract.
