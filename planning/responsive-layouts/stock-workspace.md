# Stock collection and record workspace

Issue #81; first completed piece of the vendor catalog, products, licenses, and stock milestone. Version remains 0.8.46.

## Implemented contract

Stock now uses the accepted bounded collection and complete record drawer. The collection searches item names, descriptions, vendor names, and vendor part numbers across the authorized workspace. Name and quantity sorting, deterministic paging, and the selected record are URL-addressed. A direct record URL retrieves an item even when it is outside the current page; missing or inaccessible records have an explicit unavailable state.

An item name opens one responsive drawer containing purchasing provenance, exact cost and client price, quantity and reorder facts, external order and tracking links, and the complete append-only movement history. Creation, item editing, quantity adjustments, and archive confirmation stay in this workspace. Failed writes retain the active form. Escape, backdrop dismissal, and the mobile return link protect unfinished edits, including an immediate Escape after typing.

The list endpoint now validates declared query parameters, caps page size, and returns canonical page metadata. The existing scoped item endpoint supports direct reads without changing invoice permissions or tenant isolation. OpenAPI and the generated TypeScript contract describe the additive collection and detail behavior.

## Evidence

- Six PostgreSQL stock scenarios cover exact costs, movement history, invoice integration, classification validation, bounded search and paging, direct retrieval, and cross-tenant denial.
- Component and browser-client checks cover full records, quantity changes, grouped creation fields, off-page URL restoration, query encoding, and dirty dismissal.
- All 21 focused browser scenarios pass in Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels. They cover long values, page and drawer bounds, heading focus, accessibility, and immediate keyboard dismissal protection.
- The project frontend gate passes all 590 tests across 117 files, localization enforcement, coverage, typechecking, the production build, and existing compressed bundle budgets.

Vendor catalog, products, and licenses remain in the grouped milestone. Its real browser-to-Django-to-PostgreSQL acceptance stays deferred until those connected pieces are integrated. Existing user and demo data was preserved; no version, deployment, or Wiki publication change is part of this checkpoint.
