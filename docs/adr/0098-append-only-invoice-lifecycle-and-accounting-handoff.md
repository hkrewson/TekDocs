# ADR 0098: Append-only invoice lifecycle and accounting handoff

Status: Accepted for the pre-1.0 invoice boundary

Date: 2026-09-01

## Context

ADR 0091 established exact money arithmetic, gapless numbering, immutable issued invoices, retained artifacts, and a broad accounts-receivable design. The implemented product now needs to show what happened after issuance without becoming the authoritative ledger or permitting an external system to rewrite legal artifacts.

Accounting providers use different status models and may redeliver, reject, or mutate records. Storing a provider's current payload as invoice truth would make an issued invoice mutable by proxy. Storing payment processing credentials or initiating settlement would also expand TekDocs into a payments product.

## Decision

The issued invoice remains the immutable authority for its number, dates, lines, totals, tax snapshot, parties, signature, PDF, and CSV. Post-issue facts are separate immutable `InvoiceLifecycleEvent` rows protected by forced row-level security and database retention guards.

Events record a bounded type, occurrence and recording times, attributable actor, optional provider and external identifiers, exact same-currency payment amount, optional related issued invoice, and a short reference note. Provider payloads are never retained. An invoice-scoped idempotency key and provider/external-event uniqueness make repeated callbacks safe.

TekDocs derives lifecycle at read time. Void and credit events take precedence, followed by paid, partially paid, overdue, externally synchronized, delivered, and issued. Reconciliation is independently derived as unsynchronized, synchronized, rejected, duplicate, or externally changed. No scheduler mutates an overdue flag.

The `tekdocs-accounting-invoice/v1` export is the connector boundary. It uses exact decimal strings, contains frozen invoice values and the issued content digest, and has a stable `tekdocs:invoice:<invoice-id>:v1` idempotency key. New contract fields must be optional or require a new format version.

The client portal receives lifecycle and balance projections only. It does not receive the event stream, provider identities, external IDs, internal reconciliation state, staff attribution, or notes.

Issuance creates an ordinary exact-Workspace invoice due reminder. Delivery successes and failures enter the same event stream so an operator can see whether retry is appropriate. A failed attempt does not increment the retained successful-delivery count.

Invoice readiness reports missing issuer identity, address, country, currency, contact, and numbering configuration. A taxed invoice cannot issue without an issuer tax registration. TekDocs does not determine tax jurisdiction or claim statutory accounting or tax compliance.

## Consequences

- External accounting and payment systems provide observations, not write authority over issued invoices.
- Payment events are records of settlement performed elsewhere; TekDocs stores no payment credential and initiates no transfer.
- Void and credit are explicit linked history records. The original issued artifact is retained unchanged.
- Quotes, expenses, purchasing, payroll, bank reconciliation, chart of accounts, general ledger, payment processing, automatic tax determination, and tax filing remain unavailable.
- A future provider connector consumes the versioned export and event contract instead of adding provider-specific columns to invoices.

This decision narrows and supersedes the parts of ADR 0091 that proposed native payment allocation and mutable invoice states. Its arithmetic, numbering, issuance, artifact, and client-isolation decisions remain in force.
