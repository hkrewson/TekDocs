# Invoice collection and focused workspace

## Scope

Phase 6 migrates the client invoice route from an automatically selected split
layout to a bounded collection and one focused invoice workspace. Invoice
settings in the MSP Workspace are a separate route and remain pending.

## Acceptance

- Opening the client invoice route shows the collection without implicitly
  selecting the first invoice.
- Search and draft/issued filtering run on the authorized server collection;
  ordering, page and page size are URL-addressed and capped at 100 rows.
- Collection rows omit invoice lines, retained proof fields and lifecycle-event
  history. Opening a row loads the full invoice from the authorized detail
  endpoint, including records outside the current page or filter.
- The focused invoice URL survives reload and browser history and provides an
  explicit return to the collection.
- Draft editing, stock-backed lines, issuance, delivery, downloads, accounting
  updates and recurring-draft navigation retain their existing permission and
  confirmation behavior.
- Personal visible-column and page-size choices use the existing collection
  preference boundary and never store workspace filters.
- The collection and focused record fit 320, 390, 768, 1024, 1280 and 1440px
  in Chromium, Firefox and WebKit with no horizontal page overflow or automated
  accessibility violations.
- Invoice lines retain an optional billing unit. The focused MSP record and client
  portal show it with quantity and rate; CSV and accounting exports carry the same
  signed snapshot.
- Newly issued retained PDFs use friendly dates, an explicit amount due, clear
  quantity/unit/rate columns, issuer contact details, project notes, payment
  instructions and issue-time document metadata.

## Evidence

- Component regression: `frontend/src/accounting/Invoices.test.tsx`
- Server query and summary contract: `backend/apps/core/tests/test_invoice_drafts.py`
- Browser matrix: `frontend/e2e/invoice-layout.spec.ts`
- Preserved lifecycle and recurring workflows: `frontend/e2e/invoices.spec.ts`

## Retained invoice document checkpoint

The PDF is generated and signed only when a draft is issued. Existing issued PDFs
remain immutable, so the improved document applies to new invoices rather than
silently changing retained evidence. Payment instructions come from the MSP invoice
defaults and are included in the issuer snapshot. If they are blank, the PDF gives
the due date and billing contact without inventing payment details.

Client billing addresses remain deliberately absent because organizations do not
yet have a dedicated billing-address/contact model; a site address is not assumed
to be the billing address. Tax calculation and legal/tax policy are unchanged.
Logo branding and tagged-PDF output remain explicit future document-quality work.

The invoice layout matrix passes 21 cases across the three browser engines. The
supported invoice backend target passes its invoice, stock, permission, IDOR,
row-level isolation and migration coverage. The repository-wide gate passes all
629 frontend tests in 117 files, schema and migration agreement, policy checks,
and the production build and bundle budgets.
