# Credential-reference workspace

Credential references are a Phase 4 operational-record slice for both the MSP
route and organization workspaces. The implementation keeps TekDocs' security
boundary explicit: list and detail responses contain the reference identity,
provider label, timestamps, and permissions, while the private provider URL is
only resolved by the existing audited open endpoint.

## Collection and record behavior

- The collection uses compact identity rows with server-side search and bounded
  pages of 25, 50, or 100. Search, page, and page size live in the URL.
- Selecting a name opens the shared overlay drawer through the `credential`
  query parameter. The list remains full width and retains its search, page,
  scroll, and focus context when the drawer closes.
- Direct links fetch one authorized record even when it is outside the current
  page. Missing, archived, and newly inaccessible records show a retryable
  unavailable state without revealing whether another workspace owns the ID.
- The record drawer explains what TekDocs stores, shows the provider and last
  update time, and contains the useful actions: open in 1Password, edit, and
  archive. Row actions are deliberately absent from the collection.
- Create and edit forms live in the drawer. Validation and request failures keep
  entered values. Dirty forms guard backdrop, Escape, return-link, and browser
  navigation dismissal. Archive remains an explicit confirmation and states
  that the provider item and its access do not change.

## Responsive and accessibility behavior

The shared drawer is a right-side overlay at larger widths and a full-viewport
surface below 768 CSS pixels. It locks background scrolling and provides one
scrolling body. The collection has one ordinary page scroll, long identities
wrap, primary actions remain visible, and the drawer restores focus to the
originating row when possible. Keyboard Escape, focus containment, visible
labels, dialog names, and the 390px axe check are covered in browser tests.

## Verification evidence

- `backend/apps/core/tests/test_credential_references.py` covers authorized
  detail retrieval, archived records, sibling-workspace isolation, and omission
  of private links.
- `frontend/src/credential-references/CredentialReferences.test.tsx` covers the
  drawer, create, archive, dirty-form retention, URL paging, and direct-link
  retry states.
- `frontend/src/credential-references/api.test.ts` covers organization-scoped
  list/detail paths and the audited provider-open URL.
- `frontend/e2e/credential-references-layout.spec.ts` covers MSP and organization
  routes, 320/390/768/1024/1280/1440 widths, full-screen mobile drawers,
  overflow, accessibility, URL state, direct records, and dirty dismissal.

The next Phase 4 slices are Domains and Certificates. They should reuse the
same URL-addressable collection and drawer behavior while keeping registration,
DNS/RDAP observations, certificate observations, and check history specific to
those record types.
