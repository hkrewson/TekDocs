# ADR 0102: MSP stock inventory and invoice sources

- Status: Accepted for the pre-1.0 inventory boundary
- Date: 2026-09-05

## Context

TekDocs distinguishes supplier catalog records from client assets. Neither record answers a common MSP question: what consumable or resellable material does the MSP currently hold for use at any client? Cable, connectors, patch leads, drives, and spare equipment may be purchased from a vendor, consumed in fractional units, and later billed to a client without becoming a client asset.

The invoice system already accepts snapshotted product, service-rate, and contract-cost sources. Treating MSP stock as another catalog product would lose on-hand quantity and procurement provenance. Treating each spool or box as a client asset would assign it to the wrong owner before it is used.

## Decision

`StockItem` is tenant-owned MSP inventory. It records a plain item name and description, optional vendor and part number, unit, exact quantity on hand, reorder level, currency, internal unit cost, client unit price, and optional latest-order provenance. The order and tracking values are labels and links only; TekDocs does not retrieve their contents or provide purchase-order, receiving, or accounts-payable workflow.

Internal cost permits six decimal places so landed cost can be represented for fractional supplies. Invoice-facing client price continues to obey the invoice currency rules. All API values remain decimal strings and never pass through floating-point arithmetic.

`StockMovement` is an append-only tenant-owned history row. Receiving, client use, returns, and corrections change the item balance under a row lock and store the resulting balance in the same transaction. A change that would make stock negative is rejected. Client use requires an exact same-tenant organization classified as a client. Database triggers retain movement history and validate item, client, vendor, and actor scope; both stock tables use forced row-level security.

A draft invoice line may retain a stock-item origin. The line snapshots the current name, client price, currency, and selected quantity in the same manner as other invoice origins. Creating or issuing an invoice does not change stock. The physical use is recorded separately because installation and invoicing may happen at different times, and a mutable draft is not evidence that material was consumed.

Stock uses the established invoice view and edit permissions for this initial bounded slice. It is available only in the MSP Workspace and appears beside Invoices under Business.

## Consequences

- Supplier catalogs remain reference data, client assets remain deployed client-owned equipment, and MSP stock remains centrally owned supply.
- Stock history can explain the current balance without making an invoice or vendor order authoritative for physical use.
- Operators must record actual use explicitly. TekDocs does not reserve quantities for drafts or infer consumption from issued invoices.
- Multi-warehouse bins, purchase orders, supplier ordering, batch/lot tracking, serialized-stock conversion, stock valuation, and accounting entries remain outside this decision and require separate product decisions.
- Issue [#63](https://github.com/hkrewson/TekDocs/issues/63) owns the implementation and verification record.
