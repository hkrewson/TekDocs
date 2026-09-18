# Vendor collection and supplier record workspace

Issue #81; completed Vendors piece of the vendor catalog, products, licenses, and stock milestone. Version remains 0.8.46.

## Implemented contract

The client Vendors area now uses a bounded, searchable, sortable, paginated supplier directory. Search covers display name, legal name, and website. Supplier name and connected asset count have deterministic ordering. Search, ordering, page, and selected supplier are URL-addressed, and a direct supplier URL retrieves an authorized record outside the current page.

A supplier name opens one responsive, read-only drawer with classifications, legal name, website, and the asset count that connects the supplier to the client. The drawer links to the supplier organization workspace and its product catalog. The record explains why the supplier appears in this client workspace. Creation, editing, and archive actions remain in the supplier organization workspace because this directory is derived from client assets and grants only asset-view access.

The list endpoint rejects undeclared parameters, caps page size, and returns canonical page metadata. The direct endpoint applies the same workspace, operational-owner, asset permission, and derived-scope checks as the list, so a supplier connected only to another client returns not found. OpenAPI and generated TypeScript types describe both routes.

## Evidence

- Focused PostgreSQL coverage verifies search, bounded paging, canonical metadata, direct retrieval, rejected parameters, and cross-client denial.
- Three component scenarios cover a complete supplier record, off-page direct restoration, query/sort URL state, and the workspace/catalog links. Browser-client checks cover exact organization and MSP request paths.
- All 21 focused browser scenarios pass in Chromium, Firefox, and WebKit at 320, 390, 768, 1024, 1280, and 1440 pixels. They cover long values, page and drawer bounds, heading focus, accessibility, direct retrieval, URL retention, and keyboard dismissal.
- The project frontend gate passes all 592 tests across 117 files, localization enforcement, coverage, typechecking, the production build, and existing compressed bundle budgets.

Products and Licenses remain before the grouped real browser-to-Django-to-PostgreSQL acceptance. Documents follow the operational-record sequence as Phase 5. Existing user and demo data was preserved; no version, deployment, or Wiki publication change is part of this checkpoint.
