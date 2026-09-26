# NetBox identity register

Phase 3 (#80), required pre-1.0 under #60/#75. Version remains 0.8.46.

## Implemented boundary

The Networks workspace now mounts a separate NetBox identity register for MSP and
organization routes. It replaces the dormant, unbounded reconciliation table with
a 25-row bounded collection, optional 50/100-row pages, full-collection search,
object-type filtering, deterministic server sorting, personal columns, compact
mobile rows, and explicit loading, empty, failed, and denied states. The register
stores only the stable TekDocs-to-NetBox object identity already supported by the
domain model. It does not store a NetBox URL or credential and it does not silently
apply remote observations.

Linking opens one overlay drawer rather than adding a page-wide form. Eligible
TekDocs records are fetched in bounded pages and the selected record is returned
independently when it falls outside the current page. Software assets, linked
records, and sibling-workspace records are excluded. Failed writes retain the
selected record and object ID. Dirty dismissal uses the shared guard. Unlinking
keeps its explicit consequential confirmation. Opening or closing the drawer
preserves the list page, search, filter, sort, and column context.

## API compatibility and authorization

The existing unpaginated reference and choice endpoints remain compatible. New
`reference-collection` and `choice-collection` endpoints provide the bounded UI
contract without silently truncating legacy consumers. Unknown query parameters
are rejected. Search, filters, counts, paging, and selected-choice lookup all run
inside the resolved operational workspace. Reads require `networks.view`; the
response exposes management capability from `networks.edit`, and writes continue
to recheck that permission on the server.

The `network-netbox` preference feature allows only record, type, object ID, and
observation columns. Identity remains required. Preferences contain no NetBox
values or workspace filters and retain their installation/user ownership model.
No domain migration or recovery-format change is required.

## Verification and remaining acceptance

Focused backend tests cover bounded pages, off-page search, numeric object search,
object filtering, strict queries, selected choices, and sibling isolation. Frontend
tests cover URL page retention, the bounded link drawer, and failed-write value
retention. `netbox-layout.spec.ts` exercises both workspace routes at 320, 390,
768, 1024, 1280, and 1440 CSS pixels across maintained browsers, including axe,
overflow, off-page search, and personal-column persistence.

This checkpoint resolves the NetBox implementation gap inside the broader Networks
routes. Those routes remain in progress until the combined technician walkthrough,
assistive-technology review, production-image exercise, and Phase 8 release gates
accept the complete Networks workspace.
