# Bounded Files register

Phase 5 and Phase 8 acceptance under #60/#85. Version remains 0.8.46.

## Problem and completed behavior

The standalone Files route previously loaded one page of complete document records
and flattened their embedded attachments in the browser. Files attached to documents
outside that page could not be found, while each row paid for unrelated document
content, placements, publications, and history. Search therefore appeared global but
was incomplete.

Files now uses an authorized file-summary collection. Search, file use, ordering,
page, and page size are URL-addressed and evaluated over the complete visible
workspace. Pages contain 25, 50, or 100 rows and default to 25. File name remains the
identity column; personal column choices and page size use the existing installation,
user, and feature-scoped preference service under the `files` feature key. Preference
failure falls back to the curated columns without blocking the register.

The responsive table becomes labeled records below 768 CSS pixels. Long filenames,
document titles, checksums, media types, sizes, dates, and actions wrap without page
overflow. The owning-document link retains the MSP or organization route. Downloads
continue to use the existing protected attachment endpoint; upload, replacement,
removal, scanning, and PDF reading remain in the focused document workspace.

## API and authorization

`GET /api/v1/documents/files` and
`GET /api/v1/workspaces/organizations/{organization_id}/documents/files` return only
bounded file summaries. Supported parameters are `q`, `kind`, `ordering`, `page`, and
`page_size`; undeclared parameters are rejected. Search covers filename, owning
document title, and media type. Ordering has an explicit entity-ID tie break.

The collection starts from the same authorized document scope as Documentation and
then selects active attachments. This preserves MSP ownership, client ownership,
explicit MSP-document listings, assigned-client visibility, and indistinguishable
cross-workspace denial. It does not expose storage keys or file content. Existing
document and download APIs are unchanged, and there is no model, migration, RLS, or
recovery-format change.

## Verification

- Backend coverage proves 26 files across two pages, off-page search, deterministic
  ordering, strict query rejection, and sibling-client isolation.
- Component coverage proves file/document/download rendering and the empty state.
- API-client coverage proves the encoded organization collection request.
- `frontend/e2e/files-layout.spec.ts` covers all six required widths in Chromium,
  Firefox, and WebKit, plus explicit organization routing at 390 and 1280 pixels.
  It checks full-collection search, paging, URL reset, column persistence,
  accessibility, long content, document links, API boundaries, and page overflow.

Technician screen-reader, native zoom, and mobile-keyboard walkthroughs and the final
release/recovery gates remain Phase 8 work. Production deployment, external push,
Wiki publication, and a version change remain separate.
