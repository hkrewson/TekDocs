# Domain and certificate workspaces

Phase 4 responsive-layout checkpoint. Version remains 0.8.46.

## Delivered behavior

Domains and Certificates now use bounded collections in MSP and organization
workspaces. Both default to 25 rows, support 25/50/100 page sizes, and preserve
search, ordering, page, page size, and the selected record in the URL. The
domain API adds an explicit paginated response while preserving the legacy
unpaginated response for existing callers.

Domain names open the shared overlay drawer. The drawer provides registration
facts, monitoring warnings and recent runs, TLS endpoints, certificate history,
and the existing Check Now operations without repeating the collection row.
Domain creation and endpoint creation retain entered values after failure and
use the shared dirty-change guard for backdrop, Escape, Back, and browser
navigation dismissal.

Certificates use domains as their bounded parent collection. Selecting a domain
opens its endpoint summary in the same drawer; selecting an endpoint replaces
the drawer body with current certificate facts, validation status, evidence,
and run history. Endpoint and domain query identifiers support bookmarks,
Back/Forward restoration, and records outside the current collection page.
There are no nested drawers or page-wide secondary scroll regions.

Below 768 CSS pixels the drawer fills the viewport and uses a feature-specific
Back control. At larger widths it overlays the collection without squeezing it.
The collection emphasizes identity and state on narrow screens, retains access
to long names, and does not introduce horizontal page overflow.

## Compatibility and authorization

The existing domain collection remains an array unless a caller explicitly
requests `paginated=true`. The bounded form returns `results`, `page`,
`page_size`, `count`, `has_more`, and `can_manage`; search, status filtering,
and ordering are applied to the complete authorized collection with a stable
entity-ID tie break. OpenAPI and generated frontend types describe both response
forms. Existing workspace isolation, management permissions, monitoring policy,
and certificate operations remain authoritative.

## Verification evidence

- Domain API authorization, legacy compatibility, page metadata, search,
  filtering, ordering, and rejected query parameters:
  `backend/apps/core/tests/test_domains.py`
- Domain and certificate component states, URL restoration, creation, monitoring,
  evidence, errors, and dirty guards:
  `frontend/src/domains/Domains.test.tsx` and
  `frontend/src/domains/Certificates.test.tsx`
- API request construction: `frontend/src/domains/api.test.ts`
- Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 CSS
  pixels, including organization routes, direct records, accessibility,
  overflow, and dirty drafts: `frontend/e2e/domains-layout.spec.ts`
- Fresh browser-to-Django-to-PostgreSQL creation and persistence for a domain
  and TLS endpoint: `frontend/e2e/live-workspace.spec.ts`

Final technician walkthroughs and the broader Phase 8 production/release gates
remain open. Deployment, external push, Wiki publication, and version changes
are separate actions.
