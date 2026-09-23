# Client billing identity

Phase 6 follow-up; organization drawer and retained invoice document. Version remains 0.8.46.

## Delivered behavior

Each organization has a dedicated billing contact, email, phone, and postal address. These values are separate from Sites because a service location is not necessarily the legal billing destination. The existing organization drawer shows the billing identity as a compact section and opens one focused editor for it; failed saves retain the entered values and dirty dismissal uses the shared Keep editing/Discard changes guard.

Issuing an invoice copies the client billing identity into the immutable customer snapshot. The retained PDF, MSP invoice record, and client portal invoice detail all use that snapshot. Editing the organization later changes future invoices only. Drafts do not claim an immutable bill-to identity, and bounded invoice collection responses omit billing identity and line detail.

The organization API additions are optional on writes and always present on reads. Country values use uppercase ISO alpha-2 codes. Migration `0151_organization_billing_identity` adds fields to the existing tenant-owned Organization row, so it introduces no new ownership or RLS boundary. OpenAPI and generated browser types describe the additive contract.

## Acceptance

- Organization create, partial update, validation, authorization, archive, and bounded-collection coverage remains under the existing organization target.
- Invoice issue coverage verifies the customer snapshot and proves later organization edits do not rewrite it.
- Portal coverage verifies summary/detail separation and the exact client boundary.
- Component and responsive browser coverage includes long billing values, mobile drawer containment, accessibility, and guarded billing edits.
- The full project gate, invoice-delivery target, upgrade rehearsal, and local browser-to-Django-to-PostgreSQL journey close the slice.

Existing issued invoice artifacts remain byte-for-byte unchanged. Logo branding and tagged-PDF accessibility remain separate document-quality work.
