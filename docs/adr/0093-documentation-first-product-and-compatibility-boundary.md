# ADR 0093: Documentation-first product and compatibility boundary

## Status

Accepted for the 1.0 line.

## Decision

TekDocs is a structured MSP documentation and inventory platform that integrates with systems of action. Invoices remain a bounded supported capability. Native ticketing, PSA, CRM, general-ledger, payment-processing, payroll, RMM, and MDM workflows are excluded.

The maintained matrix is `docs/PRODUCT_BOUNDARY.md`. Backend workspace payloads and the typed frontend registry enumerate only supported visible capabilities. Unsupported routes return an unavailable result; roadmap placeholders do not appear in the application.

The 1.x compatibility promise is defined in `docs/COMPATIBILITY.md`. Django migrations are the sole database upgrade authority, and external systems remain authoritative for projected workflow state.

## Consequences

- `/invoices` is canonical; `/accounting` is a compatibility redirect.
- `/tickets` is not a product route.
- Connector work must state authority, synchronization, write scope, data minimization, and failure behavior.
- Issue #40 may decompose implementation hotspots, but it may not redefine this product boundary.
- A 1.0 release record must prove the boundary, compatibility rehearsals, security disposition, browser/accessibility results, production artifacts, pilot results, and intentional deferrals.

