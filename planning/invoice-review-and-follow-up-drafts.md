# Invoice review and follow-up drafts

Status: complete in the frozen `0.9.0` database-first baseline, including issued credit notes, void-before-delivery, and supported recovery evidence.

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

## Implemented corrections extension

A delivered or otherwise financially wrong invoice can now create an editable credit-note draft that copies immutable line snapshots without live origins. Issuance assigns the credit note its own transactional series and signed retained artifact, links it to the exact source invoice, and derives the source's credited amount and remaining balance from append-only lifecycle evidence. Cumulative credit notes cannot exceed the source total.

An undelivered ordinary invoice can now be voided through its own privileged, recently authenticated action. The append-only void retains the issued row, number, and artifact, blocks later delivery, and removes the invoice from the client portal. Delivery prevents voiding and directs the operator to a credit note instead. Generic lifecycle updates can no longer synthesize void or credit events.

## Verification

Focused coverage includes draft defaults and overrides, immutability after default changes, supplemental and replacement behavior, origin-free replacement lines, exact-Workspace denial, migration backfill, frontend review/edit actions, responsive party layouts, and retained failure states. The correction extension additionally has service, database-trigger, authorization, portal, signed-artifact, OpenAPI, generated-type, UI and migration-cycle coverage.

The billing-specific restore and supported encrypted recovery rehearsals restore issued invoices, credit notes, void evidence, numbering series and signed PDF bytes on clean stacks. The full composed `make check` gate also passes after normalizing the local product-boundary status contract. External issue, human and final-release evidence remain separate closeout work.
