# ADR 0033: Commercial contracts and cost projection

- Status: Accepted for `0.3.7`
- Date: 2026-08-10

## Decision

A `CommercialContract` is an addressable, client-owned Entity related to one same-tenant organization classified as a vendor, manufacturer, or partner. It records the operational agreement identity, service/support/lease/subscription kind, lifecycle status, bounded description and reference, term, renewal date, auto-renew state, and notice period. These non-financial fields use `assets.view`; changes and archival use MFA/CSRF-protected `assets.edit`.

Financial terms are separate `ContractCost` rows. Amount uses fixed-precision decimal storage, currency is a normalized three-letter code, quantity is positive fixed precision, and billing cadence is a bounded enum. Cost labels, amounts, currency, quantity, dates, and references are one sensitive projection classified as `cost`. A contract serializer omits the entire `costs` member unless the central policy grants `costs.view` in the exact organization scope. Creating, changing, or archiving a cost requires both `assets.edit` and `costs.view`; a user who can edit operational contract fields cannot infer or overwrite hidden terms.

Contract list/search matches only contract name, provider name, operational description, and contract reference. It never filters, sorts, aggregates, counts, or highlights cost rows or values. Provider selection is bounded to active same-tenant organization anchors with an eligible classification. Scoped managers, exact-workspace lookup, PostgreSQL relationship guards, forced RLS, and sibling/cross-tenant tests defend the boundary below the serializer.

## Consequences

- A client service agreement remains useful to staff without financial access while its cost member is structurally absent.
- `costs.view` remains independently delegable at tenant, organization, or collection scope and does not grant contract mutation.
- Cost audit events contain only the contract entity and cost-row identifier, never labels, amounts, currency, quantity, or references.
- Operational contract fields cannot classify arbitrary prose automatically. The editor explicitly directs authors to keep pricing and rate details in protected cost rows; operator guidance and review remain part of the boundary.
- This slice does not implement accounting, invoices, purchasing, cost totals, currency conversion, taxes, cost allocation to assets/licenses, files, scheduled renewal notifications, or service dependency graphs.
