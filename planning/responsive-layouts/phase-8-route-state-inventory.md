# Phase 8 route and state inventory

Issue #85; first acceptance checkpoint for the pre-1.0 responsive-layout work.
Version remains 0.8.46.

## Result

`routes.json` is now checked against the application router and the supported
workspace-capability registry. It contains every literal shell route, every
organization-capability route expanded from the shared registry, redirects and
unavailable-route handling. A route cannot be marked in progress or complete
without concrete state notes and existing evidence files. Status values use one
stable vocabulary: `pending`, `in_progress`, and `complete`.

The repository check fails when a supported route is added without inventory,
when a retired route remains in the inventory, when routes are duplicated, when
evidence files disappear, or when a started route retains the placeholder state
description. This makes the inventory an active release contract instead of a
manually maintained list that can drift from the product.

The reconciliation records 61 supported routes: 51 complete, 10 in progress,
and none pending. Domains and Certificates now pass the shared responsive
collection and drawer contract in MSP and organization workspaces, completing
the Phase 4 implementation routes. Authentication reset and client-portal entry paths
are tracked alongside the React router. Assets, Documentation/Files, Networks, and
Contracts have implemented layouts with broader acceptance still open; they
remain `in_progress` rather than being reported as unfinished screens.

## State coverage

Each route records the states that apply to it and links to the component,
browser, live-runtime, or implementation evidence that exercises those states.
Authentication and portal state machines remain recorded in
`authentication-and-client-portal.md`; nested record and query states remain in
their feature implementation records. `routes.json` points to those records
instead of duplicating their complete state matrices.

## Verification

- `python3 scripts/check-responsive-route-inventory.py`
- `python3 -m unittest scripts.tests.test_check_responsive_route_inventory`
- `make check-responsive-route-inventory`
- `make check` at the completed checkpoint

This checkpoint does not claim technician walkthrough, production-image,
upgrade/recovery, security, or final release acceptance. Those remain later
Phase 8 gates. Production deployment, external push, Wiki publication, and a
version change remain separate work.
