# Invoice review and follow-up drafts

Status: implemented pre-1.0 foundation at version 0.8.46. This does not complete the issued credit-note and void workflow assigned to the corrections milestone.

## Problem and boundary

Issued invoices must stay immutable, but immutability must not force an operator to recreate client, address, notes, and line context when work was omitted. The prior draft API also resolved issuer and customer identity only during issuance, which meant the operator could not inspect or tailor the printed parties before committing the invoice.

This slice keeps issued artifacts unchanged and adds two kinds of linked draft:

- A **supplement** starts with no lines. It carries the source invoice's client, currency, notes, reviewed sender, and reviewed bill-to snapshot so the operator only adds the omitted work.
- A **replacement** copies the source's visible line descriptions, quantities, units, prices, and tax snapshots. Copied lines deliberately have no live catalog, rate, contract-cost, or stock origin. This preserves the issued values and prevents a replacement draft from consuming stock a second time.

Both kinds retain an exact source-invoice relationship protected by the client Workspace boundary. A follow-up is only a draft; it does not silently void, credit, or change the balance of its source.

## Draft party contract

Every newly created draft snapshots the client billing identity and, when configured, the MSP invoice identity. Existing drafts are backfilled during upgrade from their current client and MSP defaults. Authorized staff can edit the sender and bill-to values for that draft without changing either default record.

The invoice detail and the final issue confirmation display the draft-specific parties, dates, item count, and total. Issuance uses those saved snapshots rather than re-reading mutable organization or MSP defaults. Required sender and bill-to address fields are validated at issue, taxed invoices validate the draft-specific tax registration, and failed issuance leaves the draft intact.

Issued PDF, CSV, accounting export, staff detail, and client portal continue to use the same immutable snapshots. Later default changes cannot rewrite them.

## Interfaces and authorization

`PATCH /api/v1/workspaces/organizations/{organization}/invoices/{invoice}` accepts bounded `issuer` and `bill_to` objects only for drafts. `POST .../{invoice}/follow-up` accepts `supplement` or `replacement` and requires the existing invoice-edit permission. The source must be an issued invoice in the exact same tenant and client Workspace; service validation, foreign keys, database checks, the invoice guard trigger, forced RLS, route inventory, and the IDOR matrix all cover this boundary.

The detail response exposes `issuer`, `bill_to`, and an optional source summary. Bounded collection summaries omit all three.

## Remaining corrections work

A delivered invoice that is financially wrong still requires a separately numbered, signed credit note with negative receivable effects. An undelivered invoice still requires the privileged void-before-delivery transition. Those documents must be implemented on the append-only lifecycle boundary before the corrections milestone can close. A replacement draft currently provides reviewed re-entry and lineage; it does not claim that the source has been voided or credited.

## Verification

Focused coverage includes draft defaults and overrides, immutability after default changes, supplemental and replacement behavior, origin-free replacement lines, exact-Workspace denial, migration backfill, frontend review/edit actions, responsive party layouts, and retained failure states. OpenAPI, generated types, the project gate, Docker/PostgreSQL tests, and the supported upgrade/recovery gates remain required before release closure.
