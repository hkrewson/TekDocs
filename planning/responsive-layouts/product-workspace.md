# Product catalog collection and record workspace

Issue #81; completed Products piece of the vendor catalog, products, licenses, and stock milestone. Version remains 0.8.46.

## Implemented contract

The supplier Products area now uses a bounded, searchable, filterable, sortable, paginated directory. Search covers product identity and description, filtering narrows hardware or software, and name and update time have deterministic ordering. Search, type, ordering, page, and selected product are URL-addressed. A direct product URL retrieves an authorized product outside the current page.

A product name opens one responsive record drawer with product identity, default invoice price, models, specification values and version history, and associated published documents. Authorized users can create and edit products, add or revise schema-driven models, associate exact published documents, and archive products, models, or document associations inside the same record workspace. The former automatically selected split pane and separate page editor are removed.

The list endpoint rejects undeclared parameters, caps page size, and returns canonical page metadata. List and direct-detail serialization use the same document-view permission context. Existing supplier classification, workspace scope, asset permissions, append-only model revisions, and archive consequences remain authoritative. OpenAPI and generated TypeScript types describe the bounded query and response contract.

## Evidence

- The complete catalog PostgreSQL module passes, including bounded product search, sorting, paging, rejected parameters, supplier classification, workspace isolation, specification versions, stale-write protection, and append-only history.
- Eleven focused component and API-client tests pass for products, templates, models, model revisions, document associations, failure states, archive consequences, exact request paths, and query encoding.
- All 21 focused browser scenarios pass in Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels. They cover long values, collection and drawer bounds, models, documentation, editing, heading focus, accessibility, direct off-page retrieval, URL retention, and keyboard dismissal. The nine existing catalog language and no-template scenarios also pass in all three engines.
- The project frontend gate passes all 592 tests across 117 files, localization enforcement, coverage, typechecking, generated-client agreement, the production build, and existing compressed bundle budgets. A pre-existing Stock test raced its asynchronous list on the first run; awaiting the item made its existing assertion deterministic, and the complete clean rerun passed.

Licenses remains before the grouped real browser-to-Django-to-PostgreSQL acceptance. Documents follows the operational-record sequence as Phase 5. Existing user and demo data was preserved; no version, deployment, or Wiki publication change is part of this checkpoint.
